"""
Hybrid RAG Orchestrator - 다중 소스 RAG 시스템

로컬 문서 + 웹 검색 + 공식 문서를 결합하여 더 완벽한 답변 제공

📝 Changelog:
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


class HybridRAGOrchestrator:
    """
    다중 소스 RAG 시스템
    - 로컬 문서 (기존 RAG)
    - 웹 검색 (Tavily MCP)
    - 공식 문서 (Context7 MCP) - 추후 구현
    """

    def __init__(
        self,
        local_rag,
        cache_manager,
        enable_web_search: bool = True,
        enable_doc_search: bool = False
    ):
        """
        하이브리드 RAG 오케스트레이터 초기화

        Args:
            local_rag: 기존 RAG 시스템
            cache_manager: 캐시 매니저
            enable_web_search: 웹 검색 활성화 여부
            enable_doc_search: 공식 문서 검색 활성화 여부
        """
        self.local_rag = local_rag
        self.cache = cache_manager
        self.analyzer = QueryAnalyzer()

        # 성능 모니터링
        self.metrics = MetricsCollector(cache_manager.redis)

        # MCP 클라이언트 초기화
        self.web_search_enabled = enable_web_search
        self.doc_search_enabled = enable_doc_search

        # Tavily 클라이언트
        self.tavily_client = None
        if enable_web_search:
            self.tavily_client = self._init_tavily()

        # Context7 클라이언트 (추후 구현)
        self.context7_client = None
        if enable_doc_search:
            self.context7_client = self._init_context7()

        logger.info("🔗 HybridRAGOrchestrator initialized")
        logger.info(f"  - Web Search: {self.web_search_enabled}")
        logger.info(f"  - Doc Search: {self.doc_search_enabled}")

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
                    timeout=15.0
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

    async def answer(
        self,
        query: str,
        group_ids: List[str],
        user_id: str,
        search_mode: str = 'smart',
        system_prompt: Optional[str] = None,
        top_k: int = 5,
        document_ids: Optional[List[str]] = None
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
                   f"fresh={analysis['needs_fresh_info']}")

        # 2. 검색 소스 결정
        sources_to_use = self._select_sources(analysis, search_mode)
        logger.info(f"🎯 Selected sources: {sources_to_use}")

        # 3. 병렬 검색 실행
        search_tasks = []

        # 로컬 문서 검색
        if 'local' in sources_to_use:
            search_tasks.append(self._search_local(query, group_ids, top_k, document_ids))
        else:
            search_tasks.append(asyncio.sleep(0, result=[]))

        # 웹 검색
        if 'web' in sources_to_use and self.tavily_client:
            search_tasks.append(self._search_web(query, analysis))
        else:
            search_tasks.append(asyncio.sleep(0, result=[]))

        # 공식 문서 검색
        if 'docs' in sources_to_use and self.context7_client:
            search_tasks.append(self._search_docs(query, analysis))
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

        # 5. LLM 답변 생성
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
                'is_internal': analysis['is_internal']
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
            'sources': merged_results,
            'search_summary': search_summary
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

        # 최신 정보 필요 시 웹 검색 추가
        if analysis['needs_fresh_info'] and self.web_search_enabled:
            sources.append('web')

        # 기술 스택 명시 시 공식 문서 추가
        if analysis['tech_stack'] and self.doc_search_enabled:
            sources.append('docs')

        return sources

    @log_slow_query(threshold_seconds=2.0)
    async def _search_local(self, query: str, group_ids: List[str], top_k: int = 5, document_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        로컬 문서 검색 (기존 RAG 시스템)

        Args:
            query: 검색 쿼리
            group_ids: 검색할 그룹 ID 목록
            top_k: 검색할 문서 개수 (기본값: 5)
            document_ids: 검색할 문서 ID/파일명 목록 (Optional)
        """
        try:
            if document_ids:
                logger.info(f"📚 Local search: top_k={top_k}, document_ids={document_ids}")
            else:
                logger.info(f"📚 Local search: top_k={top_k}")

            # Vector DB 직접 사용 (embedding 생성 포함)
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

            logger.info(f"🌐 Web search found {len(web_chunks)} results")
            return web_chunks

        except Exception as e:
            logger.error(f"❌ Web search error: {e}")
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

            # 1단계: Library 검색 (GET /libs/search)
            search_params = {
                "libraryName": tech_stack_name,
                "query": query
            }

            search_response = await http_client.get(
                f"{base_url}/libs/search",
                params=search_params
            )

            if search_response.status_code != 200:
                logger.warning(f"⚠️  Context7 library search failed: {search_response.status_code}")
                return []

            search_data = search_response.json()
            results = search_data.get('results', [])

            if not results:
                logger.warning(f"⚠️  No libraries found for: {tech_stack}")
                return []

            # 첫 번째 매칭 라이브러리 사용
            library = results[0]
            library_id = library.get('id')

            if not library_id:
                logger.warning("⚠️  No library ID found")
                return []

            logger.info(f"📖 Found library: {library.get('name', library_id)}")

            # 2단계: 문서 컨텍스트 조회 (GET /context)
            context_params = {
                "libraryId": library_id,
                "query": query
            }

            context_response = await http_client.get(
                f"{base_url}/context",
                params=context_params
            )

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
            except:
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

        return answer

    def _build_hybrid_prompt(
        self,
        query: str,
        local: List[Dict],
        web: List[Dict],
        docs: List[Dict],
        analysis: Dict
    ) -> str:
        """하이브리드 RAG 프롬프트 생성"""

        prompt = f"""질문: {query}

# 제공된 정보 소스 (총 {len(local) + len(web) + len(docs)}개)

"""

        # 내부 문서
        if local:
            prompt += f"## 📁 내부 문서 ({len(local)}개) ⭐ 최우선 참조\n\n"
            for i, chunk in enumerate(local, 1):
                meta = chunk['metadata']
                filename = meta.get('filename', 'Unknown')
                score = chunk.get('score', 0.0)
                freshness = chunk.get('freshness', 0.5)

                prompt += f"""[내부-{i}] {filename}
관련도: {score:.0%} | 신선도: {freshness:.0%}
---
{chunk['content'][:800]}
...

"""

        # 웹 검색 결과
        if web:
            prompt += f"\n## 🌐 최신 웹 정보 ({len(web)}개)\n\n"
            for i, chunk in enumerate(web, 1):
                meta = chunk['metadata']
                title = meta.get('title', 'Unknown')
                url = meta.get('url', '')
                pub_date = meta.get('published_date', '최근')

                prompt += f"""[웹-{i}] {title}
출처: {url}
발행일: {pub_date}
---
{chunk['content'][:800]}
...

"""

        # 공식 문서
        if docs:
            prompt += f"\n## 📚 공식 문서 ({len(docs)}개)\n\n"
            for i, chunk in enumerate(docs, 1):
                meta = chunk['metadata']
                library = meta.get('library', 'Unknown')
                version = meta.get('version', '')

                prompt += f"""[문서-{i}] {library} {version}
---
{chunk['content'][:800]}
...

"""

        # 답변 작성 지침
        prompt += """
# 답변 작성 지침

## 🔴 중요: 정보 우선순위 (절대 규칙)
"""

        # 로컬 문서가 있는 경우 강력한 우선순위 지침 추가
        if local:
            prompt += f"""
⭐ **내부 문서가 {len(local)}개 제공되었습니다. 반드시 먼저 확인하세요!**

1. **내부 문서 최우선**: 질문에 대한 답변이 내부 문서에 있다면, 반드시 내부 문서를 기반으로 답변하세요.
2. **"정보 없음" 금지**: 내부 문서에 관련 정보가 조금이라도 있다면, "제공된 문서에 정보가 없습니다"라고 답하지 마세요.
3. **부분 정보도 활용**: 내부 문서에 완전한 답은 없더라도 관련 정보가 있다면 그것을 기반으로 답변하세요.
4. **보조 자료로 활용**: 내부 문서가 주 답변이고, 웹/공식 문서는 보충 설명용입니다.

"""
        else:
            prompt += """
1. **정보 우선순위**: 내부 문서 > 공식 문서 > 웹 정보
   - 내부 문서가 있으면 반드시 최우선으로 참조
   - 정보 충돌 시 내부 문서 내용을 기준으로 판단

"""

        prompt += """
## 기본 원칙
1. **정보 통합**: 제공된 모든 소스를 종합하여 포괄적인 답변 제공
2. **출처 명시**: 각 주장마다 출처 표시
   - 내부 문서: [내부:파일명]
   - 웹 정보: [웹:사이트명]
   - 공식 문서: [문서:라이브러리명]
3. **최신성 표시**: 웹 정보 인용 시 발행 날짜 명시

## 답변 구조
1. 핵심 답변 (2-3문장) - 내부 문서 기반 우선
2. 상세 설명 - 내부 문서 내용 중심
3. 추가 정보 - 웹/공식 문서로 보충 (필요시)

## 특수 상황
- 정보 부족: 모든 소스를 확인한 후에만 "제공된 자료에는 [내용]에 대한 정보가 부족합니다"라고 답변
- 정보 충돌: 내부 문서 우선, 다른 소스는 "참고로, [출처]에서는..."으로 보충

답변을 작성해주세요.
"""

        return prompt
