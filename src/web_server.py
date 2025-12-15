"""
Web Server - FastAPI application
"""

import os
import json
import shutil
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from loguru import logger
from dotenv import load_dotenv

from .embeddings import EmbeddingModel
from .pdf_processor import PDFProcessor
from .document_processor import DocumentProcessor
from .vector_db import VectorDB
from .llm import LLM, RAGSystem
from .document_tracker import DocumentTracker
from .cache_manager import CacheManager

# Load environment variables
load_dotenv()

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jinaai/jina-embeddings-v3")
LLM_MODEL = os.getenv("LLM_MODEL", "mlx-community/Qwen3-30B-A3B-4bit")
MODEL_DIR = os.getenv("MODEL_DIR", "./model")
DATA_DIR = os.getenv("DATA_DIR", "./data")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 512))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 50))

# Initialize FastAPI
app = FastAPI(
    title="PDF RAG Chatbot",
    description="PDF 문서 기반 질의응답 챗봇",
    version="1.0.0"
)

# Mount static files
static_path = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Global instances (initialized on startup)
embedding_model: Optional[EmbeddingModel] = None
vector_db: Optional[VectorDB] = None
llm: Optional[LLM] = None
rag_system: Optional[RAGSystem] = None
cache_manager: Optional[CacheManager] = None
suggested_questions_pool: list = []  # Pre-generated question pool


# Error message helper
def create_error_response(error: Exception, context: str = "") -> dict:
    """
    Create user-friendly error response with helpful suggestions
    """
    error_type = type(error).__name__
    error_msg = str(error)

    # User-friendly error messages with solutions
    error_responses = {
        "FileNotFoundError": {
            "message": "파일을 찾을 수 없습니다",
            "detail": f"요청한 파일이 존재하지 않습니다: {error_msg}",
            "solution": "파일 경로를 확인하거나 문서를 다시 업로드해주세요."
        },
        "PermissionError": {
            "message": "권한 오류가 발생했습니다",
            "detail": f"파일에 대한 접근 권한이 없습니다: {error_msg}",
            "solution": "파일 권한을 확인하거나 관리자에게 문의하세요."
        },
        "ValueError": {
            "message": "잘못된 값이 입력되었습니다",
            "detail": f"입력값 오류: {error_msg}",
            "solution": "입력 형식을 확인하고 다시 시도해주세요."
        },
        "ConnectionError": {
            "message": "연결 오류가 발생했습니다",
            "detail": f"서비스 연결 실패: {error_msg}",
            "solution": "잠시 후 다시 시도하거나 네트워크 연결을 확인해주세요."
        },
        "TimeoutError": {
            "message": "요청 시간이 초과되었습니다",
            "detail": f"처리 시간 초과: {error_msg}",
            "solution": "문서 크기가 큰 경우 시간이 걸릴 수 있습니다. 잠시 후 다시 시도해주세요."
        },
        "KeyError": {
            "message": "필수 정보가 누락되었습니다",
            "detail": f"누락된 키: {error_msg}",
            "solution": "요청 형식을 확인하고 다시 시도해주세요."
        }
    }

    # Get specific error response or use generic
    if error_type in error_responses:
        response = error_responses[error_type]
    else:
        response = {
            "message": "예상치 못한 오류가 발생했습니다",
            "detail": f"{error_type}: {error_msg}",
            "solution": "문제가 지속되면 관리자에게 문의하세요."
        }

    # Add context if provided
    if context:
        response["context"] = context

    return response


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


class QueryResponse(BaseModel):
    answer: str
    sources: list
    context: list


class LLMChangeRequest(BaseModel):
    llm_model: str


