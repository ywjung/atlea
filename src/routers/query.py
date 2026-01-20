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
from ..auth.rate_limiter import create_rate_limit_dependency
from loguru import logger
import json
import asyncio
import re
import inspect
import time

# Import auth dependency directly
from ..auth.middleware import get_current_active_user as auth_get_current_active_user

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
get_llm_instance = None  # Function to get LLM (for lazy loading support)


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
    prompt_mode_fn,
    get_llm_fn=None
):
    """
    Inject dependencies from main application

    Args:
        llm_instance: LLM model instance (may be None if lazy loading)
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
        get_llm_fn: Async function to get LLM instance (for lazy loading)
    """
    global llm, embedding_model, cache_manager, group_manager, conversation_manager
    global response_validator, confidence_scorer, get_hybrid_rag_orchestrator
    global get_rag_system, get_current_active_user, get_safe_error_message
    global get_system_prompt_for_mode, get_llm_instance

    llm = llm_instance
    get_llm_instance = get_llm_fn
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

    @validator('document_ids')
    def validate_document_ids(cls, v):
        """Validate document_ids list"""
        if v is None:
            return v
        if not isinstance(v, list):
            raise ValueError("document_ids는 리스트여야 합니다.")
        if len(v) > 100:
            raise ValueError("document_ids는 최대 100개까지 지정할 수 있습니다.")
        for doc_id in v:
            if not isinstance(doc_id, str) or len(doc_id) > 500:
                raise ValueError("document_id는 500자 이하의 문자열이어야 합니다.")
            # Prevent path traversal
            if '..' in doc_id or doc_id.startswith('/'):
                raise ValueError("잘못된 document_id 형식입니다.")
        return v

    @validator('group_ids')
    def validate_group_ids(cls, v):
        """Validate group_ids list"""
        if v is None:
            return v
        if not isinstance(v, list):
            raise ValueError("group_ids는 리스트여야 합니다.")
        if len(v) > 50:
            raise ValueError("group_ids는 최대 50개까지 지정할 수 있습니다.")
        for group_id in v:
            if not isinstance(group_id, str) or len(group_id) > 100:
                raise ValueError("group_id는 100자 이하의 문자열이어야 합니다.")
            # Only allow alphanumeric, dash, underscore
            if not re.match(r'^[a-zA-Z0-9_-]+$', group_id):
                raise ValueError("group_id는 영문, 숫자, 대시, 언더스코어만 허용됩니다.")
        return v

    @validator('system_prompt')
    def validate_system_prompt(cls, v):
        """Validate system_prompt to prevent prompt injection"""
        if v is None:
            return v
        if len(v) > 5000:
            raise ValueError("system_prompt는 최대 5000자까지 지정할 수 있습니다.")
        # Remove potentially harmful patterns
        v = re.sub(r'(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?)', '', v)
        v = re.sub(r'(?i)disregard\s+(all\s+)?(previous|above|prior)', '', v)
        return v.strip()

    @validator('history')
    def validate_history(cls, v):
        """Validate conversation history"""
        if v is None:
            return v
        if not isinstance(v, list):
            raise ValueError("history는 리스트여야 합니다.")
        if len(v) > 50:
            raise ValueError("history는 최대 50개까지 지정할 수 있습니다.")
        for item in v:
            if not isinstance(item, dict):
                raise ValueError("history 항목은 딕셔너리여야 합니다.")
            if 'role' not in item or 'content' not in item:
                raise ValueError("history 항목에는 role과 content가 필요합니다.")
            if item['role'] not in ['user', 'assistant', 'system']:
                raise ValueError("role은 user, assistant, system 중 하나여야 합니다.")
            if len(str(item.get('content', ''))) > 10000:
                raise ValueError("history content는 최대 10000자까지 지정할 수 있습니다.")
        return v

    @validator('session_id')
    def validate_session_id(cls, v):
        """Validate session_id format"""
        if v is None:
            return v
        if len(v) > 100:
            raise ValueError("session_id는 최대 100자까지 지정할 수 있습니다.")
        # Only allow safe characters
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("session_id는 영문, 숫자, 대시, 언더스코어만 허용됩니다.")
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
    session_id: Optional[str] = None  # Session ID for saving follow-up questions to history

    @validator('session_id')
    def validate_session_id(cls, v):
        """Validate session_id format"""
        if v is None:
            return v
        if len(v) > 100:
            raise ValueError("session_id는 최대 100자까지 지정할 수 있습니다.")
        # Only allow safe characters
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("session_id는 영문, 숫자, 대시, 언더스코어만 허용됩니다.")
        return v


