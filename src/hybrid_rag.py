"""
Hybrid RAG Orchestrator - 다중 소스 RAG 시스템

로컬 문서 + 웹 검색 + 공식 문서를 결합하여 더 완벽한 답변 제공

📝 Changelog:
- 2026-01-22: RAG 품질 개선 기능 추가
  - Cross-encoder 기반 재랭킹 (Jina Reranker)
  - LLM 기반 쿼리 재작성 (검색 친화적 쿼리 변환)
  - Redis 설정 기반 기능 활성화/비활성화
- 2026-01-20: Crawl4AI 통합으로 SearXNG 콘텐츠 품질 개선
  - SearXNG 검색 결과 URL에서 Crawl4AI로 전체 콘텐츠 추출
  - 짧은 스니펫 대신 풍부한 페이지 콘텐츠 제공
- 2026-01-20: SearXNG 웹 검색 프로바이더 추가
  - Tavily와 SearXNG 중 선택 가능
  - Docker Compose로 SearXNG 로컬 구동 지원
- 2025-01-19: 스마트 검색 모드 개선
  - benefits_from_web 분석 필드 활용
  - 웹 검색 트리거 조건 확장 (비교, 추천, 설명 질문 등)
  - 검색 요약에 benefits_from_web 정보 추가
- 2025-01-05: 성능 모니터링 시스템 통합
  - MetricsCollector 통합
  - 검색 응답 시간 추적
  - 소스별 성능 측정
- 2025-01-04: 하이브리드 RAG 시스템 구현
  - QueryAnalyzer 통합
  - Tavily 웹 검색 통합
  - 다중 소스 결과 통합 및 랭킹
"""

import os
import time
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from loguru import logger

from .query_analyzer import QueryAnalyzer
from .metrics_collector import MetricsCollector
from .performance_utils import log_slow_query
from .reranker import get_reranker
from .query_rewriter import HybridQueryRewriter


class HybridRAGOrchestrator:
    """
    다중 소스 RAG 시스템
    - 로컬 문서 (기존 RAG)
    - 웹 검색 (Tavily 또는 SearXNG)
    - 공식 문서 (Context7 MCP) - 추후 구현
    """

    # 지원하는 웹 검색 프로바이더
    WEB_SEARCH_PROVIDERS = ['tavily', 'searxng']

    def __init__(
        self,
        local_rag,
        cache_manager,
        enable_web_search: bool = True,
        enable_doc_search: bool = False,
        web_search_provider: str = 'tavily'
    ):
        """
        하이브리드 RAG 오케스트레이터 초기화

        Args:
            local_rag: 기존 RAG 시스템
            cache_manager: 캐시 매니저
            enable_web_search: 웹 검색 활성화 여부
            enable_doc_search: 공식 문서 검색 활성화 여부
            web_search_provider: 웹 검색 프로바이더 ('tavily' 또는 'searxng')
        """
        self.local_rag = local_rag
        self.cache = cache_manager
        self.analyzer = QueryAnalyzer()

        # 성능 모니터링
        self.metrics = MetricsCollector(cache_manager.redis)

        # MCP 클라이언트 초기화
        self.web_search_enabled = enable_web_search
        self.doc_search_enabled = enable_doc_search

        # 웹 검색 프로바이더 설정
        self.web_search_provider = web_search_provider.lower()
        if self.web_search_provider not in self.WEB_SEARCH_PROVIDERS:
            logger.warning(f"⚠️ Unknown web search provider: {web_search_provider}, defaulting to 'tavily'")
            self.web_search_provider = 'tavily'

        # Tavily 클라이언트
        self.tavily_client = None
        if enable_web_search and self.web_search_provider == 'tavily':
            self.tavily_client = self._init_tavily()

        # SearXNG 클라이언트
        self.searxng_client = None
        if enable_web_search and self.web_search_provider == 'searxng':
            self.searxng_client = self._init_searxng()

        # Crawl4AI 클라이언트 (SearXNG 콘텐츠 추출용)
        self.crawl4ai_client = None
        if enable_web_search and self.web_search_provider == 'searxng':
            self.crawl4ai_client = self._init_crawl4ai()

        # Context7 클라이언트 (추후 구현)
        self.context7_client = None
        if enable_doc_search:
            self.context7_client = self._init_context7()

        # RAG 품질 개선 기능 초기화
        self._init_rag_quality_features()

        logger.info("🔗 HybridRAGOrchestrator initialized")
        logger.info(f"  - Web Search: {self.web_search_enabled} (provider: {self.web_search_provider})")
        logger.info(f"  - Doc Search: {self.doc_search_enabled}")
        logger.info(f"  - Reranking: {self.reranking_enabled}")
        logger.info(f"  - Query Rewrite: {self.query_rewrite_enabled}")

    def _init_tavily(self):
        """Tavily 웹 검색 클라이언트 초기화 (Redis 우선, 환경 변수 대체)"""
        try:
            from tavily import TavilyClient

            # API 키 가져오기: Redis 우선, 환경 변수 대체
            api_key = None

            # 1. Redis에서 확인
            try:
                redis_key = self.cache.redis.get("config:tavily_api_key")
                if redis_key:
                    api_key = redis_key.decode()
                    logger.info("🔑 Using Tavily API key from Redis")
            except Exception as e:
                logger.debug(f"Failed to get Tavily key from Redis: {e}")

            # 2. 환경 변수 확인
            if not api_key:
                api_key = os.getenv('TAVILY_API_KEY')
                if api_key:
                    logger.info("🔑 Using Tavily API key from environment variable")

            if not api_key:
                logger.warning("⚠️  TAVILY_API_KEY not found in Redis or environment, web search disabled")
                self.web_search_enabled = False
                return None

            client = TavilyClient(api_key=api_key)
            logger.info("✅ Tavily client initialized")
            return client

        except ImportError:
            logger.warning("⚠️  tavily-python not installed, web search disabled")
            self.web_search_enabled = False
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize Tavily: {e}")
            self.web_search_enabled = False
            return None

    def _init_searxng(self):
        """SearXNG 웹 검색 클라이언트 초기화 (Redis 우선, 환경 변수 대체)"""
        try:
            import httpx

            # SearXNG URL 가져오기: Redis 우선, 환경 변수 대체
            searxng_url = None

            # 1. Redis에서 확인
            try:
                redis_url = self.cache.redis.get("config:searxng_url")
                if redis_url:
                    searxng_url = redis_url.decode()
                    logger.info("🔑 Using SearXNG URL from Redis")
            except Exception as e:
                logger.debug(f"Failed to get SearXNG URL from Redis: {e}")

            # 2. 환경 변수 확인
            if not searxng_url:
                searxng_url = os.getenv('SEARXNG_URL', 'http://localhost:8888')
                logger.info(f"🔑 Using SearXNG URL from environment: {searxng_url}")

            # SearXNG 클라이언트 설정
            client = {
                'base_url': searxng_url.rstrip('/'),
                'http_client': httpx.AsyncClient(
                    timeout=15.0,
                    headers={
                        'Accept': 'application/json',
                        'User-Agent': 'ChatbotRAG/1.0'
                    }
                )
            }

            # 연결 테스트 (비동기이므로 실제 테스트는 첫 검색 시)
            logger.info(f"✅ SearXNG client initialized: {searxng_url}")
            return client

        except ImportError:
            logger.warning("⚠️  httpx not installed, SearXNG search disabled")
            self.web_search_enabled = False
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize SearXNG: {e}")
            self.web_search_enabled = False
            return None

    def _init_crawl4ai(self):
        """Crawl4AI 콘텐츠 추출 클라이언트 초기화"""
        try:
            import httpx

            # Crawl4AI URL 가져오기: Redis 우선, 환경 변수 대체
            crawl4ai_url = None

            # 1. Redis에서 확인
            try:
                redis_url = self.cache.redis.get("config:crawl4ai_url")
                if redis_url:
                    crawl4ai_url = redis_url.decode()
                    logger.info("🔑 Using Crawl4AI URL from Redis")
            except Exception as e:
                logger.debug(f"Failed to get Crawl4AI URL from Redis: {e}")

            # 2. 환경 변수 확인
            if not crawl4ai_url:
                crawl4ai_url = os.getenv('CRAWL4AI_URL', 'http://localhost:11235')
                logger.info(f"🔑 Using Crawl4AI URL from environment: {crawl4ai_url}")

            # API 토큰 (선택적)
            api_token = os.getenv('CRAWL4AI_API_TOKEN', '')

            headers = {
                'Content-Type': 'application/json',
            }
            if api_token:
                headers['Authorization'] = f'Bearer {api_token}'

            # Crawl4AI 클라이언트 설정
            client = {
                'base_url': crawl4ai_url.rstrip('/'),
                'http_client': httpx.AsyncClient(
                    timeout=15.0,  # 크롤링 타임아웃 (개별 URL은 10초)
                    headers=headers
                )
            }

            logger.info(f"✅ Crawl4AI client initialized: {crawl4ai_url}")
            return client

        except ImportError:
            logger.warning("⚠️  httpx not installed, Crawl4AI disabled")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize Crawl4AI: {e}")
            return None

    def _init_context7(self):
        """Context7 공식 문서 클라이언트 초기화 (REST API)"""
        try:
            import httpx

            # API 키 가져오기: Redis 우선, 환경 변수 대체
            api_key = None

            # 1. Redis에서 확인
            try:
                redis_key = self.cache.redis.get("config:context7_api_key")
                if redis_key:
                    api_key = redis_key.decode()
                    logger.info("🔑 Using Context7 API key from Redis")
            except Exception as e:
                logger.debug(f"Failed to get Context7 key from Redis: {e}")

            # 2. 환경 변수 확인
            if not api_key:
                api_key = os.getenv('CONTEXT7_API_KEY')
                if api_key:
                    logger.info("🔑 Using Context7 API key from environment variable")

            if not api_key:
                logger.warning("⚠️  CONTEXT7_API_KEY not found in Redis or environment, docs search disabled")
                self.doc_search_enabled = False
                return None

            # Context7 REST API v2 클라이언트 설정
            client = {
                'api_key': api_key,
                'base_url': 'https://context7.com/api/v2',
                'http_client': httpx.AsyncClient(
                    headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json'
                    },
                    timeout=8.0
                )
            }

            logger.info("✅ Context7 REST client initialized")
            return client

        except ImportError:
            logger.warning("⚠️  httpx not installed, docs search disabled")
            self.doc_search_enabled = False
            return None
        except Exception as e:
            logger.error(f"❌ Failed to initialize Context7: {e}")
            self.doc_search_enabled = False
            return None

    def _init_rag_quality_features(self):
        """RAG 품질 개선 기능 초기화 (재랭킹, 쿼리 재작성)"""
        # Redis에서 설정 로드
        self.reranking_enabled = False
        self.query_rewrite_enabled = False
        self.reranker = None
        self.query_rewriter = None

        try:
            # Redis에서 설정 확인
            reranking_setting = self.cache.redis.get("config:reranking_enabled")
            query_rewrite_setting = self.cache.redis.get("config:query_rewrite_enabled")

            self.reranking_enabled = (
                reranking_setting.decode() == "true" if reranking_setting else False
            )
            self.query_rewrite_enabled = (
                query_rewrite_setting.decode() == "true" if query_rewrite_setting else False
            )

            # 재랭킹 활성화 시 Reranker 초기화 (지연 로딩)
            if self.reranking_enabled:
                try:
                    # Redis에서 reranker 모델 설정 로드
                    reranker_model_setting = self.cache.redis.get("config:reranker_model")
                    reranker_model = (
                        reranker_model_setting.decode()
                        if reranker_model_setting
                        else "dengcao/Qwen3-Reranker-8B:Q4_K_M"
                    )

                    self.reranker = get_reranker(
                        model_type="ollama",
                        model_name=reranker_model
                    )
                    logger.info(f"🎯 Reranker initialized (model: {reranker_model})")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to initialize reranker: {e}")
                    self.reranking_enabled = False

            # 쿼리 재작성 활성화 시 QueryRewriter 초기화
            if self.query_rewrite_enabled:
                self.query_rewriter = HybridQueryRewriter(
                    use_llm=True,
                    fallback_to_rules=True
                )
                logger.info("✏️ QueryRewriter initialized")

        except Exception as e:
            logger.warning(f"⚠️ Failed to load RAG quality settings: {e}")

    def refresh_rag_quality_settings(self):
        """RAG 품질 설정 새로고침 (설정 변경 시 호출)"""
        self._init_rag_quality_features()
        logger.info("🔄 RAG quality settings refreshed")

    async def _rerank_results(
        self,
        query: str,
        results: List[Dict],
        top_k: int = 10
    ) -> List[Dict]:
        """
        검색 결과 재랭킹

        Args:
            query: 사용자 쿼리
            results: 검색 결과 리스트
            top_k: 반환할 최대 문서 수

        Returns:
            재랭킹된 결과 리스트
        """
        if not self.reranking_enabled or not self.reranker:
            return results

        if not results:
            return results

        try:
            logger.info(f"🎯 Reranking {len(results)} results...")
            start_time = time.time()

            reranked = await self.reranker.rerank_async(
                query=query,
                documents=results,
                top_k=top_k
            )

            rerank_time = time.time() - start_time
            logger.info(f"✅ Reranking completed in {rerank_time:.3f}s")

            return reranked

        except Exception as e:
            logger.error(f"❌ Reranking failed: {e}")
            return results

    async def _rewrite_query(self, query: str) -> str:
        """
        쿼리 재작성

        Args:
            query: 원본 사용자 쿼리

        Returns:
            확장된 검색 쿼리
        """
        if not self.query_rewrite_enabled or not self.query_rewriter:
            return query

        try:
            logger.info(f"✏️ Rewriting query: '{query}'")
            start_time = time.time()

            # LLM 클라이언트 전달
            llm_client = getattr(self.local_rag, 'llm', None)
            rewritten = await self.query_rewriter.rewrite(
                query=query,
                llm_client=llm_client,
                include_original=True
            )

            rewrite_time = time.time() - start_time
            logger.info(f"✅ Query rewritten in {rewrite_time:.3f}s: '{rewritten}'")

            return rewritten

        except Exception as e:
            logger.error(f"❌ Query rewrite failed: {e}")
            return query

    async def answer(
        self,
        query: str,
        group_ids: List[str],
        user_id: str,
        search_mode: str = 'smart',
        system_prompt: Optional[str] = None,
        top_k: int = 5,
        document_ids: Optional[List[str]] = None,
        query_embedding=None,
        stream: bool = False
    ) -> Dict:
        """
        하이브리드 검색 및 답변 생성

        Args:
            query: 사용자 질문
            group_ids: 검색할 그룹 ID 목록
            user_id: 사용자 ID
            search_mode: 검색 모드
                - 'smart': 자동 선택
                - 'local-only': 내부 문서만
                - 'web-enhanced': 내부 + 웹
                - 'comprehensive': 모든 소스 (내부 + 웹 + 공식문서)
                - 'tools-only': 외부 도구만 (웹 + 공식문서, 내부 문서 제외)
            system_prompt: 시스템 프롬프트 (Optional)
            top_k: 검색할 문서 개수 (기본값: 5)
            document_ids: 검색할 문서 ID/파일명 목록 (Optional)
            query_embedding: 라우터에서 미리 생성한 쿼리 임베딩 (Optional, 중복 생성 방지)
            stream: 스트리밍 모드 여부 (True면 generator 반환)

        Returns:
            {
                'answer': str,
                'sources': List[Dict],
                'search_summary': Dict
            }
        """
        # 성능 측정 시작
        start_time = time.time()

        # 1. 질문 분석
        analysis = self.analyzer.analyze(query)
        logger.info(f"📊 Query analysis: time={analysis['time_sensitivity']}, "
                   f"internal={analysis['is_internal']}, "
                   f"fresh={analysis['needs_fresh_info']}, "
                   f"web_beneficial={analysis.get('benefits_from_web', False)}")

        # 1.5. 쿼리 재작성 (검색 최적화)
        search_query = query
        if self.query_rewrite_enabled:
            search_query = await self._rewrite_query(query)

        # 2. 검색 소스 결정
        sources_to_use = self._select_sources(analysis, search_mode)
        logger.info(f"🎯 Selected sources: {sources_to_use}")

        # 3. 병렬 검색 실행
        search_tasks = []

        # 로컬 문서 검색 (재작성된 쿼리 사용)
        if 'local' in sources_to_use:
            search_tasks.append(self._search_local(search_query, group_ids, top_k, document_ids, query_embedding=query_embedding))
        else:
            search_tasks.append(asyncio.sleep(0, result=[]))

        # 웹 검색 (Tavily 또는 SearXNG) - 재작성된 쿼리 사용
        if 'web' in sources_to_use and (self.tavily_client or self.searxng_client):
            search_tasks.append(self._search_web(search_query, analysis))
        else:
            search_tasks.append(asyncio.sleep(0, result=[]))

        # 공식 문서 검색 - 재작성된 쿼리 사용
        if 'docs' in sources_to_use and self.context7_client:
            search_tasks.append(self._search_docs(search_query, analysis))
        else:
            search_tasks.append(asyncio.sleep(0, result=[]))

        # 병렬 실행
        local_results, web_results, doc_results = await asyncio.gather(*search_tasks)

        logger.info(f"🔍 Search results: local={len(local_results)}, "
                   f"web={len(web_results)}, docs={len(doc_results)}")

        # 4. 결과 통합 및 랭킹
        merged_results = self._merge_and_rank(
            local_results,
            web_results,
            doc_results,
            analysis
        )

        # 4.5. 재랭킹 (Cross-encoder 기반)
        if self.reranking_enabled and merged_results:
            merged_results = await self._rerank_results(query, merged_results, top_k=10)

        # 5. LLM 답변 생성 (스트리밍 또는 일반)
        generator = None
        if stream:
            generator = self._generate_answer_stream(query, merged_results, analysis, system_prompt)
            answer = ""  # 스트리밍 모드에서는 generator로 전달
        else:
            answer = await self._generate_answer(query, merged_results, analysis, system_prompt)

        # 6. 검색 요약 정보
        search_summary = {
            'local_count': len(local_results),
            'web_count': len(web_results),
            'docs_count': len(doc_results),
            'total_sources': len(merged_results),
            'sources_used': sources_to_use,
            'analysis': {
                'time_sensitivity': analysis['time_sensitivity'],
                'needs_fresh_info': analysis['needs_fresh_info'],
                'is_internal': analysis['is_internal'],
                'benefits_from_web': analysis.get('benefits_from_web', False)
            },
            'quality_features': {
                'reranking_enabled': self.reranking_enabled,
                'query_rewrite_enabled': self.query_rewrite_enabled,
                'rewritten_query': search_query if self.query_rewrite_enabled and search_query != query else None
            }
        }

        # 7. 성능 메트릭 기록
        response_time = time.time() - start_time
        self.metrics.record_search(
            query=query,
            search_mode=search_mode,
            sources_used=sources_to_use,
            local_count=len(local_results),
            web_count=len(web_results),
            docs_count=len(doc_results),
            response_time=response_time,
            cache_hit=False,
            user_id=user_id
        )
        logger.info(f"⏱️ Hybrid RAG completed in {response_time:.3f}s")

        return {
            'answer': answer,
            'generator': generator,
            'sources': merged_results,
            'search_summary': search_summary,
            'rewritten_query': search_query if search_query != query else None,
            'query_rewrite_enabled': self.query_rewrite_enabled,
            'reranking_enabled': self.reranking_enabled
        }

    def _select_sources(self, analysis: Dict, mode: str) -> List[str]:
        """검색 소스 선택 로직"""

        # 사용자가 명시적으로 선택한 모드
        if mode == 'local-only':
            return ['local']

        if mode == 'web-enhanced':
            sources = ['local']
            if self.web_search_enabled:
                sources.append('web')
            return sources

        if mode == 'comprehensive':
            sources = ['local']
            if self.web_search_enabled:
                sources.append('web')
            if self.doc_search_enabled:
                sources.append('docs')
            return sources

        if mode == 'tools-only':
            # 외부 도구만 사용 (로컬 문서 제외)
            sources = []
            if self.web_search_enabled:
                sources.append('web')
            if self.doc_search_enabled:
                sources.append('docs')
            # 도구가 하나도 활성화되지 않은 경우 경고
            if not sources:
                logger.warning("⚠️ tools-only mode selected but no external tools enabled")
            return sources

        # 스마트 모드: 자동 선택
        sources = []

        # 내부 문서 질문이면 로컬만
        if analysis['is_internal']:
            return ['local']

        # 기본적으로 로컬 검색
        sources.append('local')

        # 웹 검색 추가 조건:
        # 1. 최신 정보 필요
        # 2. 웹 검색이 도움되는 질문 유형
        needs_web = (
            analysis['needs_fresh_info'] or
            analysis.get('benefits_from_web', False)
        )

        if needs_web and self.web_search_enabled:
            sources.append('web')
            logger.info(f"🌐 Web search added: needs_fresh={analysis['needs_fresh_info']}, "
                       f"benefits_from_web={analysis.get('benefits_from_web', False)}")

        # 기술 스택 명시 시 공식 문서 추가
        if analysis['tech_stack'] and self.doc_search_enabled:
            sources.append('docs')

        return sources

    @log_slow_query(threshold_seconds=2.0)
    async def _search_local(self, query: str, group_ids: List[str], top_k: int = 5, document_ids: Optional[List[str]] = None, query_embedding=None) -> List[Dict]:
        """
        로컬 문서 검색 (기존 RAG 시스템)

        Args:
            query: 검색 쿼리
            group_ids: 검색할 그룹 ID 목록
            top_k: 검색할 문서 개수 (기본값: 5)
            document_ids: 검색할 문서 ID/파일명 목록 (Optional)
            query_embedding: 미리 생성된 쿼리 임베딩 (Optional, 중복 생성 방지)
        """
        try:
            if document_ids:
                logger.info(f"📚 Local search: top_k={top_k}, document_ids={document_ids}")
            else:
                logger.info(f"📚 Local search: top_k={top_k}")

            # 전달받은 임베딩이 없으면 직접 생성
            if query_embedding is None:
                from .embeddings import EmbeddingModel
                import os

                # Initialize embedding model (lazy loading)
                if not hasattr(self, '_embedding_model'):
                    use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
                    if use_ollama:
                        self._embedding_model = EmbeddingModel()
                    else:
                        model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
                        self._embedding_model = EmbeddingModel(model_name=model_name)

                # Generate query embedding
                query_embedding = self._embedding_model.encode(query)[0]
            else:
                logger.debug("♻️ Reusing pre-computed query embedding")

            # Hybrid search on vector DB
            results = self.local_rag.vector_db.hybrid_search(
                query_text=query,
                query_embedding=query_embedding,
                top_k=top_k,
                group_ids=group_ids,
                document_ids=document_ids
            )

            formatted_results = []
            for r in results:
                # Create metadata from search result
                metadata = {
                    'filename': r.get('filename', 'Unknown'),
                    'source': r.get('source', ''),
                    'chunk_index': r.get('chunk_index', 0),
                    'group_id': r.get('group_id', '')
                }

                formatted_results.append({
                    'content': r['text'],
                    'source_type': 'local',
                    'metadata': metadata,
                    'score': r['score'],
                    'freshness': self._calculate_document_freshness(metadata)
                })

            return formatted_results

        except Exception as e:
            logger.error(f"❌ Local search error: {e}")
            return []

    @log_slow_query(threshold_seconds=3.0)
    async def _search_web(self, query: str, analysis: Dict) -> List[Dict]:
        """웹 검색 (프로바이더에 따라 Tavily 또는 SearXNG 사용)"""
        if self.web_search_provider == 'searxng':
            return await self._search_web_searxng(query, analysis)
        else:
            return await self._search_web_tavily(query, analysis)

    async def _search_web_tavily(self, query: str, analysis: Dict) -> List[Dict]:
        """웹 검색 (Tavily)"""
        if not self.tavily_client:
            return []

        try:
            # Tavily 검색 실행
            search_results = self.tavily_client.search(
                query=query,
                max_results=5,
                search_depth="advanced",  # basic | advanced
                include_answer=False,
                include_raw_content=True
            )

            web_chunks = []
            for result in search_results.get('results', []):
                content = result.get('content', '')
                if not content:
                    continue

                web_chunks.append({
                    'content': content[:1000],  # 최대 1000자
                    'source_type': 'web',
                    'metadata': {
                        'url': result.get('url', ''),
                        'title': result.get('title', ''),
                        'published_date': result.get('published_date', '최근'),
                    },
                    'score': result.get('score', 0.5),
                    'freshness': 1.0  # 웹 정보는 항상 최신으로 간주
                })

            logger.info(f"🌐 Tavily search found {len(web_chunks)} results")
            return web_chunks

        except Exception as e:
            logger.error(f"❌ Tavily search error: {e}")
            return []

    async def _search_web_searxng(self, query: str, analysis: Dict) -> List[Dict]:
        """웹 검색 (SearXNG + Crawl4AI 콘텐츠 추출)"""
        if not self.searxng_client:
            return []

        try:
            http_client = self.searxng_client['http_client']
            base_url = self.searxng_client['base_url']

            # SearXNG 검색 API 호출 (JSON 형식)
            search_url = f"{base_url}/search"
            params = {
                'q': query,
                'format': 'json',
                'categories': 'general',
                'language': 'ko-KR',
                'safesearch': 0,
                'pageno': 1
            }

            response = await http_client.get(search_url, params=params)
            response.raise_for_status()
            search_results = response.json()

            results = search_results.get('results', [])[:5]  # 상위 5개만
            logger.info(f"🌐 SearXNG search found {len(results)} results")

            # Crawl4AI로 콘텐츠 추출 시도
            if self.crawl4ai_client and results:
                web_chunks = await self._enrich_with_crawl4ai(results)
                if web_chunks:
                    return web_chunks

            # Crawl4AI 실패 시 기존 로직으로 폴백
            logger.info("📝 Using SearXNG snippets (Crawl4AI unavailable or failed)")
            web_chunks = []
            for i, result in enumerate(results):
                content = result.get('content', '')
                if not content:
                    content = result.get('title', '')

                if not content:
                    continue

                # SearXNG는 score가 없으므로 순위 기반 점수 부여
                score = 1.0 - (i * 0.1)  # 1.0, 0.9, 0.8, 0.7, 0.6

                web_chunks.append({
                    'content': content[:1000],  # 최대 1000자
                    'source_type': 'web',
                    'metadata': {
                        'url': result.get('url', ''),
                        'title': result.get('title', ''),
                        'published_date': result.get('publishedDate', '최근'),
                        'engine': result.get('engine', 'searxng'),
                    },
                    'score': score,
                    'freshness': 1.0  # 웹 정보는 항상 최신으로 간주
                })

            return web_chunks

        except Exception as e:
            logger.error(f"❌ SearXNG search error: {e}")
            return []

    def _html_to_text(self, html: str) -> str:
        """HTML을 텍스트로 변환 (간단한 태그 제거)"""
        import re

        if not html:
            return ""

        # script, style 태그와 내용 제거
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', ' ', text)

        # HTML 엔티티 디코딩
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        # 연속 공백을 하나로
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    async def _enrich_with_crawl4ai(self, searxng_results: List[Dict]) -> List[Dict]:
        """Crawl4AI를 사용하여 SearXNG 검색 결과의 콘텐츠를 병렬 추출"""
        if not self.crawl4ai_client:
            return []

        try:
            http_client = self.crawl4ai_client['http_client']
            base_url = self.crawl4ai_client['base_url']

            # URL 목록 추출 (최대 5개)
            urls = [r.get('url') for r in searxng_results if r.get('url')][:5]
            if not urls:
                return []

            logger.info(f"🕷️ Crawl4AI extracting content from {len(urls)} URLs (parallel)")

            crawl_url = f"{base_url}/crawl"

            # 개별 URL 비동기 병렬 크롤링 (각각 10초 타임아웃)
            async def crawl_single_url(url):
                try:
                    payload = {"urls": [url]}
                    response = await asyncio.wait_for(
                        http_client.post(crawl_url, json=payload),
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        return url, response.json()
                except asyncio.TimeoutError:
                    logger.debug(f"⏱️ Crawl4AI timeout for: {url[:80]}")
                except Exception as e:
                    logger.debug(f"⚠️ Crawl4AI error for {url[:80]}: {e}")
                return url, None

            # 모든 URL 동시 크롤링
            tasks = [crawl_single_url(url) for url in urls]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 결과를 content_map으로 변환
            content_map = {}
            for item in raw_results:
                if isinstance(item, Exception):
                    continue
                url, crawl_data = item
                if not crawl_data:
                    continue

                # 크롤링 결과 파싱 (리스트 또는 딕셔너리 형태)
                results_list = crawl_data.get('results', crawl_data)

                cr_list = results_list if isinstance(results_list, list) else [results_list]
                for cr in cr_list:
                    if not isinstance(cr, dict) or not cr.get('success'):
                        continue

                    cr_url = cr.get('url', url)
                    raw_markdown = cr.get('markdown', '') or ''
                    cleaned_html = cr.get('cleaned_html', '') or ''

                    # Crawl4AI v0.4+: markdown이 dict일 수 있음
                    # {"raw_markdown": "...", "markdown_with_citations": "...", ...}
                    if isinstance(raw_markdown, dict):
                        markdown = (
                            raw_markdown.get('raw_markdown', '')
                            or raw_markdown.get('markdown_with_citations', '')
                            or raw_markdown.get('fit_markdown', '')
                            or ''
                        )
                    else:
                        markdown = str(raw_markdown) if raw_markdown else ''

                    if isinstance(cleaned_html, dict):
                        cleaned_html = cleaned_html.get('html', '') or ''

                    if markdown and len(markdown.strip()) > 100:
                        content_map[cr_url] = markdown[:2000]
                    elif cleaned_html:
                        text_content = self._html_to_text(cleaned_html)
                        if len(text_content) > 100:
                            content_map[cr_url] = text_content[:2000]

            # 결과가 없으면 빈 리스트 반환
            if not content_map:
                logger.warning("⚠️ Crawl4AI returned no content")
                return []

            logger.info(f"✅ Crawl4AI extracted content from {len(content_map)}/{len(urls)} URLs")

            # SearXNG 결과와 Crawl4AI 콘텐츠 결합
            web_chunks = []
            for i, result in enumerate(searxng_results):
                url = result.get('url', '')
                content = content_map.get(url, result.get('content', ''))

                if not content:
                    content = result.get('title', '')

                if not content:
                    continue

                # SearXNG는 score가 없으므로 순위 기반 점수 부여
                score = 1.0 - (i * 0.1)  # 1.0, 0.9, 0.8, 0.7, 0.6

                web_chunks.append({
                    'content': content,
                    'source_type': 'web',
                    'metadata': {
                        'url': url,
                        'title': result.get('title', ''),
                        'published_date': result.get('publishedDate', '최근'),
                        'engine': result.get('engine', 'searxng'),
                        'content_source': 'crawl4ai' if url in content_map else 'snippet',
                    },
                    'score': score,
                    'freshness': 1.0  # 웹 정보는 항상 최신으로 간주
                })

            return web_chunks

        except asyncio.TimeoutError:
            logger.warning("⚠️ Crawl4AI request timed out")
            return []
        except Exception as e:
            logger.error(f"❌ Crawl4AI extraction error: {e}")
            return []

    @log_slow_query(threshold_seconds=3.0)
    async def _search_docs(self, query: str, analysis: Dict) -> List[Dict]:
        """공식 문서 검색 (Context7 REST API v2)"""
        if not self.context7_client:
            logger.debug("📚 Context7 not initialized, skipping docs search")
            return []

        try:
            # 기술 스택 감지
            tech_stack_list = analysis.get('tech_stack')

            if not tech_stack_list or len(tech_stack_list) == 0:
                logger.debug("📚 No tech stack detected, skipping Context7 search")
                return []

            # Extract first tech stack (tech_stack is a list of dicts)
            tech_stack_info = tech_stack_list[0]
            tech_stack_name = tech_stack_info.get('name')
            tech_stack_version = tech_stack_info.get('version')

            if not tech_stack_name:
                logger.debug("📚 No tech stack name found, skipping Context7 search")
                return []

            logger.info(f"📚 Searching Context7 for tech stack: {tech_stack_name}" +
                       (f" (version: {tech_stack_version})" if tech_stack_version else ""))

            # Context7 REST API v2 호출
            http_client = self.context7_client['http_client']
            base_url = self.context7_client['base_url']

            # 1단계: Library 검색 (GET /libs/search) — 3초 타임아웃
            search_params = {
                "libraryName": tech_stack_name,
                "query": query
            }

            try:
                search_response = await asyncio.wait_for(
                    http_client.get(
                        f"{base_url}/libs/search",
                        params=search_params
                    ),
                    timeout=3.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"⚠️  Context7 library search timed out (3s) for: {tech_stack_name}")
                return []

            if search_response.status_code != 200:
                logger.warning(f"⚠️  Context7 library search failed: {search_response.status_code}")
                return []

            search_data = search_response.json()
            results = search_data.get('results', [])

            if not results:
                logger.warning(f"⚠️  No libraries found for: {tech_stack_name}")
                return []

            # 첫 번째 매칭 라이브러리 사용
            library = results[0]
            library_id = library.get('id')

            if not library_id:
                logger.warning("⚠️  No library ID found")
                return []

            logger.info(f"📖 Found library: {library.get('name', library_id)}")

            # 2단계: 문서 컨텍스트 조회 (GET /context) — 4초 타임아웃
            context_params = {
                "libraryId": library_id,
                "query": query
            }

            try:
                context_response = await asyncio.wait_for(
                    http_client.get(
                        f"{base_url}/context",
                        params=context_params
                    ),
                    timeout=4.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"⚠️  Context7 context fetch timed out (4s) for: {library_id}")
                return []

            if context_response.status_code != 200:
                logger.warning(f"⚠️  Context7 context fetch failed: {context_response.status_code}")
                return []

            # Context7 응답은 text일 수 있음
            context_text = context_response.text

            if not context_text or len(context_text.strip()) == 0:
                logger.warning("⚠️  Empty context response")
                return []

            # 결과 포맷팅 (단일 컨텍스트 문서)
            docs_chunks = [{
                'content': context_text[:2000],  # 최대 2000자
                'source_type': 'docs',
                'metadata': {
                    'library': library.get('name', tech_stack_name),
                    'library_id': library_id,
                    'title': f"{tech_stack_name.title()} Documentation",
                    'url': library.get('url', ''),
                    'version': tech_stack_version
                },
                'score': 0.9,  # 공식 문서는 높은 신뢰도
                'freshness': 0.8
            }]

            logger.info(f"📖 Context7 found documentation context ({len(context_text)} chars)")
            return docs_chunks

        except Exception as e:
            logger.error(f"❌ Context7 search error: {e}")
            logger.exception(e)  # 상세 에러 로그
            return []

    def _merge_and_rank(
        self,
        local: List[Dict],
        web: List[Dict],
        docs: List[Dict],
        analysis: Dict
    ) -> List[Dict]:
        """결과 통합 및 랭킹"""

        # 가중치 계산 (실제 검색 결과 고려)
        weights = self._calculate_source_weights(
            analysis,
            has_local=len(local) > 0,
            has_web=len(web) > 0,
            has_docs=len(docs) > 0
        )

        # 모든 결과 병합
        all_results = []

        for item in local:
            item['final_score'] = item['score'] * weights['local'] * item['freshness']
            all_results.append(item)

        for item in web:
            item['final_score'] = item['score'] * weights['web'] * item['freshness']
            all_results.append(item)

        for item in docs:
            item['final_score'] = item['score'] * weights['docs'] * item['freshness']
            all_results.append(item)

        # 최종 점수 기준 정렬
        all_results.sort(key=lambda x: x['final_score'], reverse=True)

        # 상위 10개 반환 (중복 제거 후)
        return self._deduplicate(all_results[:10])

    def _calculate_source_weights(
        self,
        analysis: Dict,
        has_local: bool = False,
        has_web: bool = False,
        has_docs: bool = False
    ) -> Dict[str, float]:
        """소스별 가중치 계산"""
        weights = {
            'local': 0.6,
            'web': 0.3,
            'docs': 0.1
        }

        # 🔴 최우선: 로컬 검색 결과가 있으면 로컬 우선
        # (사용자가 특정 문서/그룹을 선택한 경우)
        if has_local and not has_web and not has_docs:
            # 로컬 검색만 수행된 경우 - 로컬 문서만 사용
            weights['local'] = 1.0
            weights['web'] = 0.0
            weights['docs'] = 0.0
            logger.info("📚 Local-only search detected - prioritizing local documents")
            return weights

        # 내부 문서 질문이면 로컬 가중치 상승
        if analysis['is_internal']:
            weights['local'] = 0.9
            weights['web'] = 0.05
            weights['docs'] = 0.05

        # 최신 정보 필요하면 웹 가중치 상승
        elif analysis['time_sensitivity'] == 'high':
            weights['local'] = 0.3
            weights['web'] = 0.6
            weights['docs'] = 0.1

        # 기술 문서 질문이면서 로컬 결과도 있는 경우
        elif analysis['tech_stack'] and has_local:
            # 로컬 문서를 우선하되 공식 문서도 참고
            weights['local'] = 0.5  # 기존 0.3에서 상승
            weights['web'] = 0.2    # 기존 0.3에서 하락
            weights['docs'] = 0.3   # 기존 0.4에서 하락

        # 기술 문서 질문이지만 로컬 결과가 없는 경우
        elif analysis['tech_stack']:
            weights['local'] = 0.3
            weights['web'] = 0.3
            weights['docs'] = 0.4

        # 로컬 검색 결과가 있으면 기본적으로 로컬 가중치 상승
        elif has_local:
            weights['local'] = 0.7  # 기존 0.6에서 상승
            weights['web'] = 0.2    # 기존 0.3에서 하락
            weights['docs'] = 0.1

        return weights

    def _calculate_document_freshness(self, metadata: Dict) -> float:
        """문서 신선도 계산 (0.0 ~ 1.0)"""
        # 업로드 날짜가 있으면 계산
        if 'upload_date' in metadata:
            try:
                upload_date = datetime.fromisoformat(metadata['upload_date'])
                days_old = (datetime.now() - upload_date).days

                # 신선도 감쇠 함수
                if days_old < 30:
                    return 1.0
                elif days_old < 90:
                    return 0.8
                elif days_old < 180:
                    return 0.6
                else:
                    return 0.4
            except Exception:
                pass

        return 0.5  # 기본값

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:
        """중복 제거 (간단한 텍스트 해시 기반)"""
        seen_contents = set()
        unique_results = []

        for result in results:
            # 앞 200자로 중복 판단
            content_hash = hash(result['content'][:200])
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                unique_results.append(result)

        return unique_results

    async def _generate_answer(
        self,
        query: str,
        merged_results: List[Dict],
        analysis: Dict,
        system_prompt: Optional[str] = None
    ) -> str:
        """통합 답변 생성"""

        # 소스별로 그룹화
        local_chunks = [r for r in merged_results if r['source_type'] == 'local']
        web_chunks = [r for r in merged_results if r['source_type'] == 'web']
        doc_chunks = [r for r in merged_results if r['source_type'] == 'docs']

        # 강화된 프롬프트 생성
        prompt = self._build_hybrid_prompt(
            query,
            local_chunks,
            web_chunks,
            doc_chunks,
            analysis
        )

        # LLM 답변 생성 (system_prompt 지원)
        # Create messages format for OllamaLLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Use generate_response method (non-streaming)
        answer = self.local_rag.llm._generate_response(
            messages=messages,
            max_tokens=2000,
            temperature=0.5
        )

        # ⚠️ 빈 응답 체크
        if not answer or len(answer.strip()) == 0:
            logger.warning("⚠️ Empty answer from LLM in hybrid RAG")
            answer = "죄송합니다. 응답을 생성하지 못했습니다. 다시 시도해 주세요."

        return answer

    def _generate_answer_stream(
        self,
        query: str,
        merged_results: List[Dict],
        analysis: Dict,
        system_prompt: Optional[str] = None
    ):
        """스트리밍 답변 생성 - 토큰 단위로 yield하는 generator 반환"""

        # 소스별로 그룹화
        local_chunks = [r for r in merged_results if r['source_type'] == 'local']
        web_chunks = [r for r in merged_results if r['source_type'] == 'web']
        doc_chunks = [r for r in merged_results if r['source_type'] == 'docs']

        # 강화된 프롬프트 생성
        prompt = self._build_hybrid_prompt(
            query,
            local_chunks,
            web_chunks,
            doc_chunks,
            analysis
        )

        # LLM 메시지 구성
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 동기 스트리밍 generator 반환 (query.py에서 isgenerator로 감지)
        return self.local_rag.llm._stream_response(
            messages=messages,
            max_tokens=2000,
            temperature=0.5
        )

    def _build_hybrid_prompt(
        self,
        query: str,
        local: List[Dict],
        web: List[Dict],
        docs: List[Dict],
        analysis: Dict
    ) -> str:
        """하이브리드 RAG 프롬프트 생성 (컨텍스트 압축 적용)"""

        MAX_TOTAL_CONTEXT_CHARS = 4000  # 글로벌 컨텍스트 한도
        MAX_PER_DOC_CHARS = 600        # 문서당 한도

        # 소스 타입별 최대 개수 제한
        # Note: score 필드가 없는 결과도 포함 (score 필터링 제거 - 검색 엔진이 이미 관련도 순으로 정렬)
        local = local[:5]
        web = web[:3]
        docs = docs[:2]
        logger.debug(f"📊 [PROMPT] Context compression: local={len(local)}, web={len(web)}, docs={len(docs)}")

        used_chars = 0

        prompt = f"""질문: {query}

# 제공된 정보 소스 (총 {len(local) + len(web) + len(docs)}개)

"""

        # 내부 문서
        if local:
            prompt += f"## 📁 내부 문서 ({len(local)}개) ⭐ 최우선 참조\n\n"
            for i, chunk in enumerate(local, 1):
                if used_chars >= MAX_TOTAL_CONTEXT_CHARS:
                    break
                meta = chunk['metadata']
                filename = meta.get('filename', 'Unknown')
                doc_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
                score = chunk.get('score', 0.0)
                freshness = chunk.get('freshness', 0.5)

                remaining = min(MAX_PER_DOC_CHARS, MAX_TOTAL_CONTEXT_CHARS - used_chars)
                content_slice = chunk['content'][:remaining]
                used_chars += len(content_slice)

                prompt += f"""[내부:{doc_name}] (파일: {filename})
관련도: {score:.0%} | 신선도: {freshness:.0%}
---
{content_slice}
...

"""

        # 웹 검색 결과
        if web and used_chars < MAX_TOTAL_CONTEXT_CHARS:
            prompt += f"\n## 🌐 최신 웹 정보 ({len(web)}개)\n\n"
            for i, chunk in enumerate(web, 1):
                if used_chars >= MAX_TOTAL_CONTEXT_CHARS:
                    break
                meta = chunk['metadata']
                title = meta.get('title', 'Unknown')
                url = meta.get('url', '')
                pub_date = meta.get('published_date', '최근')

                remaining = min(MAX_PER_DOC_CHARS, MAX_TOTAL_CONTEXT_CHARS - used_chars)
                content_slice = chunk['content'][:remaining]
                used_chars += len(content_slice)

                prompt += f"""[웹-{i}] {title}
출처: {url}
발행일: {pub_date}
---
{content_slice}
...

"""

        # 공식 문서
        if docs and used_chars < MAX_TOTAL_CONTEXT_CHARS:
            prompt += f"\n## 📚 공식 문서 ({len(docs)}개)\n\n"
            for i, chunk in enumerate(docs, 1):
                if used_chars >= MAX_TOTAL_CONTEXT_CHARS:
                    break
                meta = chunk['metadata']
                library = meta.get('library', 'Unknown')
                version = meta.get('version', '')

                remaining = min(MAX_PER_DOC_CHARS, MAX_TOTAL_CONTEXT_CHARS - used_chars)
                content_slice = chunk['content'][:remaining]
                used_chars += len(content_slice)

                prompt += f"""[문서-{i}] {library} {version}
---
{content_slice}
...

"""

        # 답변 작성 지침 (시스템 프롬프트와 중복 제거 — 핵심만 유지)
        prompt += "\n# 지침\n"

        if local:
            prompt += f"⭐ 내부 문서 {len(local)}개 최우선 참조. 부분 정보라도 활용. 웹/공식 문서는 보충용.\n"
        prompt += """출처 형식: [내부:실제문서명], [웹:사이트명], [문서:라이브러리명] — 번호 표기 금지
"""

        # 🔴 문서명 참조 리스트 추가 — LLM이 정확한 이름을 복사하도록 유도
        doc_names = []
        if local:
            for chunk in local:
                meta = chunk['metadata']
                filename = meta.get('filename', 'Unknown')
                doc_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
                if doc_name not in doc_names and doc_name != 'Unknown':
                    doc_names.append(doc_name)

        if doc_names:
            prompt += """## 🔴 출처 표기용 정확한 문서명 목록 (반드시 이 목록에서 복사하여 사용)
아래 문서명을 인용할 때 한 글자도 변경하지 말고 그대로 복사하세요:
"""
            for name in doc_names:
                prompt += f"- [내부:{name}]\n"
            prompt += "\n"

        prompt += "답변을 작성해주세요.\n"

        return prompt
