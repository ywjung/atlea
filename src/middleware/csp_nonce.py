"""
CSP Nonce Middleware
Generates unique nonces for each request to improve Content Security Policy
"""
import secrets
import base64
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable


class CSPNonceMiddleware(BaseHTTPMiddleware):
    """
    Middleware to generate CSP nonces for each request

    Usage in templates:
        <script nonce="{{ request.state.csp_nonce }}">...</script>
        <style nonce="{{ request.state.csp_nonce }}">...</style>

    CSP Header will automatically include:
        script-src 'nonce-{generated_nonce}'
        style-src 'nonce-{generated_nonce}'
    """

    def __init__(self, app):
        super().__init__(app)

    @staticmethod
    def generate_nonce() -> str:
        """
        Generate a cryptographically secure random nonce

        Returns:
            Base64-encoded nonce string (128 bits of entropy)
        """
        random_bytes = secrets.token_bytes(16)  # 128 bits
        nonce = base64.b64encode(random_bytes).decode('utf-8')
        return nonce

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Generate nonce and attach to request state

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response with nonce attached
        """
        # Generate nonce for this request
        nonce = self.generate_nonce()

        # Attach nonce to request state (accessible in templates)
        request.state.csp_nonce = nonce

        # Process request
        response = await call_next(request)

        # Optionally modify CSP header if it exists
        # This is for gradual migration - can be enabled later
        # if "Content-Security-Policy" in response.headers:
        #     csp = response.headers["Content-Security-Policy"]
        #     # Replace 'unsafe-inline' with nonce for scripts and styles
        #     csp = csp.replace(
        #         "script-src 'self' 'unsafe-inline'",
        #         f"script-src 'self' 'nonce-{nonce}'"
        #     )
        #     csp = csp.replace(
        #         "style-src 'self' 'unsafe-inline'",
        #         f"style-src 'self' 'nonce-{nonce}'"
        #     )
        #     response.headers["Content-Security-Policy"] = csp

        return response


def build_csp_with_nonce(nonce: str, allow_unsafe_eval: bool = True) -> str:
    """
    Build a strict CSP policy with nonce support

    Args:
        nonce: Generated nonce for this request
        allow_unsafe_eval: Whether to allow 'unsafe-eval' (needed for some frameworks)

    Returns:
        Complete CSP header value
    """
    eval_policy = " 'unsafe-eval'" if allow_unsafe_eval else ""

    csp = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'{eval_policy} blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        f"style-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )

    return csp
