"""
Exception Handlers Middleware

Centralized exception handling for the FastAPI application.
Handles HTTP exceptions, validation errors, custom exceptions, and unhandled errors.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

from ..exceptions import ChatbotException
from ..config import config

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI):
    """
    Register all exception handlers with the FastAPI application.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions"""
        # Log error (but not 401/403/404)
        if exc.status_code >= 500:
            logger.error(f"HTTP {exc.status_code}: {exc.detail} - {request.url}")

        # Don't expose sensitive information in production for 500+ errors
        if config.ENV == "production" and exc.status_code >= 500:
            detail = "Internal server error"
        else:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": detail,
                "error": detail,
                "status_code": exc.status_code
            }
        )


    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors"""
        logger.warning(f"Validation error: {exc.errors()} - {request.url}")

        # Extract user-friendly error messages
        errors = exc.errors()
        error_messages = []

        for error in errors:
            field = error.get('loc', [])[-1] if error.get('loc') else 'unknown'
            msg = error.get('msg', '')

            # Extract custom error message from ValueError context
            if error.get('type') == 'value_error' and error.get('ctx'):
                ctx_error = error['ctx'].get('error')
                if ctx_error and hasattr(ctx_error, 'args'):
                    msg = str(ctx_error.args[0]) if ctx_error.args else msg

            # Format field name in Korean
            field_names = {
                'email': '이메일',
                'password': '비밀번호',
                'username': '사용자명',
                'current_password': '현재 비밀번호',
                'new_password': '새 비밀번호'
            }
            field_kr = field_names.get(field, field)

            # If message already contains the error details (like password validation), use it directly
            if '\n' in msg or '요구사항' in msg:
                error_messages.append(msg)
            else:
                error_messages.append(f"{field_kr}: {msg}")

        # Combine all error messages
        combined_message = '\n'.join(error_messages) if error_messages else "입력값이 올바르지 않습니다"

        # Prepare serializable errors for debug mode ONLY in non-production
        serializable_errors = None
        if config.DEBUG and config.ENV != "production":
            serializable_errors = []
            for error in errors:
                serializable_error = {
                    'type': error.get('type'),
                    'loc': error.get('loc'),
                    'msg': error.get('msg'),
                    # Don't expose input in errors - could contain sensitive data
                }
                # Convert ctx to serializable format (exclude sensitive data)
                if error.get('ctx'):
                    serializable_error['ctx'] = {}
                    for key, value in error['ctx'].items():
                        # Skip potentially sensitive context keys
                        if key in ('password', 'token', 'secret', 'api_key'):
                            continue
                        # Convert non-serializable objects to strings
                        if isinstance(value, Exception):
                            serializable_error['ctx'][key] = str(value)
                        else:
                            serializable_error['ctx'][key] = value
                serializable_errors.append(serializable_error)

        return JSONResponse(
            status_code=422,
            content={
                "detail": combined_message,
                "errors": serializable_errors
            }
        )


    @app.exception_handler(ChatbotException)
    async def chatbot_exception_handler(request: Request, exc: ChatbotException):
        """Handle custom chatbot exceptions"""
        # Log based on severity
        if exc.http_status >= 500:
            logger.error(f"ChatbotException [{exc.error_code}]: {exc.message} - {request.url}")
            if config.DEBUG:
                logger.debug(f"Details: {exc.details}")
        elif exc.http_status >= 400:
            logger.warning(f"ChatbotException [{exc.error_code}]: {exc.message} - {request.url}")

        # Build response
        response_content = exc.to_dict()

        # Hide details in production for server errors
        if config.ENV == "production" and exc.http_status >= 500:
            response_content["message"] = "Internal server error"
            response_content["details"] = {}

        return JSONResponse(
            status_code=exc.http_status,
            content=response_content
        )


    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all unhandled exceptions"""
        logger.exception(f"Unhandled exception: {exc} - {request.url}")

        # Don't expose internal errors in production
        if config.ENV == "production":
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "error": "Internal server error",
                    "status_code": 500
                }
            )

        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "error": str(exc),
                "type": type(exc).__name__,
                "status_code": 500
            }
        )
