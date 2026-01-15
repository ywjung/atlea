"""
File Validation Utilities

Provides filename and file content validation to prevent security vulnerabilities
including path traversal and malicious file uploads.
"""

import os
import re
import unicodedata
from fastapi import HTTPException, UploadFile


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
    # Remove any path components (get basename only)
    safe_name = os.path.basename(filename)

    # 🆕 Normalize Korean filename to NFC (자모 결합) to prevent NFD/NFC mismatch
    safe_name = unicodedata.normalize('NFC', safe_name)

    # Block directory traversal attempts
    if '..' in safe_name or '/' in safe_name or '\\' in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 경로 문자가 포함되어 있습니다."
        )

    # Block null bytes (path truncation attack)
    if '\x00' in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 문자가 포함되어 있습니다."
        )

    # Only allow safe characters: alphanumeric, common punctuation, Korean
    # Korean Unicode range: \uAC00-\uD7A3 (Hangul syllables)
    # Allow: a-z A-Z 0-9 _ - . space ( ) [ ] + & @ # ! ~ , ; = ' 한글
    # Block: / \ : * ? " < > | (filesystem reserved or dangerous)
    if not re.match(r'^[\w\-. ()\[\]+&@#!~,;=\'\uAC00-\uD7A3]+$', safe_name, re.UNICODE):
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 특수문자가 포함되어 있습니다."
        )

    # Check filename length
    if len(safe_name) > 255:
        raise HTTPException(
            status_code=400,
            detail="파일명이 너무 깁니다 (최대 255자)."
        )

    # Must have an extension
    if '.' not in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일 확장자가 필요합니다."
        )

    return safe_name


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
        HTTPException: If file content is invalid or malicious
    """
    # Read first bytes for magic number validation
    header = await file.read(max_header_bytes)
    await file.seek(0)  # Reset file pointer

    # Get file extension
    filename = file.filename or ""
    file_ext = filename.lower().split('.')[-1] if '.' in filename else ""

    # Define magic bytes for each format
    PDF_SIGNATURE = b'%PDF'
    OLE2_SIGNATURE = b'\xd0\xcf\x11\xe0'  # Used by HWP, DOC, XLS, PPT
    ZIP_SIGNATURE = b'PK\x03\x04'  # Used by HWPX, DOCX, XLSX, PPTX
    HWP_SIGNATURE = b'HWP Document File'

    # Check if file starts with valid signature
    is_pdf = header.startswith(PDF_SIGNATURE)
    is_ole2 = header.startswith(OLE2_SIGNATURE)  # HWP, DOC, XLS, PPT
    is_zip = header.startswith(ZIP_SIGNATURE)  # HWPX, DOCX, XLSX, PPTX
    is_hwp_legacy = header.startswith(HWP_SIGNATURE)

    # Validate based on extension and signature combination
    valid = False

    if file_ext == 'pdf' and is_pdf:
        valid = True
    elif file_ext == 'hwp' and (is_ole2 or is_hwp_legacy):
        valid = True
    elif file_ext == 'hwpx' and is_zip:
        valid = True
    elif file_ext in ['doc', 'xls', 'ppt'] and is_ole2:
        valid = True
    elif file_ext in ['docx', 'xlsx', 'pptx'] and is_zip:
        valid = True
    elif file_ext == 'txt':
        # TXT files don't have magic bytes, but check for malicious content
        # Check for executable signatures
        if header.startswith(b'MZ') or header.startswith(b'\x7fELF'):
            raise HTTPException(
                status_code=400,
                detail="실행 파일은 업로드할 수 없습니다."
            )
        # Check for HTML/script content
        elif b'<script' in header.lower() or b'<html' in header.lower():
            raise HTTPException(
                status_code=400,
                detail="HTML 파일은 업로드할 수 없습니다."
            )
        # TXT files are text-based, allow them
        valid = True

    if not valid:
        # Try to detect malicious content
        if header.startswith(b'MZ') or header.startswith(b'\x7fELF'):
            raise HTTPException(
                status_code=400,
                detail="실행 파일은 업로드할 수 없습니다."
            )
        elif b'<script' in header.lower() or b'<html' in header.lower():
            raise HTTPException(
                status_code=400,
                detail="HTML 파일은 업로드할 수 없습니다."
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"파일 형식이 올바르지 않습니다. 지원 형식: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT"
            )

    return True
