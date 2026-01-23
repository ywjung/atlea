"""
Ollama Reranker - 검색 결과 재랭킹 모듈

Ollama API를 사용하여 쿼리와 문서 간의 의미적 관련성을
재평가하고 검색 결과를 재정렬합니다.

📝 Changelog:
- 2026-01-23: Ollama Reranker로 전환
  - Qwen3-Reranker 모델 지원
  - Jina Reranker 제거
- 2026-01-22: 초기 구현
"""

import asyncio
import os
from typing import List, Dict, Optional, Tuple
from loguru import logger
import httpx


class OllamaReranker:
    """
    Ollama API를 사용한 Reranker

    Qwen3-Reranker 등 Ollama에서 제공하는 reranker 모델을 활용합니다.
    """

    # 기본 모델: Qwen3-Reranker-8B
    DEFAULT_MODEL = "dengcao/Qwen3-Reranker-8B:Q4_K_M"

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Ollama Reranker 초기화

        Args:
            model_name: Ollama reranker 모델 이름
            base_url: Ollama API URL (기본: http://localhost:11434)
            timeout: API 타임아웃 (초)
        """
        self.model_name = model_name or os.getenv("OLLAMA_RERANKER_MODEL", self.DEFAULT_MODEL)
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = timeout
        self._client = None

        logger.info(f"🎯 OllamaReranker initialized (model: {self.model_name}, url: {self.base_url})")

    def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 생성 (재사용)"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    def _build_rerank_prompt(self, query: str, document: str) -> str:
        """
        Qwen3-Reranker 형식의 프롬프트 생성

        Args:
            query: 사용자 쿼리
            document: 문서 내용

        Returns:
            Reranker 프롬프트
        """
        # Qwen3-Reranker 공식 프롬프트 형식
        return f"""<|im_start|>system
Judge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".
<|im_end|>
<|im_start|>user
<Instruct>: Given a web search query, retrieve relevant passages that answer the query
<Query>: {query}
<Document>: {document}
<|im_end|>
<|im_start|>assistant
"""

    async def _score_single(self, query: str, document: str) -> float:
        """
        단일 문서의 관련성 점수 계산

        Args:
            query: 사용자 쿼리
            document: 문서 내용

        Returns:
            관련성 점수 (0.0 ~ 1.0)
        """
        try:
            client = self._get_client()
            prompt = self._build_rerank_prompt(query, document[:2000])  # 최대 2000자

            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 5,  # "yes" 또는 "no"만 필요
                        "temperature": 0.0,  # 결정적 출력
                    }
                }
            )
            response.raise_for_status()
            result = response.json()

            # 응답에서 yes/no 판단
            answer = result.get("response", "").strip().lower()

            # yes → 1.0, no → 0.0, 기타 → 0.5
            if answer.startswith("yes"):
                return 1.0
            elif answer.startswith("no"):
                return 0.0
            else:
                # 불확실한 경우 중간 점수
                logger.debug(f"Uncertain reranker response: {answer}")
                return 0.5

        except Exception as e:
            logger.warning(f"Reranking score failed: {e}")
            return 0.5  # 오류 시 중간 점수

    async def _score_batch(
        self,
        query: str,
        documents: List[Dict],
        max_concurrent: int = 5
    ) -> List[Tuple[int, float]]:
        """
        배치 문서 점수 계산 (동시 처리)

        Args:
            query: 사용자 쿼리
            documents: 문서 리스트
            max_concurrent: 최대 동시 요청 수

        Returns:
            (인덱스, 점수) 튜플 리스트
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def score_with_index(idx: int, doc: Dict) -> Tuple[int, float]:
            async with semaphore:
                content = doc.get('content', '')
                if not content:
                    return (idx, 0.0)
                score = await self._score_single(query, content)
                return (idx, score)

        tasks = [score_with_index(i, doc) for i, doc in enumerate(documents)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외 처리
        scored = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Batch scoring exception: {result}")
                continue
            scored.append(result)

        return scored

    async def rerank_async(
        self,
        query: str,
        documents: List[Dict],
        top_k: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict]:
        """
        비동기 검색 결과 재랭킹

        Args:
            query: 사용자 쿼리
            documents: 검색 결과 리스트 (각 문서는 'content' 키 필요)
            top_k: 반환할 최대 문서 수
            score_threshold: 최소 점수 임계값 (이하는 필터링)

        Returns:
            재랭킹된 문서 리스트 (rerank_score 추가됨)
        """
        if not documents:
            return []

        try:
            # 배치 점수 계산
            scores = await self._score_batch(query, documents)

            # 점수 추가 및 필터링
            reranked = []
            score_map = {idx: score for idx, score in scores}

            for i, doc in enumerate(documents):
                doc = doc.copy()
                doc['rerank_score'] = score_map.get(i, 0.5)

                if doc['rerank_score'] >= score_threshold:
                    reranked.append(doc)

            # 재랭킹 점수로 정렬
            reranked.sort(key=lambda x: x['rerank_score'], reverse=True)

            logger.debug(f"🎯 Reranked {len(documents)} → {len(reranked[:top_k])} documents")

            return reranked[:top_k]

        except Exception as e:
            logger.error(f"❌ Reranking failed: {e}")
            # 실패 시 원본 반환
            return documents[:top_k]

    def rerank(
        self,
        query: str,
        documents: List[Dict],
        top_k: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict]:
        """
        동기 검색 결과 재랭킹 (비동기 메서드 래퍼)

        Args:
            query: 사용자 쿼리
            documents: 검색 결과 리스트
            top_k: 반환할 최대 문서 수
            score_threshold: 최소 점수 임계값

        Returns:
            재랭킹된 문서 리스트
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.rerank_async(query, documents, top_k, score_threshold)
        )

    async def close(self):
        """HTTP 클라이언트 정리"""
        if self._client:
            await self._client.aclose()
            self._client = None


class SentenceTransformerReranker:
    """
    Sentence Transformers Cross-encoder 기반 재랭킹 (대안)

    로컬에서 실행되는 가벼운 Cross-encoder 구현
    """

    # 기본 모델: MS MARCO 기반 다국어 모델
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None
    ):
        """
        Sentence Transformer Reranker 초기화

        Args:
            model_name: Cross-encoder 모델 이름
            device: 실행 장치
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.model = None
        self.device = device
        self._initialized = False

        logger.info(f"🎯 SentenceTransformerReranker initialized (model: {self.model_name})")

    def _lazy_init(self):
        """모델 지연 로딩"""
        if self._initialized:
            return

        try:
            from sentence_transformers import CrossEncoder

            logger.info(f"🔧 Loading cross-encoder model...")

            self.model = CrossEncoder(
                self.model_name,
                device=self.device
            )

            self._initialized = True
            logger.success(f"✅ Cross-encoder model loaded successfully")

        except ImportError as e:
            logger.error(f"❌ sentence-transformers not installed: {e}")
            raise RuntimeError(
                "Cross-encoder reranking requires sentence-transformers. "
                "Install with: pip install sentence-transformers"
            )
        except Exception as e:
            logger.error(f"❌ Failed to load cross-encoder model: {e}")
            raise

    def rerank(
        self,
        query: str,
        documents: List[Dict],
        top_k: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict]:
        """
        검색 결과 재랭킹

        Args:
            query: 사용자 쿼리
            documents: 검색 결과 리스트
            top_k: 반환할 최대 문서 수
            score_threshold: 최소 점수 임계값

        Returns:
            재랭킹된 문서 리스트
        """
        if not documents:
            return []

        # 지연 초기화
        self._lazy_init()

        try:
            # 쿼리-문서 쌍 생성
            pairs = []
            for doc in documents:
                content = doc.get('content', '')
                if content:
                    pairs.append((query, content[:2000]))  # 최대 2000자

            if not pairs:
                return documents[:top_k]

            # Cross-encoder 점수 계산
            scores = self.model.predict(pairs)

            # 점수 추가 및 정렬
            reranked = []
            for i, doc in enumerate(documents):
                if i < len(scores):
                    doc = doc.copy()
                    # 점수 정규화 (Sigmoid)
                    import math
                    normalized_score = 1 / (1 + math.exp(-float(scores[i])))
                    doc['rerank_score'] = normalized_score

                    if doc['rerank_score'] >= score_threshold:
                        reranked.append(doc)

            # 재랭킹 점수로 정렬
            reranked.sort(key=lambda x: x['rerank_score'], reverse=True)

            logger.debug(f"🎯 Reranked {len(documents)} → {len(reranked[:top_k])} documents")

            return reranked[:top_k]

        except Exception as e:
            logger.error(f"❌ Reranking failed: {e}")
            return documents[:top_k]

    async def rerank_async(
        self,
        query: str,
        documents: List[Dict],
        top_k: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict]:
        """비동기 재랭킹"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.rerank(query, documents, top_k, score_threshold)
        )


def get_reranker(
    model_type: str = "ollama",
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    device: Optional[str] = None
):
    """
    Reranker 팩토리 함수

    Args:
        model_type: 'ollama' 또는 'sentence-transformer'
        model_name: 사용할 모델 이름 (None=기본값)
        base_url: Ollama API URL (ollama 타입 전용)
        device: 실행 장치 (sentence-transformer 타입 전용)

    Returns:
        Reranker 인스턴스
    """
    if model_type.lower() == "ollama":
        return OllamaReranker(model_name=model_name, base_url=base_url)
    elif model_type.lower() in ["sentence-transformer", "st", "cross-encoder"]:
        return SentenceTransformerReranker(model_name=model_name, device=device)
    else:
        logger.warning(f"Unknown reranker type: {model_type}, using Ollama")
        return OllamaReranker(model_name=model_name, base_url=base_url)
