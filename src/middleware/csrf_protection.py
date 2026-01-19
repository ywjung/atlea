"""CSRF Protection Middleware

Provides CSRF protection for cookie-based authentication.
Requests using Authorization header (Bearer tokens) are exempt since
header-based auth is inherently CSRF-safe.
"""

import secrets
import hashlib
import time
from typing import Optional, Set
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# HTTP methods that require CSRF protection
UNSAFE_METHODS: Set[str] = {"POST", "PUT", "DELETE", "PATCH"}

# Paths exempt from CSRF protection (e.g., login, public APIs)
CSRF_EXEMPT_PATHS: Set[str] = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/captcha",
    "/api/auth/csrf-token",
    "/api/auth/password-reset",
    "/api/auth/password-reset/otp/request",
    "/api/auth/password-reset/otp/verify",
    "/api/auth/password-reset/otp/reset",
    "/api/auth/totp/status",
    "/health",
    "/api/health",
}

# Cookie settings
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_TOKEN_LENGTH = 32
CSRF_COOKIE_MAX_AGE = 3600  # 1 hour


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token"""
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


def hash_token(token: str) -> str:
    """Hash the token for comparison (constant-time safe)"""
    return hashlib.sha256(token.encode()).hexdigest()


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF Protection Middleware

    Protects against Cross-Site Request Forgery attacks by:
    1. Setting a CSRF token cookie on responses
    2. Validating CSRF token header on state-changing requests
    3. Allowing bypass for Authorization header-based requests

    Usage:
        app.add_middleware(CSRFProtectionMiddleware, redis_client=redis)
    """

    def __init__(self, app, redis_client=None, enabled: bool = True):
        super().__init__(app)
        self.redis = redis_client
        self.enabled = enabled

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip for safe methods (GET, HEAD, OPTIONS)
        if request.method not in UNSAFE_METHODS:
            response = await call_next(request)
            # Set CSRF token cookie on safe requests if not present
            if not request.cookies.get(CSRF_COOKIE_NAME):
                self._set_csrf_cookie(response)
            return response

        # Skip for exempt paths
        path = request.url.path.rstrip("/")
        if path in CSRF_EXEMPT_PATHS or any(path.startswith(p) for p in CSRF_EXEMPT_PATHS):
            return await call_next(request)

        # Skip CSRF check if using Authorization header (header-based auth is CSRF-safe)
        if request.headers.get("Authorization"):
            return await call_next(request)

        # For cookie-based auth, validate CSRF token
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)

        # If no cookie-based auth (no access_token cookie), skip CSRF
        if not request.cookies.get("access_token"):
            return await call_next(request)

        # Validate CSRF token
        if not self._validate_csrf_token(cookie_token, header_token):
            logger.warning(
                f"CSRF validation failed: path={path}, "
                f"has_cookie={bool(cookie_token)}, has_header={bool(header_token)}"
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF 토큰이 유효하지 않습니다. 페이지를 새로고침해주세요."}
            )

        return await call_next(request)

    def _validate_csrf_token(
        self, cookie_token: Optional[str], header_token: Optional[str]
    ) -> bool:
        """
        Validate CSRF token using double-submit cookie pattern.

        The header token must match the cookie token.
        Uses constant-time comparison to prevent timing attacks.
        """
        if not cookie_token or not header_token:
            return False

        # Use secrets.compare_digest for constant-time comparison
        return secrets.compare_digest(cookie_token, header_token)

    def _set_csrf_cookie(self, response: Response) -> None:
        """Set CSRF token cookie on response"""
        token = generate_csrf_token()
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=token,
            max_age=CSRF_COOKIE_MAX_AGE,
            httponly=False,  # Must be readable by JavaScript
            samesite="strict",
            secure=True,  # Only send over HTTPS
        )


def get_csrf_token_endpoint():
    """
    Endpoint to get a new CSRF token.

    Returns the current CSRF token from cookie or generates a new one.
    Frontend should call this and include the token in X-CSRF-Token header.
    """
    async def csrf_token(request: Request, response: Response):
        token = request.cookies.get(CSRF_COOKIE_NAME)
        if not token:
            token = generate_csrf_token()
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=token,
                max_age=CSRF_COOKIE_MAX_AGE,
                httponly=False,
                samesite="strict",
                secure=True,
            )
        return {"csrf_token": token}

    return csrf_token
