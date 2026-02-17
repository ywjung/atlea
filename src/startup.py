"""
Startup and Shutdown Logic for FastAPI Application

This module contains all initialization, dependency injection,
and cleanup logic for the application startup and shutdown.
"""

import os
import sys
import asyncio
import secrets
import string
from pathlib import Path
from typing import Optional
from loguru import logger

from .embeddings import EmbeddingModel
from .vector_db import VectorDB
from .llm import LLM, RAGSystem
from .document_version import DocumentVersion
from .cache_manager import CacheManager
from .model_manager import ModelManager
from .group_manager import GroupManager
from .conversation_manager import ConversationManager
from .response_validator import response_validator
from .confidence_scorer import confidence_scorer
from .feedback_analyzer import feedback_analyzer
from .hybrid_rag import HybridRAGOrchestrator
from .audit import AuditLogger
from .config import config
from .database.connection import check_db_connection, close_db

# Import routers for dependency injection
from .routers import (
    documents, cache, conversations, feedback, settings,
    groups, audit, models, prompts, query, db_backup,
    questions, tts, security, system, search, websocket_alerts,
    static_files, validation, conversion
)
from .routers import metrics as metrics_router

# Import services
from .services import question_generation, scheduler_service, reindex_service

# Import auth dependencies
from .auth.middleware import get_current_active_user
from .utils.error_handling import get_safe_error_message
from .config.prompts import get_system_prompt_for_mode


# ==================== Global Instances ====================
# These are initialized during startup and used throughout the application

embedding_model: Optional[EmbeddingModel] = None
vector_db: Optional[VectorDB] = None
llm: Optional[LLM] = None
rag_system: Optional[RAGSystem] = None
cache_manager: Optional[CacheManager] = None
conversation_manager: Optional[ConversationManager] = None
document_version: Optional[DocumentVersion] = None
audit_logger: Optional[AuditLogger] = None
group_manager: Optional[GroupManager] = None
hybrid_rag_orchestrator: Optional[HybridRAGOrchestrator] = None

# Scheduler tasks
backup_scheduler_task = None
audit_cleanup_scheduler_task = None

# Configuration from environment
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nlpai-lab/KURE-v1")
LLM_MODEL = os.getenv("LLM_MODEL", "mlx-community/Qwen3-30B-A3B-4bit")
MODEL_DIR = os.getenv("MODEL_DIR", "./model")
DATA_DIR = os.getenv("DATA_DIR", "./data")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 512))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 50))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 100))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
ENABLE_QUESTION_GENERATION = os.getenv("ENABLE_QUESTION_GENERATION", "false").lower() == "true"


# ==================== Lazy Loading Functions ====================

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


# Hybrid RAG config in-memory cache (TTL 기반)
_hybrid_rag_config_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 10  # 10초 캐시
}


async def get_hybrid_rag_orchestrator():
    """Get Hybrid RAG orchestrator instance, initializing it lazily based on PG config"""
    global hybrid_rag_orchestrator

    # 인메모리 캐시에서 설정 조회 (TTL 기반)
    import time as _time
    now = _time.time()
    if (_hybrid_rag_config_cache["data"] is not None and
            now - _hybrid_rag_config_cache["timestamp"] < _hybrid_rag_config_cache["ttl"]):
        cached = _hybrid_rag_config_cache["data"]
        is_enabled = cached["is_enabled"]
        enable_web = cached["enable_web"]
        enable_docs = cached["enable_docs"]
        web_search_provider = cached["web_search_provider"]
    else:
        # PostgreSQL에서 설정 조회
        from .services.config_service import config_get_multi
        cfg = await config_get_multi([
            "config:hybrid_rag_enabled",
            "config:hybrid_rag_web_search",
            "config:hybrid_rag_doc_search",
            "config:web_search_provider",
        ])

        is_enabled = cfg.get("config:hybrid_rag_enabled") == "true"
        enable_web = cfg.get("config:hybrid_rag_web_search") == "true"
        enable_docs = cfg.get("config:hybrid_rag_doc_search") == "true"
        web_search_provider = cfg.get("config:web_search_provider") or 'tavily'

        # 캐시 갱신
        _hybrid_rag_config_cache["data"] = {
            "is_enabled": is_enabled,
            "enable_web": enable_web,
            "enable_docs": enable_docs,
            "web_search_provider": web_search_provider
        }
        _hybrid_rag_config_cache["timestamp"] = now

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

        # PostgreSQL에서 API 키 사전 조회 (sync init에 전달)
        from .services.config_service import config_get
        tavily_key = await config_get("config:tavily_api_key") if enable_web else None
        context7_key = await config_get("config:context7_api_key") if enable_docs else None

        hybrid_rag_orchestrator = HybridRAGOrchestrator(
            local_rag=rag_instance,
            cache_manager=cache_manager,
            enable_web_search=enable_web,
            enable_doc_search=enable_docs,
            web_search_provider=web_search_provider,
            tavily_api_key=tavily_key,
            context7_api_key=context7_key,
        )
        logger.success(f"✅ Hybrid RAG ready! (Web: {enable_web}, Provider: {web_search_provider}, Docs: {enable_docs})")

    return hybrid_rag_orchestrator


