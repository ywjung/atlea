"""
Web Server - FastAPI application

Modularized version with routers and startup logic extracted.
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger
from dotenv import load_dotenv
from starlette.types import Scope, Receive, Send
from starlette.middleware.base import BaseHTTPMiddleware

from .config import config
from .middleware import RateLimitMiddleware, AuditMiddleware, CSRFProtectionMiddleware
from .middleware.csp_nonce import CSPNonceMiddleware
from .middleware.exception_handlers import register_exception_handlers

# Import all routers
from .routers import (
    auth, admin, organizations, documents, cache, conversations,
    feedback, settings, groups, audit, models, prompts, query,
    db_backup, questions, tts, security, persona
)
from .routers import metrics as metrics_router
from .routers import static_files, validation, system, search, conversion, websocket_alerts

# Import startup logic
from . import startup

# Load environment variables
load_dotenv()

# Setup production configuration
config.setup_logging()

# Validate configuration
if not config.validate():
    logger.error("Configuration validation failed. Exiting...")
    sys.exit(1)

# Print configuration (for debugging)
if config.DEBUG:
    config.print_config()


# ==================== Custom StaticFiles with Caching ====================

class CachedStaticFiles(StaticFiles):
    """StaticFiles with environment-aware browser caching"""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Wrap the send function to add cache headers
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                path = scope.get("path", "")

                # Development: No caching (always fetch fresh files)
                if config.ENV == "development":
                    headers.append((b"cache-control", b"no-cache, no-store, must-revalidate"))
                    headers.append((b"pragma", b"no-cache"))
                    headers.append((b"expires", b"0"))
                # Production: Aggressive caching
                else:
                    if path.endswith(".html"):
                        # Short cache for HTML (allow quick updates)
                        headers.append((b"cache-control", b"public, max-age=3600"))
                    else:
                        # Long cache for CSS, JS, images (use versioning for updates)
                        headers.append((b"cache-control", b"public, max-age=31536000, immutable"))

                message["headers"] = headers
            await send(message)

        await super().__call__(scope, receive, send_wrapper)


# ==================== API Tags for Documentation ====================

tags_metadata = [
    {"name": "Authentication", "description": "사용자 인증 및 계정 관리 API"},
    {"name": "Query", "description": "문서 검색 및 질의응답 API"},
    {"name": "Documents", "description": "문서 업로드, 삭제, 조회 및 관리 API"},
    {"name": "Groups", "description": "문서 그룹 생성 및 관리 API"},
    {"name": "Cache", "description": "캐시 통계 및 관리 API"},
    {"name": "Conversations", "description": "대화 세션 관리 API"},
    {"name": "Settings", "description": "모델 변경 및 시스템 설정 API"},
    {"name": "Admin", "description": "관리자 전용 API (보안 로그 등)"},
    {"name": "System", "description": "시스템 상태 및 모니터링 API"},
    {"name": "Search", "description": "독립 검색 API (Tavily, Context7)"},
    {"name": "Conversion", "description": "문서 변환 API"},
    {"name": "Quality", "description": "응답 품질 검증 통계 API"},
    {"name": "Static", "description": "정적 파일 제공 API"}
]


# ==================== Initialize FastAPI ====================

app = FastAPI(
    title="ATLEA",
    description="ATLEA (Advanced Trusted Learning & Enterprise Assistant)",
    version="2.2.0",
    openapi_tags=tags_metadata,
    debug=config.DEBUG,
    docs_url="/docs" if config.DEBUG else None,  # Disable docs in production
    redoc_url="/redoc" if config.DEBUG else None
)

# Register exception handlers
register_exception_handlers(app)


# ==================== Security Headers Middleware ====================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS filter in browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict feature permissions (allow microphone for voice input)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=()"

        # Relaxed CSP for API documentation pages
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://cdn.jsdelivr.net https://unpkg.com; "
                "connect-src 'self'; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'none';"
            )
        else:
            # Strict CSP for main application
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data:; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "media-src 'self' blob:; "
                "connect-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com wss: ws:; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'none'; "
                "report-uri /api/security/csp-report;"
            )

        # HSTS for HTTPS connections
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response


# ==================== Add Middleware ====================

# CORS middleware (must be first for proper header handling)
cors_origins = ["*"] if config.ENV == "development" else config.CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",      # JWT tokens
        "Content-Type",       # JSON requests
        "Accept",            # Content negotiation
        "Accept-Language",   # Localization
        "X-Request-ID",      # Request tracing
        "X-CSRF-Token"       # CSRF protection
    ],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
)

logger.info(f"🌐 CORS configured: {cors_origins} (ENV: {config.ENV})")

# CSRF protection middleware
app.add_middleware(CSRFProtectionMiddleware, enabled=True)

# Rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    rate=config.RATE_LIMIT_PER_MINUTE,
    burst=config.RATE_LIMIT_BURST,
    enabled=config.RATE_LIMIT_ENABLED
)

# Audit logging middleware
app.add_middleware(AuditMiddleware)

# CSP Nonce middleware
app.add_middleware(CSPNonceMiddleware)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# GZip compression middleware
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,  # Only compress responses larger than 1KB
    compresslevel=6     # Balance between speed and compression ratio
)


# ==================== Mount Static Files ====================

static_path = Path(__file__).parent.parent / "static"
app.mount("/static", CachedStaticFiles(directory=str(static_path)), name="static")


# ==================== Favicon Routes ====================

@app.get("/favicon.svg")
async def favicon_svg():
    """Serve favicon.svg from static directory"""
    favicon_path = static_path / "favicon.svg"
    return FileResponse(favicon_path, media_type="image/svg+xml")


@app.get("/favicon.ico")
async def favicon_ico():
    """Redirect favicon.ico requests to favicon.svg"""
    favicon_path = static_path / "favicon.svg"
    return FileResponse(favicon_path, media_type="image/svg+xml")


# ==================== Register Routers ====================

# Static files and HTML serving
app.include_router(static_files.router)

# Authentication and admin
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(organizations.router)

# Core functionality
app.include_router(documents.router)
app.include_router(cache.router)
app.include_router(conversations.router)
app.include_router(feedback.router)
app.include_router(settings.router)
app.include_router(groups.router)
app.include_router(audit.router)
app.include_router(models.router)
app.include_router(metrics_router.router)
app.include_router(prompts.router)
app.include_router(persona.router)
app.include_router(query.router)
app.include_router(db_backup.router)
app.include_router(questions.router)
app.include_router(tts.router)
app.include_router(security.router)

# New modularized routers
app.include_router(validation.router)
app.include_router(system.router)
app.include_router(search.router)
app.include_router(conversion.router)
app.include_router(websocket_alerts.router)

logger.info("✅ All routers registered")


# ==================== Startup and Shutdown Events ====================

@app.on_event("startup")
async def on_startup():
    """Application startup - delegate to startup module"""
    await startup.startup_event(app)


@app.on_event("shutdown")
async def on_shutdown():
    """Application shutdown - delegate to startup module"""
    await startup.shutdown_event()


# ==================== Main Entry Point ====================

if __name__ == "__main__":
    import uvicorn
    import multiprocessing

    # Production configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    environment = os.getenv("ENVIRONMENT", "production")

    # Configure logging for production
    if environment == "production":
        # Remove default logger and configure for production
        logger.remove()

        # Add structured logging with rotation
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="INFO",
            colorize=False
        )

        # Add file logging with rotation
        os.makedirs("logs", exist_ok=True)
        log_file = os.getenv("LOG_FILE", "logs/server.log")
        logger.add(
            log_file,
            rotation="100 MB",
            retention="7 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO"
        )

        logger.info("Production logging configured")
    else:
        # Development: keep colorful logging to console AND add file logging
        os.makedirs("logs", exist_ok=True)
        log_file = os.getenv("LOG_FILE", "logs/server.log")
        logger.add(
            log_file,
            rotation="10 MB",
            retention="3 days",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG"
        )
        logger.info(f"Development logging active with file: {log_file}")

    # Worker configuration
    cpu_count = multiprocessing.cpu_count()
    if environment == "development":
        workers = 1  # Single worker for easier debugging
    else:
        workers = max(4, min(8, (cpu_count * 2) + 1))

    # Timeout settings
    timeout_keep_alive = int(os.getenv("TIMEOUT_KEEP_ALIVE", 65))
    timeout_graceful_shutdown = int(os.getenv("TIMEOUT_GRACEFUL_SHUTDOWN", 30))

    # Connection limits
    limit_concurrency = int(os.getenv("LIMIT_CONCURRENCY", 1000))
    limit_max_requests = int(os.getenv("LIMIT_MAX_REQUESTS", 10000))

    # Logging configuration
    log_level = os.getenv("LOG_LEVEL", "info" if environment == "production" else "debug").lower()
    access_log = os.getenv("ACCESS_LOG", "false").lower() == "true"

    logger.info(f"🚀 Starting server in {environment.upper()} mode")
    logger.info(f"📍 Server: http://{host}:{port}")
    logger.info(f"👥 Workers: {workers} (CPU cores: {cpu_count})")
    logger.info(f"⏱️  Timeouts: keep-alive={timeout_keep_alive}s, graceful-shutdown={timeout_graceful_shutdown}s")
    logger.info(f"🔗 Limits: concurrency={limit_concurrency}, max-requests={limit_max_requests}")

    uvicorn.run(
        "src.web_server:app",
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
        access_log=access_log,
        timeout_keep_alive=timeout_keep_alive,
        timeout_graceful_shutdown=timeout_graceful_shutdown,
        limit_concurrency=limit_concurrency,
        limit_max_requests=limit_max_requests,
        # Production optimizations
        backlog=2048,
        use_colors=False if environment == "production" else True,
        server_header=False,
        date_header=True,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )
