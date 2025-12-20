"""
Web Server - FastAPI application
"""

import os
import json
import shutil
import hashlib
import asyncio
from pathlib import Path
from typing import Optional
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
from .pdf_processor import PDFProcessor
from .document_processor import DocumentProcessor
from .vector_db import VectorDB
from .llm import LLM, RAGSystem
from .document_tracker import DocumentTracker
from .cache_manager import CacheManager

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

        # Content Security Policy (moderate policy allowing CDNs for external libraries)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "  # Allow marked.js and highlight.js from trusted CDNs
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "  # Allow highlight.js CSS from CDN
            "img-src 'self' data:; "  # Allow data URIs for images
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"  # Prevent embedding in iframes
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
suggested_questions_pool: list = []  # Pre-generated question pool

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

    # PDF magic bytes: %PDF
    pdf_signature = b'%PDF'

    # HWP magic bytes: HWP Document File
    hwp_signature = b'HWP Document File'
    hwp_signature_alt = b'\xd0\xcf\x11\xe0'  # OLE2/CFB container (used by HWP 5.0+)

    # Check if file starts with valid signature
    is_pdf = header.startswith(pdf_signature)
    is_hwp = header.startswith(hwp_signature) or header.startswith(hwp_signature_alt)

    if not (is_pdf or is_hwp):
        # Try to detect what it actually is
        if header.startswith(b'MZ') or header.startswith(b'\x7fELF'):
            raise HTTPException(
                status_code=400,
                detail="실행 파일은 업로드할 수 없습니다. PDF 또는 HWP 파일만 허용됩니다."
            )
        elif header.startswith(b'PK\x03\x04'):
            raise HTTPException(
                status_code=400,
                detail="ZIP 파일은 업로드할 수 없습니다. PDF 또는 HWP 파일만 허용됩니다."
            )
        elif b'<script' in header.lower() or b'<html' in header.lower():
            raise HTTPException(
                status_code=400,
                detail="HTML 파일은 업로드할 수 없습니다. PDF 또는 HWP 파일만 허용됩니다."
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="파일 형식이 올바르지 않습니다. 유효한 PDF 또는 HWP 파일을 업로드해주세요."
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
    history: Optional[list] = None  # Conversation history [{"role": "user/assistant", "content": "..."}]

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
    global embedding_model, vector_db, cache_manager, suggested_questions_pool

    try:
        logger.info("🚀 Starting application initialization (fast mode)...")

        # Initialize embedding model (required for search)
        logger.info("📚 Loading embedding model...")
        embedding_model = EmbeddingModel(
            model_name=EMBEDDING_MODEL,
            model_dir=MODEL_DIR
        )

        # Initialize vector database
        logger.info("🔌 Connecting to Redis...")
        vector_db = VectorDB(
            host=REDIS_HOST,
            port=REDIS_PORT,
            embedding_dim=embedding_model.get_embedding_dim()
        )

        # Initialize cache manager
        logger.info("💾 Initializing cache manager...")
        cache_manager = CacheManager(
            redis_client=vector_db.client,
            embedding_model=embedding_model.model,
            similarity_threshold=0.95,  # 95% similarity threshold
            cache_ttl=3600  # 1 hour cache
        )

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

        logger.success(f"Indexed {len(chunks)} chunks from {len(set(chunk['filename'] for chunk in chunks))} documents (PDF + HWP)")
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
    try:
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
            document_ids=request.document_ids
        )

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
    try:
        # Lazy load RAG system on first use
        rag = await get_rag_system()

        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        # Check cache first
        cached_response = cache_manager.get_cached_response(
            question=request.question,
            top_k=request.top_k,
            similarity_threshold=request.cache_threshold,
            document_ids=request.document_ids
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

        # Create query embedding
        query_embedding = embedding_model.encode(request.question)[0]

        # Query RAG system with streaming
        result = rag.query(
            question=request.question,
            query_embedding=query_embedding,
            top_k=request.top_k,
            stream=True,
            history=request.history,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            system_prompt=request.system_prompt,
            document_ids=request.document_ids
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

        # Collect response for caching
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
                document_ids=request.document_ids  # Include document filter in cache key
            )
            logger.info(f"💾 Saved response to cache for question: '{request.question[:50]}...'")

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
    try:
        logger.info("Force reindexing PDFs...")
        doc_tracker = DocumentTracker(data_dir=DATA_DIR)

        # Clear existing index
        vector_db.clear_index()

        # Clear metadata to force reindexing
        doc_tracker.clear_metadata()

        # Reindex
        await index_pdfs(doc_tracker)

        # Invalidate status cache (documents reindexed)
        invalidate_status_cache()

        return {
            "message": "Reindexing completed successfully",
            "document_count": vector_db.count_documents()
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "reindex endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


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
    List all indexed PDF and HWP documents with metadata (optimized with batch queries)
    """
    try:
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            return {"documents": []}

        # Get all PDF and HWP files
        import itertools
        all_files = list(itertools.chain(
            data_path.glob("*.pdf"),
            data_path.glob("*.hwp")
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
    Upload a new PDF or HWP document and automatically index it
    (Max file size: configurable via MAX_FILE_SIZE_MB, default 100MB)
    """
    try:
        # Security: Validate and sanitize filename
        safe_filename = validate_filename(file.filename)

        # Validate file type (extension check)
        if not (safe_filename.endswith('.pdf') or safe_filename.endswith('.hwp')):
            raise HTTPException(status_code=400, detail="Only PDF and HWP files are allowed")

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

        response = {
            "status": "ready" if rag_system else "initializing",
            "document_count": chunk_count,  # 하위 호환성 유지
            "chunk_count": chunk_count,
            "pdf_count": pdf_count,
            "embedding_model": EMBEDDING_MODEL,
            "llm_model": LLM_MODEL
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

        # Create messages for follow-up question generation
        # Simple, direct prompt without room for thinking
        simple_prompt = f"""사용자 질문: {request.question}
AI 답변: {request.answer[:500]}

위 내용을 바탕으로 후속 질문 3개를 한국어로 작성하세요 (각 질문은 한 줄, '?'로 끝남):"""

        # Generate follow-up questions using MLX
        from mlx_lm import generate as mlx_generate

        response = mlx_generate(
            llm.model,
            llm.tokenizer,
            prompt=simple_prompt,
            max_tokens=150
        )

        # Debug: Log raw response
        logger.debug(f"Raw LLM response: {response[:500]}")

        # Clean response: remove <think> tags and their content
        import re
        cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        cleaned = re.sub(r'</?think>', '', cleaned)  # Remove orphaned tags

        logger.debug(f"Cleaned response: {cleaned[:500]}")

        # Parse response into list of questions
        lines = cleaned.strip().split('\n')
        questions = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove numbering (1., 2., 3., -, *, etc.)
            original_line = line
            line = re.sub(r'^[\d\-\*\.\)]+\s*', '', line)
            line = line.strip()

            # Debug: Check each validation step
            ends_with_q = line.endswith('?')
            has_korean = bool(re.search(r'[가-힣]', line))
            long_enough = len(line) >= 5
            no_english = not re.search(r'[a-z]{3,}', line)

            logger.debug(f"Line: '{line[:50]}' | ends_with_q={ends_with_q}, has_korean={has_korean}, long_enough={long_enough}, no_english={no_english}")

            # Only keep lines that:
            # 1. End with '?'
            # 2. Contain Korean characters (가-힣)
            # 3. Are not too short (at least 5 chars)
            # 4. Don't contain English explanations (no lowercase English letters)
            if (ends_with_q and has_korean and long_enough and no_english):
                questions.append(line)

            if len(questions) >= 3:
                break

        # If we got questions, return them; otherwise use fallback
        if questions:
            logger.info(f"Generated {len(questions)} follow-up questions")
            return {"questions": questions}
        else:
            logger.warning("No valid questions generated, using fallback")
            return {
                "questions": [
                    "이 내용과 관련된 추가 정보가 있나요?",
                    "다른 규정과의 차이점은 무엇인가요?",
                    "실제 적용 사례는 어떻게 되나요?"
                ]
            }

    except Exception as e:
        logger.error(f"Failed to generate follow-up questions: {e}")
        # Fallback questions
        return {
            "questions": [
                "이 내용과 관련된 추가 정보가 있나요?",
                "다른 규정과의 차이점은 무엇인가요?",
                "실제 적용 사례는 어떻게 되나요?"
            ]
        }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))

    logger.info(f"Starting server at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
