"""
Web Server - FastAPI application
"""

import os
import json
import shutil
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, validator
from loguru import logger
from dotenv import load_dotenv
from starlette.types import Scope, Receive, Send

from .embeddings import EmbeddingModel
from .document_processor import DocumentProcessor
from .vector_db import VectorDB
from .llm import LLM, RAGSystem
from .document_tracker import DocumentTracker
from .cache_manager import CacheManager
from .model_manager import ModelManager
from .group_manager import GroupManager
from .conversation_manager import ConversationManager

# Load environment variables
load_dotenv()


# Custom StaticFiles with caching headers
class CachedStaticFiles(StaticFiles):
    """StaticFiles with aggressive browser caching for better performance"""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Wrap the send function to add cache headers
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                # Add cache control headers for static assets
                # Cache for 1 year (31536000 seconds) for versioned assets
                # Cache for 1 hour (3600 seconds) for HTML files
                path = scope.get("path", "")
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
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jinaai/jina-embeddings-v3")
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

# Initialize FastAPI
app = FastAPI(
    title="PDF RAG Chatbot",
    description="PDF 문서 기반 질의응답 챗봇",
    version="2.0.1"
)

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
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://cdn.jsdelivr.net https://unpkg.com; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )
        else:
            # Stricter CSP for main application
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )

        # HSTS only for HTTPS connections (uncomment in production with HTTPS)
        # if request.url.scheme == "https":
        #     response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


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

# Global instances (initialized on startup)
embedding_model: Optional[EmbeddingModel] = None
vector_db: Optional[VectorDB] = None
llm: Optional[LLM] = None
rag_system: Optional[RAGSystem] = None
cache_manager: Optional[CacheManager] = None
conversation_manager: Optional[ConversationManager] = None
suggested_questions_pool: list = []  # Pre-generated question pool
is_reindexing: bool = False  # Flag to track reindexing status
reindex_event: Optional[asyncio.Event] = None  # Event to signal reindex completion

# Status endpoint cache (to avoid rescanning on every request)
status_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 5  # Cache for 5 seconds
}


def invalidate_status_cache():
    """Invalidate status cache when documents change"""
    global status_cache
    status_cache["data"] = None
    status_cache["timestamp"] = 0


# Security: File content validation to prevent malicious uploads
async def validate_file_content(file: UploadFile, max_header_bytes: int = 1024) -> bool:
    """
    Validate file content by checking magic bytes (file signature)
    Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT

    Args:
        file: Uploaded file object
        max_header_bytes: Number of bytes to read for validation

    Returns:
        True if file is valid

    Raises:
        HTTPException: If file content is invalid or malicious
    """
    # Read first bytes for magic number validation
    header = await file.read(max_header_bytes)
    await file.seek(0)  # Reset file pointer

    # Get file extension
    filename = file.filename or ""
    file_ext = filename.lower().split('.')[-1] if '.' in filename else ""

    # Define magic bytes for each format
    PDF_SIGNATURE = b'%PDF'
    OLE2_SIGNATURE = b'\xd0\xcf\x11\xe0'  # Used by HWP, DOC, XLS, PPT
    ZIP_SIGNATURE = b'PK\x03\x04'  # Used by HWPX, DOCX, XLSX, PPTX
    HWP_SIGNATURE = b'HWP Document File'

    # Check if file starts with valid signature
    is_pdf = header.startswith(PDF_SIGNATURE)
    is_ole2 = header.startswith(OLE2_SIGNATURE)  # HWP, DOC, XLS, PPT
    is_zip = header.startswith(ZIP_SIGNATURE)  # HWPX, DOCX, XLSX, PPTX
    is_hwp_legacy = header.startswith(HWP_SIGNATURE)

    # Validate based on extension and signature combination
    valid = False

    if file_ext == 'pdf' and is_pdf:
        valid = True
    elif file_ext == 'hwp' and (is_ole2 or is_hwp_legacy):
        valid = True
    elif file_ext == 'hwpx' and is_zip:
        valid = True
    elif file_ext in ['doc', 'xls', 'ppt'] and is_ole2:
        valid = True
    elif file_ext in ['docx', 'xlsx', 'pptx'] and is_zip:
        valid = True
    elif file_ext == 'txt':
        # TXT files don't have magic bytes, but check for malicious content
        # Check for executable signatures
        if header.startswith(b'MZ') or header.startswith(b'\x7fELF'):
            raise HTTPException(
                status_code=400,
                detail="실행 파일은 업로드할 수 없습니다."
            )
        # Check for HTML/script content
        elif b'<script' in header.lower() or b'<html' in header.lower():
            raise HTTPException(
                status_code=400,
                detail="HTML 파일은 업로드할 수 없습니다."
            )
        # TXT files are text-based, allow them
        valid = True

    if not valid:
        # Try to detect malicious content
        if header.startswith(b'MZ') or header.startswith(b'\x7fELF'):
            raise HTTPException(
                status_code=400,
                detail="실행 파일은 업로드할 수 없습니다."
            )
        elif b'<script' in header.lower() or b'<html' in header.lower():
            raise HTTPException(
                status_code=400,
                detail="HTML 파일은 업로드할 수 없습니다."
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"파일 형식이 올바르지 않습니다. 지원 형식: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT"
            )

    return True


# Security: Filename validation to prevent path traversal
def validate_filename(filename: str) -> str:
    """
    Validate and sanitize filename to prevent path traversal attacks

    Args:
        filename: User-provided filename

    Returns:
        Sanitized filename safe for file operations

    Raises:
        HTTPException: If filename contains malicious patterns
    """
    import re

    # Remove any path components (get basename only)
    safe_name = os.path.basename(filename)

    # Block directory traversal attempts
    if '..' in safe_name or '/' in safe_name or '\\' in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 경로 문자가 포함되어 있습니다."
        )

    # Block null bytes (path truncation attack)
    if '\x00' in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 문자가 포함되어 있습니다."
        )

    # Only allow safe characters: alphanumeric, dash, underscore, dot, space, Korean
    # Korean Unicode range: \uAC00-\uD7A3 (Hangul syllables)
    if not re.match(r'^[\w\-. \uAC00-\uD7A3]+$', safe_name, re.UNICODE):
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 특수문자가 포함되어 있습니다."
        )

    # Check filename length
    if len(safe_name) > 255:
        raise HTTPException(
            status_code=400,
            detail="파일명이 너무 깁니다 (최대 255자)."
        )

    # Must have an extension
    if '.' not in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일 확장자가 필요합니다."
        )

    return safe_name


# Security: Sanitized error response helper
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