@app.on_event("startup")
async def startup_event():
    """Initialize models and database on startup"""
    global embedding_model, vector_db, llm, rag_system, cache_manager, suggested_questions_pool

    try:
        logger.info("Starting application initialization...")

        # Initialize embedding model
        logger.info("Loading embedding model...")
        embedding_model = EmbeddingModel(
            model_name=EMBEDDING_MODEL,
            model_dir=MODEL_DIR
        )

        # Initialize vector database
        logger.info("Connecting to Redis...")
        vector_db = VectorDB(
            host=REDIS_HOST,
            port=REDIS_PORT,
            embedding_dim=embedding_model.get_embedding_dim()
        )

        # Initialize cache manager
        logger.info("Initializing cache manager...")
        cache_manager = CacheManager(
            redis_client=vector_db.client,
            embedding_model=embedding_model.model,
            similarity_threshold=0.95,  # 95% similarity threshold
            cache_ttl=3600  # 1 hour cache
        )

        # Smart indexing: check if reindexing is needed
        await check_and_index_pdfs()

        # Initialize LLM
        logger.info("Loading LLM...")
        llm = LLM(
            model_name=LLM_MODEL,
            model_dir=MODEL_DIR
        )

        # Initialize RAG system
        rag_system = RAGSystem(
            vector_db=vector_db,
            llm=llm,
            top_k=5
        )

        # Pre-generate suggested questions pool
        logger.info("Generating suggested questions pool...")
        await generate_questions_pool()
        logger.success(f"Generated {len(suggested_questions_pool)} questions in pool")

        logger.success("Application initialized successfully!")
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        raise


async def generate_questions_pool():
    """
    Pre-generate a pool of 15-20 questions during startup
    These will be randomly sampled when users request suggested questions
    """
    global suggested_questions_pool

    try:
        import random
        from mlx_lm import generate

        # Get list of PDF files
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            return

        pdf_files = list(data_path.glob("*.pdf"))
        if not pdf_files:
            return

        # Generate 3-4 batches of questions for variety
        all_questions = []
        for batch_num in range(3):
            # Randomly select documents for this batch
            random.shuffle(pdf_files)
            all_docs = []

            for pdf_file in pdf_files[:5]:
                try:
                    docs = vector_db.sample_documents_by_filename(pdf_file.name, limit=2)
                    all_docs.extend(docs)
                except:
                    continue

            if not all_docs:
                continue

            random.shuffle(all_docs)

            # Create context
            context_text = "\n\n".join([
                f"[문서: {doc['filename']}]\n{doc['text'][:800]}..."
                for doc in all_docs[:8]
            ])

            # Generate questions
            system_content = "You must respond ONLY in Korean language. Never use English in your response."
            user_content = f"""다음 문서 내용을 읽고 한국어로 질문 5개만 생성하세요.

문서:
{context_text}

예시:
1. 임차보증금의 최대 한도는 얼마인가요?
2. 전산시스템은 몇 시간 운영되나요?
3. 이사회 안건 제출 기한은 언제인가요?

위 형식으로 질문 5개 (한국어만):"""

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
                max_tokens=512
            )

            # Parse questions
            lines = response.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith('-')):
                    question = line.lstrip('0123456789.-) ').strip()
                    if question and len(question) > 10:
                        # Filter: Only include questions with Korean characters
                        if any('\uac00' <= char <= '\ud7a3' for char in question):
                            all_questions.append(question)

        # Store unique Korean-only questions in the pool
        suggested_questions_pool = list(set(all_questions))

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
        logger.info("Checking for PDF changes...")
        change_summary = doc_tracker.get_change_summary()

        if not change_summary["needs_reindex"]:
            # No changes detected
            doc_count = vector_db.count_documents()
            logger.success(f"No PDF changes detected. Using existing index ({doc_count} documents)")
            return

        # Changes detected - show summary
        logger.warning("PDF changes detected:")
        if change_summary["new_files"]:
            logger.info(f"  • New files ({len(change_summary['new_files'])}): {change_summary['new_files']}")
        if change_summary["modified_files"]:
            logger.info(f"  • Modified files ({len(change_summary['modified_files'])}): {change_summary['modified_files']}")
        if change_summary["deleted_files"]:
            logger.info(f"  • Deleted files ({len(change_summary['deleted_files'])}): {change_summary['deleted_files']}")

        # Reindex
        logger.info("Reindexing required. Clearing old index...")
        vector_db.clear_index()
        await index_pdfs(doc_tracker)

    except Exception as e:
        logger.error(f"Smart indexing failed: {e}")
        # Fallback to regular indexing
        logger.info("Falling back to regular indexing...")
        doc_tracker = DocumentTracker(data_dir=DATA_DIR)
        await index_pdfs(doc_tracker)


