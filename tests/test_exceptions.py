"""
Tests for custom exception classes

📝 Changelog:
- 2025-12-30: Created comprehensive exception tests
  - Base exception functionality
  - Domain-specific exceptions
  - HTTP status code mapping
  - JSON serialization
"""

import pytest
from src.exceptions import (
    # Base
    ChatbotException,

    # Document Processing
    DocumentProcessingError,
    UnsupportedFileTypeError,
    DocumentParsingError,
    DocumentSizeTooLargeError,

    # Vector DB
    VectorDBError,
    VectorDBConnectionError,
    VectorSearchError,

    # LLM & RAG
    LLMError,
    LLMGenerationError,
    ContextTooLongError,
    RAGSystemError,

    # Authentication
    AuthenticationError,
    InvalidTokenError,
    InvalidCredentialsError,
    AuthorizationError,

    # Cache
    CacheError,
    CacheConnectionError,

    # Validation
    ValidationError,
    InvalidInputError,
    RequiredFieldMissingError,

    # Resources
    ResourceError,
    ResourceNotFoundError,
    ResourceAlreadyExistsError,

    # Rate Limiting
    RateLimitExceededError,

    # Configuration
    ConfigurationError,
)


class TestChatbotException:
    """Tests for base ChatbotException class"""

    def test_basic_exception(self):
        """Test basic exception creation"""
        exc = ChatbotException("Test error")
        assert str(exc) == "Test error"
        assert exc.error_code == "UNKNOWN_ERROR"
        assert exc.http_status == 500
        assert exc.details == {}

    def test_exception_with_details(self):
        """Test exception with custom details"""
        exc = ChatbotException(
            "Test error",
            error_code="TEST_ERROR",
            details={"key": "value"},
            http_status=400
        )
        assert exc.error_code == "TEST_ERROR"
        assert exc.http_status == 400
        assert exc.details == {"key": "value"}

    def test_to_dict(self):
        """Test JSON serialization"""
        exc = ChatbotException(
            "Test error",
            error_code="TEST_ERROR",
            details={"key": "value"}
        )
        result = exc.to_dict()
        assert result == {
            "error": "TEST_ERROR",
            "message": "Test error",
            "details": {"key": "value"}
        }


class TestDocumentProcessingErrors:
    """Tests for document processing exceptions"""

    def test_document_processing_error(self):
        """Test DocumentProcessingError"""
        exc = DocumentProcessingError("Failed to process", filename="test.pdf")
        assert exc.error_code == "DOCUMENT_PROCESSING_ERROR"
        assert exc.http_status == 422
        assert exc.details["filename"] == "test.pdf"

    def test_unsupported_file_type(self):
        """Test UnsupportedFileTypeError"""
        exc = UnsupportedFileTypeError("docx", filename="test.docx")
        assert exc.error_code == "UNSUPPORTED_FILE_TYPE"
        assert exc.http_status == 415
        assert exc.details["file_type"] == "docx"
        assert "Unsupported file type: docx" in str(exc)

    def test_document_parsing_error(self):
        """Test DocumentParsingError"""
        exc = DocumentParsingError(
            "Parse failed",
            filename="test.pdf",
            parse_error="Invalid PDF structure"
        )
        assert exc.error_code == "DOCUMENT_PARSING_ERROR"
        assert exc.details["parse_error"] == "Invalid PDF structure"

    def test_document_size_too_large(self):
        """Test DocumentSizeTooLargeError"""
        exc = DocumentSizeTooLargeError(25.5, 20.0, filename="large.pdf")
        assert exc.error_code == "DOCUMENT_SIZE_TOO_LARGE"
        assert exc.http_status == 413
        assert exc.details["size_mb"] == 25.5
        assert exc.details["max_size_mb"] == 20.0
        assert "25.5MB" in str(exc)
        assert "20" in str(exc) and "MB" in str(exc)


