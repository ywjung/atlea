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
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from loguru import logger

# Import dependencies from main app
from ..auth.middleware import get_current_active_user, require_admin
from ..document_processor import DocumentProcessor
from ..vector_db import VectorDB
from ..document_version import DocumentVersion
from ..group_manager import GroupManager
from ..cache_manager import CacheManager
from ..document_tracker import DocumentTracker
from ..embeddings import EmbeddingModel

# Create router
router = APIRouter(prefix="/api", tags=["Documents"])

# Global state variables (will be injected from main app)
vector_db: VectorDB = None
document_processor: DocumentProcessor = None
document_version: DocumentVersion = None
group_manager: GroupManager = None
cache_manager: CacheManager = None
embedding_model: EmbeddingModel = None
DATA_DIR: str = None
CHUNK_SIZE: int = None
CHUNK_OVERLAP: int = None
MAX_FILE_SIZE: int = None
MAX_FILE_SIZE_MB: int = None

# Reindexing state
is_reindexing: bool = False
should_cancel_reindex: bool = False
reindex_event: Optional[asyncio.Event] = None

# Status cache
status_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 5  # Cache for 5 seconds
}


def inject_dependencies(
    vdb: VectorDB,
    doc_processor: DocumentProcessor,
    doc_version: DocumentVersion,
    grp_manager: GroupManager,
    cache_mgr: CacheManager,
    emb_model: EmbeddingModel,
    data_dir: str,
    chunk_size: int,
    chunk_overlap: int,
    max_file_size: int,
    max_file_size_mb: int,
    reindex_evt: asyncio.Event
):
    """Inject dependencies from main app"""
    global vector_db, document_processor, document_version, group_manager, cache_manager
    global embedding_model, DATA_DIR, CHUNK_SIZE, CHUNK_OVERLAP, MAX_FILE_SIZE, MAX_FILE_SIZE_MB, reindex_event

    vector_db = vdb
    document_processor = doc_processor
    document_version = doc_version
    group_manager = grp_manager
    cache_manager = cache_mgr
    embedding_model = emb_model
    DATA_DIR = data_dir
    CHUNK_SIZE = chunk_size
    CHUNK_OVERLAP = chunk_overlap
    MAX_FILE_SIZE = max_file_size
    MAX_FILE_SIZE_MB = max_file_size_mb
    reindex_event = reindex_evt


# ============================================================================
# Pydantic Models
# ============================================================================

class DocumentAssignRequest(BaseModel):
    group_id: str


class BatchDocumentAssignRequest(BaseModel):
    filenames: List[str]


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


def invalidate_status_cache():
    """Invalidate status cache when documents change"""
    global status_cache
    status_cache["data"] = None
    status_cache["timestamp"] = 0


def set_reindex_progress(redis_client, step: str, progress: str = "0",
                        current_item: str = "", total_items: str = "0",
                        start_time: str = None, ttl: int = 3600):
    """
    재색인 진행 상태 설정 (자동 만료 포함)

    Args:
        redis_client: Redis 클라이언트
        step: 진행 단계
        progress: 진행률 (0-100)
        current_item: 현재 처리 중인 항목
        total_items: 전체 항목 수
        start_time: 시작 시간 (선택사항)
        ttl: 자동 만료 시간 (초, 기본 1시간)
    """
    mapping = {
        "step": step,
        "progress": progress,
        "current_item": current_item,
        "total_items": total_items
    }
    if start_time:
        mapping["start_time"] = start_time

    redis_client.hset("reindex:progress", mapping=mapping)
    # 자동 만료 설정 (1시간 후 자동 삭제)
    redis_client.expire("reindex:progress", ttl)


def clear_reindex_progress(redis_client):
    """재색인 진행 상태 초기화"""
    redis_client.delete("reindex:progress")


async def validate_file_content(file: UploadFile, max_header_bytes: int = 1024) -> bool:
    """
    Validate file content by checking magic bytes (file signature)
    Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT

    Args:
        file: Uploaded file object
        max_header_bytes: Number of bytes to read for validation

    Returns:
        True if file is valid

    Raises:
        HTTPException: If file format is invalid or potentially malicious
    """
    # Read file header for magic bytes check
    header = await file.read(max_header_bytes)
    await file.seek(0)  # Reset file pointer for subsequent reads

    # Define magic bytes for supported file types
    magic_bytes = {
        # PDF
        b'%PDF': 'pdf',
        # HWP (Hangul Word Processor)
        b'HWP Document File': 'hwp',
        # Microsoft Office (ZIP-based: DOCX, XLSX, PPTX, HWPX)
        b'PK\x03\x04': 'office_zip',  # ZIP archive (DOCX, XLSX, PPTX, HWPX)
        # Legacy Microsoft Office (OLE2-based: DOC, XLS, PPT)
        b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': 'office_ole',  # OLE2 (DOC, XLS, PPT)
    }

    # Check file signature
    file_type = None
    for signature, ftype in magic_bytes.items():
        if header.startswith(signature):
            file_type = ftype
            break

    # For text files, check if it's valid UTF-8 or ASCII
    if not file_type:
        try:
            header.decode('utf-8')
            file_type = 'text'
        except UnicodeDecodeError:
            pass

    if not file_type:
        raise HTTPException(
            status_code=400,
            detail="지원되지 않는 파일 형식이거나 손상된 파일입니다."
        )

    return True


async def cleanup_old_index_async(index_name: str):
    """Cleanup old index after a grace period (async task)"""
    try:
        # Wait 5 minutes before cleanup to ensure all in-flight queries complete
        logger.info(f"⏰ Waiting 5 minutes before cleaning up old index: {index_name}")
        await asyncio.sleep(300)

        logger.info(f"🗑️ Starting cleanup of old index: {index_name}")
        vector_db.cleanup_old_index(index_name)
        logger.success(f"✅ Successfully cleaned up old index: {index_name}")
    except Exception as e:
        logger.error(f"Failed to cleanup old index {index_name}: {e}")