# Request/Response models
class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    temperature: float = 0.7
    max_tokens: int = 2048
    system_prompt: Optional[str] = None
    cache_threshold: float = 0.95
    cache_ttl: int = 60
    document_ids: Optional[list] = None  # Filter by specific document IDs/filenames
    group_ids: Optional[list] = None  # Filter by group IDs (OR logic)
    history: Optional[list] = None  # Conversation history [{"role": "user/assistant", "content": "..."}]
    session_id: Optional[str] = None  # Conversation session ID for history persistence

    @validator('question')
    def sanitize_question(cls, v):
        """Validate and sanitize question input to prevent XSS and injection"""
        import re
        import html

        # Check if empty
        if not v or not v.strip():
            raise ValueError("질문을 입력해주세요.")

        # Check length
        if len(v) > 10000:
            raise ValueError("질문이 너무 깁니다 (최대 10,000자).")

        # HTML escape to prevent XSS
        sanitized = html.escape(v)

        # Block obvious malicious patterns
        dangerous_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'onerror\s*=',
            r'onload\s*=',
            r'onclick\s*=',
            r'eval\s*\(',
            r'document\.cookie',
            r'<iframe[^>]*>',
            r'<embed[^>]*>',
            r'<object[^>]*>'
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, sanitized, re.IGNORECASE):
                raise ValueError("입력에 허용되지 않는 패턴이 포함되어 있습니다.")

        return sanitized

    @validator('system_prompt')
    def sanitize_system_prompt(cls, v):
        """Sanitize system prompt if provided"""
        import html

        if v is None:
            return v

        # Check length
        if len(v) > 5000:
            raise ValueError("시스템 프롬프트가 너무 깁니다 (최대 5,000자).")

        # HTML escape
        return html.escape(v)

    @validator('top_k')
    def validate_top_k(cls, v):
        """Validate top_k parameter"""
        if v < 1 or v > 50:
            raise ValueError("top_k는 1-50 사이의 값이어야 합니다.")
        return v

    @validator('temperature')
    def validate_temperature(cls, v):
        """Validate temperature parameter"""
        if v < 0 or v > 2:
            raise ValueError("temperature는 0-2 사이의 값이어야 합니다.")
        return v

    @validator('max_tokens')
    def validate_max_tokens(cls, v):
        """Validate max_tokens parameter"""
        if v < 1 or v > 8192:
            raise ValueError("max_tokens는 1-8192 사이의 값이어야 합니다.")
        return v


class QueryResponse(BaseModel):
    answer: str
    sources: list
    context: list


class LLMChangeRequest(BaseModel):
    llm_model: str


class EmbeddingChangeRequest(BaseModel):
    embedding_model: str


# Lazy loading functions for LLM (only load when needed)
async def get_llm() -> LLM:
    """Get LLM instance, loading it lazily on first use"""
    global llm
    if llm is None:
        logger.info("⚡ Loading LLM on first use (lazy loading)...")
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


@app.on_event("startup")
async def startup_event():
    """Initialize models and database on startup (fast startup with lazy loading)"""
    global embedding_model, vector_db, cache_manager, group_manager, conversation_manager, suggested_questions_pool, reindex_event

    try:
        logger.info("🚀 Starting application initialization (fast mode)...")

        # Initialize reindex event
        reindex_event = asyncio.Event()
        reindex_event.set()  # Initially set (not reindexing)

        # Initialize embedding model (required for search)
        logger.info("📚 Loading embedding model...")
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

        # Initialize cache manager with production settings
        logger.info("💾 Initializing cache manager...")

        # Production cache configuration
        cache_similarity_threshold = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", 0.95))
        cache_ttl = int(os.getenv("CACHE_TTL", 3600))  # Default 1 hour

        cache_manager = CacheManager(
            redis_client=vector_db.client,
            embedding_model=embedding_model.model,
            similarity_threshold=cache_similarity_threshold,
            cache_ttl=cache_ttl
        )

        logger.info(f"Cache configured: similarity={cache_similarity_threshold}, TTL={cache_ttl}s")

        # Initialize group manager
        logger.info("📁 Initializing group manager...")
        group_manager = GroupManager(redis_client=vector_db.client)

        # Initialize conversation manager
        logger.info("💬 Initializing conversation manager...")
        conversation_manager = ConversationManager(redis_client=vector_db.client)

        # Smart indexing: check if reindexing is needed
        await check_and_index_pdfs()

        # LLM will be loaded lazily on first chat request
        logger.info("⚡ LLM will load on first use (lazy loading enabled)")

        # Optional: Start question generation in background (only if enabled)
        if ENABLE_QUESTION_GENERATION:
            logger.info("📝 Starting background question generation (enabled in config)...")
            asyncio.create_task(generate_questions_pool_background())
        else:
            logger.info("⏭️  Question generation disabled (set ENABLE_QUESTION_GENERATION=true to enable)")

        logger.success("✅ Application initialized successfully! (Fast startup mode)")
        logger.info("💡 First chat request will load LLM automatically")
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        raise


async def _generate_questions_for_document(filename: str) -> list:
    """
    Generate Korean questions for a single document

    Args:
        filename: Name of the document file

    Returns:
        List of generated Korean questions
    """
    from mlx_lm import generate

    try:
        # Sample chunks from document
        docs = vector_db.sample_documents_by_filename(filename, limit=5)
        if not docs:
            return []

        # Create context from chunks
        context_text = "\n\n".join([
            f"{doc['text'][:800]}"
            for doc in docs[:5]
        ])

        # Generate questions using LLM
        system_content = "You must respond ONLY in Korean language. Never use English in your response."
        user_content = f"""다음은 "{filename}" 문서의 내용입니다. 이 문서를 읽고 한국어로 질문 12개를 생성하세요.

문서 내용:
{context_text}

다양한 유형의 질문을 만드세요:
1. 구체적 수치/기한: "임차보증금의 최대 한도는 얼마인가요?"
2. 절차/방법: "이사회 안건은 어떻게 제출하나요?"
3. 조건/기준: "징계 감경을 받을 수 있는 조건은 무엇인가요?"
4. 비교/차이: "문서규칙과 인사규정의 차이는 무엇인가요?"
5. 정의/개념: "전산업무관리지침에서 정의하는 시스템이란?"
6. 책임/담당: "비품 관리를 담당하는 부서는 어디인가요?"
7. 기한/기간: "연차 신청은 며칠 전까지 해야 하나요?"
8. 범위/대상: "출장비 지급 대상은 누구인가요?"

위 형식으로 한국어 질문 12개만 생성하세요 (번호 없이):"""

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

        prompt = llm.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        response = generate(
            llm.model,
            llm.tokenizer,
            prompt=prompt,
            max_tokens=1024
        )

        # Parse and filter questions
        lines = response.strip().split('\n')
        questions = []
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-') or '?' in line):
                question = line.lstrip('0123456789.-) ').strip()
                if question and len(question) > 10 and question.endswith('?'):
                    # Filter: Only include questions with Korean characters
                    if any('\uac00' <= char <= '\ud7a3' for char in question):
                        questions.append(question)

        return questions

    except Exception as e:
        logger.warning(f"Failed to generate questions for {filename}: {e}")
        return []


