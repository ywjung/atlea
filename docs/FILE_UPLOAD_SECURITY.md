# File Upload Security Enhancement (Phase 2-3)

## Overview

Comprehensive file upload security implementation with multiple validation layers following defense-in-depth principles.

## Implementation Date
- **Phase**: Phase 2-3
- **Date**: 2026-02-03
- **Status**: ✅ Completed

## Security Layers Implemented

### 1. **Filename Validation** ✅
- **Location**: `src/routers/documents.py:validate_filename()`
- **Features**:
  - Path traversal protection (`..`, `/`, `\`)
  - Null byte injection prevention
  - Unicode normalization (NFC) for Korean filenames
  - Basename extraction to prevent directory injection

### 2. **File Extension Whitelist** ✅
- **Location**: `src/utils/file_security.py:ALLOWED_EXTENSIONS`
- **Allowed Extensions**:
  ```python
  {'.pdf', '.hwp', '.hwpx', '.doc', '.docx',
   '.xls', '.xlsx', '.ppt', '.pptx', '.txt'}
  ```
- **Enforcement**: Pre-upload validation with clear error messages

### 3. **MIME Type Validation** ✅ (NEW)
- **Location**: `src/utils/file_security.py:validate_mime_type()`
- **Features**:
  - Content-Type header validation against whitelist
  - MIME/extension consistency check
  - Suspicious MIME type logging for security monitoring
- **Whitelist**:
  - PDF: `application/pdf`
  - Office: `application/msword`, `application/vnd.openxmlformats-*`
  - HWP: `application/x-hwp`, `application/haansofthwp`
  - Text: `text/plain`
  - ZIP-based: `application/zip`, `application/x-zip-compressed`

### 4. **Malicious Pattern Detection** ✅ (NEW)
- **Location**: `src/utils/file_security.py:scan_malicious_patterns()`
- **Detects**:
  - Embedded scripts (XSS): `<script>` tags
  - PHP code injection: `<?php`, `<?=`
  - Shell commands (RCE): `system()`, `exec()`, `shell_exec()`
  - SQL injection patterns: `union select`, `insert into`, etc.
  - File inclusion attacks: `include()`, `require()`
  - Macro-enabled documents: VBA project detection
- **Scan Limit**: First 10MB of file content
- **Action**: Immediate rejection with security logging

### 5. **Magic Bytes Verification** ✅ (Legacy + Optional)
- **Legacy Check**: `src/routers/documents.py:validate_file_content()`
  - Validates file signatures (PDF, HWP, Office formats)
  - UTF-8/ASCII text validation
- **Optional Enhanced Check**: `src/utils/file_security.py:detect_file_type_by_magic()`
  - Uses `python-magic` library (optional dependency)
  - Cross-checks declared vs detected MIME types
  - Currently disabled by default (requires `python-magic`)

### 6. **File Size Limits** ✅ (Existing)
- **Location**: `src/routers/documents.py:upload_document()`
- **Limit**: Configurable via `MAX_FILE_SIZE_MB` (default: 100MB)
- **Enforcement**: Streaming validation during upload
- **Protection**: Prevents resource exhaustion attacks

### 7. **Upload Rate Limiting** ✅ (Existing)
- **Location**: `src/middleware/rate_limiter_redis.py`
- **Features**:
  - Token bucket algorithm with Redis backend
  - Per-IP rate limiting
  - Configurable limits and burst allowance
  - Automatic rate limit header exposure

### 8. **Virus Scanning Hook** ✅ (Placeholder)
- **Location**: `src/utils/file_security.py:scan_with_antivirus()`
- **Status**: Integration hook provided for future AV integration
- **Supported Engines**:
  - ClamAV (clamd)
  - VirusTotal API
  - Custom AV solutions
- **Implementation**: Ready for plugin when needed

## Security Architecture

### Validation Flow
```
Upload Request
    ↓
Admin Authorization Check
    ↓
Filename Sanitization (Path Traversal Prevention)
    ↓
Extension Whitelist Check
    ↓
MIME Type Validation ← [NEW]
    ↓
Malicious Pattern Scan ← [NEW]
    ↓
Magic Bytes Verification
    ↓
Streaming Upload with Size Check
    ↓
Optional: Virus Scan (Hook Available)
    ↓
Document Processing & Indexing
```

### Defense-in-Depth Layers
1. **Perimeter**: Admin-only access, rate limiting
2. **Input Validation**: Filename sanitization, extension whitelist
3. **Content Validation**: MIME type, magic bytes, pattern scanning
4. **Resource Protection**: Size limits, streaming uploads
5. **Monitoring**: Security logging, suspicious activity alerts

## Configuration

### Enable/Disable Security Features
```python
# In src/routers/documents.py:upload_document()
await validate_file_security(
    file=file,
    filename=safe_filename,
    enable_mime_check=True,        # MIME type validation
    enable_pattern_scan=True,      # Malicious pattern detection
    enable_magic_check=False       # Optional python-magic check
)
```

### Optional Dependencies
- **python-magic**: Advanced file type detection
  ```bash
  pip install python-magic
  # Also requires libmagic: brew install libmagic (Mac) / apt-get install libmagic1 (Linux)
  ```

## Security Logging

### Suspicious Activity Logs
- MIME type mismatches: `⚠️ Suspicious MIME type: {type} for file: {filename}`
- Extension mismatches: `⚠️ MIME/extension mismatch: {mime} vs {ext}`
- Malicious patterns: `🚨 Malicious pattern detected: {pattern} in {filename}`

### Log Locations
- **Application logs**: `logs/server.log`
- **Audit logs**: Redis `audit:security:*` keys
- **Security events**: WebSocket alerts for admins

## Testing Recommendations

### Security Test Cases
1. **Path Traversal**: Upload file named `../../etc/passwd.pdf`
2. **Null Byte Injection**: Upload file named `malicious.pdf\x00.txt`
3. **Extension Spoofing**: Upload `.exe` file renamed as `.pdf`
4. **MIME Mismatch**: Upload PDF with Content-Type `text/html`
5. **Malicious Content**: Upload document with embedded `<script>` tags
6. **Size Limit**: Upload file exceeding `MAX_FILE_SIZE_MB`
7. **Rate Limiting**: Rapid consecutive upload attempts

### Manual Testing
```bash
# Test path traversal
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@../../../etc/passwd;filename=../../etc/passwd.pdf"

# Test MIME type validation
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/html" \
  -F "file=@document.pdf"

# Test size limit
dd if=/dev/zero of=large.pdf bs=1M count=101  # Create 101MB file
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@large.pdf"
```

## Compliance

### Security Standards
- ✅ **OWASP Top 10 2021**:
  - A03:2021 – Injection (SQL, Command, XSS prevention)
  - A04:2021 – Insecure Design (Defense-in-depth)
  - A05:2021 – Security Misconfiguration (Secure defaults)
  - A08:2021 – Software and Data Integrity Failures (File validation)

- ✅ **CWE Coverage**:
  - CWE-22: Path Traversal
  - CWE-434: Unrestricted Upload of File with Dangerous Type
  - CWE-79: Cross-site Scripting (XSS)
  - CWE-89: SQL Injection
  - CWE-78: OS Command Injection

### Audit Requirements
- All suspicious uploads logged
- Security events sent to admin WebSocket alerts
- 90-day audit log retention in Redis

## Future Enhancements

### Recommended Additions
1. **Virus Scanning Integration**: Implement ClamAV or VirusTotal API
2. **Content Sandboxing**: Process uploads in isolated environment
3. **User Upload Quotas**: Per-user storage limits
4. **File Encryption**: Encrypt files at rest
5. **Digital Signatures**: Verify document authenticity
6. **Advanced DLP**: Data loss prevention for sensitive content

### Monitoring Improvements
1. **Metrics Dashboard**: Real-time upload security metrics
2. **Anomaly Detection**: ML-based suspicious pattern detection
3. **Threat Intelligence**: Integration with threat feeds
4. **Automated Response**: Auto-block IPs with repeated violations

## References

### Internal Documentation
- `src/utils/file_security.py`: Security validation module
- `src/routers/documents.py`: Document upload endpoint
- `src/middleware/rate_limiter_redis.py`: Rate limiting middleware

### External Resources
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [CWE-434: Unrestricted Upload](https://cwe.mitre.org/data/definitions/434.html)
- [NIST SP 800-53: Media Protection](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)

## Changelog

### Version 2.3.0 (2026-02-03)
- ✅ Added MIME type validation
- ✅ Implemented malicious pattern detection
- ✅ Created comprehensive security validation module
- ✅ Added virus scanning integration hook
- ✅ Enhanced security logging and monitoring
- ✅ Documented security architecture and testing procedures
