"""
Error Handling Utilities

Provides safe error message generation for user display
while preventing information disclosure.
"""

from typing import Optional, NoReturn
from fastapi import HTTPException
from loguru import logger


# Standard HTTP error messages (Korean)
HTTP_ERROR_MESSAGES = {
    # 4xx Client Errors
    400: "잘못된 요청입니다",
    401: "인증이 필요합니다",
    403: "접근 권한이 없습니다",
    404: "요청한 리소스를 찾을 수 없습니다",
    409: "요청이 현재 상태와 충돌합니다",
    422: "요청 데이터를 처리할 수 없습니다",
    429: "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요",
    # 5xx Server Errors
    500: "서버 오류가 발생했습니다",
    502: "게이트웨이 오류가 발생했습니다",
    503: "서비스를 일시적으로 사용할 수 없습니다",
    504: "요청 시간이 초과되었습니다",
}


def raise_http_error(
    status_code: int,
    detail: Optional[str] = None,
    context: str = "",
    error: Optional[Exception] = None
) -> NoReturn:
    """
    Raise HTTPException with consistent error messages.

    Args:
        status_code: HTTP status code
        detail: Optional custom detail message (Korean preferred)
        context: Context for logging (not exposed to user)
        error: Optional exception for logging

    Raises:
        HTTPException: Always raises with consistent message format
    """
    if error:
        logger.error(f"HTTP {status_code} in {context}: {type(error).__name__}: {str(error)}")
    elif context:
        logger.warning(f"HTTP {status_code} in {context}")

    message = detail if detail else HTTP_ERROR_MESSAGES.get(status_code, "오류가 발생했습니다")
    raise HTTPException(status_code=status_code, detail=message)


def raise_not_found(resource: str = "리소스", context: str = "") -> NoReturn:
    """Raise 404 Not Found with consistent message."""
    raise_http_error(404, f"요청한 {resource}을(를) 찾을 수 없습니다", context)


def raise_unauthorized(detail: str = "인증이 필요합니다", context: str = "") -> NoReturn:
    """Raise 401 Unauthorized with consistent message."""
    raise_http_error(401, detail, context)


def raise_forbidden(detail: str = "접근 권한이 없습니다", context: str = "") -> NoReturn:
    """Raise 403 Forbidden with consistent message."""
    raise_http_error(403, detail, context)


def raise_bad_request(detail: str = "잘못된 요청입니다", context: str = "") -> NoReturn:
    """Raise 400 Bad Request with consistent message."""
    raise_http_error(400, detail, context)


def raise_server_error(
    error: Exception,
    context: str = "",
    detail: Optional[str] = None
) -> NoReturn:
    """
    Raise 500 Internal Server Error with safe message.

    Logs the actual error server-side but returns safe message to client.
    """
    safe_message = detail if detail else get_safe_error_message(error, context)
    raise_http_error(500, safe_message, context, error)


def raise_service_unavailable(
    service: str = "서비스",
    context: str = ""
) -> NoReturn:
    """Raise 503 Service Unavailable with consistent message."""
    raise_http_error(503, f"{service}을(를) 일시적으로 사용할 수 없습니다", context)


def get_safe_error_message(error: Exception, context: str = "") -> str:
    """
    Get sanitized error message for user display (prevents information disclosure)

    Security: Never expose internal details like:
    - File paths or directory structure
    - Database connection strings or queries
    - Stack traces or exception details
    - Internal system information

    All detailed errors are logged server-side only.

    Args:
        error: The exception that occurred
        context: Context description for logging (not exposed to user)

    Returns:
        Generic, safe error message for user display
    """
    error_type = type(error).__name__

    # Log full error details server-side for debugging
    logger.error(f"Error in {context}: {error_type}: {str(error)}")

    # Map exception types to generic user-friendly messages
    # Security: DO NOT include error details or internal information
    error_messages = {
        "FileNotFoundError": "요청한 파일을 찾을 수 없습니다.",
        "PermissionError": "파일에 대한 접근 권한이 없습니다.",
        "ValueError": "잘못된 입력값입니다.",
        "ConnectionError": "서비스 연결에 실패했습니다. 잠시 후 다시 시도해주세요.",
        "TimeoutError": "요청 처리 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
        "KeyError": "필수 정보가 누락되었습니다.",
        "TypeError": "잘못된 데이터 형식입니다.",
        "AttributeError": "요청을 처리하는 중 오류가 발생했습니다.",
        "IndexError": "유효하지 않은 인덱스입니다.",
        "KeyboardInterrupt": "작업이 취소되었습니다.",
        "MemoryError": "메모리가 부족합니다.",
        "OSError": "시스템 오류가 발생했습니다.",
        "IOError": "입출력 오류가 발생했습니다.",
    }

    # Return generic safe message (no internal details exposed)
    safe_message = error_messages.get(
        error_type,
        "요청을 처리하는 중 오류가 발생했습니다."  # Generic fallback for unknown errors
    )

    return safe_message