async def generate_questions_pool():
    """
    Generate 10+ Korean questions per PDF/HWP document
    Questions are stored with document metadata for tracking
    """
    global suggested_questions_pool

    try:
        # Get list of PDF and HWP files
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            return

        import itertools
        pdf_files = list(itertools.chain(
            data_path.glob("*.pdf"),
            data_path.glob("*.hwp")
        ))
        if not pdf_files:
            return

        logger.info(f"Generating questions for {len(pdf_files)} documents in parallel...")
        all_questions = []

        # Generate questions for each document in parallel using asyncio.gather()
        tasks = [_generate_questions_for_document(pdf_file.name) for pdf_file in pdf_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for pdf_file, doc_questions in zip(pdf_files, results):
            if isinstance(doc_questions, Exception):
                logger.warning(f"  • {pdf_file.name}: Failed - {doc_questions}")
                continue
            if doc_questions:
                all_questions.extend(doc_questions)
                logger.info(f"  • {pdf_file.name}: {len(doc_questions)} questions generated")

        # Store unique Korean-only questions in the pool
        suggested_questions_pool = list(set(all_questions))
        logger.info(f"Total unique questions: {len(suggested_questions_pool)}")

    except Exception as e:
        logger.error(f"Failed to generate questions pool: {e}")
        # Set fallback questions
        suggested_questions_pool = [
            "이 문서의 주요 내용은 무엇인가요?",
            "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
            "이 문서를 간단히 요약해주세요.",
            "문서에서 다루는 핵심 주제는 무엇인가요?",
            "이 문서에서 얻을 수 있는 주요 정보는 무엇인가요?"
        ]


async def generate_questions_pool_background():
    """
    Background task wrapper for question generation
    Runs asynchronously without blocking server startup
    """
    try:
        logger.info("📝 Background: Generating question pool for all documents...")
        start_time = asyncio.get_event_loop().time()

        await generate_questions_pool()

        elapsed = asyncio.get_event_loop().time() - start_time
        logger.success(f"✅ Question pool ready! Generated {len(suggested_questions_pool)} questions in {elapsed:.1f}s")
    except Exception as e:
        logger.error(f"❌ Background question generation failed: {e}")
        logger.warning("App will continue with empty question pool")


async def generate_questions_for_new_documents(new_files: list):
    """
    Generate questions for newly added documents
    Called when new documents are detected and indexed
    """
    global suggested_questions_pool

    try:
        logger.info(f"Generating questions for {len(new_files)} new documents in parallel...")
        new_questions = []

        # Generate questions for each new document in parallel using asyncio.gather()
        tasks = [_generate_questions_for_document(filename) for filename in new_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for filename, doc_questions in zip(new_files, results):
            if isinstance(doc_questions, Exception):
                logger.warning(f"  • {filename}: Failed - {doc_questions}")
                continue
            if doc_questions:
                new_questions.extend(doc_questions)
                logger.info(f"  • {filename}: {len(doc_questions)} new questions generated")

        # Add new questions to existing pool (keep unique)
        suggested_questions_pool = list(set(suggested_questions_pool + new_questions))
        logger.success(f"Added {len(new_questions)} new questions. Total: {len(suggested_questions_pool)}")

    except Exception as e:
        logger.error(f"Failed to generate questions for new documents: {e}")


async def check_and_index_pdfs():
    """
    Smart indexing: Check if reindexing is needed and perform if necessary
    """
    try:
        # Initialize document tracker
        doc_tracker = DocumentTracker(data_dir=DATA_DIR)

        # Check if database is already indexed
        is_indexed = vector_db.is_indexed()

        if not is_indexed:
            # No documents in database - perform initial indexing
            logger.info("Database is empty. Performing initial indexing...")
            await index_pdfs(doc_tracker)
            return

        # Database has documents - check for changes
        logger.info("Checking for document changes...")
        change_summary = doc_tracker.get_change_summary()

        if not change_summary["needs_reindex"]:
            # No changes detected
            doc_count = vector_db.count_documents()
            logger.success(f"No document changes detected. Using existing index ({doc_count} documents)")
            return

        # Changes detected - show summary
        logger.warning("Document changes detected:")
        new_files_list = []
        if change_summary["new_files"]:
            new_files_list = change_summary['new_files']
            logger.info(f"  • New files ({len(new_files_list)}): {new_files_list}")
        if change_summary["modified_files"]:
            logger.info(f"  • Modified files ({len(change_summary['modified_files'])}): {change_summary['modified_files']}")
        if change_summary["deleted_files"]:
            logger.info(f"  • Deleted files ({len(change_summary['deleted_files'])}): {change_summary['deleted_files']}")

        # Reindex
        logger.info("Reindexing required. Clearing old index...")
        vector_db.clear_index()
        await index_pdfs(doc_tracker)

        # Generate questions for new documents
        if new_files_list:
            logger.info("Generating questions for new documents...")
            await generate_questions_for_new_documents(new_files_list)

    except Exception as e:
        logger.error(f"Smart indexing failed: {e}")
        # Fallback to regular indexing
        logger.info("Falling back to regular indexing...")
        doc_tracker = DocumentTracker(data_dir=DATA_DIR)
        await index_pdfs(doc_tracker)


async def index_pdfs(doc_tracker: DocumentTracker):
    """
    Process and index all documents (PDF and HWP)

    Args:
        doc_tracker: DocumentTracker instance
    """
    try:
        logger.info(f"Processing documents from {DATA_DIR}...")

        # Process all documents (PDF and HWP)
        doc_processor = DocumentProcessor(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        chunks = doc_processor.process_directory(DATA_DIR)

        if not chunks:
            logger.warning("No chunks created from documents")
            return

        # Create embeddings
        logger.info(f"Creating embeddings for {len(chunks)} chunks...")
        texts = [chunk["text"] for chunk in chunks]
        embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=True)

        # Add to vector database
        logger.info("Adding documents to vector database...")
        vector_db.add_documents(chunks, embeddings)

        # Save metadata for future change detection
        logger.info("Saving document metadata...")
        doc_tracker.update_metadata()

        # Save index state to Redis
        from datetime import datetime
        index_state = {
            "indexed_at": datetime.now().isoformat(),
            "total_chunks": len(chunks),
            "total_files": len(set(chunk["filename"] for chunk in chunks))
        }
        vector_db.save_index_state(index_state)

        logger.success(f"Indexed {len(chunks)} chunks from {len(set(chunk['filename'] for chunk in chunks))} documents")
    except Exception as e:
        logger.error(f"Failed to index documents: {e}")
        raise


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main page"""
    index_file = static_path / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return index_file.read_text(encoding="utf-8")


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Query endpoint for chatbot (with lazy LLM loading)
    """
    # Wait for reindexing to complete if in progress
    if is_reindexing:
        logger.info(f"⏳ Query waiting for reindex to complete...")
        await reindex_event.wait()
        logger.info(f"✅ Reindex complete, processing query")

    try:
        # Save user question to conversation history
        if request.session_id and conversation_manager:
            conversation_manager.add_message(
                session_id=request.session_id,
                role="user",
                content=request.question
            )
            logger.debug(f"💬 Saved user message to session {request.session_id}")

        # Lazy load RAG system on first use
        rag = await get_rag_system()

        # Create query embedding
        query_embedding = embedding_model.encode(request.question)[0]

        # Query RAG system
        result = rag.query(
            question=request.question,
            query_embedding=query_embedding,
            top_k=request.top_k,
            history=request.history,
            document_ids=request.document_ids,
            group_ids=request.group_ids
        )

        # Save assistant response to conversation history
        if request.session_id and conversation_manager:
            metadata = {
                "sources": result["sources"],
                "chunk_count": len(result["context"])
            }
            conversation_manager.add_message(
                session_id=request.session_id,
                role="assistant",
                content=result["answer"],
                metadata=metadata
            )
            logger.debug(f"💬 Saved assistant response to session {request.session_id}")

        return QueryResponse(
            answer=result["answer"],
            sources=result["sources"],
            context=[
                {
                    "text": doc["text"][:200] + "..." if len(doc["text"]) > 200 else doc["text"],
                    "filename": doc["filename"],
                    "score": doc["score"]
                }
                for doc in result["context"]
            ]
        )
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "query endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/query/stream")
async def query_stream(request: QueryRequest):
    """
    Streaming query endpoint for chatbot with caching (with lazy LLM loading)
    """
    # Wait for reindexing to complete if in progress
    if is_reindexing:
        logger.info(f"⏳ Streaming query waiting for reindex to complete...")
        await reindex_event.wait()
        logger.info(f"✅ Reindex complete, processing streaming query")

    try:
        # Save user question to conversation history
        if request.session_id and conversation_manager:
            conversation_manager.add_message(
                session_id=request.session_id,
                role="user",
                content=request.question
            )
            logger.debug(f"💬 Saved user message to session {request.session_id}")

        # Lazy load RAG system on first use
        rag = await get_rag_system()

        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        # Check cache first
        cached_response = cache_manager.get_cached_response(
            question=request.question,
            top_k=request.top_k,
            similarity_threshold=request.cache_threshold,
            document_ids=request.document_ids,
            group_ids=request.group_ids
        )

        if cached_response:
            # Cache HIT - return cached response as stream
            logger.info(f"✅ Cache HIT (similarity: {cached_response['similarity']:.4f})")

            context_data = {
                "sources": cached_response["sources"],
                "context": cached_response.get("context", []),  # Use cached context for source details
                "cached": True,
                "similarity": cached_response["similarity"]
            }

            # Save cached response to conversation history
            if request.session_id and conversation_manager:
                metadata = {
                    "sources": cached_response["sources"],
                    "cached": True,
                    "similarity": cached_response["similarity"]
                }
                conversation_manager.add_message(
                    session_id=request.session_id,
                    role="assistant",
                    content=cached_response["response"],
                    metadata=metadata
                )
                logger.debug(f"💬 Saved cached response to session {request.session_id}")

            async def generate_cached_stream():
                # Send metadata with cache indicator
                yield f"data: {json.dumps({'type': 'metadata', 'data': context_data})}\n\n"

                # Stream cached response character by character for smooth UX
                response_text = cached_response["response"]
                chunk_size = 8  # Characters per chunk

                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"
                    # Small delay to simulate streaming
                    import asyncio
                    await asyncio.sleep(0.01)

                # Send completion message
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return StreamingResponse(
                generate_cached_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )

        # Cache MISS - generate new response
        logger.info("❌ Cache MISS - generating new response")

        # Create query embedding (run in thread pool to avoid blocking)
        query_embedding = await asyncio.to_thread(
            lambda: embedding_model.encode(request.question)[0]
        )

        # Query RAG system with streaming (run in thread pool to avoid blocking)
        result = await asyncio.to_thread(
            rag.query,
            question=request.question,
            query_embedding=query_embedding,
            top_k=request.top_k,
            stream=True,
            history=request.history,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            system_prompt=request.system_prompt,
            document_ids=request.document_ids,
            group_ids=request.group_ids
        )

        # Prepare context and sources for the first message
        context_data = {
            "sources": result["sources"],
            "context": [
                {
                    "text": doc["text"],  # Send full text for accurate source details
                    "filename": doc["filename"],
                    "score": doc["score"]
                }
                for doc in result["context"]
            ],
            "cached": False
        }

        # Collect response for caching and conversation history
        full_response = []

        async def generate_stream():
            # First, send sources and context
            yield f"data: {json.dumps({'type': 'metadata', 'data': context_data})}\n\n"

            # Then stream the answer
            for chunk in result["answer"]:
                if chunk:
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"

            # Save to cache after completion
            complete_response = ''.join(full_response)
            cache_manager.save_to_cache(
                question=request.question,
                response=complete_response,
                sources=result["sources"],
                top_k=request.top_k,
                cache_ttl=request.cache_ttl,
                context=context_data["context"],  # Save context for source details
                document_ids=request.document_ids,  # Include document filter in cache key
                group_ids=request.group_ids  # Include group filter in cache key
            )
            logger.info(f"💾 Saved response to cache for question: '{request.question[:50]}...'")

            # Save assistant response to conversation history
            if request.session_id and conversation_manager:
                metadata = {
                    "sources": result["sources"],
                    "chunk_count": len(result["context"]),
                    "cached": False
                }
                conversation_manager.add_message(
                    session_id=request.session_id,
                    role="assistant",
                    content=complete_response,
                    metadata=metadata
                )
                logger.debug(f"💬 Saved assistant response to session {request.session_id}")

            # Send completion message
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "streaming query endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/reindex")
async def reindex():
    """
    Force reindex all PDFs
    """
    global is_reindexing, reindex_event

    try:
        # Set reindexing flag and clear event to block search requests
        is_reindexing = True
        reindex_event.clear()  # Clear event to signal reindexing in progress
        logger.info("🔄 Force reindexing PDFs... (search requests will wait)")

        doc_tracker = DocumentTracker(data_dir=DATA_DIR)

        # Clear existing index
        vector_db.clear_index()

        # Clear metadata to force reindexing
        doc_tracker.clear_metadata()

        # Reindex
        await index_pdfs(doc_tracker)

        # Invalidate status cache (documents reindexed)
        invalidate_status_cache()

        # Clear document count cache (all documents reindexed)
        vector_db.clear_document_count_cache()

        # Synchronize group document counts after reindexing
        group_manager.sync_document_counts()

        logger.success("✅ Reindexing completed (search enabled)")

        return {
            "message": "Reindexing completed successfully",
            "document_count": vector_db.count_documents()
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "reindex endpoint")
        raise HTTPException(status_code=500, detail=safe_message)
    finally:
        # Always clear the flag and set the event, even if reindexing fails
        is_reindexing = False
        reindex_event.set()  # Signal completion to waiting queries
        logger.info("🔓 Reindex completed, releasing waiting queries")