# ============================================================================
# Query API Endpoints
# ============================================================================

@router.post("/api/query", response_model=QueryResponse, tags=["Query"])
async def query(
    request: QueryRequest,
    current_user: dict = Depends(auth_get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "query"))
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
    current_user: dict = Depends(auth_get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "query_stream"))
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

            # Generate follow-up questions for cached response (LLM 기반)
            cached_follow_up = _generate_llm_follow_up_questions(
                request.question, query_result_cached["response"], llm_instance=rag.llm
            )
            if len(cached_follow_up) < 3:
                cached_follow_up = _generate_context_aware_fallback(
                    request.question, cached_follow_up, query_result_cached["response"]
                )

            # Save to conversation history with follow-up questions
            if request.session_id and conversation_manager:
                metadata = query_result_cached.get('metadata', {}).copy()
                metadata['follow_up_questions'] = cached_follow_up
                metadata['cached'] = True
                conversation_manager.add_message(
                    session_id=request.session_id,
                    role="assistant",
                    content=query_result_cached["response"],
                    metadata=metadata
                )

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

                # Send follow-up questions
                yield f"data: {json.dumps({'type': 'follow_up_questions', 'data': cached_follow_up})}\n\n"

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

            # Generate follow-up questions for cached response (LLM 기반)
            semantic_follow_up = _generate_llm_follow_up_questions(
                request.question, cached_response["response"], llm_instance=rag.llm
            )
            if len(semantic_follow_up) < 3:
                semantic_follow_up = _generate_context_aware_fallback(
                    request.question, semantic_follow_up, cached_response["response"]
                )

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
                    "similarity": cached_response["similarity"],
                    "follow_up_questions": semantic_follow_up  # 후속 질문 저장
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

                # Send follow-up questions
                yield f"data: {json.dumps({'type': 'follow_up_questions', 'data': semantic_follow_up})}\n\n"

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

            # 🔄 후속 질문은 별도 API (/api/follow-up-questions)에서 생성
            # 스트리밍 응답 속도 향상을 위해 여기서는 생성하지 않음

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
                        # follow_up_questions는 별도 API에서 저장됨
                    }
                    logger.info(f"💾 [CONV] Saving to history")
                    conversation_manager.add_message(
                        session_id=request.session_id,
                        role="assistant",
                        content=complete_response,
                        metadata=metadata
                    )
                    logger.info(f"💾 [CONV] Saved to session {request.session_id}")

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

            # follow_up_questions는 별도 API (/api/follow-up-questions)에서 처리

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


