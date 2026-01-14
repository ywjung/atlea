"""
Documents Router
문서 관리 및 재인덱싱 관련 API 엔드포인트

이 모듈은 web_server.py에서 분리되었습니다.
- 문서 업로드, 다운로드, 삭제
- 문서 버전 관리
- 재인덱싱 및 진행 상황 추적
"""

import os
import time
import itertools
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse
from loguru import logger

# Import dependencies from main app
from ..auth.middleware import get_current_active_user
from ..document_processor import DocumentProcessor
from ..vector_db import VectorDB
from ..document_version import DocumentVersion
from ..group_manager import GroupManager
from ..cache_manager import CacheManager

# Create router
router = APIRouter(prefix="/api", tags=["Documents"])

# Global state variables (will be injected from main app)
vector_db: VectorDB = None
document_processor: DocumentProcessor = None
document_version: DocumentVersion = None
group_manager: GroupManager = None
cache_manager: CacheManager = None
DATA_DIR: str = None


def inject_dependencies(
    vdb: VectorDB,
    doc_processor: DocumentProcessor,
    doc_version: DocumentVersion,
    grp_manager: GroupManager,
    cache_mgr: CacheManager,
    data_dir: str
):
    """Inject dependencies from main app"""
    global vector_db, document_processor, document_version, group_manager, cache_manager, DATA_DIR
    vector_db = vdb
    document_processor = doc_processor
    document_version = doc_version
    group_manager = grp_manager
    cache_manager = cache_mgr
    DATA_DIR = data_dir


# ============================================================================
# Helper Functions (from web_server.py)
# ============================================================================

def validate_filename(filename: str) -> str:
    """
    Validate and sanitize filename to prevent path traversal attacks

    Args:
        filename: User-provided filename

    Returns:
        Sanitized filename safe for file operations

    Raises:
        HTTPException: If filename contains malicious patterns
    """
    import unicodedata

    # Remove any path components (get basename only)
    safe_name = os.path.basename(filename)

    # Normalize Korean filename to NFC (자모 결합)
    safe_name = unicodedata.normalize('NFC', safe_name)

    # Block directory traversal attempts
    if '..' in safe_name or '/' in safe_name or '\\' in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 문자가 포함되어 있습니다."
        )

    # Block null bytes
    if '\x00' in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 문자가 포함되어 있습니다."
        )

    return safe_name


def get_safe_error_message(error: Exception, context: str = "") -> str:
    """
    Get sanitized error message for user display (prevents information disclosure)

    Args:
        error: The exception that occurred
        context: Context description for logging

    Returns:
        Generic, safe error message for user display
    """
    error_type = type(error).__name__

    # Log full error details server-side
    logger.error(f"Error in {context}: {error_type}: {str(error)}")

    # Map exception types to generic user-friendly messages
    error_messages = {
        "FileNotFoundError": "요청한 파일을 찾을 수 없습니다.",
        "PermissionError": "파일에 대한 접근 권한이 없습니다.",
        "ValueError": "잘못된 입력값입니다.",
    }

    # Return generic message
    return error_messages.get(error_type, "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/reindex/progress")