class TestVectorDBErrors:
    """Tests for vector database exceptions"""

    def test_vector_db_error(self):
        """Test VectorDBError"""
        exc = VectorDBError("Connection failed", operation="search")
        assert exc.error_code == "VECTOR_DB_ERROR"
        assert exc.details["operation"] == "search"

    def test_vector_db_connection_error(self):
        """Test VectorDBConnectionError"""
        exc = VectorDBConnectionError()
        assert exc.error_code == "VECTOR_DB_CONNECTION_ERROR"
        assert exc.http_status == 503
        assert "connect" in str(exc).lower()

    def test_vector_search_error(self):
        """Test VectorSearchError"""
        exc = VectorSearchError("Search failed", query="test query")
        assert exc.error_code == "VECTOR_SEARCH_ERROR"
        assert exc.details["query"] == "test query"


class TestLLMErrors:
    """Tests for LLM and RAG exceptions"""

    def test_llm_error(self):
        """Test LLMError"""
        exc = LLMError("Generation failed", model="gpt-4")
        assert exc.error_code == "LLM_ERROR"
        assert exc.details["model"] == "gpt-4"

    def test_llm_generation_error(self):
        """Test LLMGenerationError"""
        exc = LLMGenerationError(
            "Failed to generate",
            model="gpt-4",
            prompt_length=5000
        )
        assert exc.error_code == "LLM_GENERATION_ERROR"
        assert exc.details["prompt_length"] == 5000

    def test_context_too_long(self):
        """Test ContextTooLongError"""
        exc = ContextTooLongError(10000, 8192)
        assert exc.error_code == "CONTEXT_TOO_LONG"
        assert exc.http_status == 413
        assert exc.details["token_count"] == 10000
        assert exc.details["max_tokens"] == 8192
        assert "10000" in str(exc)
        assert "8192" in str(exc)

    def test_rag_system_error(self):
        """Test RAGSystemError"""
        exc = RAGSystemError("RAG failed", stage="retrieval")
        assert exc.error_code == "RAG_SYSTEM_ERROR"
        assert exc.details["stage"] == "retrieval"


class TestAuthenticationErrors:
    """Tests for authentication and authorization exceptions"""

    def test_authentication_error(self):
        """Test AuthenticationError"""
        exc = AuthenticationError()
        assert exc.error_code == "AUTHENTICATION_ERROR"
        assert exc.http_status == 401
        assert "Authentication failed" in str(exc)

    def test_invalid_token(self):
        """Test InvalidTokenError"""
        exc = InvalidTokenError()
        assert exc.error_code == "INVALID_TOKEN"
        assert exc.http_status == 401
        assert "token" in str(exc).lower()

    def test_invalid_credentials(self):
        """Test InvalidCredentialsError"""
        exc = InvalidCredentialsError()
        assert exc.error_code == "INVALID_CREDENTIALS"
        assert exc.http_status == 401
        assert "username or password" in str(exc).lower()

    def test_authorization_error(self):
        """Test AuthorizationError"""
        exc = AuthorizationError(required_role="admin")
        assert exc.error_code == "AUTHORIZATION_ERROR"
        assert exc.http_status == 403
        assert exc.details["required_role"] == "admin"


class TestCacheErrors:
    """Tests for cache exceptions"""

    def test_cache_error(self):
        """Test CacheError"""
        exc = CacheError("Cache operation failed", operation="get")
        assert exc.error_code == "CACHE_ERROR"
        assert exc.details["operation"] == "get"

    def test_cache_connection_error(self):
        """Test CacheConnectionError"""
        exc = CacheConnectionError()
        assert exc.error_code == "CACHE_CONNECTION_ERROR"
        assert exc.http_status == 503
        assert "connect" in str(exc).lower()


class TestValidationErrors:
    """Tests for validation exceptions"""

    def test_validation_error(self):
        """Test ValidationError"""
        exc = ValidationError("Invalid input", field="email")
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.http_status == 400
        assert exc.details["field"] == "email"

    def test_invalid_input_error(self):
        """Test InvalidInputError"""
        exc = InvalidInputError(
            "Invalid email format",
            field="email",
            value="invalid-email"
        )
        assert exc.error_code == "INVALID_INPUT"
        assert exc.details["value"] == "invalid-email"

    def test_required_field_missing(self):
        """Test RequiredFieldMissingError"""
        exc = RequiredFieldMissingError("username")
        assert exc.error_code == "REQUIRED_FIELD_MISSING"
        assert exc.http_status == 400
        assert exc.details["field"] == "username"
        assert "username" in str(exc)


