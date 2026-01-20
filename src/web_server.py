"""
Web Server - FastAPI application
"""

import os
import sys
import json
import shutil
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, validator
from loguru import logger
from dotenv import load_dotenv
from starlette.types import Scope, Receive, Send
from starlette.exceptions import HTTPException as StarletteHTTPException

from .embeddings import EmbeddingModel
from .document_processor import DocumentProcessor
from .vector_db import VectorDB
from .llm import LLM, RAGSystem
from .document_tracker import DocumentTracker
from .document_version import DocumentVersion
from .cache_manager import CacheManager
from .model_manager import ModelManager
from .group_manager import GroupManager
from .conversation_manager import ConversationManager
from .response_validator import response_validator
from .confidence_scorer import confidence_scorer
from .feedback_analyzer import feedback_analyzer
from .hybrid_rag import HybridRAGOrchestrator
from .metrics_collector import MetricsCollector
from .config import config
from .config.prompts import (
    PROMPT_KEY_BASIC,
    PROMPT_KEY_HYBRID,
    PROMPT_KEY_TOOLS_ONLY,
    PROMPT_KEY_LEGACY,
    DEFAULT_BASIC_PROMPT,
    DEFAULT_HYBRID_PROMPT,
    DEFAULT_TOOLS_ONLY_PROMPT,
    get_system_prompt_for_mode
)
from .utils.validation import validate_filename, validate_file_content
from .utils.error_handling import get_safe_error_message
from .middleware import RateLimitMiddleware, AuditMiddleware, CSRFProtectionMiddleware, get_csrf_token_endpoint
from .middleware.csp_nonce import CSPNonceMiddleware
from .audit import AuditLogger, AuditAction
from .exceptions import (
    ChatbotException,
    DocumentProcessingError,
    VectorDBError,
    LLMError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    ResourceNotFoundError,
    RateLimitExceededError
)

# v2.2.0: Authentication router
from .routers import auth, admin, organizations, documents, cache, conversations, feedback, settings, groups, audit, models, prompts, query, redis_backup, questions
from .routers import metrics as metrics_router
from .auth.middleware import get_current_active_user, require_admin
from .middleware.exception_handlers import register_exception_handlers
from .services import question_generation, scheduler_service, reindex_service

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


# Custom StaticFiles with caching headers
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


# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nlpai-lab/KURE-v1")
LLM_MODEL = os.getenv("LLM_MODEL", "mlx-community/Qwen3-30B-A3B-4bit")
MODEL_DIR = os.getenv("MODEL_DIR", "./model")
DATA_DIR = os.getenv("DATA_DIR", "./data")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 512))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 50))
# Performance optimization: disable slow startup tasks
ENABLE_QUESTION_GENERATION = os.getenv("ENABLE_QUESTION_GENERATION", "false").lower() == "true"
# File upload size limit (in MB)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 100))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024  # Convert to bytes
# API Tags for documentation organization
tags_metadata = [
    {
        "name": "Authentication",
        "description": "사용자 인증 및 계정 관리 API"
    },
    {
        "name": "Query",
        "description": "문서 검색 및 질의응답 API"
    },
    {
        "name": "Documents",
        "description": "문서 업로드, 삭제, 조회 및 관리 API"
    },
    {
        "name": "Groups",
        "description": "문서 그룹 생성 및 관리 API"
    },
    {
        "name": "Cache",
        "description": "캐시 통계 및 관리 API"
    },
    {
        "name": "Conversations",
        "description": "대화 세션 관리 API"
    },
    {
        "name": "Settings",
        "description": "모델 변경 및 시스템 설정 API"
    },
    {
        "name": "Admin",
        "description": "관리자 전용 API (보안 로그 등)"
    },
    {
        "name": "System",
        "description": "시스템 상태 및 모니터링 API"
    }
]

# Initialize FastAPI
app = FastAPI(
    title="PDF RAG Chatbot",
    description="PDF 문서 기반 질의응답 챗봇",
    version="2.1.0",
    openapi_tags=tags_metadata,
    debug=config.DEBUG,
    docs_url="/docs" if config.DEBUG else None,  # Disable docs in production
    redoc_url="/redoc" if config.DEBUG else None
)

# Register exception handlers (Phase 2: Modularization)
register_exception_handlers(app)

# Security Headers Middleware
from starlette.middleware.base import BaseHTTPMiddleware

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

        # Restrict feature permissions
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Relaxed CSP for API documentation pages (/docs, /redoc, /openapi.json)
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
            # Stricter CSP for main application (removed unsafe-eval for security)
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data:; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "connect-src 'self' https://cdn.jsdelivr.net wss: ws:; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'none';"
            )

        # HSTS for HTTPS connections (enabled for production security)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response


# Add CORS middleware (must be first for proper header handling)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # Restrict allowed headers to only what's needed (security best practice)
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

# Add CSRF protection middleware (protects cookie-based auth from CSRF attacks)
# Requests with Authorization header are exempt (header-based auth is CSRF-safe)
app.add_middleware(CSRFProtectionMiddleware, enabled=True)

# Add rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    rate=config.RATE_LIMIT_PER_MINUTE,
    burst=config.RATE_LIMIT_BURST,
    enabled=config.RATE_LIMIT_ENABLED
)

# Add audit logging middleware (will use app.state.audit_logger after startup)
app.add_middleware(AuditMiddleware)

# Add CSP Nonce middleware (generates nonce for each request)
app.add_middleware(CSPNonceMiddleware)

# Add security headers middleware (must be before GZip to affect all responses)
app.add_middleware(SecurityHeadersMiddleware)

# Add GZip compression middleware for response compression (60-80% size reduction)
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,  # Only compress responses larger than 1KB
    compresslevel=6     # Balance between speed and compression ratio (1-9)
)

# Mount static files with caching headers
static_path = Path(__file__).parent.parent / "static"
app.mount("/static", CachedStaticFiles(directory=str(static_path)), name="static")

# Favicon routes for browsers
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

# v2.2.0: Register authentication router
app.include_router(auth.router)

# Register admin router
app.include_router(admin.router)

# Register organizations router
app.include_router(organizations.router)

# Register documents router (Phase 1: Modularization - 19 endpoints)
app.include_router(documents.router)

# Register cache router (Phase 1: Modularization - 4 endpoints)
app.include_router(cache.router)

# Register conversations router (Phase 1: Modularization - 7 endpoints)
app.include_router(conversations.router)

# Register feedback router (Phase 1: Modularization - 5 endpoints)
app.include_router(feedback.router)

# Register settings router (Phase 1: Modularization - 5 endpoints)
app.include_router(settings.router)

# Register groups router (Phase 1: Modularization - 9 endpoints)
app.include_router(groups.router)

# Register audit router (Phase 1: Modularization - 4 endpoints)
app.include_router(audit.router)

# Register models router (Phase 1: Modularization - 3 endpoints)
app.include_router(models.router)

# Register metrics router (Phase 1: Modularization - 4 endpoints)
app.include_router(metrics_router.router)

# Register prompts router (Phase 1: Modularization - 4 endpoints)
app.include_router(prompts.router)

# Register query router (Phase 1: Modularization - 3 endpoints)
app.include_router(query.router)

# Register redis_backup router (Phase 2: Modularization - 7 endpoints)
app.include_router(redis_backup.router)

# Register questions router (Phase 3: Modularization - 1 endpoint)
app.include_router(questions.router)