async def rebuild_doc_group_mappings():
    """
    Rebuild doc:group:{filename} mappings from indexed document data

    This ensures that all documents have proper group assignments after reindex.
    Document data contains group_id, so we extract it and create the reverse mapping.
    """
    try:
        # Get current index name
        index_name = vector_db.active_index_name

        # Scan all document chunks to get filename → group_id mappings
        file_to_group = {}
        cursor = 0

        while True:
            cursor, keys = vector_db.client.scan(cursor, match=f"doc:{index_name}:*", count=100)

            for key in keys:
                # Skip non-document keys
                if any(x in key for x in [':hash:', ':group:', ':version:', ':counts:', ':files']):
                    continue

                # Get document data
                doc_data = vector_db.client.hgetall(key)
                if not doc_data:
                    continue

                filename = doc_data.get('filename')
                group_id = doc_data.get('group_id')

                if filename and group_id and filename not in file_to_group:
                    file_to_group[filename] = group_id

            if cursor == 0:
                break

        if not file_to_group:
            logger.warning("⚠️  No documents found for group mapping rebuild")
            return

        logger.info(f"📊 Found {len(file_to_group)} unique documents")

        # Rebuild doc:group mappings and group:docs sets
        pipe = vector_db.client.pipeline()
        for filename, group_id in file_to_group.items():
            pipe.set(f"doc:group:{filename}", group_id)
            pipe.sadd(f"group:docs:{group_id}", filename)

        pipe.execute()

        logger.success(f"✅ Rebuilt {len(file_to_group)} document group mappings")

    except Exception as e:
        logger.error(f"Failed to rebuild doc:group mappings: {e}")
        # Don't raise - this shouldn't fail the entire reindex