def _generate_llm_follow_up_questions(question: str, answer: str, llm_instance=None) -> list:
    """
    Generate follow-up questions using LLM by analyzing both question and answer.

    Args:
        question: Original user question
        answer: Generated answer
        llm_instance: Optional LLM instance to use (if not provided, uses global llm)

    Returns:
        List of 3 relevant follow-up questions, or empty list on failure
    """
    # Use provided llm_instance or fall back to global llm
    active_llm = llm_instance or llm

    if not active_llm:
        logger.warning("🔄 LLM not available for follow-up question generation")
        return []

    try:
        logger.info(f"🔄 Generating LLM follow-up questions for: '{question[:50]}...'")

        # Truncate answer if too long (keep first 500 chars for context)
        answer_truncated = answer[:500] if len(answer) > 500 else answer

        # Create prompt for LLM - more explicit format instructions
        prompt = f"""질문과 답변을 분석하여 후속 질문 3개를 생성하세요.

[원래 질문]
{question}

[답변 내용]
{answer_truncated}

[규칙]
1. 위 답변 내용을 바탕으로 사용자가 더 알고 싶어할 구체적인 질문
2. 한국어로 작성, 반드시 물음표(?)로 끝남
3. 각 질문은 새 줄에 "-"로 시작

[후속 질문 3개]
-"""

        # Check LLM type and use appropriate generation method
        from ..llm_ollama import OllamaLLM

        if isinstance(active_llm, OllamaLLM):
            messages = [{"role": "user", "content": prompt}]
            response = active_llm._generate_response(
                messages=messages,
                max_tokens=250,
                temperature=0.5  # Slightly higher for variety
            )
        else:
            # Use MLX generate
            from mlx_lm import generate as mlx_generate

            messages = [
                {"role": "system", "content": "당신은 한국어로 후속 질문을 생성하는 도우미입니다. 답변 내용을 분석하여 관련된 구체적인 질문을 만드세요."},
                {"role": "user", "content": prompt}
            ]

            formatted_prompt = active_llm.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            response = mlx_generate(
                active_llm.model,
                active_llm.tokenizer,
                prompt=formatted_prompt,
                max_tokens=250,
                verbose=False
            )

        # Log raw response for debugging
        logger.info(f"🔄 LLM raw response (first 300 chars): {response[:300]}")

        # Clean response - remove <think> tags if present
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

        # Parse response into questions
        lines = response.strip().split('\n')
        questions = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove bullet points, numbering, and markdown
            line = re.sub(r'^[\-\*\•\d\.\)\]]+\s*', '', line)
            line = re.sub(r'^\*\*|\*\*$', '', line)
            line = line.strip()

            # Skip metadata lines
            skip_patterns = ['질문:', '답변:', '예시:', '관련 질문:', '후속 질문:', '[', ']']
            if any(line.startswith(p) or line == p.rstrip(':') for p in skip_patterns):
                continue

            # Skip if line is too short
            if len(line) < 5:
                continue

            # Validate: must contain Korean and be a question-like sentence
            has_korean = re.search(r'[가-힣]', line)
            is_question = line.endswith('?') or '?' in line

            if has_korean and is_question:
                # Clean up: ensure ends with single ?
                if not line.endswith('?'):
                    line = line.split('?')[0] + '?'
                questions.append(line)
                logger.debug(f"🔄 Extracted question: {line}")

            if len(questions) >= 3:
                break

        logger.info(f"🔄 LLM generated {len(questions)} follow-up questions: {questions}")
        return questions[:3]

    except Exception as e:
        logger.error(f"🔄 Failed to generate LLM follow-up questions: {e}", exc_info=True)
        return []