@app.get("/api/cache/stats")
async def get_cache_stats():
    """
    Get cache statistics
    """
    try:
        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        stats = cache_manager.get_cache_stats()
        return stats
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "cache stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/cache/clear")
async def clear_cache():
    """
    Clear all cached responses
    """
    try:
        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        count = cache_manager.clear_cache()
        return {
            "message": "Cache cleared successfully",
            "entries_cleared": count
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "clear cache endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/documents")
async def list_documents():
    """
    List all indexed documents with metadata (optimized with batch queries)
    Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT
    """
    try:
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            return {"documents": []}

        # Get all supported document files
        import itertools
        all_files = list(itertools.chain(
            data_path.glob("*.pdf"),
            data_path.glob("*.hwp"),
            data_path.glob("*.hwpx"),
            data_path.glob("*.doc"),
            data_path.glob("*.docx"),
            data_path.glob("*.xls"),
            data_path.glob("*.xlsx"),
            data_path.glob("*.ppt"),
            data_path.glob("*.pptx"),
            data_path.glob("*.txt")
        ))

        if not all_files:
            return {"documents": [], "total_count": 0}

        # Batch count chunks for all files at once (avoids N+1 queries)
        filenames = [f.name for f in all_files]
        chunk_counts = {}
        if vector_db:
            try:
                chunk_counts = vector_db.batch_count_documents_by_filenames(filenames)
            except Exception as e:
                logger.error(f"Failed to batch count documents: {e}")
                # Fall back to zero counts
                chunk_counts = {filename: 0 for filename in filenames}

        # Build document list with pre-fetched chunk counts
        documents = []
        for pdf_file in all_files:
            # Get file stats
            stat = pdf_file.stat()

            # Get chunk count from batch result
            chunk_count = chunk_counts.get(pdf_file.name, 0)

            documents.append({
                "id": pdf_file.name,  # Use filename as ID for filtering
                "name": pdf_file.name,  # Display name
                "filename": pdf_file.name,  # Keep for backward compatibility
                "size": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),  # For JavaScript formatDate
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),  # Keep for backward compatibility
                "chunk_count": chunk_count,
                "indexed": chunk_count > 0
            })

        # Sort by modified date (newest first)
        documents.sort(key=lambda x: x["created_at"], reverse=True)

        return {
            "documents": documents,
            "total_count": len(documents)
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "list documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/documents/{filename}/chunks")
async def get_document_chunks(filename: str):
    """
    Get all chunks for a specific document
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        if not vector_db:
            raise HTTPException(status_code=500, detail="Vector database not available")

        # Get chunks for this document from vector DB
        chunks = vector_db.get_chunks_by_filename(safe_filename)

        if not chunks:
            return {
                "filename": safe_filename,
                "chunks": [],
                "total_count": 0,
                "message": "No chunks found for this document"
            }

        # Format chunks for display
        formatted_chunks = []
        for i, chunk in enumerate(chunks, 1):
            formatted_chunks.append({
                "index": i,
                "text": chunk.get("text", ""),
                "page": chunk.get("page", "N/A"),
                "metadata": chunk.get("metadata", {})
            })

        return {
            "filename": safe_filename,
            "chunks": formatted_chunks,
            "total_count": len(formatted_chunks)
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "get document chunks endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a new document and automatically index it
    Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX
    (Max file size: configurable via MAX_FILE_SIZE_MB, default 100MB)
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(file.filename)

        # Validate file type (extension check)
        allowed_extensions = ['.pdf', '.hwp', '.hwpx', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
        if not any(safe_filename.endswith(ext) for ext in allowed_extensions):
            raise HTTPException(
                status_code=400,
                detail="지원되지 않는 파일 형식입니다. 지원 형식: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT"
            )

        # Security: Validate file content (magic bytes check)
        await validate_file_content(file)

        # Create data directory if it doesn't exist
        data_path = Path(DATA_DIR)
        data_path.mkdir(parents=True, exist_ok=True)

        # Save uploaded file path (using validated filename)
        file_path = data_path / safe_filename

        # Check if file already exists (filename collision)
        if file_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"File '{safe_filename}' already exists. Please delete it first or rename your file."
            )

        # Stream file to disk while calculating hash (memory-efficient)
        # Uses chunked reading to avoid loading entire file into memory
        file_hash = hashlib.md5()
        file_size = 0
        chunk_size = 8192  # 8KB chunks

        try:
            with file_path.open("wb") as buffer:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break

                    # Check file size limit during streaming
                    file_size += len(chunk)
                    if file_size > MAX_FILE_SIZE:
                        # Remove partial file
                        file_path.unlink(missing_ok=True)
                        file_size_mb = file_size / 1024 / 1024
                        raise HTTPException(
                            status_code=413,
                            detail=f"파일 크기({file_size_mb:.1f}MB)가 너무 큽니다. 최대 {MAX_FILE_SIZE_MB}MB까지 업로드 가능합니다."
                        )

                    # Write chunk and update hash
                    buffer.write(chunk)
                    file_hash.update(chunk)

        except HTTPException:
            raise
        except Exception as e:
            # Clean up partial file on error
            file_path.unlink(missing_ok=True)
            logger.error(f"Failed to save file: {e}")
            # Security: Use sanitized error message (prevents information disclosure)
            safe_message = get_safe_error_message(e, "file save operation")
            raise HTTPException(status_code=500, detail=safe_message)

        # Get final hash
        file_hash_hex = file_hash.hexdigest()

        # Check for duplicate content using Redis
        hash_key = f"doc:hash:{file_hash_hex}"
        existing_filename = vector_db.client.get(hash_key)

        if existing_filename:
            # Remove the newly uploaded file (it's a duplicate)
            file_path.unlink(missing_ok=True)
            existing_filename = existing_filename.decode('utf-8') if isinstance(existing_filename, bytes) else existing_filename
            raise HTTPException(
                status_code=409,
                detail=f"이 파일과 동일한 내용의 문서가 이미 업로드되어 있습니다: '{existing_filename}'. 같은 파일을 다시 업로드할 필요가 없습니다."
            )

        logger.info(f"Uploaded file: {safe_filename}")

        # Process and index the new document (PDF or HWP)
        try:
            doc_processor = DocumentProcessor(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP
            )

            # Process single file (automatically detects PDF or HWP)
            chunks = doc_processor.process_document(str(file_path))

            if not chunks:
                logger.warning(f"No chunks created from {safe_filename}")
                return {
                    "message": "File uploaded but no content could be extracted",
                    "filename": safe_filename,
                    "indexed": False
                }

            # Create embeddings
            logger.info(f"Creating embeddings for {len(chunks)} chunks from {safe_filename}...")
            texts = [chunk["text"] for chunk in chunks]
            embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=False)

            # Add to vector database
            vector_db.add_documents(chunks, embeddings)

            # Update document tracker
            doc_tracker = DocumentTracker(data_dir=DATA_DIR)
            doc_tracker.update_metadata()

            logger.success(f"Indexed {len(chunks)} chunks from {safe_filename}")

            # Store file hash to prevent future duplicates
            vector_db.client.set(hash_key, safe_filename)
            logger.info(f"Stored file hash for duplicate detection: {file_hash_hex[:8]}...")

            # Invalidate status cache (document set changed)
            invalidate_status_cache()

            # Clear document count cache (new document added)
            vector_db.clear_document_count_cache()

            # Automatically assign new document to default group (미분류)
            try:
                default_group_id = group_manager.get_default_group_id()
                group_manager.assign_document(safe_filename, default_group_id)
                logger.info(f"Assigned {safe_filename} to default group (미분류)")
            except Exception as e:
                logger.warning(f"Failed to assign document to default group: {e}")
                # Don't fail the upload if group assignment fails

            # Get file stats
            stat = file_path.stat()

            return {
                "message": "File uploaded and indexed successfully",
                "filename": safe_filename,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "chunk_count": len(chunks),
                "indexed": True
            }

        except Exception as e:
            # If indexing fails, remove the uploaded file
            logger.error(f"Failed to index {safe_filename}: {e}")
            if file_path.exists():
                file_path.unlink()
            # Security: Use sanitized error message (prevents information disclosure)
            safe_message = get_safe_error_message(e, "document indexing")
            raise HTTPException(status_code=500, detail=safe_message)

    except HTTPException:
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "upload endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    """
    Delete a PDF document and remove it from the index
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(filename)

        data_path = Path(DATA_DIR)
        file_path = data_path / safe_filename

        # Check if file exists
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{safe_filename}' not found")

        # Calculate hash before deletion to remove from hash registry
        try:
            with file_path.open("rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
                hash_key = f"doc:hash:{file_hash}"
                vector_db.client.delete(hash_key)
                logger.info(f"Removed file hash from registry: {file_hash[:8]}...")
        except Exception as e:
            logger.error(f"Failed to remove file hash: {e}")
            # Continue with deletion even if hash removal fails

        # Delete from vector database
        if vector_db:
            try:
                deleted_count = vector_db.delete_by_filename(safe_filename)
                logger.info(f"Deleted {deleted_count} chunks for {safe_filename} from vector DB")
            except Exception as e:
                logger.error(f"Failed to delete from vector DB: {e}")
                # Continue with file deletion even if vector DB deletion fails

        # Remove document from all groups
        try:
            group_manager.delete_document_from_all_groups(safe_filename)
            logger.info(f"Removed {safe_filename} from all groups")
        except Exception as e:
            logger.warning(f"Failed to remove document from groups: {e}")
            # Continue with file deletion even if group removal fails

        # Delete file
        file_path.unlink()
        logger.info(f"Deleted file: {safe_filename}")

        # Update document tracker
        try:
            doc_tracker = DocumentTracker(data_dir=DATA_DIR)
            doc_tracker.update_metadata()
        except Exception as e:
            logger.error(f"Failed to update document tracker: {e}")

        # Clear cache since document set has changed
        if cache_manager:
            try:
                cache_manager.clear_cache()
                logger.info("Cleared cache after document deletion")
            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")

        # Invalidate status cache (document set changed)
        invalidate_status_cache()

        # Clear document count cache (document deleted)
        vector_db.clear_document_count_cache()

        return {
            "message": f"Document '{safe_filename}' deleted successfully",
            "filename": safe_filename,
            "chunks_removed": deleted_count if vector_db else 0
        }

    except HTTPException:
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "delete endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/status")
async def status():
    """
    Get system status with detailed information (cached for performance)
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
            except:
                pass

        # System is ready if documents are indexed (LLM loads on first use)
        is_ready = (chunk_count > 0) or (rag_system is not None)

        # Determine status: reindexing > ready > initializing
        if is_reindexing:
            status_value = "reindexing"
        elif is_ready:
            status_value = "ready"
        else:
            status_value = "initializing"

        response = {
            "status": status_value,
            "document_count": chunk_count,  # 하위 호환성 유지
            "chunk_count": chunk_count,
            "pdf_count": pdf_count,
            "embedding_model": EMBEDDING_MODEL,
            "llm_model": LLM_MODEL,
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


@app.get("/api/models")
async def list_available_models():
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


@app.post("/api/change-llm")
async def change_llm(request: LLMChangeRequest):
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


@app.post("/api/change-embedding")
async def change_embedding(request: EmbeddingChangeRequest):
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
        embedding_model = EmbeddingModel(
            model_name=EMBEDDING_MODEL,
            model_dir=MODEL_DIR
        )

        # Reinitialize vector DB with new embedding model
        vector_db = VectorDB(
            embedding_model=embedding_model,
            redis_host=REDIS_HOST,
            redis_port=REDIS_PORT
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


@app.get("/api/suggested-questions")
async def get_suggested_questions():
    """
    Get suggested questions from pre-generated pool
    Fast response by sampling from startup-generated questions
    """
    try:
        import random

        # Use pre-generated question pool for fast response
        if not suggested_questions_pool:
            # Fallback if pool is empty
            logger.warning("Question pool is empty, using fallback questions")
            return {
                "questions": [
                    "이 문서의 주요 내용은 무엇인가요?",
                    "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
                    "이 문서를 간단히 요약해주세요.",
                    "문서에서 다루는 핵심 주제는 무엇인가요?",
                    "이 문서에서 얻을 수 있는 주요 정보는 무엇인가요?"
                ]
            }

        # Sample 50 random questions from the pool for better autocomplete coverage
        num_questions = min(50, len(suggested_questions_pool))
        selected_questions = random.sample(suggested_questions_pool, num_questions)

        logger.info(f"Returning {num_questions} questions from pool of {len(suggested_questions_pool)}")
        return {"questions": selected_questions}

    except Exception as e:
        logger.error(f"Failed to get suggested questions: {e}")
        return {
            "questions": [
                "이 문서의 주요 내용은 무엇인가요?",
                "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
                "이 문서를 간단히 요약해주세요."
            ]
        }


# ============================================================================
# Group Management API Endpoints
# ============================================================================

class GroupCreateRequest(BaseModel):
    name: str
    description: str = ""
    color: str = "#3B82F6"
    icon: str = "📁"
    parent_id: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class GroupMoveRequest(BaseModel):
    new_parent_id: Optional[str] = None


class DocumentAssignRequest(BaseModel):
    group_id: str


class BatchDocumentAssignRequest(BaseModel):
    filenames: List[str]


@app.get("/api/groups")
async def list_groups():
    """
    Get all groups with hierarchy

    Returns:
        List of all groups with their metadata and tree structure
    """
    try:
        groups = group_manager.get_all_groups()
        tree = group_manager.get_group_tree()

        return {
            "groups": groups,
            "tree": tree
        }
    except Exception as e:
        logger.error(f"Failed to list groups: {e}")
        safe_message = get_safe_error_message(e, "list groups endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/groups")
async def create_group(request: GroupCreateRequest):
    """
    Create a new group

    Args:
        request: Group creation parameters

    Returns:
        Created group ID and details
    """
    try:
        group_id = group_manager.create_group(
            name=request.name,
            description=request.description,
            color=request.color,
            icon=request.icon,
            parent_id=request.parent_id,
            created_by="system"
        )

        if not group_id:
            raise HTTPException(status_code=400, detail="Failed to create group")

        group = group_manager.get_group(group_id)
        logger.info(f"Created group: {group_id} ({request.name})")

        return {
            "success": True,
            "group_id": group_id,
            "group": group
        }
    except ValueError as e:
        # Validation errors (e.g., invalid parent_id)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create group: {e}")
        safe_message = get_safe_error_message(e, "create group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.put("/api/groups/{group_id}")
async def update_group(group_id: str, request: GroupUpdateRequest):
    """
    Update group metadata

    Args:
        group_id: ID of the group to update
        request: Fields to update

    Returns:
        Updated group details
    """
    try:
        # Build update dict from non-None fields
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.color is not None:
            updates["color"] = request.color
        if request.icon is not None:
            updates["icon"] = request.icon

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        success = group_manager.update_group(
            group_id=group_id,
            updated_by="system",
            **updates
        )

        if not success:
            raise HTTPException(status_code=404, detail="Group not found")

        group = group_manager.get_group(group_id)
        logger.info(f"Updated group: {group_id}")

        return {
            "success": True,
            "group": group
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update group: {e}")
        safe_message = get_safe_error_message(e, "update group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.delete("/api/groups/{group_id}")
async def delete_group(group_id: str, reassign_to: Optional[str] = None):
    """
    Delete a group and reassign its documents

    Args:
        group_id: ID of the group to delete
        reassign_to: Group ID to reassign documents to (defaults to parent or default group)

    Returns:
        Number of documents reassigned
    """
    try:
        # Prevent deletion of default group
        default_group_id = group_manager.get_default_group_id()
        if group_id == default_group_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete default group"
            )

        reassigned_count = group_manager.delete_group(
            group_id=group_id,
            reassign_to=reassign_to
        )

        logger.info(f"Deleted group: {group_id}, reassigned {reassigned_count} documents")

        return {
            "success": True,
            "reassigned_documents": reassigned_count
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete group: {e}")
        safe_message = get_safe_error_message(e, "delete group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.patch("/api/groups/{group_id}/move")
async def move_group(group_id: str, request: GroupMoveRequest):
    """
    Move a group to a new parent (change hierarchy)

    Args:
        group_id: ID of the group to move
        request: New parent group ID

    Returns:
        Updated group details
    """
    try:
        success = group_manager.move_group(
            group_id=group_id,
            new_parent_id=request.new_parent_id,
            updated_by="system"
        )

        if not success:
            raise HTTPException(status_code=404, detail="Group not found")

        group = group_manager.get_group(group_id)
        logger.info(f"Moved group: {group_id} to parent {request.new_parent_id}")

        return {
            "success": True,
            "group": group
        }
    except ValueError as e:
        # Circular reference or validation errors
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to move group: {e}")
        safe_message = get_safe_error_message(e, "move group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.put("/api/documents/{filename}/group")
async def assign_document_to_group(filename: str, request: DocumentAssignRequest):
    """
    Assign a document to a group

    Args:
        filename: Document filename
        request: Target group ID

    Returns:
        Success status
    """
    try:
        success = group_manager.assign_document(
            filename=filename,
            group_id=request.group_id
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Document or group not found"
            )

        logger.info(f"Assigned document '{filename}' to group {request.group_id}")

        return {
            "success": True,
            "filename": filename,
            "group_id": request.group_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign document: {e}")
        safe_message = get_safe_error_message(e, "assign document endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/groups/{group_id}/documents")
async def batch_assign_documents(group_id: str, request: BatchDocumentAssignRequest):
    """
    Batch assign multiple documents to a group

    Args:
        group_id: Target group ID
        request: List of filenames to assign

    Returns:
        Number of documents successfully assigned
    """
    try:
        assigned_count = group_manager.batch_assign_documents(
            filenames=request.filenames,
            group_id=group_id
        )

        logger.info(f"Batch assigned {assigned_count}/{len(request.filenames)} documents to group {group_id}")

        return {
            "success": True,
            "assigned_count": assigned_count,
            "total_requested": len(request.filenames)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to batch assign documents: {e}")
        safe_message = get_safe_error_message(e, "batch assign documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.delete("/api/groups/{group_id}/documents/{filename}")
async def remove_document_from_group(group_id: str, filename: str):
    """
    Remove a document from a group (reassigns to default group)

    Args:
        group_id: Group ID to remove document from
        filename: Document filename to remove

    Returns:
        Success status
    """
    try:
        success = group_manager.remove_document_from_group(
            filename=filename,
            group_id=group_id
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="문서 또는 그룹을 찾을 수 없습니다."
            )

        logger.info(f"Removed document '{filename}' from group {group_id}")

        return {
            "success": True,
            "filename": filename,
            "group_id": group_id,
            "message": "문서가 기본 그룹으로 이동되었습니다."
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove document from group: {e}")
        safe_message = get_safe_error_message(e, "remove document from group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/groups/{group_id}/documents")
async def list_group_documents(group_id: str):
    """
    Get all documents in a group

    Args:
        group_id: Group ID to query

    Returns:
        List of document filenames in the group
    """
    try:
        documents = group_manager.get_group_documents(group_id)

        return {
            "group_id": group_id,
            "documents": documents,
            "count": len(documents)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list group documents: {e}")
        safe_message = get_safe_error_message(e, "list group documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/groups/sync-counts")
async def sync_group_document_counts():
    """
    Synchronize document counts for all groups
    Recalculates counts from actual SET cardinality
    """
    try:
        group_manager.sync_document_counts()
        return {"status": "success", "message": "그룹별 문서 개수가 동기화되었습니다"}
    except Exception as e:
        logger.error(f"Failed to sync document counts: {e}")
        safe_message = get_safe_error_message(e, "sync document counts endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


# ============================================================================
# Conversation History API Endpoints
# ============================================================================

@app.post("/api/conversations")
async def create_conversation(title: str = None):
    """
    Create a new conversation session

    Args:
        title: Optional conversation title

    Returns:
        Session ID and metadata
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        session_id = conversation_manager.create_session(title=title)
        session = conversation_manager.get_session(session_id)

        return {
            "session_id": session_id,
            "session": session
        }
    except Exception as e:
        logger.error(f"Failed to create conversation: {e}")
        safe_message = get_safe_error_message(e, "create conversation endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/conversations")