async def index_pdfs(doc_tracker: DocumentTracker, target_index: Optional[str] = None):
    """
    Process and index all documents (PDF and HWP)

    Args:
        doc_tracker: DocumentTracker instance
        target_index: Optional target index name for dual index system (Blue-Green deployment)
    """
    try:
        # Update progress: Step 1 - Processing documents
        set_reindex_progress(
            vector_db.client,
            step="문서 처리 중",
            progress="0"
        )

        logger.info(f"Processing documents from {DATA_DIR}...")

        # Process all documents (PDF and HWP) in thread pool to avoid blocking
        doc_processor = DocumentProcessor(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )

        loop = asyncio.get_event_loop()
        chunks = await loop.run_in_executor(
            None,  # Use default ThreadPoolExecutor
            doc_processor.process_directory,
            DATA_DIR
        )

        if not chunks:
            logger.warning("No chunks created from documents")
            return

        # Calculate total unique documents
        unique_sources = set(chunk.get("source", "") for chunk in chunks)
        total_documents = len(unique_sources)
        total_chunks = len(chunks)

        logger.info(f"📚 Processing {total_documents} documents → {total_chunks} chunks")

        # Update progress: Step 2 - Creating embeddings
        set_reindex_progress(
            vector_db.client,
            step="임베딩 생성 중",
            progress="0",
            current_item="0",
            total_items=str(total_documents)
        )

        # Create embeddings
        logger.info(f"Creating embeddings for {len(chunks)} chunks...")
        texts = [chunk["text"] for chunk in chunks]

        # Create embeddings with progress tracking
        import numpy as np
        batch_size = 32
        embeddings_list = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            # Check for cancellation before processing batch
            global should_cancel_reindex
            if should_cancel_reindex:
                logger.warning("🛑 Reindexing cancelled by user")
                set_reindex_progress(
                    vector_db.client,
                    step="취소됨",
                    progress="0"
                )
                raise Exception("Reindexing cancelled by user")

            batch = texts[i:i + batch_size]

            # Run CPU-intensive embedding generation in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            batch_embeddings = await loop.run_in_executor(
                None,  # Use default ThreadPoolExecutor
                lambda b=batch: embedding_model.encode(b, batch_size=batch_size, show_progress_bar=False)
            )
            embeddings_list.append(batch_embeddings)

            # Update progress with document count
            current_batch = (i // batch_size) + 1
            progress = int((current_batch / total_batches) * 100)

            # Calculate how many unique documents processed so far
            processed_chunks = chunks[:min(i + batch_size, len(chunks))]
            processed_sources = set(chunk.get("source", "") for chunk in processed_chunks)
            current_documents = len(processed_sources)

            set_reindex_progress(
                vector_db.client,
                step="임베딩 생성 중",
                progress=str(progress),
                current_item=str(current_documents),
                total_items=str(total_documents)
            )

        embeddings = np.vstack(embeddings_list)

        # Update progress: Step 3 - Adding to database
        set_reindex_progress(
            vector_db.client,
            step="데이터베이스 저장 중",
            progress="50"
        )

        # Add to vector database (use target_index for Blue-Green deployment)
        if target_index:
            logger.info(f"Adding documents to new index: {target_index} (Blue-Green deployment)")
            vector_db.add_documents(chunks, embeddings, target_index=target_index)
        else:
            logger.info("Adding documents to vector database...")
            vector_db.add_documents(chunks, embeddings)

        # Yield control to event loop
        await asyncio.sleep(0)

        # Update progress: Step 4 - Saving metadata
        set_reindex_progress(
            vector_db.client,
            step="메타데이터 저장 중",
            progress="90"
        )

        # Save metadata for future change detection
        logger.info("Saving document metadata...")
        doc_tracker.update_metadata()

        # Yield control to event loop
        await asyncio.sleep(0)

        # Create document versions for newly indexed documents
        logger.info("Creating document versions...")
        from pathlib import Path
        data_path = Path(DATA_DIR)
        version_created_count = 0
        version_skipped_count = 0

        # Get unique filenames from chunks
        unique_filenames = set(chunk.get("filename", "") for chunk in chunks)

        for filename in unique_filenames:
            if not filename:
                continue

            # Count chunks for this file
            file_chunks = [c for c in chunks if c.get("filename") == filename]
            chunk_count = len(file_chunks)

            # Check if version already exists
            try:
                existing_versions = document_version.list_versions(filename)
                if existing_versions:
                    # Update chunk_count for latest version
                    latest_version = document_version.get_latest_version(filename)
                    if latest_version:
                        version_key = f"doc:version:{filename}:v{latest_version}"
                        try:
                            # Update chunk_count and indexed status in version metadata
                            vector_db.client.hset(version_key, mapping={
                                'chunk_count': chunk_count,
                                'indexed': 'True'
                            })
                            logger.debug(f"Updated chunk_count={chunk_count} for {filename} v{latest_version}")
                        except Exception as e:
                            logger.warning(f"Failed to update chunk_count for {filename}: {e}")
                    version_skipped_count += 1
                    continue
            except Exception:
                pass

            # Find the source file
            source_path = data_path / filename
            if not source_path.exists():
                logger.debug(f"Source file not found for version creation: {filename}")
                continue

            # Create V1 version
            try:
                document_version.create_version(
                    source_path=source_path,
                    filename=filename,
                    user_id="system",
                    comment="Initial version (created during reindex)",
                    chunk_count=chunk_count
                )
                version_created_count += 1
                logger.debug(f"Created V1 for {filename} ({chunk_count} chunks)")
            except Exception as e:
                logger.debug(f"Failed to create version for {filename}: {e}")

        if version_created_count > 0:
            logger.success(f"✅ Created versions for {version_created_count} documents (skipped {version_skipped_count})")
        elif version_skipped_count > 0:
            logger.info(f"✓ All documents already have versions ({version_skipped_count} files)")

        # Yield control to event loop
        await asyncio.sleep(0)

        logger.success("✅ Document indexing completed!")

    except Exception as e:
        logger.error(f"Failed to index documents: {e}")
        raise


async def run_reindex_task():
    """Background task for reindexing with Blue-Green deployment (zero downtime)"""
    global is_reindexing, should_cancel_reindex, reindex_event

    logger.info("🚀 Background reindex task STARTED (Blue-Green deployment)")

    # Reset cancellation flag at start
    should_cancel_reindex = False

    # Reset progress state in Redis
    import time
    start_time = time.time()

    set_reindex_progress(
        vector_db.client,
        step="준비 중",
        progress="0",
        start_time=str(start_time)
    )

    # Generate new index name with timestamp
    new_index_name = f"{vector_db.base_index_name}_v{int(start_time)}"
    old_index_name = vector_db.active_index_name

    try:
        logger.info(f"🔵 Creating new index: {new_index_name}")
        logger.info(f"🟢 Active index (serving queries): {old_index_name}")

        # Create new index (does not affect active index)
        if not vector_db.create_new_index(new_index_name):
            raise Exception("Failed to create new index")

        set_reindex_progress(
            vector_db.client,
            step="새 인덱스 구축 중",
            progress="5"
        )

        logger.info("📋 Creating DocumentTracker...")
        doc_tracker = DocumentTracker(data_dir=DATA_DIR)

        logger.info("🗑️ Clearing metadata...")
        doc_tracker.clear_metadata()

        logger.info("🔄 Building new index (active index continues serving queries)...")
        # Build new index in background (using target_index parameter)
        # This will be handled by index_pdfs with the new index

        # Temporarily store the new index name for index_pdfs to use
        vector_db.client.set("index:building", new_index_name, ex=3600)

        await index_pdfs(doc_tracker, target_index=new_index_name)

        set_reindex_progress(
            vector_db.client,
            step="인덱스 전환 중",
            progress="95"
        )

        logger.info(f"🔄 Swapping indexes: {old_index_name} → {new_index_name}")
        # Atomic swap - instant switch with zero downtime
        if not vector_db.swap_indexes(new_index_name):
            raise Exception("Failed to swap indexes")

        logger.info("🔄 Invalidating status cache...")
        invalidate_status_cache()

        logger.info("🗑️ Clearing document count cache...")
        vector_db.clear_document_count_cache()

        logger.info("🔄 Synchronizing group document counts...")
        group_manager.sync_document_counts()

        logger.info("🔨 Rebuilding document group mappings...")
        await rebuild_doc_group_mappings()

        # Schedule cleanup of old index (async, non-blocking)
        logger.info(f"🗑️ Scheduling cleanup of old index: {old_index_name}")
        asyncio.create_task(cleanup_old_index_async(old_index_name))

        logger.success(f"✅ Reindexing completed with zero downtime!")
        logger.success(f"   Old index: {old_index_name}")
        logger.success(f"   New index: {new_index_name}")

        set_reindex_progress(
            vector_db.client,
            step="완료",
            progress="100"
        )

    except Exception as e:
        logger.error(f"❌ Reindexing failed: {str(e)}")
        logger.exception("Full traceback:")

        set_reindex_progress(
            vector_db.client,
            step="실패",
            progress="0"
        )

        # Cleanup new index on failure
        try:
            vector_db.cleanup_old_index(new_index_name)
            logger.info(f"Cleaned up failed index: {new_index_name}")
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup failed index: {cleanup_error}")

    finally:
        # Always reset reindexing flag and signal completion
        is_reindexing = False
        reindex_event.set()
        logger.info("🏁 Reindex task finished")


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

        # Batch fetch document group IDs (avoids N+1 queries)
        doc_group_map = {}
        if cache_manager:
            pipe = cache_manager.redis.pipeline()
            for filename in filenames:
                pipe.get(f'doc:group:{filename}')

            group_results = pipe.execute()
            for filename, group_id in zip(filenames, group_results):
                if group_id:
                    doc_group_map[filename] = group_id.decode('utf-8') if isinstance(group_id, bytes) else group_id

        # Build document list with pre-fetched chunk counts
        documents = []
        for pdf_file in all_files:
            # Filter by organization: check if document's group belongs to user's org
            doc_group_id = doc_group_map.get(pdf_file.name)
            if doc_group_id:
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


# ============================================================================
# Additional Endpoints (Extracted from web_server.py)
# ============================================================================

# POST /api/reindex
@router.post("/reindex", tags=["Documents"])
async def reindex(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Force reindex all PDFs in background (관리자 전용)
    """
    global is_reindexing, reindex_event

    try:
        # 관리자 권한 확인
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

        # If already reindexing, return current status
        if is_reindexing:
            logger.info("⏳ Reindexing already in progress...")
            return {
                "message": "Reindexing is already in progress",
                "status": "in_progress"
            }

        # Set reindexing flag and clear event
        is_reindexing = True
        reindex_event.clear()
        logger.info("🔄 Starting reindex in background... (search requests will wait)")

        # Start background task
        background_tasks.add_task(run_reindex_task)

        return {
            "message": "Reindexing started in background",
            "status": "started"
        }
    except Exception as e:
        logger.error(f"❌ Failed to start reindexing: {str(e)}")
        is_reindexing = False
        reindex_event.set()
        safe_message = get_safe_error_message(e, "reindex endpoint")
        raise HTTPException(status_code=500, detail=safe_message)



# POST /api/reindex/cancel
@router.post("/reindex/cancel", tags=["Documents"])
async def cancel_reindex(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Cancel ongoing reindexing operation

    Returns:
        - message: Status message
        - status: Current reindexing status
    """
    global should_cancel_reindex, is_reindexing

    try:
        # If not reindexing, nothing to cancel
        if not is_reindexing:
            logger.info("❌ No reindexing in progress to cancel")
            return {
                "message": "재색인이 진행 중이지 않습니다",
                "status": "not_running"
            }

        # Set cancellation flag
        should_cancel_reindex = True
        logger.info("🛑 Reindex cancellation requested by user")

        # Update progress to show cancellation (with 1 hour TTL to auto-clear)
        set_reindex_progress(
            vector_db.client,
            step="취소 중...",
            progress="0"
        )

        return {
            "message": "재색인 취소가 요청되었습니다",
            "status": "cancelling"
        }
    except Exception as e:
        logger.error(f"❌ Failed to cancel reindexing: {str(e)}")
        safe_message = get_safe_error_message(e, "cancel reindex endpoint")
        raise HTTPException(status_code=500, detail=safe_message)



# DELETE /api/reindex/progress
@router.delete("/reindex/progress", tags=["Documents"])
async def clear_reindex_progress_api(
    request: Request,
    user: dict = Depends(require_admin)
):
    """
    재색인 진행 상태 초기화 (관리자 전용)

    에러 상태에 갇힌 진행 상태를 수동으로 초기화합니다.
    정상적인 경우 TTL에 의해 자동으로 만료되지만,
    필요시 관리자가 수동으로 초기화할 수 있습니다.

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    try:
        clear_reindex_progress(vector_db.client)
        logger.info("🧹 Reindex progress state cleared by admin")

        return {
            "success": True,
            "message": "진행 상태가 초기화되었습니다"
        }
    except Exception as e:
        logger.error(f"❌ Failed to clear reindex progress: {str(e)}")
        safe_message = get_safe_error_message(e, "clear reindex progress endpoint")
        raise HTTPException(status_code=500, detail=safe_message)



# GET /api/documents/{filename}/chunks
@router.get("/documents/{filename}/chunks", tags=["Documents"])
async def get_document_chunks(
    filename: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get all chunks for a specific document (로그인 필요)
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        if not vector_db:
            raise HTTPException(status_code=500, detail="Vector database not available")

        # Get chunks for this document from vector DB
        chunks = vector_db.get_chunks_by_filename(safe_filename)

        if not chunks:
            return {
                "filename": safe_filename,
                "chunks": [],
                "total_count": 0,
                "message": "No chunks found for this document"
            }

        # Get the latest version's chunk count (not all versions!)
        expected_chunk_count = len(chunks)  # Default to all chunks
        if document_version:
            try:
                latest_version = document_version.get_latest_version(safe_filename)
                if latest_version:
                    version_meta = document_version.get_version(safe_filename, latest_version)
                    if version_meta and 'chunk_count' in version_meta:
                        # chunk_count might be None or '0' for old versions - use actual count in that case
                        chunk_count_from_meta = version_meta.get('chunk_count')
                        if chunk_count_from_meta and int(chunk_count_from_meta) > 0:
                            expected_chunk_count = int(chunk_count_from_meta)
                        # else: keep expected_chunk_count as len(chunks)
            except Exception as e:
                logger.warning(f"Failed to get version metadata for {safe_filename}: {e}")

        # Only return chunks from the latest version
        # Since chunks are sorted by chunk_index, we take the first N chunks
        # where N = expected chunk count from the latest version
        chunks_to_return = chunks[:expected_chunk_count]

        # Format chunks for display
        formatted_chunks = []
        for i, chunk in enumerate(chunks_to_return, 1):
            formatted_chunks.append({
                "index": i,
                "text": chunk.get("text", ""),
                "page": chunk.get("page", "N/A"),
                "metadata": chunk.get("metadata", {})
            })

        return {
            "filename": safe_filename,
            "chunks": formatted_chunks,
            "total_count": len(formatted_chunks)
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "get document chunks endpoint")
        raise HTTPException(status_code=500, detail=safe_message)



# POST /api/documents/upload
@router.post("/documents/upload", tags=["Documents"])
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Upload a new document and automatically index it (관리자 전용)
    Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX
    (Max file size: configurable via MAX_FILE_SIZE_MB, default 100MB)
    """
    try:
        # 관리자 권한 확인
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

        # Use authenticated user
        username = current_user.get("username", "system")

        # Remove old manual token extraction
        if False:
            try:
                from .auth.utils import verify_token
                auth_header = request.headers.get("Authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    user_data = verify_token(token)
                    if user_data:
                        # Token contains: user_id (always), username (optional)
                        logger.debug(f"Token data: {user_data}")
                        username = user_data.get("username")
                        user_id = user_data.get("user_id")
                        logger.debug(f"Extracted username: {username}, user_id: {user_id}")
                        current_user = username or user_id or "system"
                        logger.info(f"Upload user identified: {current_user}")
                    else:
                        logger.warning("Token verification returned None")
                else:
                    logger.warning("No valid Authorization header found")
            except Exception as e:
                logger.warning(f"Could not extract user from token: {e}")
                # Continue with system user
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(file.filename)

        # Validate file type (extension check)
        allowed_extensions = ['.pdf', '.hwp', '.hwpx', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
        if not any(safe_filename.endswith(ext) for ext in allowed_extensions):
            raise HTTPException(
                status_code=400,
                detail="지원되지 않는 파일 형식입니다. 지원 형식: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT"
            )

        # Security: Validate file content (magic bytes check)
        await validate_file_content(file)

        # Create data directory if it doesn't exist
        data_path = Path(DATA_DIR)
        data_path.mkdir(parents=True, exist_ok=True)

        # Save uploaded file path (using validated filename)
        file_path = data_path / safe_filename

        # v2.3.0: Check if file already exists (will create new version)
        is_update = file_path.exists()
        old_file_hash = None
        if is_update:
            logger.info(f"File '{safe_filename}' already exists - will create new version")
            # Calculate old file hash before overwriting, so we can delete it later
            try:
                with file_path.open("rb") as f:
                    old_file_hash = hashlib.md5(f.read()).hexdigest()
                    logger.debug(f"Old file hash: {old_file_hash[:8]}...")
            except Exception as e:
                logger.warning(f"Failed to calculate old file hash: {e}")
                # Continue with upload even if old hash calculation fails

        # Stream file to disk while calculating hash (memory-efficient)
        # Uses chunked reading to avoid loading entire file into memory
        file_hash = hashlib.md5()
        file_size = 0
        chunk_size = 8192  # 8KB chunks

        try:
            with file_path.open("wb") as buffer:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break

                    # Check file size limit during streaming
                    file_size += len(chunk)
                    if file_size > MAX_FILE_SIZE:
                        # Remove partial file
                        file_path.unlink(missing_ok=True)
                        file_size_mb = file_size / 1024 / 1024
                        raise HTTPException(
                            status_code=413,
                            detail=f"파일 크기({file_size_mb:.1f}MB)가 너무 큽니다. 최대 {MAX_FILE_SIZE_MB}MB까지 업로드 가능합니다."
                        )

                    # Write chunk and update hash
                    buffer.write(chunk)
                    file_hash.update(chunk)

        except HTTPException:
            raise
        except Exception as e:
            # Clean up partial file on error
            file_path.unlink(missing_ok=True)
            logger.error(f"Failed to save file: {e}")
            # Security: Use sanitized error message (prevents information disclosure)
            safe_message = get_safe_error_message(e, "file save operation")
            raise HTTPException(status_code=500, detail=safe_message)

        # Get final hash
        file_hash_hex = file_hash.hexdigest()

        # v2.3.0: Check for duplicate content
        # If updating existing file with same content, skip version creation
        logger.debug(f"Duplicate check: is_update={is_update}, document_version={document_version is not None}")
        if is_update and document_version:
            latest_version = document_version.get_latest_version(safe_filename)
            logger.debug(f"Latest version for {safe_filename}: {latest_version}")
            if latest_version:
                latest_meta = document_version.get_version(safe_filename, latest_version)
                logger.debug(f"Latest metadata: {latest_meta}")
                if latest_meta:
                    stored_hash = latest_meta.get('file_hash')
                    logger.info(f"Hash comparison: stored={stored_hash}, new={file_hash_hex}, match={stored_hash == file_hash_hex}")
                    if stored_hash == file_hash_hex:
                        # Same content - no need to create new version
                        # Keep the file in data/ directory (do NOT delete)
                        logger.warning(f"⚠️ 중복 파일 감지: '{safe_filename}'는 이미 업로드된 파일과 동일합니다")
                        return {
                            "message": f"이 파일은 이미 업로드된 '{safe_filename}'와 동일합니다. 중복 업로드가 필요하지 않습니다.",
                            "filename": safe_filename,
                            "current_version": latest_version,
                            "chunk_count": latest_meta.get('chunk_count', 0),
                            "indexed": True,
                            "is_duplicate": True
                        }
                    else:
                        logger.info(f"File content changed - will create new version (old hash: {stored_hash[:8]}..., new hash: {file_hash_hex[:8]}...)")
                else:
                    logger.warning(f"No metadata found for version {latest_version}")
            else:
                logger.info(f"No previous version found for {safe_filename} - this is the first version")

        # Delete old hash key BEFORE duplicate check (prevents orphaned hashes)
        # This must happen before duplicate check to work correctly
        if is_update and old_file_hash and old_file_hash != file_hash_hex:
            old_hash_key = f"doc:hash:{old_file_hash}"
            try:
                vector_db.client.delete(old_hash_key)
                logger.info(f"Deleted old file hash from registry: {old_file_hash[:8]}...")
            except Exception as e:
                logger.warning(f"Failed to delete old file hash: {e}")
                # Continue even if old hash deletion fails

        # Check for duplicate content in other files using Redis
        hash_key = f"doc:hash:{file_hash_hex}"
        existing_filename = vector_db.client.get(hash_key)

        if existing_filename:
            existing_filename = existing_filename.decode('utf-8') if isinstance(existing_filename, bytes) else existing_filename
            # Allow same filename (update), reject different filename (duplicate)
            if existing_filename != safe_filename:
                # Remove the newly uploaded file (it's a duplicate of another file)
                file_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=409,
                    detail=f"이 파일과 동일한 내용의 문서가 이미 업로드되어 있습니다: '{existing_filename}'. 같은 파일을 다시 업로드할 필요가 없습니다."
                )

        logger.info(f"Uploaded file: {safe_filename}")

        # Process and index the new document (PDF or HWP)
        try:
            doc_processor = DocumentProcessor(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP
            )

            # Process single file (automatically detects PDF or HWP)
            logger.info(f"Processing document: {safe_filename}")
            chunks = doc_processor.process_document(str(file_path))

            if not chunks:
                logger.warning(f"No chunks created from {safe_filename}")
                # 파일은 저장되었지만 내용 추출 실패
                raise HTTPException(
                    status_code=422,
                    detail=f"파일에서 텍스트를 추출할 수 없습니다. 파일이 비어있거나 읽을 수 없는 형식일 수 있습니다. 파일을 확인해주세요."
                )

            # Create embeddings
            logger.info(f"Creating embeddings for {len(chunks)} chunks from {safe_filename}...")
            texts = [chunk["text"] for chunk in chunks]
            embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=False)

            # 🆕 Delete existing chunks before adding new ones (prevent duplicate chunks with old group_ids)
            if is_update:
                try:
                    deleted_count = vector_db.delete_by_filename(safe_filename)
                    logger.info(f"🗑️ Deleted {deleted_count} old chunks for {safe_filename} before reindexing")
                except Exception as e:
                    logger.warning(f"Failed to delete old chunks: {e}")
                    # Continue with upload even if deletion fails

            # 🆕 Assign document to group BEFORE adding chunks (so chunks get correct group_id)
            try:
                default_group_id = group_manager.get_default_group_id()

                # Assign user's organization to default group if not already assigned
                user_org_id = current_user.get('organization_id')
                if user_org_id:
                    default_group_key = f'group:{default_group_id}'
                    default_group_data = cache_manager.redis.hgetall(default_group_key)

                    # Only assign organization if default group has no organization
                    if not default_group_data.get(b'organization_id'):
                        cache_manager.redis.hset(default_group_key, 'organization_id', user_org_id)
                        cache_manager.redis.sadd(f'org:groups:{user_org_id}', default_group_id)
                        logger.info(f"✅ Assigned default group to organization: {user_org_id}")

                # Update doc:group mapping BEFORE add_documents
                group_manager.assign_document(safe_filename, default_group_id)
                logger.info(f"📎 Assigned {safe_filename} to default group (미분류) before indexing")
            except Exception as e:
                logger.warning(f"Failed to assign document to default group: {e}")
                # Continue with upload even if group assignment fails

            # Add to vector database
            vector_db.add_documents(chunks, embeddings)

            # Update document tracker
            doc_tracker = DocumentTracker(data_dir=DATA_DIR)
            doc_tracker.update_metadata()

            logger.success(f"Indexed {len(chunks)} chunks from {safe_filename}")

            # v2.3.0: Create version entry
            version_created = False
            new_version_num = None
            if document_version:
                try:
                    version_meta = document_version.create_version(
                        source_path=file_path,
                        filename=safe_filename,
                        user_id=username,
                        comment="Uploaded via API" if not is_update else "Updated via API",
                        chunk_count=len(chunks)
                    )
                    new_version_num = version_meta['version']
                    version_created = True
                    logger.success(f"Created version {new_version_num} for {safe_filename}")
                except Exception as e:
                    logger.error(f"Failed to create version entry: {e}")
                    # Don't fail the upload if version creation fails

            # Store file hash to prevent future duplicates
            vector_db.client.set(hash_key, safe_filename)
            logger.info(f"Stored file hash for duplicate detection: {file_hash_hex[:8]}...")

            # Invalidate status cache (document set changed)
            invalidate_status_cache()

            # Clear document count cache (new document added)
            vector_db.clear_document_count_cache()

            # Note: Group assignment moved earlier (before add_documents) to ensure correct group_id

            # Get file stats
            stat = file_path.stat()

            response = {
                "message": "File uploaded and indexed successfully" if not is_update else "File updated and indexed successfully",
                "filename": safe_filename,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "chunk_count": len(chunks),
                "indexed": True,
                "is_update": is_update
            }

            # v2.3.0: Add version info to response
            if version_created and new_version_num:
                response["version"] = new_version_num
                response["version_created"] = True

            return response

        except HTTPException:
            # HTTPException은 그대로 전달 (이미 사용자 친화적인 메시지)
            if file_path.exists():
                file_path.unlink()
            raise
        except Exception as e:
            # If indexing fails, remove the uploaded file
            logger.error(f"Failed to index {safe_filename}: {e}")
            if file_path.exists():
                file_path.unlink()

            # 구체적인 에러 유형에 따라 사용자 친화적인 메시지 제공
            error_type = type(e).__name__
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                detail = "문서 서비스 연결에 실패했습니다. 잠시 후 다시 시도해주세요."
            elif "memory" in str(e).lower() or "size" in str(e).lower():
                detail = "파일이 너무 커서 처리할 수 없습니다. 파일 크기를 줄여주세요."
            elif "encoding" in str(e).lower() or "decode" in str(e).lower():
                detail = "파일 인코딩 문제가 발생했습니다. 파일 형식을 확인해주세요."
            else:
                # 일반적인 에러 - 보안을 위해 상세 정보는 로그에만 기록
                detail = f"문서 처리 중 오류가 발생했습니다. 파일 형식이나 내용을 확인해주세요. (오류: {error_type})"

            raise HTTPException(status_code=500, detail=detail)

    except HTTPException:
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "upload endpoint")
        raise HTTPException(status_code=500, detail=safe_message)



# DELETE /api/documents/{filename}
@router.delete("/documents/{filename}", tags=["Documents"])
async def delete_document(
    filename: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete a PDF document and remove it from the index
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        data_path = Path(DATA_DIR)
        file_path = data_path / safe_filename

        # Check if file exists
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{safe_filename}' not found")

        # Calculate hash before deletion to remove from hash registry
        try:
            with file_path.open("rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
                hash_key = f"doc:hash:{file_hash}"
                vector_db.client.delete(hash_key)
                logger.info(f"Removed file hash from registry: {file_hash[:8]}...")
        except Exception as e:
            logger.error(f"Failed to remove file hash: {e}")
            # Continue with deletion even if hash removal fails

        # Delete from vector database
        if vector_db:
            try:
                deleted_count = vector_db.delete_by_filename(safe_filename)
                logger.info(f"Deleted {deleted_count} chunks for {safe_filename} from vector DB")
            except Exception as e:
                logger.error(f"Failed to delete from vector DB: {e}")
                # Continue with file deletion even if vector DB deletion fails

        # Remove document from all groups
        try:
            group_manager.delete_document_from_all_groups(safe_filename)
            logger.info(f"Removed {safe_filename} from all groups")
        except Exception as e:
            logger.warning(f"Failed to remove document from groups: {e}")
            # Continue with file deletion even if group removal fails

        # Delete all versions
        try:
            if document_version:
                deleted_versions = document_version.delete_all_versions(safe_filename)
                logger.info(f"Deleted {deleted_versions} versions for {safe_filename}")
        except Exception as e:
            logger.warning(f"Failed to delete versions: {e}")
            # Continue with file deletion even if version deletion fails

        # Delete file
        file_path.unlink()
        logger.info(f"Deleted file: {safe_filename}")

        # Update document tracker
        try:
            doc_tracker = DocumentTracker(data_dir=DATA_DIR)
            doc_tracker.update_metadata()
        except Exception as e:
            logger.error(f"Failed to update document tracker: {e}")

        # Clear cache since document set has changed
        if cache_manager:
            try:
                cache_manager.clear_cache()
                logger.info("Cleared cache after document deletion")
            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")

        # Invalidate status cache (document set changed)
        invalidate_status_cache()

        # Clear document count cache (document deleted)
        vector_db.clear_document_count_cache()

        return {
            "message": f"Document '{safe_filename}' deleted successfully",
            "filename": safe_filename,
            "chunks_removed": deleted_count if vector_db else 0
        }

    except HTTPException:
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "delete endpoint")
        raise HTTPException(status_code=500, detail=safe_message)




# GET /api/documents/{filename}/download-pdf
@router.get("/documents/{filename}/download-pdf", tags=["Documents"])
async def download_document_as_pdf(
    filename: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Download document converted to PDF format

    Args:
        filename: Document filename

    Returns:
        FileResponse with PDF file (original if PDF, converted otherwise)
    """
    try:
        from fastapi.responses import FileResponse
        import subprocess
        import tempfile

        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        data_path = Path(DATA_DIR)
        file_path = data_path / safe_filename

        # Check if file exists
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{safe_filename}' not found")

        # If already PDF, return as is
        if safe_filename.lower().endswith('.pdf'):
            return FileResponse(
                path=str(file_path),
                filename=safe_filename,
                media_type='application/pdf'
            )

        # For non-PDF files, use document-service for conversion
        try:
            # Check if document-service is available
            import httpx

            # Call document-service conversion API
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Read file content
                with open(file_path, 'rb') as f:
                    files = {'file': (safe_filename, f, 'application/octet-stream')}

                    # Try to convert using document-service
                    response = await client.post(
                        'http://document-service:8081/api/convert/to-pdf',
                        files=files
                    )

                    if response.status_code == 200:
                        # Save converted PDF to temp file
                        pdf_filename = safe_filename.rsplit('.', 1)[0] + '.pdf'
                        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                        temp_pdf.write(response.content)
                        temp_pdf.close()

                        return FileResponse(
                            path=temp_pdf.name,
                            filename=pdf_filename,
                            media_type='application/pdf',
                            background=BackgroundTasks().add_task(lambda: Path(temp_pdf.name).unlink())
                        )
        except Exception as e:
            logger.warning(f"PDF conversion failed: {e}")
            # Fall through to return original file

        # If conversion not available, return original file
        raise HTTPException(
            status_code=400,
            detail=f"PDF conversion not available for {safe_filename}. Only original file can be downloaded."
        )

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "download-pdf endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


# ============================================================================
# v2.3.0: Document Version Management API Endpoints
# ============================================================================



# GET /api/documents/{filename}/view
@router.get("/documents/{filename}/view", tags=["Documents"])
async def view_document(
    filename: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    View/download a document file
    
    Args:
        filename: Document filename
        
    Returns:
        File content for viewing/downloading
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)
        
        # Get file path
        data_path = Path(DATA_DIR)
        file_path = data_path / safe_filename
        
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Document '{safe_filename}' not found"
            )
        
        # Determine media type based on file extension
        file_ext = file_path.suffix.lower()
        media_types = {
            '.pdf': 'application/pdf',
            '.txt': 'text/plain; charset=utf-8',
            '.hwp': 'application/x-hwp',
            '.hwpx': 'application/vnd.hancom.hwpx',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        
        media_type = media_types.get(file_ext, 'application/octet-stream')

        # Return file for viewing
        # Use RFC 5987 encoding for non-ASCII filenames in Content-Disposition header
        from urllib.parse import quote

        # Try ASCII encoding first, fall back to UTF-8 encoding if needed
        try:
            safe_filename.encode('ascii')
            # ASCII filename - use simple format
            content_disposition = f'inline; filename="{safe_filename}"'
        except UnicodeEncodeError:
            # Non-ASCII filename - use RFC 5987 format
            encoded_filename = quote(safe_filename)
            content_disposition = f"inline; filename*=UTF-8''{encoded_filename}"

        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            headers={
                "Content-Disposition": content_disposition
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "view document endpoint")
        raise HTTPException(status_code=500, detail=safe_message)




# GET /api/documents/{filename}/versions
@router.get("/documents/{filename}/versions", tags=["Documents", "Versions"])
async def list_document_versions(
    filename: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get all versions of a document

    Returns:
        List of version metadata (newest first)
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        if not document_version:
            raise HTTPException(status_code=503, detail="Document version manager not initialized")

        # Get all versions
        versions = document_version.list_versions(safe_filename)

        return {
            "filename": safe_filename,
            "versions": versions,
            "total_count": len(versions)
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "list versions endpoint")
        raise HTTPException(status_code=500, detail=safe_message)




# GET /api/documents/{filename}/versions/compare
@router.get("/documents/{filename}/versions/compare", tags=["Documents", "Versions"])
async def compare_document_versions(
    filename: str,
    version1: int,
    version2: int,
    method: str = "auto",  # "hash", "text", "embedding", "llm", "auto"
    current_user: dict = Depends(get_current_active_user)
):
    """
    Compare two versions of a document

    Args:
        filename: Document filename
        version1: First version number
        version2: Second version number
        method: Similarity calculation method
            - "hash": Hash-based (fast, 100% if same, 0% if different)
            - "text": Text-based using difflib (medium speed, edit distance)
            - "embedding": Embedding-based (slower, semantic similarity)
            - "llm": LLM-based with detailed analysis (slowest, most detailed)
            - "auto": Automatic selection based on file size (default)

    Returns:
        Comparison data showing differences between versions
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        if not document_version:
            raise HTTPException(status_code=503, detail="Document version manager not initialized")

        # Compare versions with specified method
        comparison = document_version.compare_versions(safe_filename, version1, version2, method=method)

        if not comparison:
            raise HTTPException(
                status_code=404,
                detail=f"Could not compare versions {version1} and {version2} for '{safe_filename}'"
            )

        return comparison

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "compare versions endpoint")
        raise HTTPException(status_code=500, detail=safe_message)




# GET /api/documents/{filename}/versions/{version}
@router.get("/documents/{filename}/versions/{version}", tags=["Documents", "Versions"])
async def get_document_version(
    filename: str,
    version: int,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get metadata for a specific version of a document

    Args:
        filename: Document filename
        version: Version number

    Returns:
        Version metadata
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        if not document_version:
            raise HTTPException(status_code=503, detail="Document version manager not initialized")

        # Get version metadata
        version_meta = document_version.get_version(safe_filename, version)

        if not version_meta:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version} not found for document '{safe_filename}'"
            )

        return version_meta

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "get version endpoint")
        raise HTTPException(status_code=500, detail=safe_message)




# POST /api/documents/{filename}/versions/{version}/restore
@router.post("/documents/{filename}/versions/{version}/restore", tags=["Documents", "Versions"])
async def restore_document_version(
    filename: str,
    version: int,
    request: Request = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Restore a document to a specific version

    This will:
    1. Restore the file to the data directory
    2. Re-index the restored version
    3. Create a new version entry for the restored file

    Args:
        filename: Document filename
        version: Version number to restore

    Returns:
        Success message with new version info
    """
    try:
        # Get current user from token
        current_user = "system"
        if request:
            try:
                from .auth.utils import verify_token
                auth_header = request.headers.get("Authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    user_data = verify_token(token)
                    if user_data:
                        # Token contains: user_id (always), username (optional)
                        logger.debug(f"Token data: {user_data}")
                        username = user_data.get("username")
                        user_id = user_data.get("user_id")
                        logger.debug(f"Extracted username: {username}, user_id: {user_id}")
                        current_user = username or user_id or "system"
                        logger.info(f"Restore user identified: {current_user}")
                    else:
                        logger.warning("Token verification returned None")
                else:
                    logger.warning("No valid Authorization header found")
            except Exception as e:
                logger.warning(f"Could not extract user from token: {e}")

        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        if not document_version:
            raise HTTPException(status_code=503, detail="Document version manager not initialized")

        # Check if version exists
        version_meta = document_version.get_version(safe_filename, version)
        if not version_meta:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version} not found for document '{safe_filename}'"
            )

        # Target path in data directory
        data_path = Path(DATA_DIR)
        target_path = data_path / safe_filename

        # Restore the file
        success = document_version.restore_version(safe_filename, version, target_path)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to restore version")

        logger.info(f"Restored {safe_filename} to version {version}")

        # Re-index the restored document
        try:
            # Delete existing chunks for this document
            if vector_db:
                vector_db.delete_by_filename(safe_filename)

            # Process and index the restored document
            doc_processor = DocumentProcessor(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP
            )

            chunks = doc_processor.process_document(str(target_path))

            if chunks:
                # Create embeddings
                texts = [chunk["text"] for chunk in chunks]
                embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=False)

                # Add to vector database
                vector_db.add_documents(chunks, embeddings)

                logger.success(f"Re-indexed {len(chunks)} chunks for restored {safe_filename}")

                # Create a new version entry for the restored file
                new_version_meta = document_version.create_version(
                    source_path=target_path,
                    filename=safe_filename,
                    user_id=current_user,
                    comment=f"Restored from version {version}",
                    chunk_count=len(chunks)
                )

                # Invalidate caches
                invalidate_status_cache()
                vector_db.clear_document_count_cache()

                return {
                    "message": f"Document '{safe_filename}' restored to version {version}",
                    "restored_version": version,
                    "new_version": new_version_meta["version"],
                    "filename": safe_filename,
                    "chunk_count": len(chunks),
                    "indexed": True
                }
            else:
                logger.warning(f"No chunks created from restored {safe_filename}")
                return {
                    "message": f"Document '{safe_filename}' restored but no content could be extracted",
                    "restored_version": version,
                    "filename": safe_filename,
                    "indexed": False
                }

        except Exception as e:
            logger.error(f"Failed to re-index restored document: {e}")
            # File was restored but indexing failed
            return {
                "message": f"Document '{safe_filename}' restored but indexing failed",
                "restored_version": version,
                "filename": safe_filename,
                "indexed": False,
                "error": str(e)
            }

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "restore version endpoint")
        raise HTTPException(status_code=500, detail=safe_message)




# DELETE /api/documents/{filename}/versions/{version}
@router.delete("/documents/{filename}/versions/{version}", tags=["Documents", "Versions"])
async def delete_document_version(
    filename: str,
    version: int,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete a specific version of a document

    Note: Cannot delete the latest version if it's the only version

    Args:
        filename: Document filename
        version: Version number to delete

    Returns:
        Success message
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        if not document_version:
            raise HTTPException(status_code=503, detail="Document version manager not initialized")

        # Check if this is the only version
        versions = document_version.list_versions(safe_filename)
        if len(versions) == 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the only version of a document"
            )

        # Delete the version
        success = document_version.delete_version(safe_filename, version)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version} not found for document '{safe_filename}'"
            )

        return {
            "message": f"Version {version} of '{safe_filename}' deleted successfully",
            "filename": safe_filename,
            "deleted_version": version,
            "remaining_versions": len(versions) - 1
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "delete version endpoint")
        raise HTTPException(status_code=500, detail=safe_message)




# POST /api/documents/migrate-versions
@router.post("/documents/migrate-versions", tags=["Documents", "Versions"])
async def migrate_document_versions(
    request: Request = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Create V1 versions for all existing documents that don't have versions yet
    This is a migration endpoint for existing documents uploaded before version control was implemented
    """
    try:
        # Check if document version manager is initialized
        if not document_version:
            raise HTTPException(
                status_code=503,
                detail="Document version manager not initialized"
            )

        # Get current user from token
        current_user = "system"
        if request:
            try:
                from .auth.utils import verify_token
                auth_header = request.headers.get("Authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    user_data = verify_token(token)
                    if user_data:
                        # Token contains: user_id (always), username (optional)
                        current_user = user_data.get("username") or user_data.get("user_id") or "system"
            except Exception as e:
                logger.debug(f"Could not extract user from token: {e}")

        # Get all files in data directory
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            raise HTTPException(status_code=404, detail="Data directory not found")

        # Allowed file extensions
        allowed_extensions = ['.pdf', '.hwp', '.hwpx', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']

        migrated_files = []
        skipped_files = []
        failed_files = []

        for file_path in data_path.iterdir():
            if file_path.is_file() and any(file_path.name.endswith(ext) for ext in allowed_extensions):
                filename = file_path.name

                # Skip if file is in versions directory
                if 'versions' in file_path.parts:
                    continue

                # Check if file already has versions
                try:
                    existing_versions = document_version.list_versions(filename)
                    if existing_versions:
                        skipped_files.append({
                            "filename": filename,
                            "reason": f"Already has {len(existing_versions)} version(s)"
                        })
                        continue
                except Exception as e:
                    logger.debug(f"Error checking versions for {filename}: {e}")

                # Get chunk count from Redis if available
                chunk_count = 0
                try:
                    # Use SCAN instead of KEYS to avoid blocking Redis
                    chunk_keys = cache_manager.safe_scan_keys(f"chunk:{filename}:*")
                    chunk_count = len(chunk_keys) if chunk_keys else 0
                except Exception as e:
                    logger.debug(f"Could not get chunk count for {filename}: {e}")

                # Create V1 version for this file
                try:
                    version_meta = document_version.create_version(
                        source_path=file_path,
                        filename=filename,
                        user_id=current_user,
                        comment="Initial version (migrated)",
                        chunk_count=chunk_count
                    )
                    migrated_files.append({
                        "filename": filename,
                        "version": version_meta['version'],
                        "size": version_meta['file_size'],
                        "chunk_count": chunk_count
                    })
                    logger.info(f"Created initial version for {filename}")
                except Exception as e:
                    logger.error(f"Failed to create version for {filename}: {e}")
                    failed_files.append({
                        "filename": filename,
                        "error": str(e)
                    })

        return {
            "message": f"Migration complete: {len(migrated_files)} files migrated",
            "migrated": migrated_files,
            "failed": failed_files
        }
    except Exception as e:
        safe_message = get_safe_error_message(e, "migrate versions endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


# PUT /api/documents/{filename}/group
@router.put("/documents/{filename}/group", tags=["Documents"])
async def assign_document_to_group(
    filename: str,
    request: DocumentAssignRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Assign a document to a group

    Args:
        filename: Document filename
        request: Target group ID

    Returns:
        Success status
    """
    try:
        success = group_manager.assign_document(
            filename=filename,
            group_id=request.group_id
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Document or group not found"
            )

        logger.info(f"Assigned document '{filename}' to group {request.group_id}")

        return {
            "success": True,
            "filename": filename,
            "group_id": request.group_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign document: {e}")
        safe_message = get_safe_error_message(e, "assign document endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/groups/{group_id}/documents", tags=["Groups"])
async def batch_assign_documents(
    group_id: str,
    request: BatchDocumentAssignRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Batch assign multiple documents to a group

    Args:
        group_id: Target group ID
        request: List of filenames to assign

    Returns:
        Number of documents successfully assigned


    """
    try:
        assigned_count = group_manager.batch_assign_documents(
            filenames=request.filenames,
            group_id=group_id
        )

        logger.info(f"Batch assigned {assigned_count}/{len(request.filenames)} documents to group {group_id}")

        return {
            "success": True,
            "assigned_count": assigned_count,
            "total_requested": len(request.filenames)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to batch assign documents: {e}")
        safe_message = get_safe_error_message(e, "batch assign documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)
