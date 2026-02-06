"""
File Upload Security Utilities

Enhanced file validation and security checks for uploaded documents.
Implements defense-in-depth approach with multiple validation layers.
"""

import re
from typing import Tuple, Optional
from fastapi import HTTPException, UploadFile
from loguru import logger

# Optional dependency: python-magic for file type detection
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logger.debug("python-magic not installed, magic-based file type detection disabled")


# Whitelist of allowed file extensions
ALLOWED_EXTENSIONS = {
    '.pdf', '.hwp', '.hwpx',
    '.doc', '.docx',
    '.xls', '.xlsx',
    '.ppt', '.pptx',
    '.txt'
}

# MIME type whitelist mapping
ALLOWED_MIME_TYPES = {
    # PDF
    'application/pdf': ['.pdf'],
    # HWP
    'application/x-hwp': ['.hwp'],
    'application/haansofthwp': ['.hwp'],
    # Microsoft Office (legacy)
    'application/msword': ['.doc'],
    'application/vnd.ms-excel': ['.xls'],
    'application/vnd.ms-powerpoint': ['.ppt'],
    # Microsoft Office (modern)
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx', '.hwpx'],
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
    # ZIP (for HWPX and Office formats)
    'application/zip': ['.docx', '.xlsx', '.pptx', '.hwpx'],
    'application/x-zip-compressed': ['.docx', '.xlsx', '.pptx', '.hwpx'],
    # Text
    'text/plain': ['.txt'],
    # Octet-stream (generic fallback for some office formats)
    'application/octet-stream': ['.hwp', '.hwpx', '.doc', '.xls', '.ppt']
}

# Malicious patterns to detect (basic heuristics)
MALICIOUS_PATTERNS = {
    # Embedded scripts (XSS in documents)
    'embedded_script': re.compile(rb'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),

    # PHP code injection
    'php_code': re.compile(rb'<\?php|<\?=', re.IGNORECASE),

    # Shell commands (potential RCE)
    'shell_command': re.compile(rb'(?:system|exec|shell_exec|passthru|popen|proc_open)\s*\(', re.IGNORECASE),

    # SQL injection patterns
    'sql_injection': re.compile(rb'(?:union|select|insert|update|delete|drop|create)\s+(?:from|into|table)', re.IGNORECASE),

    # File inclusion attacks
    'file_inclusion': re.compile(rb'(?:include|require|include_once|require_once)\s*\(', re.IGNORECASE),

    # Macro-enabled Office documents (potential malware vector)
    'macro_enabled': re.compile(rb'(?:Microsoft\s+Office|xl/vbaProject\.bin|word/vbaProject\.bin)', re.IGNORECASE),
}


async def validate_mime_type(file: UploadFile, filename: str) -> bool:
    """
    Validate file MIME type matches extension

    Args:
        file: Uploaded file object
        filename: Validated filename with extension

    Returns:
        True if MIME type is valid

    Raises:
        HTTPException: If MIME type is invalid or doesn't match extension
    """
    content_type = file.content_type
    file_ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    # Check if extension is in whitelist
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"파일 확장자가 허용되지 않습니다: {file_ext}"
        )

    # Verify MIME type is in whitelist
    if content_type not in ALLOWED_MIME_TYPES:
        # Log for security monitoring
        logger.warning(f"⚠️ Suspicious MIME type: {content_type} for file: {filename}")
        raise HTTPException(
            status_code=400,
            detail="허용되지 않는 파일 형식입니다."
        )

    # Verify MIME type matches file extension
    allowed_extensions = ALLOWED_MIME_TYPES.get(content_type, [])
    if file_ext not in allowed_extensions:
        logger.warning(f"⚠️ MIME/extension mismatch: {content_type} vs {file_ext} for {filename}")

        # Special case: application/octet-stream can be various office formats
        if content_type != 'application/octet-stream':
            raise HTTPException(
                status_code=400,
                detail="파일 형식과 확장자가 일치하지 않습니다."
            )

    return True


async def scan_malicious_patterns(content: bytes, filename: str, max_scan_bytes: int = 10 * 1024 * 1024) -> bool:
    """
    Scan file content for malicious patterns

    Args:
        content: File content (first N bytes)
        filename: Filename for logging
        max_scan_bytes: Maximum bytes to scan (default 10MB)

    Returns:
        True if no malicious patterns detected

    Raises:
        HTTPException: If malicious patterns are detected
    """
    # Scan first N bytes for suspicious patterns
    scan_content = content[:max_scan_bytes]

    for pattern_name, pattern in MALICIOUS_PATTERNS.items():
        if pattern.search(scan_content):
            logger.error(f"🚨 Malicious pattern detected: {pattern_name} in {filename}")
            raise HTTPException(
                status_code=400,
                detail="파일에 허용되지 않는 내용이 포함되어 있습니다."
            )

    return True


async def detect_file_type_by_magic(content: bytes, filename: str) -> Tuple[str, str]:
    """
    Detect file type using libmagic (file signature analysis)

    Args:
        content: File content (first few KB)
        filename: Filename for logging

    Returns:
        Tuple of (mime_type, file_type_description)

    Raises:
        HTTPException: If file type cannot be determined or is suspicious
    """
    if not MAGIC_AVAILABLE:
        logger.debug("python-magic not available, skipping magic-based detection")
        return "application/octet-stream", "Binary data"

    try:
        # Use python-magic to detect file type
        mime = magic.Magic(mime=True)
        detected_mime = mime.from_buffer(content)

        mime_desc = magic.Magic()
        file_description = mime_desc.from_buffer(content)

        logger.debug(f"File type detected: {detected_mime} ({file_description}) for {filename}")

        return detected_mime, file_description

    except Exception as e:
        logger.error(f"Failed to detect file type for {filename}: {e}")
        raise HTTPException(
            status_code=400,
            detail="파일 형식을 확인할 수 없습니다."
        )