# ==================== Admin Creation ====================

async def create_default_admin():
    """Create default admin user if no admin exists

    비밀번호 설정 우선순위:
    1. ADMIN_DEFAULT_PASSWORD 환경변수
    2. 자동 생성된 랜덤 비밀번호 (보안상 권장)
    """
    from .auth.service import AuthService
    from .auth.models import UserCreate

    try:
        auth_service = AuthService()

        # Check if any admin exists
        users_result = await auth_service.get_all_users(page=1, page_size=1000)
        admin_exists = any(u.get('role') == 'admin' for u in users_result['users'])

        if not admin_exists:
            # 환경변수에서 자격 증명 로드
            default_email = config.ADMIN_DEFAULT_EMAIL
            default_username = config.ADMIN_DEFAULT_USERNAME
            default_password = config.ADMIN_DEFAULT_PASSWORD

            # 비밀번호가 설정되지 않았으면 랜덤 생성
            password_auto_generated = False
            if not default_password:
                # 강력한 랜덤 비밀번호 생성 (16자: 대소문자, 숫자, 특수문자)
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                default_password = ''.join(secrets.choice(alphabet) for _ in range(16))
                password_auto_generated = True

            # Check if user already exists (PG)
            from .database.connection import SyncSessionFactory
            from .database.models.user import User as PgUser
            from sqlalchemy import select

            with SyncSessionFactory() as db_session:
                stmt = select(PgUser).where(PgUser.email == default_email)
                existing_user = db_session.execute(stmt).scalar_one_or_none()

            if existing_user:
                # User exists, just upgrade to admin
                with SyncSessionFactory() as db_session:
                    user = db_session.get(PgUser, existing_user.id)
                    user.role = "admin"
                    db_session.commit()
                logger.info(f"Upgraded existing user {default_email} to admin")
            else:
                # Create new admin user
                user_data = UserCreate(
                    email=default_email,
                    username=default_username,
                    password=default_password
                )
                user = await auth_service.create_user(user_data)

                # Set as admin (PG)
                with SyncSessionFactory() as db_session:
                    pg_user = db_session.execute(
                        select(PgUser).where(PgUser.email == default_email)
                    ).scalar_one_or_none()
                    if pg_user:
                        pg_user.role = "admin"
                        db_session.commit()

                logger.success(f"✅ Created default admin user: {default_email}")

                # 보안: 비밀번호는 로그에 출력하지 않음
                if password_auto_generated:
                    # 자동 생성된 비밀번호만 파일에 안전하게 저장
                    try:
                        password_file = ".admin_initial_password"
                        with open(password_file, "w") as f:
                            f.write(f"Initial Admin Password (DELETE THIS FILE AFTER READING)\n")
                            f.write(f"Email: {default_email}\n")
                            f.write(f"Password: {default_password}\n")
                            f.write(f"\n⚠️  Change this password immediately after first login!\n")
                        # 파일 권한 설정 (소유자만 읽기 가능)
                        os.chmod(password_file, 0o600)
                        logger.warning(f"🔐 Auto-generated admin password saved to: {password_file}")
                        logger.warning("⚠️  Please read the file, login, change password, then DELETE the file!")
                    except Exception as file_error:
                        logger.error(f"❌ Could not save password file: {file_error}")
                        # 파일 저장 실패 시 보안을 위해 비밀번호를 로그에 출력하지 않음
                        logger.error("❌ Auto-generated admin password could not be saved. Please set ADMIN_DEFAULT_PASSWORD env var and restart.")
                else:
                    logger.info("ℹ️  Admin password set from ADMIN_DEFAULT_PASSWORD environment variable")
                    logger.warning("⚠️  Please change the default admin password after first login!")
        else:
            logger.info("ℹ️  Admin user already exists, skipping default admin creation")

    except Exception as e:
        logger.warning(f"⚠️  Failed to create default admin: {e}")
        # Don't fail startup if admin creation fails


