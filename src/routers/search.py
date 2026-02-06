"""
Search Router

Independent search APIs for Tavily (web search) and Context7 (docs search).
These are standalone search endpoints that return raw search results without LLM processing.
"""

from typing import Optional, List
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from ..auth.middleware import get_current_active_user

router = APIRouter(prefix="/api/search", tags=["Search"])

# Global dependencies (injected at startup)
_get_hybrid_rag_orchestrator = None


def inject_dependencies(hybrid_rag_fn):
    """Inject dependencies for search router"""
    global _get_hybrid_rag_orchestrator
    _get_hybrid_rag_orchestrator = hybrid_rag_fn


# ==================== Request/Response Models ====================

class WebSearchRequest(BaseModel):
    """Tavily 웹 검색 요청"""
    query: str = Field(..., description="검색 쿼리", example="latest AI developments 2026")
    max_results: int = Field(5, description="최대 결과 수", ge=1, le=20)
    search_depth: str = Field("basic", description="검색 깊이 (basic 또는 advanced)")
    include_domains: Optional[List[str]] = Field(None, description="포함할 도메인 목록", example=None)
    exclude_domains: Optional[List[str]] = Field(None, description="제외할 도메인 목록", example=None)


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


# ==================== Endpoints ====================

@router.post("/web", response_model=WebSearchResponse)
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
        rag = await _get_hybrid_rag_orchestrator()

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


@router.post("/docs", response_model=DocsSearchResponse)
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
        rag = await _get_hybrid_rag_orchestrator()

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