async def validate_file_security(
    file: UploadFile,
    filename: str,
    enable_mime_check: bool = True,
    enable_pattern_scan: bool = True,
    enable_magic_check: bool = False,  # Optional: requires python-magic
    max_scan_bytes: int = 10 * 1024 * 1024
) -> bool:
    """
    Comprehensive file security validation

    Performs multiple layers of security checks:
    1. MIME type validation
    2. Malicious pattern detection
    3. File magic number verification (optional)

    Args:
        file: Uploaded file object
        filename: Validated filename
        enable_mime_check: Enable MIME type validation
        enable_pattern_scan: Enable malicious pattern scanning
        enable_magic_check: Enable libmagic file type detection
        max_scan_bytes: Maximum bytes to scan

    Returns:
        True if all validations pass

    Raises:
        HTTPException: If any validation fails
    """
    # 1. MIME type validation
    if enable_mime_check:
        await validate_mime_type(file, filename)

    # Read file content for pattern scanning
    if enable_pattern_scan or enable_magic_check:
        content = await file.read(max_scan_bytes)
        await file.seek(0)  # Reset file pointer

        # 2. Malicious pattern detection
        if enable_pattern_scan:
            await scan_malicious_patterns(content, filename, max_scan_bytes)

        # 3. File magic number verification (optional)
        if enable_magic_check and MAGIC_AVAILABLE:
            detected_mime, _ = await detect_file_type_by_magic(content[:1024], filename)

            # Cross-check with declared MIME type
            if file.content_type not in [detected_mime, 'application/octet-stream']:
                logger.warning(
                    f"⚠️ MIME type mismatch: declared={file.content_type}, "
                    f"detected={detected_mime} for {filename}"
                )
                # Don't fail on mismatch, but log for monitoring

    logger.info(f"✅ Security validation passed for: {filename}")
    return True


# ClamAV integration
try:
    import clamd
    CLAMD_AVAILABLE = True
except ImportError:
    CLAMD_AVAILABLE = False
    logger.debug("clamd not installed, antivirus scanning disabled")


async def scan_with_antivirus(
    file_path: str,
    clamd_host: str = "localhost",
    clamd_port: int = 3310,
    timeout: int = 30
) -> Optional[str]:
    """
    Scan file with ClamAV antivirus

    Integrates with ClamAV daemon (clamd) for real-time virus scanning.

    Args:
        file_path: Path to uploaded file
        clamd_host: ClamAV daemon hostname (default: localhost)
        clamd_port: ClamAV daemon port (default: 3310)
        timeout: Scan timeout in seconds (default: 30)

    Returns:
        None if clean, threat description if infected

    Raises:
        ConnectionError: If ClamAV daemon is not available
        TimeoutError: If scan takes longer than timeout

    Example:
        result = await scan_with_antivirus("/tmp/uploaded_file.pdf")
        if result:
            logger.error(f"Virus detected: {result}")
            # Handle infected file
    """
    if not CLAMD_AVAILABLE:
        logger.warning("⚠️ ClamAV client not available, skipping virus scan")
        return None

    try:
        # Connect to ClamAV daemon
        cd = clamd.ClamdNetworkSocket(host=clamd_host, port=clamd_port, timeout=timeout)

        # Ping to check if daemon is available
        try:
            cd.ping()
        except Exception as e:
            logger.warning(f"⚠️ ClamAV daemon not available at {clamd_host}:{clamd_port}: {e}")
            return None

        # Scan the file using stream (avoids Docker volume mount issues)
        logger.debug(f"🔍 Scanning file with ClamAV: {file_path}")

        # Read file and send as stream to ClamAV
        with open(file_path, 'rb') as f:
            scan_result = cd.instream(f)

        # Parse result
        # instream returns: {'stream': ('FOUND', 'virus_name')} or {'stream': ('OK', None)}
        if 'stream' in scan_result:
            status, virus_name = scan_result['stream']
            if status == "FOUND":
                logger.error(f"🚨 Virus detected in {file_path}: {virus_name}")
                return virus_name
            elif status == "ERROR":
                logger.error(f"❌ ClamAV scan error for {file_path}: {virus_name}")
                # Return error as threat to be safe
                return f"Scan error: {virus_name}"
            elif status == "OK":
                # Clean file
                logger.debug(f"✅ File is clean: {file_path}")
                return None

        # Default: assume clean if no explicit result
        logger.debug(f"✅ File is clean: {file_path}")
        return None

    except clamd.ConnectionError as e:
        logger.error(f"❌ ClamAV connection error: {e}")
        # Don't block upload on connection failure
        logger.warning(f"⚠️ Continuing without virus scan due to connection error")
        return None

    except Exception as e:
        logger.error(f"❌ ClamAV scan failed: {e}")
        # Don't block upload on scan failure, but log the issue
        logger.warning(f"⚠️ Continuing without virus scan due to error: {e}")
        return None