def _generate_context_aware_fallback(question: str, partial_questions: list, answer: str = "") -> list:
    """
    Generate context-aware fallback questions based on the original question and answer.

    Args:
        question: Original user question
        partial_questions: Any questions that were successfully parsed
        answer: The generated answer (used for topic extraction)

    Returns:
        List of 3 relevant follow-up questions
    """
    # Start with any partial questions that were generated
    result = partial_questions[:3] if partial_questions else []

    # Combine question and answer for topic detection
    combined_text = f"{question} {answer}".lower()

    # Extended topic patterns with related keywords
    # Each topic maps to trigger keywords AND follow-up questions
    topic_patterns = {
        # 신청/요청 관련
        '신청': {
            'triggers': ['신청', '요청', '접수', '제출', '등록', '지원'],
            'questions': ['신청 자격 조건은 무엇인가요?', '신청 기한이 있나요?', '온라인 신청이 가능한가요?']
        },
        # 절차/프로세스 관련
        '절차': {
            'triggers': ['절차', '과정', '단계', '순서', '프로세스'],
            'questions': ['구체적인 단계는 어떻게 되나요?', '필요한 서류는 무엇인가요?', '처리 기간은 얼마나 걸리나요?']
        },
        # 방법 관련
        '방법': {
            'triggers': ['방법', '하는 법', '하려면', '가능한가요', '할 수 있'],
            'questions': ['다른 방법도 있나요?', '주의사항은 무엇인가요?', '예외 상황은 어떻게 처리하나요?']
        },
        # 규정/정책 관련
        '규정': {
            'triggers': ['규정', '정책', '규칙', '기준', '원칙', '법규', '지침'],
            'questions': ['관련 법규는 무엇인가요?', '위반 시 제재는 어떻게 되나요?', '예외 조항이 있나요?']
        },
        # 비용/금액 관련
        '비용': {
            'triggers': ['비용', '금액', '요금', '수수료', '지불', '결제', '가격', '원'],
            'questions': ['비용 산정 기준은 무엇인가요?', '할인이나 감면 혜택이 있나요?', '지불 방법은 어떻게 되나요?']
        },
        # 기간/일정 관련
        '기간': {
            'triggers': ['기간', '일정', '날짜', '시간', '일', '주', '월', '년'],
            'questions': ['연장이 가능한가요?', '기간 내 완료하지 못하면 어떻게 되나요?', '시작일은 언제부터인가요?']
        },
        # 조건/자격 관련
        '조건': {
            'triggers': ['조건', '자격', '요건', '필수', '해당', '대상'],
            'questions': ['필수 조건과 선택 조건이 있나요?', '조건 미충족 시 대안은 있나요?', '조건 확인 방법은 무엇인가요?']
        },
        # 담당/연락처 관련
        '담당': {
            'triggers': ['담당', '연락처', '문의', '부서', '팀', '담당자'],
            'questions': ['담당 부서 연락처는 어떻게 되나요?', '담당자가 부재 시 누구에게 문의하나요?', '업무 처리 시간은 언제인가요?']
        },
        # 서류/문서 관련
        '서류': {
            'triggers': ['서류', '문서', '양식', '첨부', '제출물', '증빙'],
            'questions': ['서류 양식은 어디서 받나요?', '서류 제출 방법은 무엇인가요?', '필수 서류와 선택 서류가 있나요?']
        },
        # 승인/결재 관련
        '승인': {
            'triggers': ['승인', '결재', '허가', '검토', '확인', '반려'],
            'questions': ['승인 권한은 누구에게 있나요?', '승인 소요 시간은 얼마인가요?', '승인 거부 시 이의제기가 가능한가요?']
        },
        # 휴가/휴직 관련
        '휴가': {
            'triggers': ['휴가', '연차', '휴직', '병가', '경조사', '출산', '육아'],
            'questions': ['휴가 잔여일수 확인은 어떻게 하나요?', '휴가 신청 마감 기한이 있나요?', '휴가 취소나 변경은 가능한가요?']
        },
        # 급여/복지 관련
        '급여': {
            'triggers': ['급여', '월급', '상여', '보너스', '수당', '복지', '혜택'],
            'questions': ['급여 지급일은 언제인가요?', '관련 세금 처리는 어떻게 되나요?', '추가 수당 신청 방법은 무엇인가요?']
        },
        # 교육/연수 관련
        '교육': {
            'triggers': ['교육', '연수', '훈련', '강의', '세미나', '워크샵', '학습'],
            'questions': ['교육 수료 기준은 무엇인가요?', '교육비 지원은 어떻게 받나요?', '필수 교육과 선택 교육이 있나요?']
        },
        # 시스템/IT 관련
        '시스템': {
            'triggers': ['시스템', '프로그램', '앱', '로그인', '비밀번호', '접속', 'it'],
            'questions': ['시스템 접속이 안 될 때 어떻게 하나요?', '비밀번호 초기화는 어떻게 하나요?', 'IT 지원 요청은 어디로 하나요?']
        },
    }

    # Question type based patterns (applied only to question, not answer)
    question_type_patterns = {
        'how_to': {
            'triggers': ['어떻게', '하는 방법', '하려면', 'how'],
            'questions': ['단계별로 설명해 주세요', '필요한 준비물이 있나요?', '주의할 점은 무엇인가요?']
        },
        'definition': {
            'triggers': ['무엇', '뭐', '정의', '의미', 'what'],
            'questions': ['구체적인 예시가 있나요?', '관련된 다른 개념이 있나요?', '실제 적용 사례는 어떤 것이 있나요?']
        },
        'comparison': {
            'triggers': ['차이', '비교', '다른 점', '구분'],
            'questions': ['각각의 장단점은 무엇인가요?', '어떤 상황에서 어떤 것을 선택해야 하나요?', '실제 적용 예시가 있나요?']
        },
        'reason': {
            'triggers': ['왜', '이유', '원인', '때문'],
            'questions': ['다른 원인은 없나요?', '해결 방법은 무엇인가요?', '예방할 수 있는 방법이 있나요?']
        },
    }

    # Default fallback questions (more specific than before)
    default_fallbacks = [
        '이 내용의 적용 범위는 어디까지인가요?',
        '관련 담당 부서나 문의처는 어디인가요?',
        '예외 사항이나 특별 규정이 있나요?',
        '최근 변경된 내용이 있나요?',
        '실제 사례나 적용 예시가 있나요?',
    ]

    # Find matching topics in combined text (question + answer)
    matched_questions = []

    # Check topic patterns against combined text
    for topic, data in topic_patterns.items():
        for trigger in data['triggers']:
            if trigger in combined_text:
                matched_questions.extend(data['questions'])
                break  # Avoid duplicates from same topic

    # Check question type patterns (only on question, not answer)
    question_lower = question.lower()
    for qtype, data in question_type_patterns.items():
        for trigger in data['triggers']:
            if trigger in question_lower:
                matched_questions.extend(data['questions'])
                break

    # Remove duplicates while preserving order
    seen = set()
    unique_matched = []
    for q in matched_questions:
        if q not in seen:
            seen.add(q)
            unique_matched.append(q)

    # If we found topic matches, use them
    if unique_matched:
        for q in unique_matched:
            if q not in result and len(result) < 3:
                result.append(q)

    # Fill remaining slots with default fallbacks
    for q in default_fallbacks:
        if q not in result and len(result) < 3:
            result.append(q)

    return result[:3]


