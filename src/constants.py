"""
Application Constants

Centralized constants for timeouts, TTLs, limits, and other configuration values.
Using constants improves maintainability and makes the code self-documenting.
"""

from typing import Final, List

# ==================== Timeouts (seconds) ====================

class Timeouts:
    """HTTP and operation timeouts in seconds"""

    # Quick operations (health checks, simple queries)
    QUICK: Final[int] = 5

    # Standard operations (API calls, document processing)
    STANDARD: Final[int] = 30

    # Long operations (LLM inference, file processing)
    LONG: Final[int] = 60

    # Very long operations (bulk operations, large file processing)
    VERY_LONG: Final[int] = 300

    # Docker operations
    DOCKER_CHECK: Final[int] = 5
    DOCKER_COPY: Final[int] = 30
    DOCKER_RESTART: Final[int] = 30

    # External API calls
    SMTP_CONNECTION: Final[int] = 10
    HTTP_REQUEST: Final[int] = 30
    LLM_INFERENCE: Final[int] = 300
    EMBEDDING_REQUEST: Final[int] = 60
    WEB_CRAWL: Final[int] = 30
    WEB_SEARCH: Final[int] = 15


# ==================== Cache TTLs (seconds) ====================

class CacheTTL:
    """Cache Time-To-Live values in seconds"""

    # Short-lived cache (frequently changing data)
    SHORT: Final[int] = 60  # 1 minute

    # Standard cache
    STANDARD: Final[int] = 300  # 5 minutes

    # Medium cache (settings, configuration)
    MEDIUM: Final[int] = 600  # 10 minutes

    # Long cache (static data)
    LONG: Final[int] = 3600  # 1 hour

    # Very long cache (rarely changing data)
    VERY_LONG: Final[int] = 86400  # 24 hours

    # Specific caches
    SMTP_SETTINGS: Final[int] = 300  # 5 minutes
    QUERY_CACHE: Final[int] = 600  # 10 minutes
    DOCUMENT_CACHE: Final[int] = 3600  # 1 hour
    CONFIG_CACHE: Final[int] = 300  # 5 minutes


# ==================== Limits ====================

class Limits:
    """Various application limits"""

    # Pagination
    DEFAULT_PAGE_SIZE: Final[int] = 20
    MAX_PAGE_SIZE: Final[int] = 100

    # File operations
    MAX_FILE_SIZE_MB: Final[int] = 100
    MAX_UPLOAD_FILES: Final[int] = 10

    # Cache sizes
    QUERY_CACHE_MAX_SIZE: Final[int] = 500

    # Rate limiting
    DEFAULT_RATE_LIMIT_PER_MINUTE: Final[int] = 60
    DEFAULT_RATE_LIMIT_BURST: Final[int] = 10

    # Session
    SESSION_EXPIRY_DAYS: Final[int] = 30

    # Backup
    MAX_BACKUP_RETENTION_DAYS: Final[int] = 30

    # Search results
    MAX_SEARCH_RESULTS: Final[int] = 50
    DEFAULT_SEARCH_RESULTS: Final[int] = 10

    # Conversation
    MAX_CONVERSATION_HISTORY: Final[int] = 50

    # Webhook
    DEFAULT_WEBHOOK_TIMEOUT: Final[int] = 30
    DEFAULT_WEBHOOK_RETRY_COUNT: Final[int] = 3


# ==================== HTTP Status Messages ====================

class ErrorMessages:
    """Standardized error messages (Korean)"""

    # Authentication
    INVALID_CREDENTIALS: Final[str] = "이메일 또는 비밀번호가 올바르지 않습니다"
    SESSION_EXPIRED: Final[str] = "세션이 만료되었습니다"
    UNAUTHORIZED: Final[str] = "인증이 필요합니다"
    FORBIDDEN: Final[str] = "접근 권한이 없습니다"

    # Validation
    INVALID_INPUT: Final[str] = "잘못된 입력값입니다"
    REQUIRED_FIELD_MISSING: Final[str] = "필수 항목이 누락되었습니다"

    # Resources
    NOT_FOUND: Final[str] = "요청한 리소스를 찾을 수 없습니다"
    USER_NOT_FOUND: Final[str] = "사용자를 찾을 수 없습니다"
    FILE_NOT_FOUND: Final[str] = "파일을 찾을 수 없습니다"

    # Server errors
    INTERNAL_ERROR: Final[str] = "서버 오류가 발생했습니다"
    SERVICE_UNAVAILABLE: Final[str] = "서비스를 일시적으로 사용할 수 없습니다"

    # Rate limiting
    RATE_LIMIT_EXCEEDED: Final[str] = "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요"


# ==================== File Types ====================

class AllowedFileTypes:
    """Allowed file extensions for upload"""

    DOCUMENTS: Final[List[str]] = ["pdf", "hwp", "hwpx", "doc", "docx", "xls", "xlsx", "ppt", "pptx"]
    IMAGES: Final[List[str]] = ["jpg", "jpeg", "png", "gif", "webp"]
    ALL: Final[List[str]] = DOCUMENTS + IMAGES