# WebSocket endpoint for real-time security alerts
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    실시간 보안 알림을 위한 WebSocket 엔드포인트
    관리자만 접근 가능 (토큰 기반 인증)
    """
    from .auth.alert_system import alert_manager

    try:
        # WebSocket 연결 수락
        await alert_manager.connect(websocket)

        # 연결 유지 및 메시지 수신
        while True:
            try:
                # 클라이언트로부터 메시지 수신 (ping/pong)
                data = await websocket.receive_text()

                # ping 메시지에 대한 pong 응답
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                # 통계 요청
                elif data == "get_stats":
                    await alert_manager.send_stats()

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        # 연결 해제
        await alert_manager.disconnect(websocket)


# Global instances (initialized on startup)
embedding_model: Optional[EmbeddingModel] = None
vector_db: Optional[VectorDB] = None
llm: Optional[LLM] = None
rag_system: Optional[RAGSystem] = None
cache_manager: Optional[CacheManager] = None
conversation_manager: Optional[ConversationManager] = None
document_version: Optional[DocumentVersion] = None  # v2.3.0: Document version management
audit_logger: Optional[AuditLogger] = None  # v2.4.0: Audit logging
# suggested_questions_pool moved to question_generation service (Phase 3.1: Modularization)
# reindex_event moved to reindex_service (Phase 3.3: Modularization)

# Status endpoint cache (to avoid rescanning on every request)
status_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 5  # Cache for 5 seconds
}

# Request/Response models
class LLMChangeRequest(BaseModel):
    llm_model: str


class EmbeddingChangeRequest(BaseModel):
    embedding_model: str


class CacheEnabledRequest(BaseModel):
    enabled: bool



# 🆕 독립 검색 API 모델 (Tavily, Context7)
class WebSearchRequest(BaseModel):
    """Tavily 웹 검색 요청"""
    query: str = Field(..., description="검색 쿼리", example="latest AI developments 2026")
    max_results: int = Field(5, description="최대 결과 수", ge=1, le=20)
    search_depth: str = Field("basic", description="검색 깊이 (basic 또는 advanced)")
    include_domains: Optional[List[str]] = Field(None, description="포함할 도메인 목록 (예: ['github.com', 'stackoverflow.com'])", example=None)
    exclude_domains: Optional[List[str]] = Field(None, description="제외할 도메인 목록 (예: ['wikipedia.org'])", example=None)


class WebSearchResponse(BaseModel):
    """Tavily 웹 검색 응답"""
    success: bool
    results: List[dict]
    query: str
    search_depth: str


class DocsSearchRequest(BaseModel):
    """Context7 공식 문서 검색 요청"""
    query: str
    tech_stack: Optional[str] = None  # 'react', 'vue', 'spring-boot' 등
    max_results: int = 3


class DocsSearchResponse(BaseModel):
    """Context7 공식 문서 검색 응답"""
    success: bool
    results: List[dict]
    query: str
    tech_stack: Optional[str] = None


class HwpxConversionRequest(BaseModel):
    """HWPX 변환 요청"""
    content: str = Field(..., description="변환할 HTML 또는 Markdown 내용")
    content_type: str = Field(default="html", description="내용 타입: 'html' 또는 'markdown'")
    filename: Optional[str] = Field(default=None, description="출력 파일명 (선택사항)")


# Lazy loading functions for LLM (only load when needed)
async def get_llm() -> LLM:
    """Get LLM instance, loading it lazily on first use"""
    global llm
    if llm is None:
        logger.info("⚡ Loading LLM on first use (lazy loading)...")
        # Check if we're using Ollama backend
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            # For Ollama, don't pass model_name - let it read from OLLAMA_LLM_MODEL env var
            llm = LLM(
                model_dir=MODEL_DIR
            )
        else:
            # For local LLM (MLX/Transformers), pass the model name
            llm = LLM(
                model_name=LLM_MODEL,
                model_dir=MODEL_DIR
            )
        logger.success("✅ LLM loaded successfully!")
    return llm


async def get_rag_system() -> RAGSystem:
    """Get RAG system instance, initializing it lazily on first use"""
    global rag_system
    if rag_system is None:
        logger.info("⚡ Initializing RAG system on first use...")
        llm_instance = await get_llm()
        rag_system = RAGSystem(
            vector_db=vector_db,
            llm=llm_instance,
            top_k=5
        )
        logger.success("✅ RAG system ready!")
    return rag_system


async def get_hybrid_rag_orchestrator():
    """Get Hybrid RAG orchestrator instance, initializing it lazily based on Redis config"""
    global hybrid_rag_orchestrator

    # Check Redis configuration
    hybrid_rag_enabled = cache_manager.redis.get("config:hybrid_rag_enabled")
    web_search_enabled = cache_manager.redis.get("config:hybrid_rag_web_search")
    doc_search_enabled = cache_manager.redis.get("config:hybrid_rag_doc_search")
    web_search_provider_raw = cache_manager.redis.get("config:web_search_provider")

    # Decode Redis values (they're stored as bytes)
    is_enabled = hybrid_rag_enabled and hybrid_rag_enabled.decode() == "true"
    enable_web = web_search_enabled and web_search_enabled.decode() == "true"
    enable_docs = doc_search_enabled and doc_search_enabled.decode() == "true"
    web_search_provider = web_search_provider_raw.decode() if web_search_provider_raw else 'tavily'

    if not is_enabled:
        return None  # Hybrid RAG disabled

    # Check if config has changed and needs reinitialization
    needs_reinit = False
    if hybrid_rag_orchestrator is not None:
        current_provider = getattr(hybrid_rag_orchestrator, 'web_search_provider', 'tavily')
        current_web_enabled = getattr(hybrid_rag_orchestrator, 'web_search_enabled', False)
        current_doc_enabled = getattr(hybrid_rag_orchestrator, 'doc_search_enabled', False)

        if (current_provider != web_search_provider or
            current_web_enabled != enable_web or
            current_doc_enabled != enable_docs):
            logger.info(f"🔄 Config changed: provider={current_provider}→{web_search_provider}, "
                       f"web={current_web_enabled}→{enable_web}, docs={current_doc_enabled}→{enable_docs}")
            needs_reinit = True

    # Initialize if not already created or if config changed
    if hybrid_rag_orchestrator is None or needs_reinit:
        logger.info("⚡ Initializing Hybrid RAG orchestrator...")
        rag_instance = await get_rag_system()
        hybrid_rag_orchestrator = HybridRAGOrchestrator(
            local_rag=rag_instance,
            cache_manager=cache_manager,
            enable_web_search=enable_web,
            enable_doc_search=enable_docs,
            web_search_provider=web_search_provider
        )
        logger.success(f"✅ Hybrid RAG ready! (Web: {enable_web}, Provider: {web_search_provider}, Docs: {enable_docs})")

    return hybrid_rag_orchestrator


async def create_default_admin(redis_client):
    """Create default admin user if no admin exists"""
    from .auth.service import AuthService
    from .auth.models import UserCreate

    try:
        auth_service = AuthService(redis_client)

        # Check if any admin exists
        users_result = await auth_service.get_all_users(page=1, page_size=1000)
        admin_exists = any(u.get('role') == 'admin' for u in users_result['users'])

        if not admin_exists:
            # Default admin credentials
            default_email = "admin@admin.com"
            default_password = "Admin123!@#"  # Strong default password
            default_username = "관리자"

            # Check if user already exists
            existing_user_id = redis_client.get(f"user:email:{default_email}")

            if existing_user_id:
                # User exists, just upgrade to admin
                user_id = existing_user_id.decode() if isinstance(existing_user_id, bytes) else existing_user_id
                redis_client.hset(f"user:{user_id}", "role", "admin")
                logger.info(f"✅ Upgraded existing user {default_email} to admin")
            else:
                # Create new admin user
                user_data = UserCreate(
                    email=default_email,
                    username=default_username,
                    password=default_password
                )
                user = await auth_service.create_user(user_data)

                # Set as admin
                redis_client.hset(f"user:{user.user_id}", "role", "admin")

                logger.success(f"✅ Created default admin user: {default_email}")
                logger.info(f"   Username: {default_username}")
                logger.info(f"   Password: {default_password}")
                logger.warning("⚠️  Please change the default admin password after first login!")
        else:
            logger.info("ℹ️  Admin user already exists, skipping default admin creation")

    except Exception as e:
        logger.warning(f"⚠️  Failed to create default admin: {e}")
        # Don't fail startup if admin creation fails


# ==================== Scheduler Tasks ====================
# Scheduler tasks moved to scheduler_service (Phase 3: Modularization)
backup_scheduler_task = None
audit_cleanup_scheduler_task = None

@app.on_event("startup")
async def startup_event():
    """Initialize models and database on startup (fast startup with lazy loading)"""
    global embedding_model, vector_db, cache_manager, group_manager, conversation_manager, document_version, audit_logger, backup_scheduler_task, audit_cleanup_scheduler_task, hybrid_rag_orchestrator

    # Configure file logging (development mode) - only once
    environment = os.getenv("ENVIRONMENT", "development")
    if environment != "production":
        log_file = os.getenv("LOG_FILE", "server.log")
        try:
            logger.add(
                log_file,
                rotation="10 MB",
                retention="3 days",
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                level="DEBUG",
                colorize=False  # Disable color codes for clean parsing
            )
            logger.info(f"📝 File logging enabled: {log_file}")
        except Exception as e:
            # Handler might already exist on reload, that's OK
            pass

    try:
        logger.info("🚀 Starting application initialization (fast mode)...")

        # Initialize reindex service (Phase 3.3: Modularization)
        logger.info("🔄 Injecting dependencies into reindex_service...")
        reindex_service.inject_dependencies(vector_db_instance=vector_db)
        reindex_service.initialize_reindex_event()
        logger.info("✅ Reindex service initialized")

        # Initialize embedding model (required for search)
        logger.info("📚 Loading embedding model...")
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            # For Ollama, don't pass model_name - let it read from OLLAMA_EMBEDDING_MODEL env var
            embedding_model = EmbeddingModel(
                model_dir=MODEL_DIR
            )
        else:
            # For local embedding model
            embedding_model = EmbeddingModel(
                model_name=EMBEDDING_MODEL,
                model_dir=MODEL_DIR
            )

        # Initialize vector database with production-ready Redis configuration
        logger.info("🔌 Connecting to Redis...")

        # Production Redis configuration
        redis_max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", 50))
        redis_socket_timeout = int(os.getenv("REDIS_SOCKET_TIMEOUT", 5))
        redis_socket_keepalive = os.getenv("REDIS_SOCKET_KEEPALIVE", "true").lower() == "true"

        vector_db = VectorDB(
            host=REDIS_HOST,
            port=REDIS_PORT,
            embedding_dim=embedding_model.get_embedding_dim(),
            # Production Redis connection pool settings
            max_connections=redis_max_connections,
            socket_timeout=redis_socket_timeout,
            socket_keepalive=redis_socket_keepalive,
            socket_keepalive_options={},
            health_check_interval=30  # Check connection health every 30s
        )

        logger.info(f"Redis configured: max_connections={redis_max_connections}, timeout={redis_socket_timeout}s")

        # Clean up stale reindexing state from previous abnormal shutdown (Phase 3.3: Using reindex_service)
        reindex_service.cleanup_stale_reindex_state()

        # Set rate limit configuration in Redis from environment variable
        try:
            rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "false").lower()
            vector_db.client.set("config:rate_limit_enabled", rate_limit_enabled)
            logger.info(f"⚙️  Rate limiting: {rate_limit_enabled}")
        except Exception as e:
            logger.warning(f"Failed to set rate limit config in Redis: {e}")

        # Initialize cache manager with production settings
        logger.info("💾 Initializing cache manager...")

        # Production cache configuration
        cache_similarity_threshold = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", 0.90))  # Lowered from 0.95 to 0.90
        cache_ttl = int(os.getenv("CACHE_TTL", 3600))  # Default 1 hour
        memory_cache_size = int(os.getenv("MEMORY_CACHE_SIZE", 200))  # Increased from 50 to 200 for better hit rate

        cache_manager = CacheManager(
            redis_client=vector_db.client,
            embedding_model=embedding_model.model,
            similarity_threshold=cache_similarity_threshold,
            cache_ttl=cache_ttl,
            memory_cache_size=memory_cache_size
        )

        logger.info(f"Cache configured: similarity={cache_similarity_threshold}, TTL={cache_ttl}s")

        # Store cache_manager in app state for v2.2.0 auth system access
        app.state.cache_manager = cache_manager
        logger.info(f"✅ Stored cache_manager in app.state (redis client: {cache_manager.redis is not None})")

        # Initialize SecurityLogger with Redis for webhook support
        from src.auth.security_logger import SecurityLogger
        SecurityLogger.set_redis(cache_manager.redis)
        logger.info("✅ SecurityLogger initialized with Redis (webhook support enabled)")

        # Inject Redis into FeedbackAnalyzer for persistence
        feedback_analyzer.redis = cache_manager.redis
        feedback_analyzer._load_from_redis()
        logger.info(f"✅ FeedbackAnalyzer initialized with Redis persistence (loaded {len(feedback_analyzer.feedback_history)} feedbacks)")

        # Initialize audit logger (v2.4.0)
        audit_logger = AuditLogger(
            redis_client=cache_manager.redis,
            retention_days=90  # 90일 보관
        )
        app.state.audit_logger = audit_logger
        logger.info("✅ AuditLogger initialized (retention=90 days)")

        # Create default admin user if no admin exists
        await create_default_admin(cache_manager.redis)

        # Initialize group manager
        logger.info("📁 Initializing group manager...")
        group_manager = GroupManager(redis_client=vector_db.client)

        # Initialize conversation manager
        logger.info("💬 Initializing conversation manager...")
        conversation_manager = ConversationManager(redis_client=vector_db.client)

        # v2.3.0: Initialize document version manager
        logger.info("📋 Initializing document version manager...")
        max_versions = int(os.getenv("DOCUMENT_MAX_VERSIONS", 10))
        document_version = DocumentVersion(
            redis_client=vector_db.client,
            data_dir=DATA_DIR,
            max_versions=max_versions
        )
        logger.info(f"Document version manager configured: max_versions={max_versions}")

        # Inject dependencies into documents router (18 endpoints)
        logger.info("📄 Injecting dependencies into documents router...")
        documents.inject_dependencies(
            vdb=vector_db,
            doc_processor=None,  # DocumentProcessor is created per-request, not global
            doc_version=document_version,
            grp_manager=group_manager,
            cache_mgr=cache_manager,
            emb_model=embedding_model,
            data_dir=DATA_DIR,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            max_file_size=MAX_FILE_SIZE,
            max_file_size_mb=MAX_FILE_SIZE_MB,
            reindex_evt=reindex_service.get_reindex_event()  # Phase 3.3: From reindex_service
        )
        logger.info("✅ Documents router dependencies injected (19 endpoints)")

        # Inject dependencies into cache router (4 endpoints)
        logger.info("💾 Injecting dependencies into cache router...")
        cache.inject_dependencies(
            cache_mgr=cache_manager,
            redis=vector_db.client
        )
        logger.info("✅ Cache router dependencies injected (4 endpoints)")

        # Inject dependencies into conversations router (7 endpoints)
        logger.info("💬 Injecting dependencies into conversations router...")
        conversations.inject_dependencies(
            conv_manager=conversation_manager
        )
        logger.info("✅ Conversations router dependencies injected (7 endpoints)")

        # Inject dependencies into feedback router (5 endpoints)
        logger.info("👍 Injecting dependencies into feedback router...")
        feedback.inject_dependencies(
            fb_analyzer=feedback_analyzer,
            conv_manager=conversation_manager,
            cache_mgr=cache_manager
        )
        logger.info("✅ Feedback router dependencies injected (5 endpoints)")

        # Inject dependencies into settings router (5 endpoints)
        logger.info("⚙️ Injecting dependencies into settings router...")
        settings.inject_dependencies(
            cache_mgr=cache_manager
        )
        logger.info("✅ Settings router dependencies injected (5 endpoints)")

        # Inject dependencies into groups router (9 endpoints)
        logger.info("📁 Injecting dependencies into groups router...")
        groups.inject_dependencies(
            grp_manager=group_manager
        )
        logger.info("✅ Groups router dependencies injected (9 endpoints)")

        # Inject dependencies into audit router (4 endpoints)
        logger.info("📋 Injecting dependencies into audit router...")
        audit.inject_dependencies(
            audit_log=audit_logger,
            cache_mgr=cache_manager
        )
        logger.info("✅ Audit router dependencies injected (4 endpoints)")

        # Define model reload callback for models router
        def model_reload_callback(backend: str, llm_model: str = None, embedding_model_name: str = None):
            """Callback to reload models when configuration changes"""
            global llm, rag_system, embedding_model, vector_db, LLM_MODEL, EMBEDDING_MODEL

            llm_changed = False
            embedding_changed = False
            use_ollama = backend == "ollama"

            # LLM 모델 즉시 적용
            if llm_model:
                try:
                    if use_ollama:
                        # Ollama: 환경변수에서 읽음
                        llm = LLM(model_dir=MODEL_DIR)
                    else:
                        # Local: 직접 모델명 전달
                        LLM_MODEL = llm_model
                        llm = LLM(model_name=LLM_MODEL, model_dir=MODEL_DIR)

                    # RAG 시스템 재초기화
                    rag_system = RAGSystem(
                        vector_db=vector_db,
                        llm=llm,
                        top_k=5
                    )
                    llm_changed = True
                    logger.success(f"✅ LLM model changed to: {llm_model}")
                except Exception as e:
                    logger.error(f"Failed to reload LLM: {e}")

            # 임베딩 모델 즉시 적용
            if embedding_model_name:
                try:
                    if use_ollama:
                        # Ollama: 환경변수에서 읽음
                        from embeddings_ollama import OllamaEmbedding
                        embedding_model = OllamaEmbedding(model_dir=MODEL_DIR)
                    else:
                        # Local: 직접 모델명 전달
                        EMBEDDING_MODEL = embedding_model_name
                        embedding_model = EmbeddingModel(
                            model_name=EMBEDDING_MODEL,
                            model_dir=MODEL_DIR
                        )

                    # Vector DB 재초기화
                    vector_db = VectorDB(
                        host=REDIS_HOST,
                        port=REDIS_PORT,
                        embedding_dim=embedding_model.get_embedding_dim()
                    )

                    # RAG 시스템에 새 vector_db 적용
                    if rag_system:
                        rag_system = RAGSystem(
                            vector_db=vector_db,
                            llm=llm,
                            top_k=5
                        )

                    embedding_changed = True
                    logger.success(f"✅ Embedding model changed to: {embedding_model_name}")
                    logger.warning("⚠️ 기존 문서들을 새로운 임베딩 모델로 재색인해야 합니다")
                except Exception as e:
                    logger.error(f"Failed to reload embedding model: {e}")

            # 응답 메시지 구성
            response = {
                "llm_changed": llm_changed,
                "embedding_changed": embedding_changed,
                "restart_required": False
            }

            if llm_changed and embedding_changed:
                response["message"] = "LLM 및 임베딩 모델이 즉시 적용되었습니다."
                response["warning"] = "임베딩 모델 변경으로 인해 문서 재색인이 필요합니다."
            elif llm_changed:
                response["message"] = "LLM 모델이 즉시 적용되었습니다."
            elif embedding_changed:
                response["message"] = "임베딩 모델이 즉시 적용되었습니다."
                response["warning"] = "임베딩 모델 변경으로 인해 기존 문서를 모두 재색인해야 합니다."
            else:
                response["message"] = "설정이 저장되었습니다."

            return response

        # Inject dependencies into models router (3 endpoints)
        logger.info("🤖 Injecting dependencies into models router...")
        models.inject_dependencies(
            cache_mgr=cache_manager,
            reload_callback=model_reload_callback
        )
        logger.info("✅ Models router dependencies injected (3 endpoints)")

        # Inject dependencies into metrics router (4 endpoints)
        logger.info("📊 Injecting dependencies into metrics router...")
        metrics_router.inject_dependencies(
            cache_mgr=cache_manager
        )
        logger.info("✅ Metrics router dependencies injected (4 endpoints)")

        # Inject dependencies into prompts router (4 endpoints)
        logger.info("📝 Injecting dependencies into prompts router...")
        prompts.inject_dependencies(
            cache_mgr=cache_manager
        )
        logger.info("✅ Prompts router dependencies injected (4 endpoints)")

        # Inject dependencies into query router (3 endpoints)
        logger.info("🔍 Injecting dependencies into query router...")
        query.inject_dependencies(
            llm_instance=llm,
            embedding_model_instance=embedding_model,
            cache_mgr=cache_manager,
            group_mgr=group_manager,
            conversation_mgr=conversation_manager,
            response_val=response_validator,
            confidence_score=confidence_scorer,
            hybrid_rag_fn=get_hybrid_rag_orchestrator,
            rag_system_fn=get_rag_system,
            auth_dependency=get_current_active_user,
            error_msg_fn=get_safe_error_message,
            prompt_mode_fn=get_system_prompt_for_mode,
            get_llm_fn=get_llm
        )
        logger.info("✅ Query router dependencies injected (3 endpoints)")

        # Inject dependencies into redis_backup router (7 endpoints)
        logger.info("💾 Injecting dependencies into redis_backup router...")
        redis_backup.inject_dependencies(
            cache_mgr=cache_manager
        )
        logger.info("✅ Redis backup router dependencies injected (7 endpoints)")

        # Inject dependencies into question_generation service (Phase 3: Modularization)
        logger.info("📝 Injecting dependencies into question_generation service...")
        question_generation.inject_dependencies(
            llm_instance=llm,
            vector_db_instance=vector_db,
            data_dir=DATA_DIR
        )
        logger.info("✅ Question generation service dependencies injected")

        # Inject dependencies into questions router (1 endpoint)
        logger.info("❓ Injecting dependencies into questions router...")
        questions.inject_dependencies(
            question_gen_service=question_generation
        )
        logger.info("✅ Questions router dependencies injected (1 endpoint)")

        # Inject dependencies into scheduler_service (Phase 3: Modularization)
        logger.info("🕐 Injecting dependencies into scheduler_service...")
        scheduler_service.inject_dependencies(
            cache_mgr=cache_manager,
            audit_log=audit_logger
        )
        logger.info("✅ Scheduler service dependencies injected")

        # Auto-migrate existing documents to version control
        logger.info("🔄 Running document version migration...")
        try:
            data_path = Path(DATA_DIR)
            if data_path.exists():
                allowed_extensions = ['.pdf', '.hwp', '.hwpx', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
                migrated_count = 0
                skipped_count = 0

                for file_path in data_path.iterdir():
                    if file_path.is_file() and any(file_path.name.endswith(ext) for ext in allowed_extensions):
                        filename = file_path.name

                        # Skip if file is in versions directory
                        if 'versions' in file_path.parts:
                            continue

                        # Check if file already has versions
                        try:
                            existing_versions = document_version.list_versions(filename)
                            if existing_versions:
                                skipped_count += 1
                                continue
                        except Exception:
                            pass

                        # Get chunk count from Redis if available
                        chunk_count = 0
                        try:
                            chunk_keys = vector_db.client.keys(f"chunk:{filename}:*")
                            chunk_count = len(chunk_keys) if chunk_keys else 0
                        except Exception:
                            pass

                        # Create V1 version for this file
                        try:
                            document_version.create_version(
                                source_path=file_path,
                                filename=filename,
                                user_id="system",
                                comment="Initial version (auto-migrated)",
                                chunk_count=chunk_count
                            )
                            migrated_count += 1
                            logger.debug(f"Created V1 for {filename}")
                        except Exception as e:
                            logger.debug(f"Failed to create version for {filename}: {e}")

                if migrated_count > 0:
                    logger.success(f"✅ Migrated {migrated_count} documents to version control (skipped {skipped_count})")
                else:
                    logger.info(f"✓ All documents already have versions (checked {skipped_count} files)")
        except Exception as e:
            logger.warning(f"Version migration failed (non-critical): {e}")
            # Don't fail startup if migration fails

        # LLM will be loaded lazily on first chat request
        # Note: Indexing is now handled by documents router (manual reindex button)
        logger.info("⚡ LLM will load on first use (lazy loading enabled)")

        # Optional: Start question generation in background (only if enabled)
        if ENABLE_QUESTION_GENERATION:
            logger.info("📝 Starting background question generation (enabled in config)...")
            asyncio.create_task(question_generation.generate_questions_pool_background())
        else:
            logger.info("⏭️  Question generation disabled (set ENABLE_QUESTION_GENERATION=true to enable)")

        # Start backup scheduler (Phase 3: Using scheduler_service)
        global backup_scheduler_task
        backup_scheduler_task = asyncio.create_task(scheduler_service.backup_scheduler())
        logger.info("🕐 Backup scheduler initialized")

        # Start audit log cleanup scheduler (Phase 3: Using scheduler_service)
        global audit_cleanup_scheduler_task
        audit_cleanup_scheduler_task = asyncio.create_task(scheduler_service.audit_cleanup_scheduler())
        logger.info("🗑️ Audit log cleanup scheduler initialized")

        # Initialize Hybrid RAG Orchestrator (will check Redis config at runtime)
        global hybrid_rag_orchestrator
        hybrid_rag_orchestrator = None  # Will be initialized lazily when needed
        logger.info("🔗 Hybrid RAG orchestrator ready (lazy initialization)")

        logger.success("✅ Application initialized successfully! (Fast startup mode)")
        logger.info("💡 First chat request will load LLM automatically")
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    global backup_scheduler_task, audit_cleanup_scheduler_task

    # Stop backup scheduler
    if backup_scheduler_task:
        backup_scheduler_task.cancel()
        try:
            await backup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("🛑 Backup scheduler stopped")

    # Stop audit cleanup scheduler
    if audit_cleanup_scheduler_task:
        audit_cleanup_scheduler_task.cancel()
        try:
            await audit_cleanup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("🛑 Audit cleanup scheduler stopped")



@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main page with no-cache headers"""
    index_file = static_path / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")

    content = index_file.read_text(encoding="utf-8")

    # Always use no-cache for index.html to ensure users get latest version
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )





# ============================================================================
# Reindex Progress Helper Functions
# ============================================================================


@app.get("/api/validation/stats", tags=["Quality", "Admin"])
async def get_validation_stats(
    current_user: dict = Depends(get_current_active_user)
):
    """
    응답 품질 검증 통계 조회

    Returns:
        - total_checks: 총 검증 횟수
        - total_violations: 총 위반 횟수
        - pass_rate: 검증 통과율
        - violation_by_pattern: 패턴별 위반 횟수
    """
    try:
        stats = response_validator.get_statistics()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        safe_message = get_safe_error_message(e, "validation stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/validation/stats/reset", tags=["Quality", "Admin"])
async def reset_validation_stats(
    current_user: dict = Depends(get_current_active_user)
):
    """
    응답 품질 검증 통계 초기화
    """
    try:
        response_validator.reset_statistics()
        return {
            "success": True,
            "message": "검증 통계가 초기화되었습니다"
        }
    except Exception as e:
        safe_message = get_safe_error_message(e, "reset validation stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/status", tags=["System"])
async def status():
    """
    Get system status with detailed information (cached for performance)
    Public endpoint for health checks
    """
    global status_cache

    try:
        # Check if cache is valid
        import time
        current_time = time.time()
        if (status_cache["data"] is not None and
            current_time - status_cache["timestamp"] < status_cache["ttl"]):
            # Return cached response
            return status_cache["data"]

        # Cache miss or expired - recalculate status
        chunk_count = vector_db.count_documents() if vector_db else 0
        pdf_count = vector_db.count_unique_files() if vector_db else 0

        # Get index state
        index_state = vector_db.get_index_state() if vector_db else None

        # Check for PDF changes
        change_info = None
        if vector_db and vector_db.is_indexed():
            try:
                doc_tracker = DocumentTracker(data_dir=DATA_DIR)
                change_summary = doc_tracker.get_change_summary()
                change_info = {
                    "needs_reindex": change_summary["needs_reindex"],
                    "total_changes": change_summary["total_changes"]
                }
            except Exception:
                pass

        # System is ready if documents are indexed (LLM loads on first use)
        is_ready = (chunk_count > 0) or (rag_system is not None)

        # Check if reindexing is in progress (Phase 3.3: Using reindex_service)
        is_reindexing = reindex_service.is_reindexing()

        # Determine status: reindexing > ready > initializing
        if is_reindexing:
            status_value = "reindexing"
        elif is_ready:
            status_value = "ready"
        else:
            status_value = "initializing"

        # Get current models from environment variables (관리자 페이지에서 변경 시 즉시 반영)
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            current_llm_model = os.getenv("OLLAMA_LLM_MODEL", "qwen3:latest")
            current_embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "daynice/kure-v1:latest")
        else:
            current_llm_model = os.getenv("LLM_MODEL", LLM_MODEL)
            current_embedding_model = os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL)

        response = {
            "status": status_value,
            "document_count": chunk_count,  # 하위 호환성 유지
            "chunk_count": chunk_count,
            "pdf_count": pdf_count,
            "embedding_model": current_embedding_model,
            "llm_model": current_llm_model,
            "is_reindexing": is_reindexing
        }

        if index_state:
            response["index_state"] = index_state

        if change_info:
            response["changes"] = change_info

        # Update cache
        status_cache["data"] = response
        status_cache["timestamp"] = current_time

        return response
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/system-prompt", tags=["System"])
async def get_public_system_prompt(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """시스템 프롬프트 조회 (로그인한 사용자만 접근 가능)

    관리자가 설정한 시스템 프롬프트를 로그인한 사용자가 조회할 수 있는 엔드포인트

    Args:
        current_user: 현재 로그인한 사용자 정보

    Returns:
        저장된 시스템 프롬프트 또는 기본값
    """
    try:
        redis_client = request.app.state.cache_manager.redis

        # Redis에서 조회
        system_prompt = redis_client.get("system:default_prompt")

        if system_prompt:
            # bytes를 str로 변환
            if isinstance(system_prompt, bytes):
                system_prompt = system_prompt.decode('utf-8')
        else:
            # 기본값
            system_prompt = """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다.

# 🎯 역할 정의
- 제공된 문서만을 기반으로 정확하고 신뢰할 수 있는 답변 제공
- 사용자의 질문 의도를 정확히 파악하여 맞춤형 답변 작성
- 전문적이면서도 이해하기 쉬운 설명 제공

# ⚠️ 필수 준수 규칙 (CRITICAL)

## 1. 환각(Hallucination) 방지 - 최우선 원칙
✅ 반드시 지킬 것:
- 제공된 문서에 있는 정보만 사용
- 불확실한 내용은 추측하지 않음
- 문서에 없는 정보는 절대 만들어내지 않음

❌ 절대 금지:
- 일반 지식이나 학습 데이터 기반 답변
- 문서에 없는 내용 추가
- 불확실한 정보를 확실한 것처럼 제시

## 2. 출처 명시
- 답변의 근거가 되는 문서와 위치를 명확히 밝힘
- 여러 문서의 정보를 종합할 때는 각각의 출처를 구분하여 표시

## 3. 불확실성 표현
문서에 정보가 불충분하거나 없을 때:
- "제공된 문서에는 해당 정보가 없습니다"
- "문서에서 명확한 답변을 찾을 수 없습니다"
- "추가 자료가 필요합니다"

# 📋 답변 작성 가이드

## 구조화된 답변
1. **핵심 답변**: 질문에 대한 직접적인 답
2. **상세 설명**: 필요시 맥락과 배경 정보
3. **출처 표시**: 정보의 근거가 된 문서 명시

## 스타일
- 명확하고 간결한 문장
- 전문 용어 사용 시 설명 추가
- 필요시 예시나 비유 활용
- 마크다운 형식으로 가독성 향상"""

        return {
            "system_prompt": system_prompt
        }

    except Exception as e:
        logger.error(f"Failed to get system prompt: {e}")
        # 에러 발생 시에도 기본값 반환
        return {
            "system_prompt": """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다. 제공된 문서 내용을 정확하게 분석하여 사용자에게 도움이 되는 답변을 제공합니다."""
        }


@app.get("/api/system/metrics", tags=["System"])
async def get_system_metrics(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """시스템 메트릭 조회 (관리자 및 로그인한 사용자)

    시스템 전체의 성능 및 상태 메트릭을 조회합니다:
    - Redis 메모리 사용량 및 통계
    - 캐시 히트율 및 검색 통계
    - 슬로우 쿼리 성능 통계

    Args:
        current_user: 현재 로그인한 사용자 정보

    Returns:
        시스템 메트릭 정보
    """
    try:
        metrics_collector = request.app.state.metrics_collector

        if not metrics_collector:
            raise HTTPException(status_code=500, detail="Metrics collector not available")

        # 시스템 메트릭 조회
        metrics = metrics_collector.get_system_metrics()

        return {
            "success": True,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models", tags=["Settings"])
async def list_available_models(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get list of locally available models (both LLM and Embedding)
    Returns only models that are downloaded and ready to use
    """
    try:
        model_manager = ModelManager(model_dir=MODEL_DIR)
        models = model_manager.list_local_models()

        # Separate LLM and Embedding models
        llm_models = []
        embedding_models = []

        # Keywords to identify model types
        embedding_keywords = ["embedding", "KURE", "e5", "jina", "bge", "gte"]
        llm_keywords = ["instruct", "chat", "Qwen", "Llama", "GPT", "rnj"]

        for model in models:
            display_name = model["name"]

            # Determine if it's an embedding model
            is_embedding = any(keyword.lower() in display_name.lower() for keyword in embedding_keywords)

            # Add user-friendly labels for known models
            if "Qwen3-30B" in display_name:
                label = "Qwen 3 30B A3B 4bit"
            elif "rnj-1-instruct" in display_name:
                label = "RNJ-1 Instruct 4bit"
            elif "Qwen2.5-3B" in display_name:
                label = "Qwen 2.5 3B Instruct 4bit"
            elif "KURE" in display_name:
                label = "KURE-v1 (Korean Embedding)"
            elif "jina-embeddings" in display_name:
                label = "Jina Embeddings v3"
            elif "multilingual-e5" in display_name:
                label = "Multilingual E5 Large"
            else:
                # Use model name as label if not recognized
                label = display_name.split("/")[-1]

            model_info = {
                "value": display_name,
                "label": label,
                "size": model["size"]
            }

            if is_embedding:
                embedding_models.append(model_info)
            else:
                llm_models.append(model_info)

        # Sort by name for consistent ordering
        llm_models.sort(key=lambda x: x["label"])
        embedding_models.sort(key=lambda x: x["label"])

        logger.info(f"Found {len(llm_models)} LLM models and {len(embedding_models)} embedding models")
        return {
            "llm_models": llm_models,
            "embedding_models": embedding_models
        }

    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")


@app.post("/api/change-llm", tags=["Settings"])
async def change_llm(
    request: LLMChangeRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Change the LLM model dynamically
    """
    global llm, rag_system, LLM_MODEL

    try:
        logger.info(f"Changing LLM model to: {request.llm_model}")

        # Update the LLM_MODEL variable
        LLM_MODEL = request.llm_model

        # Reload LLM with new model
        llm = LLM(
            model_name=LLM_MODEL,
            model_dir=MODEL_DIR
        )

        # Reinitialize RAG system with new LLM
        rag_system = RAGSystem(llm, vector_db, cache_manager)

        logger.success(f"LLM model changed to: {LLM_MODEL}")

        return {
            "status": "success",
            "llm_model": LLM_MODEL,
            "message": "LLM model changed successfully"
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "change model endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/change-embedding", tags=["Settings"])
async def change_embedding(
    request: EmbeddingChangeRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Change the Embedding model dynamically
    Requires re-indexing all documents with new embeddings
    """
    global embedding_model, vector_db, EMBEDDING_MODEL

    try:
        logger.info(f"Changing Embedding model to: {request.embedding_model}")

        # Update the EMBEDDING_MODEL variable
        EMBEDDING_MODEL = request.embedding_model

        # Reload embedding model
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            # For Ollama, don't pass model_name - let it read from OLLAMA_EMBEDDING_MODEL env var
            embedding_model = EmbeddingModel(
                model_dir=MODEL_DIR
            )
        else:
            # For local embedding model
            embedding_model = EmbeddingModel(
                model_name=EMBEDDING_MODEL,
                model_dir=MODEL_DIR
            )

        # Reinitialize vector DB with new embedding model
        vector_db = VectorDB(
            host=REDIS_HOST,
            port=REDIS_PORT,
            embedding_dim=embedding_model.get_embedding_dim()
        )

        # Note: Existing embeddings in Redis are now incompatible
        # User needs to reindex documents
        logger.warning("Embedding model changed - existing document embeddings are now incompatible")
        logger.info("Please use the reindex endpoint to update all document embeddings")

        return {
            "status": "success",
            "embedding_model": EMBEDDING_MODEL,
            "message": "Embedding model changed successfully",
            "warning": "기존 문서들을 새로운 임베딩 모델로 재색인해야 합니다. '재색인' 버튼을 클릭하세요."
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "change embedding model endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


# ============================================================================
# 🆕 독립 검색 API 엔드포인트 (Tavily, Context7)
# ============================================================================

@app.post("/api/search/web", response_model=WebSearchResponse, tags=["Search"])
async def search_web(
    request: WebSearchRequest,
    current_user: dict = Depends(get_current_active_user),
    app_request: Request = None
):
    """
    Tavily 웹 검색 독립 API

    - 인증 필요 (로그인한 사용자만)
    - Tavily API 키는 서버에서 관리
    - 검색 결과를 그대로 반환 (LLM 답변 생성 안 함)
    """
    try:
        # Hybrid RAG 인스턴스 가져오기 (lazy 초기화)
        rag = await get_hybrid_rag_orchestrator()

        # Tavily 초기화 확인
        if not rag.tavily_client:
            raise HTTPException(
                status_code=503,
                detail="웹 검색 기능이 비활성화되어 있습니다. Tavily API 키를 설정해주세요."
            )

        logger.info(f"🌐 웹 검색 요청: '{request.query}' (depth={request.search_depth})")

        # Tavily 검색 수행
        search_params = {
            "query": request.query,
            "max_results": request.max_results,
            "search_depth": request.search_depth,
            "include_answer": False,
            "include_raw_content": True
        }

        # 도메인 필터 추가 (유효한 도메인만 포함)
        if request.include_domains:
            # 유효한 도메인만 필터링 (점이 있고 최소 2글자 이상)
            valid_domains = [d for d in request.include_domains if '.' in d and len(d) > 2]
            if valid_domains:
                search_params["include_domains"] = valid_domains
        if request.exclude_domains:
            # 유효한 도메인만 필터링
            valid_domains = [d for d in request.exclude_domains if '.' in d and len(d) > 2]
            if valid_domains:
                search_params["exclude_domains"] = valid_domains

        search_results = rag.tavily_client.search(**search_params)

        # 결과 포맷팅
        formatted_results = []
        for result in search_results.get('results', []):
            formatted_results.append({
                'title': result.get('title', ''),
                'url': result.get('url', ''),
                'content': result.get('content', ''),
                'published_date': result.get('published_date', ''),
                'score': result.get('score', 0.0)
            })

        logger.success(f"✅ 웹 검색 완료: {len(formatted_results)}개 결과")

        return WebSearchResponse(
            success=True,
            results=formatted_results,
            query=request.query,
            search_depth=request.search_depth
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 웹 검색 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"웹 검색 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/api/search/docs", response_model=DocsSearchResponse, tags=["Search"])
async def search_docs(
    request: DocsSearchRequest,
    current_user: dict = Depends(get_current_active_user),
    app_request: Request = None
):
    """
    Context7 공식 문서 검색 독립 API

    - 인증 필요 (로그인한 사용자만)
    - Context7 API 키는 서버에서 관리
    - React, Vue, Spring Boot 등 공식 문서 검색
    """
    try:
        # Hybrid RAG 인스턴스 가져오기 (lazy 초기화)
        rag = await get_hybrid_rag_orchestrator()

        # Context7 초기화 확인
        if not rag.context7_client:
            raise HTTPException(
                status_code=503,
                detail="공식 문서 검색 기능이 비활성화되어 있습니다. Context7을 설정해주세요."
            )

        logger.info(f"📚 공식 문서 검색 요청: '{request.query}' (tech_stack={request.tech_stack})")

        # tech_stack이 명시되지 않은 경우 쿼리 분석으로 감지
        tech_stack = request.tech_stack
        if not tech_stack and rag.query_analyzer:
            analysis = rag.query_analyzer.analyze(request.query)
            tech_stack = analysis.get('tech_stack')
            logger.info(f"🔍 자동 감지된 기술 스택: {tech_stack}")

        # Context7 검색 수행
        analysis = {'tech_stack': tech_stack} if tech_stack else {}
        docs_results = await rag._search_docs(request.query, analysis)

        # 결과 포맷팅
        formatted_results = []
        for result in docs_results[:request.max_results]:
            formatted_results.append({
                'title': result.get('metadata', {}).get('title', ''),
                'url': result.get('metadata', {}).get('url', ''),
                'content': result.get('content', ''),
                'library': result.get('metadata', {}).get('library', tech_stack),
                'relevance_score': result.get('score', 0.0)
            })

        logger.success(f"✅ 공식 문서 검색 완료: {len(formatted_results)}개 결과")

        return DocsSearchResponse(
            success=True,
            results=formatted_results,
            query=request.query,
            tech_stack=tech_stack
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 공식 문서 검색 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"공식 문서 검색 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/api/convert/hwpx", tags=["Conversion"])
async def convert_to_hwpx(
    request: HwpxConversionRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    HTML/Markdown을 HWPX 형식으로 변환

    - 인증 필요 (로그인한 사용자만)
    - Java document-service에 프록시 요청
    - HWPX 파일을 바이너리로 반환
    """
    try:
        import httpx

        logger.info(f"📄 HWPX 변환 요청: content_type={request.content_type}, 길이={len(request.content)}")

        # Java 서비스 URL
        java_service_url = os.getenv("DOCUMENT_SERVICE_URL", "http://localhost:8081")

        # 엔드포인트 선택
        if request.content_type == "markdown":
            endpoint = f"{java_service_url}/api/conversion/markdown-to-hwpx"
            payload = {
                "markdownContent": request.content,
                "filename": request.filename
            }
        else:  # html
            endpoint = f"{java_service_url}/api/conversion/html-to-hwpx"
            payload = {
                "htmlContent": request.content,
                "filename": request.filename
            }

        # Java 서비스에 요청
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"❌ Java 서비스 오류: {response.status_code} - {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"HWPX 변환 실패: {error_detail}"
                )

            # 파일명 추출 (Content-Disposition 헤더에서)
            content_disposition = response.headers.get("content-disposition", "")
            filename = request.filename or "document.hwpx"
            if "filename=" in content_disposition:
                # filename*=UTF-8''encoded_name 형식 처리
                import urllib.parse
                parts = content_disposition.split("filename=")
                if len(parts) > 1:
                    filename_part = parts[1].strip('"').strip("'")
                    try:
                        filename = urllib.parse.unquote(filename_part)
                    except Exception:
                        pass

            if not filename.endswith(".hwpx"):
                filename += ".hwpx"

            logger.success(f"✅ HWPX 변환 완료: {filename}, {len(response.content)} bytes")

            # HWPX 파일 반환
            return Response(
                content=response.content,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(len(response.content))
                }
            )

    except httpx.TimeoutException:
        logger.error("❌ Java 서비스 타임아웃")
        raise HTTPException(
            status_code=504,
            detail="HWPX 변환 서비스 응답 시간 초과"
        )
    except httpx.ConnectError:
        logger.error("❌ Java 서비스 연결 실패")
        raise HTTPException(
            status_code=503,
            detail="HWPX 변환 서비스에 연결할 수 없습니다. 서비스가 실행 중인지 확인하세요."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ HWPX 변환 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"HWPX 변환 중 오류가 발생했습니다: {str(e)}"
        )


# ============================================================================
# Group Management API Endpoints
# ============================================================================

class DocumentAssignRequest(BaseModel):
    group_id: str




# ============================================================================
# Conversation History API Endpoints
# ============================================================================


# ============================================================================
# Follow-up Questions API
# ============================================================================



@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint for load balancers and monitoring systems.
    Returns detailed system status including Redis, models, and cache.
    Optimized for fast response (<10ms).
    """
    try:
        import psutil
        from datetime import datetime

        # Check Redis connectivity (fast PING only)
        redis_healthy = False
        redis_info = {}
        try:
            vector_db.client.ping()
            redis_healthy = True
            # Minimal info for performance - avoid expensive INFO command
            redis_info = {
                "connected": True
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

        # Check cache stats (lightweight)
        cache_stats = {}
        if cache_manager:
            cache_stats = cache_manager.get_cache_stats()

        # System resources (instant read, no interval)
        cpu_percent = psutil.cpu_percent(interval=0)  # Instant, no blocking
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Model status (simple bool check)
        models_loaded = {
            "embedding": embedding_model is not None,
            "llm": llm is not None,
            "rag": rag_system is not None
        }

        # Overall health status
        is_healthy = redis_healthy and all(models_loaded.values())

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "redis": {
                "healthy": redis_healthy,
                "info": redis_info
            },
            "cache": {
                "entries": cache_stats.get("total_entries", 0),
                "hit_rate": (cache_stats.get("cache_hits", 0) / max(cache_stats.get("total_queries", 1), 1)) * 100
            },
            "models": models_loaded,
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": disk.percent
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


@app.get("/metrics", tags=["System"])
async def metrics():
    """
    Prometheus-compatible metrics endpoint for monitoring.
    Returns key performance metrics in plain text format.
    """
    try:
        import psutil

        # Get cache stats
        cache_stats = cache_manager.get_cache_stats() if cache_manager else {}

        # Get Redis stats
        redis_info = {}
        try:
            info = vector_db.client.info()
            redis_info = {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "total_commands": info.get("total_commands_processed", 0)
            }
        except Exception:
            pass

        # System metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        # Format metrics in Prometheus format
        metrics_output = f"""# HELP cache_entries Total number of cache entries
# TYPE cache_entries gauge
cache_entries {cache_stats.get('total_entries', 0)}

# HELP cache_queries_total Total number of cache queries
# TYPE cache_queries_total counter
cache_queries_total {cache_stats.get('total_queries', 0)}

# HELP cache_hits_total Total number of cache hits
# TYPE cache_hits_total counter
cache_hits_total {cache_stats.get('cache_hits', 0)}

# HELP redis_connected_clients Number of Redis client connections
# TYPE redis_connected_clients gauge
redis_connected_clients {redis_info.get('connected_clients', 0)}

# HELP redis_memory_used_bytes Redis memory usage in bytes
# TYPE redis_memory_used_bytes gauge
redis_memory_used_bytes {redis_info.get('used_memory', 0)}

# HELP system_cpu_percent CPU usage percentage
# TYPE system_cpu_percent gauge
system_cpu_percent {cpu_percent}

# HELP system_memory_percent Memory usage percentage
# TYPE system_memory_percent gauge
system_memory_percent {memory.percent}
"""

        return Response(content=metrics_output, media_type="text/plain")
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return Response(content="", media_type="text/plain", status_code=500)


# DEPRECATED: 이 엔드포인트는 src/routers/auth.py의 신버전으로 대체되었습니다
# Redis 기반의 더 빠르고 안정적인 엔드포인트를 사용하세요
# @app.get("/api/admin/security-logs", tags=["Admin"])
# async def get_security_logs(
#     request: Request,
#     limit: int = 100,
#     offset: int = 0,
#     level: Optional[str] = None,
#     event_type: Optional[str] = None,
#     start_date: Optional[str] = None,
#     end_date: Optional[str] = None
# ):
#     """
#     Get security logs (admin only)
#
#     Args:
#         limit: Number of logs to return
#         offset: Number of logs to skip
#         level: Filter by log level (INFO, WARNING, ERROR, CRITICAL)
#         event_type: Filter by event type
#         start_date: Filter from this date (ISO format)
#         end_date: Filter to this date (ISO format)
#
#     Returns:
#         List of security log entries
#     """
#     try:
#         # Get token from Authorization header or cookies
#         token = None
#         auth_header = request.headers.get("Authorization")
#         if auth_header and auth_header.startswith("Bearer "):
#             token = auth_header.split(" ")[1]
#         else:
#             token = request.cookies.get("access_token")
#
#         if not token:
#             raise HTTPException(status_code=401, detail="Not authenticated")
#
#         from .auth.utils import verify_token, get_user
#         user_data = verify_token(token)
#         if not user_data:
#             raise HTTPException(status_code=401, detail="Invalid token")
#
#         # Get user and check admin role
#         redis_client = request.app.state.cache_manager.redis
#         user = get_user(user_data["user_id"], redis_client)
#         if not user or user.get("role") != "admin":
#             raise HTTPException(status_code=403, detail="Admin access required")
#
#         # Determine log file path
#         log_file_path = os.getenv("LOG_FILE", "server.log")
#         if not os.path.isabs(log_file_path):
#             log_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), log_file_path)
#
#         if not os.path.exists(log_file_path):
#             return {
#                 "logs": [],
#                 "total_count": 0,
#                 "limit": limit,
#                 "offset": offset
#             }
#
#         # Read and parse security logs
#         security_logs = []
#         with open(log_file_path, 'r', encoding='utf-8') as f:
#             for line in f:
#                 if "SECURITY_EVENT:" in line:
#                     try:
#                         # Extract JSON part
#                         json_start = line.index("SECURITY_EVENT:") + len("SECURITY_EVENT:")
#                         json_str = line[json_start:].strip()
#                         log_data = json.loads(json_str)
#
#                         # Apply filters
#                         if level and log_data.get("level") != level:
#                             continue
#                         if event_type and log_data.get("event_type") != event_type:
#                             continue
#                         if start_date:
#                             try:
#                                 from datetime import datetime
#                                 log_time = datetime.fromisoformat(log_data.get("timestamp", ""))
#                                 start_time = datetime.fromisoformat(start_date)
#                                 if log_time < start_time:
#                                     continue
#                             except:
#                                 pass
#                         if end_date:
#                             try:
#                                 from datetime import datetime
#                                 log_time = datetime.fromisoformat(log_data.get("timestamp", ""))
#                                 end_time = datetime.fromisoformat(end_date)
#                                 if log_time > end_time:
#                                     continue
#                             except:
#                                 pass
#
#                         security_logs.append(log_data)
#                     except (ValueError, json.JSONDecodeError) as e:
#                         logger.warning(f"Failed to parse security log line: {e}")
#                         continue
#
#         # Sort by timestamp descending (most recent first)
#         security_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
#
#         # Apply pagination
#         total_count = len(security_logs)
#         paginated_logs = security_logs[offset:offset + limit]
#
#         return {
#             "logs": paginated_logs,
#             "total_count": total_count,
#             "limit": limit,
#             "offset": offset
#         }
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Failed to get security logs: {e}")
#         raise HTTPException(status_code=500, detail="Failed to retrieve security logs")




if __name__ == "__main__":
    import uvicorn
    import multiprocessing
    import sys

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

        # Add file logging with rotation (keep 7 days, rotate at 100MB)
        log_file = os.getenv("LOG_FILE", "/tmp/chatbot_production.log")
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
        log_file = os.getenv("LOG_FILE", "server.log")
        logger.add(
            log_file,
            rotation="10 MB",
            retention="3 days",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG"
        )
        logger.info(f"Development logging active with file: {log_file}")

    # Worker configuration based on CPU cores
    # Production: (CPU cores * 2) + 1, with min 4 and max 8
    cpu_count = multiprocessing.cpu_count()
    if environment == "development":
        workers = 1  # Single worker for easier debugging
    else:
        workers = max(4, min(8, (cpu_count * 2) + 1))

    # Timeout settings for production
    timeout_keep_alive = int(os.getenv("TIMEOUT_KEEP_ALIVE", 65))  # Keep-alive timeout
    timeout_graceful_shutdown = int(os.getenv("TIMEOUT_GRACEFUL_SHUTDOWN", 30))

    # Connection limits
    limit_concurrency = int(os.getenv("LIMIT_CONCURRENCY", 1000))  # Max concurrent connections
    limit_max_requests = int(os.getenv("LIMIT_MAX_REQUESTS", 10000))  # Max requests before worker restart

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
        backlog=2048,  # Connection backlog queue size
        use_colors=False if environment == "production" else True,
        server_header=False,  # Don't expose server version
        date_header=True,
        proxy_headers=True,  # Support X-Forwarded-* headers
        forwarded_allow_ips="*"  # Allow all proxy IPs (configure for specific IPs in production)
    )