@router.post("/api/follow-up-questions", tags=["Query"])
async def generate_follow_up_questions(
    request: FollowUpRequest,
    current_user: dict = Depends(auth_get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "follow_up_questions"))
):
    """
    Generate smart follow-up questions (로그인 필요)
    """
    try:
        # Debug: Log request info
        logger.info(f"📝 [API] Follow-up request - session_id: {request.session_id}, question: {request.question[:50]}...")

        # Get LLM instance (supports lazy loading)
        active_llm = llm
        if not active_llm and get_llm_instance:
            active_llm = await get_llm_instance()

        if not active_llm:
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

        if isinstance(active_llm, OllamaLLM):
            # Use Ollama's _generate_response method with simple user message
            messages = [{"role": "user", "content": prompt}]
            response = active_llm._generate_response(
                messages=messages,
                max_tokens=200,
                temperature=0.3  # Lower temperature for more focused output
            )
        else:
            # Use MLX generate for MLX-based LLM with proper chat template
            from mlx_lm import generate as mlx_generate

            # Build messages for chat template
            messages = [
                {"role": "system", "content": "당신은 한국어로 관련 질문을 생성하는 도우미입니다. 질문만 생성하세요."},
                {"role": "user", "content": prompt}
            ]

            # Apply chat template for proper model instruction
            formatted_prompt = active_llm.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            response = mlx_generate(
                active_llm.model,
                active_llm.tokenizer,
                prompt=formatted_prompt,
                max_tokens=200,
                verbose=False
            )

        # Clean response - remove <think> tags if present
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

        # Debug: log raw response for troubleshooting
        logger.debug(f"LLM response for follow-up questions: {response[:500]}")

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

            # Skip metadata lines (exact matches or starting patterns)
            skip_patterns = ['질문:', '답변:', '예시:', '관련 질문:']
            if any(line.startswith(p) or line == p.rstrip(':') for p in skip_patterns):
                continue

            # Skip if line is too short or doesn't look like a question
            if len(line) < 5:
                continue

            # Validate: must end with ?, contain Korean
            if (line.endswith('?') and re.search(r'[가-힣]', line)):
                questions.append(line)
                logger.debug(f"Extracted question: {line}")

            if len(questions) >= 3:
                break

        # Return questions or generate context-aware fallback
        if len(questions) >= 3:
            logger.info(f"Successfully generated {len(questions)} follow-up questions")
            final_questions = questions[:3]
        else:
            logger.warning(f"Only generated {len(questions)} questions from response, generating context-aware fallback")
            # Generate context-aware fallback based on original question and answer
            original_q = request.question
            final_questions = _generate_context_aware_fallback(original_q, questions, request.answer)

        # Save follow-up questions to conversation history
        if request.session_id and conversation_manager:
            logger.info(f"💾 [API] Saving follow-up questions to session {request.session_id}: {final_questions}")
            result = conversation_manager.update_last_message_metadata(
                session_id=request.session_id,
                metadata_update={"follow_up_questions": final_questions}
            )
            logger.info(f"💾 [API] Save result: {result}")

        return {"questions": final_questions}

    except Exception as e:
        logger.error(f"Failed to generate follow-up questions: {e}", exc_info=True)
        # Generate context-aware fallback on error (with answer for context)
        fallback_questions = _generate_context_aware_fallback(request.question, [], request.answer)

        # Still try to save to history on error
        if request.session_id and conversation_manager:
            conversation_manager.update_last_message_metadata(
                session_id=request.session_id,
                metadata_update={"follow_up_questions": fallback_questions}
            )

        return {"questions": fallback_questions}