class TestResourceErrors:
    """Tests for resource exceptions"""

    def test_resource_error(self):
        """Test ResourceError"""
        exc = ResourceError("Resource error", resource_type="document")
        assert exc.error_code == "RESOURCE_ERROR"
        assert exc.details["resource_type"] == "document"

    def test_resource_not_found(self):
        """Test ResourceNotFoundError"""
        exc = ResourceNotFoundError("document", "doc123")
        assert exc.error_code == "RESOURCE_NOT_FOUND"
        assert exc.http_status == 404
        assert exc.details["resource_id"] == "doc123"
        assert "document" in str(exc)
        assert "doc123" in str(exc)

    def test_resource_already_exists(self):
        """Test ResourceAlreadyExistsError"""
        exc = ResourceAlreadyExistsError("user", "john@example.com")
        assert exc.error_code == "RESOURCE_ALREADY_EXISTS"
        assert exc.http_status == 409
        assert exc.details["resource_id"] == "john@example.com"
        assert "already exists" in str(exc)


class TestRateLimitError:
    """Tests for rate limiting exception"""

    def test_rate_limit_exceeded(self):
        """Test RateLimitExceededError"""
        exc = RateLimitExceededError(retry_after=60)
        assert exc.error_code == "RATE_LIMIT_EXCEEDED"
        assert exc.http_status == 429
        assert exc.details["retry_after_seconds"] == 60

    def test_rate_limit_no_retry_after(self):
        """Test RateLimitExceededError without retry_after"""
        exc = RateLimitExceededError()
        assert exc.error_code == "RATE_LIMIT_EXCEEDED"
        assert exc.http_status == 429
        assert "retry_after_seconds" not in exc.details


class TestConfigurationError:
    """Tests for configuration exception"""

    def test_configuration_error(self):
        """Test ConfigurationError"""
        exc = ConfigurationError("Invalid config", config_key="DATABASE_URL")
        assert exc.error_code == "CONFIGURATION_ERROR"
        assert exc.http_status == 500
        assert exc.details["config_key"] == "DATABASE_URL"

    def test_configuration_error_no_key(self):
        """Test ConfigurationError without config_key"""
        exc = ConfigurationError("Invalid config")
        assert exc.error_code == "CONFIGURATION_ERROR"
        assert "config_key" not in exc.details


class TestExceptionInheritance:
    """Tests for exception inheritance hierarchy"""

    def test_all_inherit_from_base(self):
        """Test that all exceptions inherit from ChatbotException"""
        exceptions = [
            DocumentProcessingError("test"),
            VectorDBError("test"),
            LLMError("test"),
            AuthenticationError(),
            CacheError("test"),
            ValidationError("test"),
            ResourceError("test"),
            RateLimitExceededError(),
            ConfigurationError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, ChatbotException)
            assert isinstance(exc, Exception)

    def test_specific_inheritance(self):
        """Test specific inheritance chains"""
        # Document errors
        assert isinstance(UnsupportedFileTypeError("txt"), DocumentProcessingError)
        assert isinstance(DocumentParsingError("test"), DocumentProcessingError)

        # Vector DB errors
        assert isinstance(VectorDBConnectionError(), VectorDBError)
        assert isinstance(VectorSearchError("test"), VectorDBError)

        # LLM errors
        assert isinstance(LLMGenerationError("test"), LLMError)
        assert isinstance(ContextTooLongError(100, 50), LLMError)

        # Auth errors
        assert isinstance(InvalidTokenError(), AuthenticationError)
        assert isinstance(InvalidCredentialsError(), AuthenticationError)

        # Cache errors
        assert isinstance(CacheConnectionError(), CacheError)

        # Validation errors
        assert isinstance(InvalidInputError("test"), ValidationError)
        assert isinstance(RequiredFieldMissingError("test"), ValidationError)

        # Resource errors
        assert isinstance(ResourceNotFoundError("type", "id"), ResourceError)
        assert isinstance(ResourceAlreadyExistsError("type", "id"), ResourceError)