# ==================== Model Reload Callback ====================

def create_model_reload_callback():
    """Create callback for reloading models when configuration changes"""
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
                    # Ollama: OllamaLLM 클래스 직접 임포트하여 사용
                    from .llm_ollama import OllamaLLM
                    llm = OllamaLLM(model_name=llm_model, model_dir=MODEL_DIR)
                else:
                    # Local: llm.py의 원본 LocalLLM 클래스 사용
                    from .llm import LocalLLM
                    LLM_MODEL = llm_model
                    llm = LocalLLM(model_name=LLM_MODEL, model_dir=MODEL_DIR)

                # RAG 시스템 재초기화
                rag_system = RAGSystem(
                    vector_db=vector_db,
                    llm=llm,
                    top_k=5
                )
                llm_changed = True
                logger.success(f"✅ LLM model changed to: {llm_model} (backend: {backend})")
            except Exception as e:
                logger.error(f"Failed to reload LLM: {e}")

        # 임베딩 모델 즉시 적용
        if embedding_model_name:
            try:
                if use_ollama:
                    # Ollama: 모델명 직접 전달
                    from .embeddings_ollama import OllamaEmbedding
                    embedding_model = OllamaEmbedding(model_name=embedding_model_name, model_dir=MODEL_DIR)
                else:
                    # Local: 직접 모델명 전달
                    EMBEDDING_MODEL = embedding_model_name
                    embedding_model = EmbeddingModel(
                        model_name=EMBEDDING_MODEL,
                        model_dir=MODEL_DIR
                    )

                # Vector DB 재초기화
                vector_db = VectorDB(
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

    return model_reload_callback


# ==================== Startup Event ====================

async def startup_event(app):
    """Initialize models and database on startup (fast startup with lazy loading)"""
    global embedding_model, vector_db, cache_manager, group_manager, conversation_manager
    global document_version, audit_logger, backup_scheduler_task, audit_cleanup_scheduler_task
    global hybrid_rag_orchestrator

    # Configure file logging (development mode) - only once
    environment = os.getenv("ENVIRONMENT", "development")
    os.makedirs("logs", exist_ok=True)
    if environment != "production":
        log_file = os.getenv("LOG_FILE", "logs/server.log")
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
            embedding_model = EmbeddingModel(model_dir=MODEL_DIR)
        else:
            embedding_model = EmbeddingModel(
                model_name=EMBEDDING_MODEL,
                model_dir=MODEL_DIR
            )

        # Initialize vector database (PostgreSQL)
        logger.info("🔌 Initializing vector database...")

        vector_db = VectorDB(
            embedding_dim=embedding_model.get_embedding_dim(),
        )

        logger.info(f"VectorDB initialized (embedding_dim={embedding_model.get_embedding_dim()})")

        # Verify PostgreSQL connection
        logger.info("🐘 Checking PostgreSQL connection...")
        pg_ok = await check_db_connection()
        if pg_ok:
            logger.success("✅ PostgreSQL connection verified")
        else:
            logger.warning("⚠️  PostgreSQL not available")

        # Clean up stale reindexing state from previous abnormal shutdown
        reindex_service.cleanup_stale_reindex_state()

        # Set rate limit configuration in PostgreSQL
        try:
            from .services.config_service import config_set
            rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "false").lower()
            await config_set("config:rate_limit_enabled", rate_limit_enabled, "boolean")
            logger.info(f"⚙️  Rate limiting: {rate_limit_enabled}")
        except Exception as e:
            logger.warning(f"Failed to set rate limit config: {e}")

        # Initialize cache manager with production settings
        logger.info("💾 Initializing cache manager...")

        # Production cache configuration
        cache_similarity_threshold = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", 0.90))
        cache_ttl = int(os.getenv("CACHE_TTL", 3600))
        memory_cache_size = int(os.getenv("MEMORY_CACHE_SIZE", 200))

        cache_manager = CacheManager(
            embedding_model=embedding_model.model,
            similarity_threshold=cache_similarity_threshold,
            cache_ttl=cache_ttl,
            memory_cache_size=memory_cache_size
        )

        logger.info(f"Cache configured: similarity={cache_similarity_threshold}, TTL={cache_ttl}s")

        # Store cache_manager in app state
        app.state.cache_manager = cache_manager
        logger.info(f"✅ Stored cache_manager in app.state")

        # Initialize SecurityLogger (PG-based)
        from .auth.security_logger import SecurityLogger
        SecurityLogger.initialize()
        logger.info("✅ SecurityLogger initialized")

        # FeedbackAnalyzer loads from PG on init
        logger.info(f"✅ FeedbackAnalyzer initialized ({len(feedback_analyzer.feedback_history)} feedbacks)")

        # Initialize audit logger
        audit_logger = AuditLogger(retention_days=90)
        app.state.audit_logger = audit_logger
        logger.info("✅ AuditLogger initialized (retention=90 days)")

        # Create default admin user
        await create_default_admin()

        # Initialize managers
        logger.info("📁 Initializing group manager...")
        group_manager = GroupManager()

        logger.info("💬 Initializing conversation manager...")
        conversation_manager = ConversationManager()

        logger.info("📋 Initializing document version manager...")
        max_versions = int(os.getenv("DOCUMENT_MAX_VERSIONS", 10))
        document_version = DocumentVersion(
            data_dir=DATA_DIR,
            max_versions=max_versions
        )
        logger.info(f"Document version manager configured: max_versions={max_versions}")

        # ==================== Dependency Injection ====================

        # Inject into documents router
        logger.info("📄 Injecting dependencies into documents router...")
        documents.inject_dependencies(
            vdb=vector_db,
            doc_processor=None,
            doc_version=document_version,
            grp_manager=group_manager,
            cache_mgr=cache_manager,
            emb_model=embedding_model,
            audit_log=audit_logger,
            data_dir=DATA_DIR,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            max_file_size=MAX_FILE_SIZE,
            max_file_size_mb=MAX_FILE_SIZE_MB,
            reindex_evt=reindex_service.get_reindex_event()
        )
        logger.info("✅ Documents router dependencies injected (19 endpoints)")

        # Inject into other routers
        cache.inject_dependencies(cache_mgr=cache_manager)
        logger.info("✅ Cache router dependencies injected (4 endpoints)")

        conversations.inject_dependencies(conv_manager=conversation_manager)
        logger.info("✅ Conversations router dependencies injected (7 endpoints)")

        feedback.inject_dependencies(
            fb_analyzer=feedback_analyzer,
            conv_manager=conversation_manager,
            cache_mgr=cache_manager
        )
        logger.info("✅ Feedback router dependencies injected (5 endpoints)")

        settings.inject_dependencies(cache_mgr=cache_manager)
        logger.info("✅ Settings router dependencies injected (5 endpoints)")

        groups.inject_dependencies(grp_manager=group_manager)
        logger.info("✅ Groups router dependencies injected (9 endpoints)")

        audit.inject_dependencies(audit_log=audit_logger, cache_mgr=cache_manager)
        logger.info("✅ Audit router dependencies injected (4 endpoints)")

        security.inject_dependencies(cache_mgr=cache_manager, audit_log=audit_logger)
        logger.info("✅ Security router dependencies injected (3 endpoints)")

        # Inject model reload callback into models router
        logger.info("🤖 Injecting dependencies into models router...")
        models.inject_dependencies(
            cache_mgr=cache_manager,
            reload_callback=create_model_reload_callback()
        )
        logger.info("✅ Models router dependencies injected (3 endpoints)")

        metrics_router.inject_dependencies(cache_mgr=cache_manager)
        logger.info("✅ Metrics router dependencies injected (4 endpoints)")

        prompts.inject_dependencies(cache_mgr=cache_manager)
        logger.info("✅ Prompts router dependencies injected (4 endpoints)")

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

        db_backup.inject_dependencies()
        logger.info("✅ DB backup router initialized")

        # Inject into services
        question_generation.inject_dependencies(
            llm_instance=llm,
            vector_db_instance=vector_db,
            data_dir=DATA_DIR
        )
        logger.info("✅ Question generation service dependencies injected")

        questions.inject_dependencies(question_gen_service=question_generation)
        logger.info("✅ Questions router dependencies injected (1 endpoint)")

        # TTS 라우터는 초기화 후 재주입 (아래 참조)
        logger.info("⏳ TTS router dependencies will be injected after initialization")

        # Inject into new modularized routers (Phase 2-2)
        system.inject_dependencies(
            vector_db_instance=vector_db,
            cache_mgr=cache_manager,
            emb_model=embedding_model,
            llm_instance=llm,
            rag_system_instance=rag_system,
            reindex_svc=reindex_service,
            data_dir=DATA_DIR,
            llm_model=LLM_MODEL,
            embedding_model=EMBEDDING_MODEL
        )
        logger.info("✅ System router dependencies injected (5 endpoints)")

        search.inject_dependencies(hybrid_rag_fn=get_hybrid_rag_orchestrator)
        logger.info("✅ Search router dependencies injected (2 endpoints)")

        websocket_alerts.inject_dependencies(cache_mgr=cache_manager)
        logger.info("✅ WebSocket alerts router dependencies injected (1 endpoint)")

        # Initialize TTS service
        logger.info("🔊 Initializing TTS service...")
        tts_service = None
        try:
            tts_service = tts.initialize_tts_service(eager_load=True)
            if tts_service:
                logger.success("✅ TTS model loaded at startup")
            else:
                logger.info("⏭️ TTS is disabled or not configured")
        except Exception as e:
            logger.warning(f"⚠️ TTS initialization failed (non-critical): {e}")

        # TTS 라우터에 dependencies 주입 (초기화 완료 후)
        tts.inject_dependencies(cache_mgr=cache_manager, tts_svc=tts_service)
        logger.info("✅ TTS router dependencies injected (8 endpoints)")

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

                        # Get chunk count from PostgreSQL
                        chunk_count = 0
                        try:
                            from .database.connection import SyncSessionFactory as _SyncSF
                            from .database.models.document_chunk import DocumentChunk
                            from sqlalchemy import func as sa_func
                            with _SyncSF() as _db:
                                chunk_count = _db.query(sa_func.count(DocumentChunk.id)).filter(
                                    DocumentChunk.filename == filename
                                ).scalar() or 0
                        except Exception:
                            pass

                        # Create V1 version
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
                    logger.success(f"✅ Migrated {migrated_count} documents (skipped {skipped_count})")
                else:
                    logger.info(f"✓ All documents already have versions (checked {skipped_count} files)")
        except Exception as e:
            logger.warning(f"Version migration failed (non-critical): {e}")

        # Pre-load LLM at startup
        try:
            logger.info("⚡ Pre-loading LLM at startup...")
            await get_llm()
            logger.success("✅ LLM pre-loaded successfully")
        except Exception as e:
            logger.warning(f"⚠️ LLM pre-load failed (will lazy-load): {e}")

        # Optional: Start question generation
        if ENABLE_QUESTION_GENERATION:
            logger.info("📝 Starting background question generation...")
            asyncio.create_task(question_generation.generate_questions_pool_background())
        else:
            logger.info("⏭️  Question generation disabled")

        # Start schedulers
        global backup_scheduler_task, audit_cleanup_scheduler_task
        backup_scheduler_task = asyncio.create_task(scheduler_service.backup_scheduler())
        logger.info("🕐 Backup scheduler initialized")

        audit_cleanup_scheduler_task = asyncio.create_task(scheduler_service.audit_cleanup_scheduler())
        logger.info("🗑️ Audit log cleanup scheduler initialized")

        # Initialize Hybrid RAG Orchestrator (lazy)
        hybrid_rag_orchestrator = None
        logger.info("🔗 Hybrid RAG orchestrator ready (lazy initialization)")

        logger.success("✅ Application initialized successfully!")
        logger.info("💡 First chat request will load LLM automatically")

    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        raise


# ==================== Shutdown Event ====================

async def shutdown_event():
    """Cleanup on application shutdown"""
    global backup_scheduler_task, audit_cleanup_scheduler_task

    # Close PostgreSQL connection pool
    try:
        await close_db()
    except Exception as e:
        logger.warning(f"PostgreSQL cleanup error: {e}")

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