async def list_conversations(limit: int = 50, offset: int = 0):
    """
    List conversation sessions (sorted by most recent)

    Args:
        limit: Maximum number of sessions to return
        offset: Number of sessions to skip

    Returns:
        List of conversation sessions
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        sessions = conversation_manager.list_sessions(limit=limit, offset=offset)
        total_count = conversation_manager.get_session_count()

        return {
            "sessions": sessions,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Failed to list conversations: {e}")
        safe_message = get_safe_error_message(e, "list conversations endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/conversations/{session_id}")
async def get_conversation(session_id: str, limit: int = None, offset: int = 0):
    """
    Get conversation session with messages

    Args:
        session_id: Conversation session ID
        limit: Maximum number of messages to return (None = all)
        offset: Number of messages to skip

    Returns:
        Session metadata and messages
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        session = conversation_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Conversation {session_id} not found")

        messages = conversation_manager.get_messages(session_id, limit=limit, offset=offset)

        return {
            "session": session,
            "messages": messages,
            "message_count": len(messages)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversation: {e}")
        safe_message = get_safe_error_message(e, "get conversation endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.delete("/api/conversations/{session_id}")
async def delete_conversation(session_id: str):
    """
    Delete a conversation session and all its messages

    Args:
        session_id: Conversation session ID

    Returns:
        Success message
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        success = conversation_manager.delete_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Conversation {session_id} not found")

        return {
            "status": "success",
            "message": f"Conversation {session_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}")
        safe_message = get_safe_error_message(e, "delete conversation endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


# ============================================================================
# Follow-up Questions API
# ============================================================================

class FollowUpRequest(BaseModel):
    question: str
    answer: str
    context: Optional[list] = []


@app.post("/api/follow-up-questions")
async def generate_follow_up_questions(request: FollowUpRequest):
    """
    Generate smart follow-up questions based on current conversation context
    """
    try:
        if not llm:
            raise HTTPException(status_code=503, detail="LLM not initialized")

        # Use direct mlx_lm.generate for more deterministic output
        from mlx_lm import generate as mlx_generate

        # Create simple completion prompt - pattern-based
        prompt = f"""다음 예시를 참고하여 관련 질문 3개를 한국어로 생성하세요.

질문: 계약서 작성 방법은?
답변: 계약서는 양식에 따라 작성하며 필요 서류를 첨부합니다.
관련 질문:
- 계약 기간은 얼마나 되나요?
- 계약 해지 시 절차는 어떻게 되나요?
- 계약서 양식은 어디서 받을 수 있나요?

질문: 출장비 신청 절차는?
답변: 출장비는 사전에 신청하며 견적서를 제출합니다.
관련 질문:
- 출장비 지급 기준은 무엇인가요?
- 출장 후 정산 기한은 언제까지인가요?
- 해외 출장비는 별도 규정이 있나요?

질문: {request.question}
답변: {request.answer[:300]}
관련 질문:
-"""

        # Generate using direct MLX
        response = mlx_generate(
            llm.model,
            llm.tokenizer,
            prompt=prompt,
            max_tokens=200,
            verbose=False
        )

        # Clean response - remove <think> tags if present
        import re
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

        logger.debug(f"LLM response for follow-up questions: {response[:300]}")

        # Parse response into questions - handle bullet point format
        lines = response.strip().split('\n')
        questions = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove bullet points, numbering, and markdown
            line = re.sub(r'^[\-\*\•\d\.\)\]]+\s*', '', line)
            line = re.sub(r'^\*\*|\*\*$', '', line)  # Remove bold
            line = line.strip()

            # Skip non-question lines (metadata, labels, etc.)
            if not line or '질문' in line or '답변' in line or '예시' in line or '관련' in line:
                continue

            # Validate: must end with ?, contain Korean, min length 5
            if (line.endswith('?') and
                re.search(r'[가-힣]', line) and
                len(line) >= 5):
                questions.append(line)
                logger.debug(f"Valid question found: {line}")

            if len(questions) >= 3:
                break

        # Return questions or fallback
        if len(questions) >= 3:
            logger.info(f"Successfully generated {len(questions)} follow-up questions")
            return {"questions": questions[:3]}
        else:
            logger.warning(f"Only generated {len(questions)} questions, using fallback")
            return {
                "questions": [
                    "이 내용과 관련된 추가 정보가 있나요?",
                    "다른 규정과의 차이점은 무엇인가요?",
                    "실제 적용 사례는 어떻게 되나요?"
                ]
            }

    except Exception as e:
        logger.error(f"Failed to generate follow-up questions: {e}", exc_info=True)
        return {
            "questions": [
                "이 내용과 관련된 추가 정보가 있나요?",
                "다른 규정과의 차이점은 무엇인가요?",
                "실제 적용 사례는 어떻게 되나요?"
            ]
        }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for load balancers and monitoring systems.
    Returns detailed system status including Redis, models, and cache.
    """
    try:
        import psutil
        import time
        from datetime import datetime

        # Check Redis connectivity
        redis_healthy = False
        redis_info = {}
        try:
            vector_db.client.ping()
            redis_healthy = True
            info = vector_db.client.info()
            redis_info = {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0)
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

        # Check cache stats
        cache_stats = {}
        if cache_manager:
            cache_stats = cache_manager.get_cache_stats()

        # System resources
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Model status
        models_loaded = {
            "embedding": embedding_model is not None,
            "llm": llm is not None,
            "rag": rag_system is not None
        }

        # Overall health status
        is_healthy = redis_healthy and all(models_loaded.values())

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
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


@app.get("/metrics")
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
        except:
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
        # Development: keep colorful logging
        logger.info("Development logging active")

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
    log_level = os.getenv("LOG_LEVEL", "info" if environment == "production" else "debug")
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