async def index_pdfs(doc_tracker: DocumentTracker):
    """
    Process and index PDF documents

    Args:
        doc_tracker: DocumentTracker instance
    """
    try:
        logger.info(f"Processing PDFs from {DATA_DIR}...")

        # Process PDFs
        pdf_processor = PDFProcessor(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        chunks = pdf_processor.process_directory(DATA_DIR)

        if not chunks:
            logger.warning("No chunks created from PDFs")
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

        logger.success(f"Indexed {len(chunks)} chunks from PDF documents")
    except Exception as e:
        logger.error(f"Failed to index PDFs: {e}")
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
    Query endpoint for chatbot
    """
    try:
        if not rag_system:
            raise HTTPException(status_code=503, detail="System not initialized")

        # Create query embedding
        query_embedding = embedding_model.encode(request.question)[0]

        # Query RAG system
        result = rag_system.query(
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
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query/stream")
async def query_stream(request: QueryRequest):
    """
    Streaming query endpoint for chatbot with caching
    """
    try:
        if not rag_system or not cache_manager:
            raise HTTPException(status_code=503, detail="System not initialized")

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
        result = rag_system.query(
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
        logger.error(f"Streaming query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

        return {
            "message": "Reindexing completed successfully",
            "document_count": vector_db.count_documents()
        }
    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents")
async def list_documents():
    """
    List all indexed PDF documents with metadata
    """
    try:
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            return {"documents": []}

        documents = []

        # Get all PDF files
        for pdf_file in data_path.glob("*.pdf"):
            # Get file stats
            stat = pdf_file.stat()

            # Count chunks in vector DB for this document
            chunk_count = 0
            if vector_db:
                try:
                    # Query to count chunks for this filename
                    # This is a rough estimate - you might need to adjust based on your VectorDB implementation
                    chunk_count = vector_db.count_documents_by_filename(pdf_file.name)
                except:
                    chunk_count = 0

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
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a new PDF or HWP document and automatically index it
    """
    try:
        # Validate file type
        if not (file.filename.endswith('.pdf') or file.filename.endswith('.hwp')):
            raise HTTPException(status_code=400, detail="Only PDF and HWP files are allowed")

        # Create data directory if it doesn't exist
        data_path = Path(DATA_DIR)
        data_path.mkdir(parents=True, exist_ok=True)

        # Read file content for hash calculation and duplicate detection
        file_content = await file.read()

        # Calculate MD5 hash of file content
        file_hash = hashlib.md5(file_content).hexdigest()

        # Check for duplicate content using Redis
        hash_key = f"doc:hash:{file_hash}"
        existing_filename = vector_db.client.get(hash_key)

        if existing_filename:
            existing_filename = existing_filename.decode('utf-8') if isinstance(existing_filename, bytes) else existing_filename
            raise HTTPException(
                status_code=409,
                detail=f"이 파일과 동일한 내용의 문서가 이미 업로드되어 있습니다: '{existing_filename}'. 같은 파일을 다시 업로드할 필요가 없습니다."
            )

        # Save uploaded file
        file_path = data_path / file.filename

        # Check if file already exists (filename collision)
        if file_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"File '{file.filename}' already exists. Please delete it first or rename your file."
            )

        # Save file
        with file_path.open("wb") as buffer:
            buffer.write(file_content)

        logger.info(f"Uploaded file: {file.filename}")

        # Process and index the new document (PDF or HWP)
        try:
            doc_processor = DocumentProcessor(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP
            )

            # Process single file (automatically detects PDF or HWP)
            chunks = doc_processor.process_document(str(file_path))

            if not chunks:
                logger.warning(f"No chunks created from {file.filename}")
                return {
                    "message": "File uploaded but no content could be extracted",
                    "filename": file.filename,
                    "indexed": False
                }

            # Create embeddings
            logger.info(f"Creating embeddings for {len(chunks)} chunks from {file.filename}...")
            texts = [chunk["text"] for chunk in chunks]
            embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=False)

            # Add to vector database
            vector_db.add_documents(chunks, embeddings)

            # Update document tracker
            doc_tracker = DocumentTracker(data_dir=DATA_DIR)
            doc_tracker.update_metadata()

            logger.success(f"Indexed {len(chunks)} chunks from {file.filename}")

            # Store file hash to prevent future duplicates
            vector_db.client.set(hash_key, file.filename)
            logger.info(f"Stored file hash for duplicate detection: {file_hash[:8]}...")

            # Get file stats
            stat = file_path.stat()

            return {
                "message": "File uploaded and indexed successfully",
                "filename": file.filename,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "chunk_count": len(chunks),
                "indexed": True
            }

        except Exception as e:
            # If indexing fails, remove the uploaded file
            logger.error(f"Failed to index {file.filename}: {e}")
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process PDF: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    """
    Delete a PDF document and remove it from the index
    """
    try:
        data_path = Path(DATA_DIR)
        file_path = data_path / filename

        # Check if file exists
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

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
                deleted_count = vector_db.delete_by_filename(filename)
                logger.info(f"Deleted {deleted_count} chunks for {filename} from vector DB")
            except Exception as e:
                logger.error(f"Failed to delete from vector DB: {e}")
                # Continue with file deletion even if vector DB deletion fails

        # Delete file
        file_path.unlink()
        logger.info(f"Deleted file: {filename}")

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

        return {
            "message": f"Document '{filename}' deleted successfully",
            "filename": filename,
            "chunks_removed": deleted_count if vector_db else 0
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
async def status():
    """
    Get system status with detailed information
    """
    try:
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
        logger.error(f"Failed to change LLM model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to change LLM model: {str(e)}")


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

        # Sample 5 random questions from the pool
        num_questions = min(5, len(suggested_questions_pool))
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
        messages = [
            {
                "role": "system",
                "content": "당신은 유용한 후속 질문을 생성하는 AI입니다. 사용자의 이해를 돕기 위해 적절한 질문을 생성합니다."
            },
            {
                "role": "user",
                "content": f"""이전 대화 내용을 바탕으로 사용자가 궁금해할 만한 후속 질문 3개를 생성해주세요.

사용자 질문: {request.question}
AI 답변: {request.answer[:500]}...

다음 가이드라인을 따라 후속 질문을 생성하세요:
1. 답변 내용을 더 깊이 이해하기 위한 질문
2. 관련된 다른 주제로 확장하는 질문
3. 실제 적용이나 절차를 묻는 질문

각 질문은 한 줄로 작성하고, 번호 없이 질문만 작성하세요.
질문1
질문2
질문3"""
            }
        ]

        # Generate follow-up questions using MLX
        from mlx_lm import generate as mlx_generate
        prompt = llm.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        response = mlx_generate(
            llm.model,
            llm.tokenizer,
            prompt=prompt,
            max_tokens=200,
            temp=0.7,
            verbose=False
        )

        # Parse response into list of questions
        questions = [q.strip() for q in response.strip().split('\n') if q.strip()]
        questions = questions[:3]  # Limit to 3 questions

        logger.info(f"Generated {len(questions)} follow-up questions")
        return {"questions": questions}

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