async def get_reindex_progress(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get current reindexing progress

    Returns progress information including:
    - in_progress: Whether reindexing is currently in progress
    - step: Current step description
    - progress: Progress percentage (0-100)
    - current_item: Current item being processed
    - total_items: Total number of items
    - elapsed_seconds: Elapsed time since start
    - estimated_remaining_seconds: Estimated remaining time
    """
    try:
        progress_data = vector_db.client.hgetall("reindex:progress")
        if not progress_data:
            return {
                "in_progress": False,
                "step": "대기 중",
                "progress": 0,
                "current_item": "",
                "total_items": "",
                "elapsed_seconds": 0,
                "estimated_remaining_seconds": 0
            }

        # Redis returns bytes keys/values when decode_responses=False
        # Convert to dict with string keys
        progress_dict = {}
        for key, value in progress_data.items():
            # Decode bytes to strings
            str_key = key.decode('utf-8') if isinstance(key, bytes) else key
            str_value = value.decode('utf-8') if isinstance(value, bytes) else value
            progress_dict[str_key] = str_value

        step = progress_dict.get("step", "대기 중")
        progress = int(progress_dict.get("progress", 0))

        # Determine if reindexing is in progress
        # In progress if: data exists, progress < 100, and step is not "완료"
        in_progress = progress < 100 and step != "완료"

        # Calculate elapsed and remaining time
        elapsed_seconds = 0
        estimated_remaining_seconds = 0

        if in_progress and "start_time" in progress_dict:
            try:
                start_time = float(progress_dict["start_time"])
                current_time = time.time()
                elapsed_seconds = int(current_time - start_time)

                # Estimate remaining time based on progress
                if progress > 0:
                    estimated_total = elapsed_seconds / (progress / 100.0)
                    estimated_remaining_seconds = int(estimated_total - elapsed_seconds)
                    # Cap at reasonable maximum (e.g., 1 hour)
                    estimated_remaining_seconds = min(estimated_remaining_seconds, 3600)
            except (ValueError, ZeroDivisionError):
                pass

        return {
            "in_progress": in_progress,
            "step": step,
            "progress": progress,
            "current_item": progress_dict.get("current_item", ""),
            "total_items": progress_dict.get("total_items", ""),
            "elapsed_seconds": elapsed_seconds,
            "estimated_remaining_seconds": estimated_remaining_seconds
        }
    except Exception as e:
        safe_message = get_safe_error_message(e, "get reindex progress endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.get("/documents")
async def list_documents(
    filter_scope: str = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    List all indexed documents with metadata (로그인 필요)
    Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT

    Args:
        filter_scope: "user" - always filter by organization (for search filters)
                     None - admin sees all, users see organization only (for admin page)
    """
    try:
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            return {"documents": []}

        # Get user's organization and groups
        user_org_id = current_user.get("org_id")
        is_admin = current_user.get("role") == "admin"

        # Determine scope: if filter_scope="user", always use organization scope
        # Otherwise, admin sees all, regular users see organization only
        if filter_scope == "user" or not is_admin:
            org_groups = group_manager.get_all_groups(org_id=user_org_id)
            org_group_ids = {g['id'] for g in org_groups}
        else:
            org_groups = group_manager.get_all_groups()
            org_group_ids = {g['id'] for g in org_groups}

        # Get all supported document files
        all_files = list(itertools.chain(
            data_path.glob("*.pdf"),
            data_path.glob("*.hwp"),
            data_path.glob("*.hwpx"),
            data_path.glob("*.doc"),
            data_path.glob("*.docx"),
            data_path.glob("*.xls"),
            data_path.glob("*.xlsx"),
            data_path.glob("*.ppt"),
            data_path.glob("*.pptx"),
            data_path.glob("*.txt")
        ))

        if not all_files:
            return {"documents": [], "total_count": 0}

        # Batch count chunks for all files at once (avoids N+1 queries)
        filenames = [f.name for f in all_files]
        chunk_counts = {}
        if vector_db:
            try:
                chunk_counts = vector_db.batch_count_documents_by_filenames(filenames)
            except Exception as e:
                logger.error(f"Failed to batch count documents: {e}")
                # Fall back to zero counts
                chunk_counts = {filename: 0 for filename in filenames}

        # Build document list with pre-fetched chunk counts
        documents = []
        for pdf_file in all_files:
            # Filter by organization: check if document's group belongs to user's org
            doc_group_id = cache_manager.redis.get(f'doc:group:{pdf_file.name}')
            if doc_group_id:
                doc_group_id = doc_group_id.decode('utf-8')
                # Skip documents not in user's organization groups
                if doc_group_id not in org_group_ids:
                    continue
            # If document has no group, skip it (documents without groups are not accessible)
            else:
                continue

            # Get file stats
            stat = pdf_file.stat()

            # Get chunk count from latest version metadata (not all versions!)
            chunk_count = 0
            if document_version:
                try:
                    latest_version = document_version.get_latest_version(pdf_file.name)
                    if latest_version:
                        version_meta = document_version.get_version(pdf_file.name, latest_version)
                        if version_meta and 'chunk_count' in version_meta:
                            # chunk_count might be None or '0' for old versions - use batch count in that case
                            chunk_count_from_meta = version_meta.get('chunk_count')
                            if chunk_count_from_meta and int(chunk_count_from_meta) > 0:
                                chunk_count = int(chunk_count_from_meta)
                            else:
                                # Fallback to batch count if chunk_count is None or 0
                                chunk_count = chunk_counts.get(pdf_file.name, 0)
                        else:
                            # Fallback to batch count if version metadata doesn't have chunk_count
                            chunk_count = chunk_counts.get(pdf_file.name, 0)
                    else:
                        # No version metadata - fallback to batch count
                        chunk_count = chunk_counts.get(pdf_file.name, 0)
                except Exception as e:
                    logger.warning(f"Failed to get version metadata for {pdf_file.name}: {e}")
                    # Fallback to batch count
                    chunk_count = chunk_counts.get(pdf_file.name, 0)
            else:
                # No version system - fallback to batch count
                chunk_count = chunk_counts.get(pdf_file.name, 0)

            documents.append({
                "id": pdf_file.name,  # Use filename as ID for filtering
                "name": pdf_file.name,  # Display name
                "filename": pdf_file.name,  # Keep for backward compatibility
                "size": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),  # For JavaScript formatDate
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),  # Keep for backward compatibility
                "chunk_count": chunk_count,
                "indexed": chunk_count > 0,
                "group_id": doc_group_id  # Add group_id for reference
            })

        # Sort by modified date (newest first)
        documents.sort(key=lambda x: x["created_at"], reverse=True)

        return {
            "documents": documents,
            "total_count": len(documents)
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "list documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.get("/documents/{filename}/download")
async def download_document(
    filename: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Download original document file

    Args:
        filename: Document filename

    Returns:
        FileResponse with the original document
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        data_path = Path(DATA_DIR)
        file_path = data_path / safe_filename

        # Check if file exists
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{safe_filename}' not found")

        # Return file for download
        return FileResponse(
            path=str(file_path),
            filename=safe_filename,
            media_type='application/octet-stream'
        )

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "download endpoint")
        raise HTTPException(status_code=500, detail=safe_message)
