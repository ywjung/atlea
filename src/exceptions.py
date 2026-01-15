"""
Custom Exception Classes - 체계적인 에러 처리를 위한 예외 클래스

📝 Changelog:
- 2025-12-30: Created custom exception hierarchy
  - Base exception with error codes
  - Domain-specific exceptions
  - HTTP status code mapping
"""

from typing import Optional, Dict, Any


class ChatbotException(Exception):
    """
    Base exception for all chatbot errors

    Attributes:
        message: Error message
        error_code: Unique error code for logging/debugging
        details: Additional context information
        http_status: HTTP status code for API responses
    """

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None,
        http_status: int = 500
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.http_status = http_status
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response"""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details
        }


# ============================================================================
# Document Processing Errors
# ============================================================================

class DocumentProcessingError(ChatbotException):
    """문서 처리 중 발생하는 에러"""

    def __init__(self, message: str, filename: Optional[str] = None, **kwargs):
        details = kwargs.pop('details', {})
        if filename:
            details['filename'] = filename
        error_code = kwargs.pop('error_code', "DOCUMENT_PROCESSING_ERROR")
        http_status = kwargs.pop('http_status', 422)
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
            http_status=http_status,
            **kwargs
        )


class UnsupportedFileTypeError(DocumentProcessingError):
    """지원하지 않는 파일 형식"""

    def __init__(self, file_type: str, filename: Optional[str] = None):
        super().__init__(
            message=f"Unsupported file type: {file_type}",
            filename=filename,
            error_code="UNSUPPORTED_FILE_TYPE",
            details={'file_type': file_type},
            http_status=415
        )


class DocumentParsingError(DocumentProcessingError):
    """문서 파싱 실패"""

    def __init__(self, message: str, filename: Optional[str] = None, parse_error: Optional[str] = None):
        details = {}
        if parse_error:
            details['parse_error'] = str(parse_error)
        super().__init__(
            message=message,
            filename=filename,
            error_code="DOCUMENT_PARSING_ERROR",
            details=details
        )


class DocumentSizeTooLargeError(DocumentProcessingError):
    """문서 크기 초과"""

    def __init__(self, size_mb: float, max_size_mb: float, filename: Optional[str] = None):
        super().__init__(
            message=f"Document size ({size_mb:.1f}MB) exceeds maximum allowed size ({max_size_mb}MB)",
            filename=filename,
            error_code="DOCUMENT_SIZE_TOO_LARGE",
            details={'size_mb': size_mb, 'max_size_mb': max_size_mb},
            http_status=413
        )


# ============================================================================
# Vector Database Errors
# ============================================================================

class VectorDBError(ChatbotException):
    """벡터 데이터베이스 에러"""

    def __init__(self, message: str, operation: Optional[str] = None, **kwargs):
        details = kwargs.pop('details', {})
        if operation:
            details['operation'] = operation
        error_code = kwargs.pop('error_code', "VECTOR_DB_ERROR")
        http_status = kwargs.pop('http_status', 500)
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
            http_status=http_status,
            **kwargs
        )


class VectorDBConnectionError(VectorDBError):
    """데이터베이스 연결 실패"""

    def __init__(self, message: str = "Failed to connect to vector database"):
        super().__init__(
            message=message,
            error_code="VECTOR_DB_CONNECTION_ERROR",
            http_status=503
        )


class VectorSearchError(VectorDBError):
    """벡터 검색 실패"""

    def __init__(self, message: str, query: Optional[str] = None):
        details = {}
        if query:
            details['query'] = query[:100]  # First 100 chars
        super().__init__(
            message=message,
            operation="search",
            error_code="VECTOR_SEARCH_ERROR",
            details=details
        )


# ============================================================================
# LLM & RAG Errors
# ============================================================================

class LLMError(ChatbotException):
    """LLM 관련 에러"""

    def __init__(self, message: str, model: Optional[str] = None, **kwargs):
        details = kwargs.pop('details', {})
        if model:
            details['model'] = model
        error_code = kwargs.pop('error_code', "LLM_ERROR")
        http_status = kwargs.pop('http_status', 500)
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
            http_status=http_status,
            **kwargs
        )


class LLMGenerationError(LLMError):
    """LLM 응답 생성 실패"""

    def __init__(self, message: str, model: Optional[str] = None, prompt_length: Optional[int] = None):
        details = {}
        if prompt_length:
            details['prompt_length'] = prompt_length
        super().__init__(
            message=message,
            model=model,
            error_code="LLM_GENERATION_ERROR",
            details=details
        )


class ContextTooLongError(LLMError):
    """컨텍스트 길이 초과"""

    def __init__(self, token_count: int, max_tokens: int):
        super().__init__(
            message=f"Context too long ({token_count} tokens), maximum is {max_tokens}",
            error_code="CONTEXT_TOO_LONG",
            details={'token_count': token_count, 'max_tokens': max_tokens},
            http_status=413
        )


class RAGSystemError(ChatbotException):
    """RAG 시스템 에러"""

    def __init__(self, message: str, stage: Optional[str] = None, **kwargs):
        details = kwargs.pop('details', {})
        if stage:
            details['stage'] = stage
        error_code = kwargs.pop('error_code', "RAG_SYSTEM_ERROR")
        http_status = kwargs.pop('http_status', 500)
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
            http_status=http_status,
            **kwargs
        )


# ============================================================================
# Authentication & Authorization Errors
# ============================================================================

class AuthenticationError(ChatbotException):
    """인증 에러"""

    def __init__(self, message: str = "Authentication failed", **kwargs):
        error_code = kwargs.pop('error_code', "AUTHENTICATION_ERROR")
        http_status = kwargs.pop('http_status', 401)
        super().__init__(
            message=message,
            error_code=error_code,
            http_status=http_status,
            **kwargs
        )


class InvalidTokenError(AuthenticationError):
    """유효하지 않은 토큰"""

    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(
            message=message,
            error_code="INVALID_TOKEN"
        )


class InvalidCredentialsError(AuthenticationError):
    """잘못된 인증 정보"""

    def __init__(self, message: str = "Invalid username or password"):
        super().__init__(
            message=message,
            error_code="INVALID_CREDENTIALS"
        )


class AuthorizationError(ChatbotException):
    """권한 에러"""

    def __init__(self, message: str = "Insufficient permissions", required_role: Optional[str] = None):
        details = {}
        if required_role:
            details['required_role'] = required_role
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            details=details,
            http_status=403
        )


# ============================================================================
# Cache Errors
# ============================================================================

class CacheError(ChatbotException):
    """캐시 관련 에러"""

    def __init__(self, message: str, operation: Optional[str] = None, **kwargs):
        details = kwargs.pop('details', {})
        if operation:
            details['operation'] = operation
        error_code = kwargs.pop('error_code', "CACHE_ERROR")
        http_status = kwargs.pop('http_status', 500)
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
            http_status=http_status,
            **kwargs
        )


class CacheConnectionError(CacheError):
    """캐시 연결 실패"""

    def __init__(self, message: str = "Failed to connect to cache"):
        super().__init__(
            message=message,
            error_code="CACHE_CONNECTION_ERROR",
            http_status=503
        )


# ============================================================================
# Validation Errors
# ============================================================================

class ValidationError(ChatbotException):
    """입력 검증 에러"""

    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        details = kwargs.pop('details', {})
        if field:
            details['field'] = field
        error_code = kwargs.pop('error_code', "VALIDATION_ERROR")
        http_status = kwargs.pop('http_status', 400)
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
            http_status=http_status,
            **kwargs
        )


class InvalidInputError(ValidationError):
    """잘못된 입력 데이터"""

    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None):
        details = {}
        if value is not None:
            details['value'] = str(value)[:100]  # First 100 chars
        super().__init__(
            message=message,
            field=field,
            error_code="INVALID_INPUT",
            details=details
        )


class RequiredFieldMissingError(ValidationError):
    """필수 필드 누락"""

    def __init__(self, field: str):
        super().__init__(
            message=f"Required field missing: {field}",
            field=field,
            error_code="REQUIRED_FIELD_MISSING"
        )


# ============================================================================
# Resource Errors
# ============================================================================

class ResourceError(ChatbotException):
    """리소스 관련 에러"""

    def __init__(self, message: str, resource_type: Optional[str] = None, **kwargs):
        details = kwargs.pop('details', {})
        if resource_type:
            details['resource_type'] = resource_type
        error_code = kwargs.pop('error_code', "RESOURCE_ERROR")
        http_status = kwargs.pop('http_status', 500)
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
            http_status=http_status,
            **kwargs
        )


class ResourceNotFoundError(ResourceError):
    """리소스를 찾을 수 없음"""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            resource_type=resource_type,
            error_code="RESOURCE_NOT_FOUND",
            details={'resource_id': resource_id},
            http_status=404
        )


class ResourceAlreadyExistsError(ResourceError):
    """리소스가 이미 존재함"""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} already exists: {resource_id}",
            resource_type=resource_type,
            error_code="RESOURCE_ALREADY_EXISTS",
            details={'resource_id': resource_id},
            http_status=409
        )


# ============================================================================
# Rate Limiting Errors
# ============================================================================

class RateLimitExceededError(ChatbotException):
    """API 호출 제한 초과"""

    def __init__(self, retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details['retry_after_seconds'] = retry_after
        super().__init__(
            message="Rate limit exceeded. Please try again later.",
            error_code="RATE_LIMIT_EXCEEDED",
            details=details,
            http_status=429
        )


# ============================================================================
# Configuration Errors
# ============================================================================

class ConfigurationError(ChatbotException):
    """설정 에러"""

    def __init__(self, message: str, config_key: Optional[str] = None):
        details = {}
        if config_key:
            details['config_key'] = config_key
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details,
            http_status=500
        )


# ============================================================================
# Export all exceptions
# ============================================================================

__all__ = [
    # Base
    'ChatbotException',

    # Document Processing
    'DocumentProcessingError',
    'UnsupportedFileTypeError',
    'DocumentParsingError',
    'DocumentSizeTooLargeError',

    # Vector DB
    'VectorDBError',
    'VectorDBConnectionError',
    'VectorSearchError',

    # LLM & RAG
    'LLMError',
    'LLMGenerationError',
    'ContextTooLongError',
    'RAGSystemError',

    # Authentication
    'AuthenticationError',
    'InvalidTokenError',
    'InvalidCredentialsError',
    'AuthorizationError',

    # Cache
    'CacheError',
    'CacheConnectionError',

    # Validation
    'ValidationError',
    'InvalidInputError',
    'RequiredFieldMissingError',

    # Resources
    'ResourceError',
    'ResourceNotFoundError',
    'ResourceAlreadyExistsError',

    # Rate Limiting
    'RateLimitExceededError',

    # Configuration
    'ConfigurationError',
]
