"""
Query & Search Router

Handles RAG query endpoints including:
- Query endpoint (standard RAG)
- Query streaming endpoint
- Follow-up questions generation

All endpoints require user authentication.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
from typing import Optional
import logging
import json
import asyncio
import re
import inspect
import time

# Configure logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["Query"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

llm = None
embedding_model = None
cache_manager = None
group_manager = None
conversation_manager = None
response_validator = None
confidence_scorer = None
get_hybrid_rag_orchestrator = None
get_rag_system = None
get_current_active_user = None
get_safe_error_message = None
get_system_prompt_for_mode = None


def inject_dependencies(
    llm_instance,
    embedding_model_instance,
    cache_mgr,
    group_mgr,
    conversation_mgr,
    response_val,
    confidence_score,
    hybrid_rag_fn,
    rag_system_fn,
    auth_dependency,
    error_msg_fn,
    prompt_mode_fn
):
    """
    Inject dependencies from main application

    Args:
        llm_instance: LLM model instance
        embedding_model_instance: Embedding model instance
        cache_mgr: CacheManager instance
        group_mgr: GroupManager instance
        conversation_mgr: ConversationManager instance
        response_val: ResponseValidator instance
        confidence_score: ConfidenceScorer instance
        hybrid_rag_fn: Function to get Hybrid RAG orchestrator
        rag_system_fn: Function to get basic RAG system
        auth_dependency: get_current_active_user dependency
        error_msg_fn: get_safe_error_message function
        prompt_mode_fn: get_system_prompt_for_mode function
    """
    global llm, embedding_model, cache_manager, group_manager, conversation_manager
    global response_validator, confidence_scorer, get_hybrid_rag_orchestrator
    global get_rag_system, get_current_active_user, get_safe_error_message
    global get_system_prompt_for_mode

    llm = llm_instance
    embedding_model = embedding_model_instance
    cache_manager = cache_mgr
    group_manager = group_mgr
    conversation_manager = conversation_mgr
    response_validator = response_val
    confidence_scorer = confidence_score
    get_hybrid_rag_orchestrator = hybrid_rag_fn
    get_rag_system = rag_system_fn
    get_current_active_user = auth_dependency
    get_safe_error_message = error_msg_fn
    get_system_prompt_for_mode = prompt_mode_fn


# ============================================================================
# Request/Response Models
# ============================================================================

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    search_mode: str = 'smart'  # 검색 모드: smart, local-only, web-enhanced, comprehensive, tools-only
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
        """Sanitize user question (prevent XSS, SQL injection)"""
        if not v or not v.strip():
            raise ValueError("질문을 입력해주세요.")
        # Remove potential XSS patterns
        v = re.sub(r'<script[^>]*>.*?</script>', '', v, flags=re.IGNORECASE | re.DOTALL)
        v = re.sub(r'javascript:', '', v, flags=re.IGNORECASE)
        v = re.sub(r'on\w+\s*=', '', v, flags=re.IGNORECASE)
        # Limit length
        if len(v) > 2000:
            raise ValueError("질문이 너무 깁니다 (최대 2000자).")
        return v.strip()

    @validator('top_k')
    def validate_top_k(cls, v):
        """Validate top_k parameter"""
        if v < 1 or v > 20:
            raise ValueError("top_k는 1-20 사이의 값이어야 합니다.")
        return v

    @validator('search_mode')
    def validate_search_mode(cls, v):
        """Validate search_mode parameter"""
        valid_modes = ['smart', 'local-only', 'web-enhanced', 'comprehensive', 'tools-only']
        if v not in valid_modes:
            raise ValueError(f"search_mode는 {', '.join(valid_modes)} 중 하나여야 합니다.")
        return v

    @validator('cache_threshold')
    def validate_cache_threshold(cls, v):
        """Validate cache_threshold parameter"""
        if v < 0 or v > 1:
            raise ValueError("cache_threshold는 0-1 사이의 값이어야 합니다.")
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
    confidence: Optional[dict] = None  # 신뢰도 점수 정보
    search_summary: Optional[dict] = None  # 하이브리드 검색 정보 (사용된 툴, 검색 결과 수)


class FollowUpRequest(BaseModel):
    question: str
    answer: str
    context: Optional[list] = []


# ============================================================================
# Query API Endpoints
# ============================================================================

@router.post("/api/query", response_model=QueryResponse, tags=["Query"])
async def query(
    request: QueryRequest,
    current_user: dict = Depends(lambda: get_current_active_user)
):
    """
    Query endpoint for chatbot (로그인 필요)
    """
    # No wait needed with Blue-Green deployment - active index always serves queries
    # Reindexing happens on a separate index, then swaps atomically

    try:
        # Save user question to conversation history
        if request.session_id and conversation_manager:
            conversation_manager.add_message(
                session_id=request.session_id,
                role="user",
                content=request.question
            )

        # Create query embedding
        query_embedding = embedding_model.encode(request.question)[0]

        # Organization-based access control: validate and filter group_ids
        user_org_id = current_user.get("org_id")

        # All users (including system admins) can only search their organization's groups
        org_groups = group_manager.get_all_groups(org_id=user_org_id)
        org_group_ids = {g['id'] for g in org_groups}

        # Validate and filter requested group_ids
        validated_group_ids = request.group_ids
        if request.group_ids is not None:
            # Specific groups requested (may be empty array)
            if len(request.group_ids) == 0:
                # Empty array means "no groups selected" - return empty result
                raise HTTPException(
                    status_code=400,
                    detail="검색할 그룹을 선택해주세요."
                )
            # Validate all requested groups belong to user's organization
            validated_group_ids = [gid for gid in request.group_ids if gid in org_group_ids]
            if len(validated_group_ids) != len(request.group_ids):
                logger.warning(f"⚠️ User {current_user.get('user_id')} attempted to access groups outside their organization")
        else:
            # No specific groups requested (None) - use all organization groups
            validated_group_ids = list(org_group_ids)

        # Validate document_ids (if using document filter instead of group filter)
        if request.document_ids is not None and len(request.document_ids) == 0:
            # Empty array means "no documents selected" - return empty result
            raise HTTPException(
                status_code=400,
                detail="검색할 문서를 선택해주세요."
            )

        # Expand group_ids to include all descendants (hierarchical search)
        expanded_group_ids = []
        for group_id in validated_group_ids:
            # Get all descendant group IDs (children, grandchildren, etc.)
            descendant_ids = group_manager.get_descendant_group_ids(group_id)
            expanded_group_ids.extend(descendant_ids)
        # Remove duplicates
        expanded_group_ids = list(set(expanded_group_ids))
        logger.info(f"🏢 Org filter: {user_org_id} | 🌲 Expanded group_ids: {validated_group_ids} → {expanded_group_ids}")

        # 🆕 자동 프롬프트 선택 (사용자가 지정하지 않은 경우)
        if not request.system_prompt:
            redis_client = cache_manager.redis
            # 초기 추정: search_mode 기반 (실제 sources는 검색 후 알 수 있음)
            auto_prompt = get_system_prompt_for_mode(
                redis_client=redis_client,
                search_mode='smart',  # Hybrid RAG의 기본 모드
                sources_used=None  # 검색 전이므로 None
            )
            request.system_prompt = auto_prompt
            logger.debug(f"📝 Auto-selected system prompt based on search mode")

        # Check if Hybrid RAG is enabled and use it, otherwise use basic RAG
        hybrid_rag = await get_hybrid_rag_orchestrator()

        if hybrid_rag is not None:
            # Use Hybrid RAG (combines local + web + docs)
            logger.info("🔗 Using Hybrid RAG (multi-source search)")

            # 사용자 선택 search_mode 사용 (기본값: smart)
            search_mode = request.search_mode or "smart"
            logger.info(f"🎯 Search mode: {search_mode}")

            result = await hybrid_rag.answer(
                query=request.question,
                group_ids=expanded_group_ids,
                user_id=current_user.get("user_id"),
                search_mode=search_mode,  # Use user-selected search mode
                system_prompt=request.system_prompt,  # 🆕 시스템 프롬프트 전달
                top_k=request.top_k,  # 🆕 검색 문서 개수 전달
                document_ids=request.document_ids  # 🆕 문서 필터 전달
            )

            # 🔄 Convert Hybrid RAG format to basic RAG format
            hybrid_sources = result.get("sources", [])
            context_docs = []
            source_names = []

            for source in hybrid_sources:
                source_type = source.get("source_type", "unknown")
                metadata = source.get("metadata", {})

                if source_type == "local":
                    filename = metadata.get("filename", "Unknown Document")
                    source_name = f"{filename} (로컬 문서)"
                elif source_type == "web":
                    title = metadata.get("title", metadata.get("url", "Web Source"))
                    source_name = f"{title} (Tavily)"
                elif source_type == "docs":
                    library = metadata.get("library", "Official Docs")
                    title = metadata.get("title", "Documentation")
                    source_name = f"{library} - {title} (Context7)"
                else:
                    source_name = "External Source"

                context_docs.append({
                    "text": source.get("content", ""),
                    "filename": source_name,
                    "score": source.get("score", 0.0)
                })
                source_names.append(source_name)

            # Add 'context' and update 'sources' keys for compatibility
            result["context"] = context_docs
            result["sources"] = list(set(source_names))  # Unique source names

        else:
            # Use basic RAG (local documents only)
            logger.info("📚 Using basic RAG (local documents only)")
            rag = await get_rag_system()
            # 🆕 로컬 전용 프롬프트 선택
            if not request.system_prompt:
                redis_client = cache_manager.redis
                request.system_prompt = get_system_prompt_for_mode(
                    redis_client=redis_client,
                    search_mode='local-only',
                    sources_used=['local']
                )
            result = rag.query(
                question=request.question,
                query_embedding=query_embedding,
                top_k=request.top_k,
                history=request.history,
                document_ids=request.document_ids,
                group_ids=expanded_group_ids,
                system_prompt=request.system_prompt  # 🆕 시스템 프롬프트 전달
            )

        # 🔍 응답 품질 검증 및 자동 수정
        original_answer = result["answer"]
        context_filenames = [doc.get("filename", "") for doc in result["context"]]

        # 검증 수행
        is_valid, violations = response_validator.validate_response(
            original_answer,
            context_filenames
        )

        # 검증 실패 시 자동 수정 시도
        if not is_valid:
            logger.warning(f"⚠️ 응답 검증 실패 - 자동 수정 시도: {violations}")
            fixed_answer, fixes = response_validator.auto_fix_response(
                original_answer,
                result["context"]
            )

            if fixes:
                logger.success(f"✅ 자동 수정 완료: {fixes}")
                result["answer"] = fixed_answer

                # 메타데이터에 수정 정보 추가
                result["validation_info"] = {
                    "original_violations": violations,
                    "auto_fixed": True,
                    "fixes_applied": fixes
                }
            else:
                logger.error(f"❌ 자동 수정 실패 - 원본 응답 반환")
                result["validation_info"] = {
                    "violations": violations,
                    "auto_fixed": False
                }
        else:
            logger.debug("✅ 응답 검증 통과")

        # 📊 신뢰도 점수 계산
        confidence_result = confidence_scorer.calculate_confidence(
            answer=result["answer"],
            context=result["context"],
            question=request.question
        )
        logger.info(f"📊 신뢰도 점수: {confidence_result['percentage']}% ({confidence_result['level']})")

        # Save assistant response to conversation history
        if request.session_id and conversation_manager:
            metadata = {
                "sources": result["sources"],
                "chunk_count": len(result["context"]),
                "context": result["context"]  # Save context for source details modal
            }
            conversation_manager.add_message(
                session_id=request.session_id,
                role="assistant",
                content=result["answer"],
                metadata=metadata
            )

        return QueryResponse(
            answer=result["answer"],
            sources=result["sources"],
            context=[
                {
                    "text": (doc["text"][:200] + "..." if len(doc["text"]) > 200 else doc["text"]) if isinstance(doc.get("text"), str) else "",
                    "filename": doc.get("filename", ""),
                    "score": doc.get("score", 0.0)
                }
                for doc in result["context"]
            ],
            confidence=confidence_result,
            search_summary=result.get("search_summary")  # 하이브리드 검색 정보 포함
        )
    except HTTPException:
        # Re-raise HTTPException as-is (e.g., 400 errors with custom messages)
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "query endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/api/query/stream", tags=["Query"])
async def query_stream(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(lambda: get_current_active_user)
):
    """
    Streaming query endpoint for chatbot (로그인 필요)
    """
    # No wait needed with Blue-Green deployment - active index always serves queries
    # Reindexing happens on a separate index, then swaps atomically

    try:
        # Ensure session exists (create if needed)
        if conversation_manager:
            if not request.session_id or not conversation_manager.session_exists(request.session_id):
                # Create new session if session_id is None or doesn't exist
                request.session_id = conversation_manager.create_session()
                logger.info(f"Created new session for user query: {request.session_id}")

            # Save user question to conversation history
            conversation_manager.add_message(
                session_id=request.session_id,
                role="user",
                content=request.question
            )

        # Lazy load RAG system on first use
        rag = await get_rag_system()

        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        # Check query result cache first (exact match, 5-min TTL)
        query_result_cached = cache_manager.get_query_result_cache(
            query_text=request.question,
            group_ids=request.group_ids
        )

        if query_result_cached:
            # Query result cache HIT - return immediately
            logger.info(f"🎯 Query result cache HIT (exact match): '{request.question[:50]}...'")

            async def generate_exact_cached_stream():
                # Send metadata
                yield f"data: {json.dumps({'type': 'metadata', 'data': query_result_cached['metadata']})}\n\n"

                # Stream cached response
                response_text = query_result_cached["response"]
                chunk_size = 8
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"
                    await asyncio.sleep(0.01)

                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return StreamingResponse(
                generate_exact_cached_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )

        # Check semantic cache (similarity-based, 1-hour TTL)
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
                "similarity": cached_response["similarity"],
                "search_summary": cached_response.get("search_summary")  # 하이브리드 검색 정보
            }

            # Save cached response to conversation history
            if request.session_id and conversation_manager:
                metadata = {
                    "sources": cached_response["sources"],
                    "context": cached_response.get("context", []),  # Save context for source details modal
                    "cached": True,
                    "similarity": cached_response["similarity"]
                }
                conversation_manager.add_message(
                    session_id=request.session_id,
                    role="assistant",
                    content=cached_response["response"],
                    metadata=metadata
                )

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

        # Organization-based access control: validate and filter group_ids
        user_org_id = current_user.get("org_id")

        # All users (including system admins) can only search their organization's groups
        org_groups = group_manager.get_all_groups(org_id=user_org_id)
        org_group_ids = {g['id'] for g in org_groups}

        # Validate and filter requested group_ids
        validated_group_ids = request.group_ids
        if request.group_ids is not None:
            # Specific groups requested (may be empty array)
            if len(request.group_ids) == 0:
                # Empty array means "no groups selected" - return empty result
                raise HTTPException(
                    status_code=400,
                    detail="검색할 그룹을 선택해주세요."
                )
            # Validate all requested groups belong to user's organization
            validated_group_ids = [gid for gid in request.group_ids if gid in org_group_ids]
            if len(validated_group_ids) != len(request.group_ids):
                logger.warning(f"⚠️ User {current_user.get('user_id')} attempted to access groups outside their organization")
        else:
            # No specific groups requested (None) - use all organization groups
            validated_group_ids = list(org_group_ids)

        # Validate document_ids (if using document filter instead of group filter)
        if request.document_ids is not None and len(request.document_ids) == 0:
            # Empty array means "no documents selected" - return empty result
            raise HTTPException(
                status_code=400,
                detail="검색할 문서를 선택해주세요."
            )

        # Expand group_ids to include all descendants (hierarchical search)
        expanded_group_ids = []
        for group_id in validated_group_ids:
            # Get all descendant group IDs (children, grandchildren, etc.)
            descendant_ids = group_manager.get_descendant_group_ids(group_id)
            expanded_group_ids.extend(descendant_ids)
        # Remove duplicates
        expanded_group_ids = list(set(expanded_group_ids))
        logger.info(f"🏢 Org filter: {user_org_id} | 🌲 Expanded group_ids: {validated_group_ids} → {expanded_group_ids}")

        # 🆕 자동 프롬프트 선택 (사용자가 지정하지 않은 경우)
        if not request.system_prompt:
            redis_client = cache_manager.redis
            # 초기 추정: search_mode 기반 (실제 sources는 검색 후 알 수 있음)
            auto_prompt = get_system_prompt_for_mode(
                redis_client=redis_client,
                search_mode='smart',  # Hybrid RAG의 기본 모드
                sources_used=None  # 검색 전이므로 None
            )
            request.system_prompt = auto_prompt
            logger.debug(f"📝 Auto-selected system prompt based on search mode")

        # Check if Hybrid RAG is enabled and use it, otherwise use basic RAG
        hybrid_rag = await get_hybrid_rag_orchestrator()

        # Track query start time (before RAG execution)
        query_start_time = time.time()

        if hybrid_rag is not None:
            # Use Hybrid RAG (combines local + web + docs) - non-streaming
            logger.info("🔗 Using Hybrid RAG (multi-source search) - streaming response")

            # 사용자 선택 search_mode 사용 (기본값: smart)
            search_mode = request.search_mode or "smart"
            logger.info(f"🎯 Search mode: {search_mode}")

            result = await hybrid_rag.answer(
                query=request.question,
                group_ids=expanded_group_ids,
                user_id=current_user.get("user_id"),
                search_mode=search_mode,  # Use user-selected search mode
                system_prompt=request.system_prompt,
                top_k=request.top_k,
                document_ids=request.document_ids  # 🆕 문서 필터 전달
            )

            # Record first token time (when Hybrid RAG query completes)
            first_token_time = time.time()

            # Convert Hybrid RAG response to streaming format
            # Extract answer and convert sources to match expected format
            answer_text = result["answer"]
            hybrid_sources = result["sources"]

            # Create context format expected by streaming endpoint
            context_docs = []
            source_names = []  # String array for frontend compatibility

            for source in hybrid_sources:
                source_type = source.get("source_type", "unknown")
                metadata = source.get("metadata", {})

                # Determine source display name based on type
                if source_type == "local":
                    # Local documents: use filename
                    filename = metadata.get("filename", "Unknown Document")
                    source_name = f"{filename} (로컬 문서)"
                elif source_type == "web":
                    # Web sources: use title or URL
                    title = metadata.get("title", metadata.get("url", "Web Source"))
                    source_name = f"{title} (Tavily)"
                elif source_type == "docs":
                    # Official docs: use library name and title
                    library = metadata.get("library", "Official Docs")
                    title = metadata.get("title", "Documentation")
                    source_name = f"{library} - {title} (Context7)"
                else:
                    source_name = "External Source"

                context_docs.append({
                    "text": source.get("content", ""),
                    "filename": source_name,  # Use formatted name
                    "score": source.get("score", 0.0),
                    "source_type": source_type
                })

                source_names.append(source_name)

            # Remove duplicates while preserving order
            unique_source_names = []
            seen = set()
            for name in source_names:
                if name not in seen:
                    seen.add(name)
                    unique_source_names.append(name)

            # Create result dict matching basic RAG format
            result = {
                "answer": answer_text,
                "context": context_docs,
                "sources": unique_source_names,  # String array for frontend
                "search_summary": result.get("search_summary", {}),
                "generator": None  # No streaming generator for Hybrid RAG
            }
        else:
            # Use basic RAG (local documents only) with streaming
            logger.info("📚 Using basic RAG (local documents only) - streaming")

            # Update prompt for local-only mode
            if not request.system_prompt:
                redis_client = cache_manager.redis
                request.system_prompt = get_system_prompt_for_mode(
                    redis_client=redis_client,
                    search_mode='local-only',
                    sources_used=['local']
                )

            # Check embedding cache first
            cached_embedding = cache_manager.get_embedding_cache(request.question)

            if cached_embedding:
                # Use cached embedding
                query_embedding = cached_embedding
            else:
                # Generate new embedding (run in thread pool to avoid blocking)
                query_embedding = await asyncio.to_thread(
                    lambda: embedding_model.encode(request.question)[0]
                )
                # Save to embedding cache
                cache_manager.set_embedding_cache(request.question, query_embedding)

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
                group_ids=expanded_group_ids  # Use validated and expanded group_ids
            )

            # Record first token time (when RAG query completes and answer is ready)
            first_token_time = time.time()

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
            "cached": False,
            "search_summary": result.get("search_summary")  # 하이브리드 검색 정보
        }

        # Collect response for caching and conversation history
        full_response = []

        async def generate_stream():
            nonlocal query_start_time, first_token_time

            # Use query start time as the actual start time
            start_time = query_start_time
            # first_token_time is already set when rag.query() completed
            token_count = 0

            # First, send sources and context
            yield f"data: {json.dumps({'type': 'metadata', 'data': context_data})}\n\n"

            # Check if answer is a generator (streaming) or string (non-streaming)
            is_generator = inspect.isgenerator(result["answer"])

            if not is_generator:
                # Hybrid RAG: answer is a complete string, split into chunks for streaming
                answer_text = result["answer"]
                chunk_size = 8  # Characters per chunk

                for i in range(0, len(answer_text), chunk_size):
                    chunk = answer_text[i:i + chunk_size]
                    if chunk:
                        # Count tokens (approximate)
                        token_count += len(chunk.split())
                        full_response.append(chunk)
                        yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"

                        # Small delay to simulate streaming
                        await asyncio.sleep(0.01)
            else:
                # answer is a generator, stream naturally
                for chunk in result["answer"]:
                    if chunk:
                        # Count tokens (approximate: split by whitespace + punctuation)
                        token_count += len(chunk.split())

                        full_response.append(chunk)
                        yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"

            # Save to cache after completion
            complete_response = ''.join(full_response)

            # 🔍 응답 품질 검증 및 자동 수정 (스트리밍)
            context_filenames = [doc.get("filename", "") for doc in result["context"]]
            is_valid, violations = response_validator.validate_response(
                complete_response,
                context_filenames
            )

            # 검증 실패 시 자동 수정 (캐시 저장 전에 수정)
            if not is_valid:
                logger.warning(f"⚠️ 스트리밍 응답 검증 실패 - 자동 수정 시도: {violations}")
                fixed_response, fixes = response_validator.auto_fix_response(
                    complete_response,
                    result["context"]
                )
                if fixes:
                    logger.success(f"✅ 스트리밍 응답 자동 수정 완료: {fixes}")
                    complete_response = fixed_response

            # 📊 신뢰도 점수 계산 (스트리밍)
            confidence_result = confidence_scorer.calculate_confidence(
                answer=complete_response,
                context=result["context"],
                question=request.question
            )
            logger.info(f"📊 스트리밍 신뢰도 점수: {confidence_result['percentage']}% ({confidence_result['level']})")

            # Calculate statistics
            end_time = time.time()
            total_time = end_time - start_time
            time_to_first_token = (first_token_time - start_time) if first_token_time else 0
            tokens_per_second = token_count / total_time if total_time > 0 else 0

            # Define background task for cache saves
            def save_to_caches():
                # Determine content type based on source documents
                content_type = 'default'
                if result.get("sources"):
                    # Check if sources contain regulation/policy documents (usually PDFs with specific keywords)
                    sources_text = ' '.join(result["sources"]).lower()
                    if any(keyword in sources_text for keyword in ['규정', '규칙', '지침', '정책', '방침', '절차']):
                        content_type = 'static_docs'  # 24-hour cache for regulations
                    elif any(keyword in sources_text for keyword in ['faq', '자주', '질문']):
                        content_type = 'realtime'  # 5-minute cache for FAQs

                # Save to semantic cache (similarity-based, dynamic TTL based on content type)
                cache_manager.save_to_cache(
                    question=request.question,
                    response=complete_response,
                    sources=result["sources"],
                    top_k=request.top_k,
                    cache_ttl=request.cache_ttl,
                    context=context_data["context"],
                    document_ids=request.document_ids,
                    group_ids=request.group_ids,
                    content_type=content_type
                )
                logger.info(f"💾 [BG] Saved to semantic cache ({content_type}): '{request.question[:50]}...'")

                # Save to query result cache (exact match, 5-min TTL)
                cache_manager.set_query_result_cache(
                    query_text=request.question,
                    result={
                        "response": complete_response,
                        "metadata": context_data
                    },
                    group_ids=request.group_ids,
                    ttl=300
                )
                logger.info(f"🎯 [BG] Saved to query result cache: '{request.question[:50]}...'")

            # Define background task for conversation history
            def save_to_conversation():
                if request.session_id and conversation_manager:
                    metadata = {
                        "sources": result["sources"],
                        "chunk_count": len(result["context"]),
                        "context": result["context"],
                        "cached": False,
                        "elapsed_time": round(total_time, 1),
                        "stats": {
                            "tokens_per_second": round(tokens_per_second, 2),
                            "total_tokens": token_count,
                            "time_to_first_token": round(time_to_first_token, 2)
                        }
                    }
                    conversation_manager.add_message(
                        session_id=request.session_id,
                        role="assistant",
                        content=complete_response,
                        metadata=metadata
                    )

            # Add background tasks (non-blocking)
            background_tasks.add_task(save_to_caches)
            background_tasks.add_task(save_to_conversation)

            # Send token statistics
            stats_data = {
                'tokens_per_second': round(tokens_per_second, 2),
                'total_tokens': token_count,
                'time_to_first_token': round(time_to_first_token, 2)
            }
            yield f"data: {json.dumps({'type': 'stats', 'data': stats_data})}\n\n"

            # Send confidence score
            yield f"data: {json.dumps({'type': 'confidence', 'data': confidence_result})}\n\n"

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
    except HTTPException:
        # Re-raise HTTPException as-is (e.g., 400 errors with custom messages)
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "query/stream endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/api/follow-up-questions", tags=["Query"])
async def generate_follow_up_questions(
    request: FollowUpRequest,
    current_user: dict = Depends(lambda: get_current_active_user)
):
    """
    Generate smart follow-up questions (로그인 필요)
    """
    try:
        if not llm:
            raise HTTPException(status_code=503, detail="LLM not initialized")

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

        # Check LLM type and use appropriate generation method
        from ..llm_ollama import OllamaLLM

        if isinstance(llm, OllamaLLM):
            # Use Ollama's _generate_response method with simple user message
            messages = [{"role": "user", "content": prompt}]
            response = llm._generate_response(
                messages=messages,
                max_tokens=200,
                temperature=0.3  # Lower temperature for more focused output
            )
        else:
            # Use MLX generate for MLX-based LLM
            from mlx_lm import generate as mlx_generate
            response = mlx_generate(
                llm.model,
                llm.tokenizer,
                prompt=prompt,
                max_tokens=200,
                verbose=False
            )

        # Clean response - remove <think> tags if present
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

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
