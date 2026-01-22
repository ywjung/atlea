"""
Cross-encoder Reranker - 검색 결과 재랭킹 모듈

Cross-encoder 모델을 사용하여 쿼리와 문서 간의 의미적 관련성을
재평가하고 검색 결과를 재정렬합니다.

📝 Changelog:
- 2026-01-22: 초기 구현
  - Jina Reranker v2 다국어 모델 지원
  - 배치 처리 및 점수 정규화
  - 비동기 처리 지원
"""

import asyncio
from typing import List, Dict, Optional
from loguru import logger


class JinaReranker:
    """
    Jina Reranker를 사용한 Cross-encoder 기반 재랭킹

    Cross-encoder는 쿼리와 문서를 함께 인코딩하여
    더 정확한 관련성 점수를 계산합니다.
    """

    # 기본 모델: Jina Reranker v2 다국어 (한국어 포함)
    DEFAULT_MODEL = "jinaai/jina-reranker-v2-base-multilingual"

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        max_length: int = 512
    ):
        """
        Reranker 초기화

        Args:
            model_name: Cross-encoder 모델 이름 (기본: Jina Reranker v2)
            device: 실행 장치 ('cuda', 'mps', 'cpu', None=auto)
            max_length: 최대 입력 길이
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.max_length = max_length
        self.model = None
        self.device = device
        self._initialized = False

        logger.info(f"🎯 JinaReranker initialized (model: {self.model_name})")

    def _lazy_init(self):
        """모델 지연 로딩 (첫 사용 시 초기화)"""
        if self._initialized:
            return

        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            import torch

            # 장치 자동 감지
            if self.device is None:
                if torch.cuda.is_available():
                    self.device = "cuda"
                elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    self.device = "mps"
                else:
                    self.device = "cpu"

            logger.info(f"🔧 Loading reranker model on {self.device}...")

            # 모델 및 토크나이저 로드
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )
            self.model.to(self.device)
            self.model.eval()

            self._initialized = True
            logger.success(f"✅ Reranker model loaded successfully on {self.device}")

        except ImportError as e:
            logger.error(f"❌ Required packages not installed: {e}")
            raise RuntimeError(
                "Cross-encoder reranking requires transformers and torch. "
                "Install with: pip install transformers torch"
            )
        except Exception as e:
            logger.error(f"❌ Failed to load reranker model: {e}")
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
            documents: 검색 결과 리스트 (각 문서는 'content' 키 필요)
            top_k: 반환할 최대 문서 수
            score_threshold: 최소 점수 임계값 (이하는 필터링)

        Returns:
            재랭킹된 문서 리스트 (rerank_score 추가됨)
        """
        if not documents:
            return []

        # 지연 초기화
        self._lazy_init()

        import torch

        try:
            # 쿼리-문서 쌍 생성
            pairs = []
            for doc in documents:
                content = doc.get('content', '')
                if content:
                    # 최대 길이 제한
                    truncated_content = content[:self.max_length * 4]  # 대략적인 토큰 추정
                    pairs.append([query, truncated_content])

            if not pairs:
                return documents[:top_k]

            # 토크나이징
            inputs = self.tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt"
            ).to(self.device)

            # 추론
            with torch.no_grad():
                outputs = self.model(**inputs)
                scores = outputs.logits.squeeze(-1)

                # Sigmoid로 0-1 범위 정규화
                scores = torch.sigmoid(scores).cpu().numpy()

            # 점수 추가 및 정렬
            reranked = []
            for i, doc in enumerate(documents):
                if i < len(scores):
                    doc = doc.copy()
                    doc['rerank_score'] = float(scores[i])

                    # 임계값 필터링
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

    async def rerank_async(
        self,
        query: str,
        documents: List[Dict],
        top_k: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict]:
        """
        비동기 재랭킹 (동기 메서드를 ThreadPool에서 실행)

        Args:
            query: 사용자 쿼리
            documents: 검색 결과 리스트
            top_k: 반환할 최대 문서 수
            score_threshold: 최소 점수 임계값

        Returns:
            재랭킹된 문서 리스트
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.rerank(query, documents, top_k, score_threshold)
        )


class SentenceTransformerReranker:
    """
    Sentence Transformers Cross-encoder 기반 재랭킹

    대안적인 Cross-encoder 구현 (더 가벼움)
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
    model_type: str = "jina",
    model_name: Optional[str] = None,
    device: Optional[str] = None
):
    """
    Reranker 팩토리 함수

    Args:
        model_type: 'jina' 또는 'sentence-transformer'
        model_name: 사용할 모델 이름 (None=기본값)
        device: 실행 장치

    Returns:
        Reranker 인스턴스
    """
    if model_type.lower() == "jina":
        return JinaReranker(model_name=model_name, device=device)
    elif model_type.lower() in ["sentence-transformer", "st", "cross-encoder"]:
        return SentenceTransformerReranker(model_name=model_name, device=device)
    else:
        logger.warning(f"Unknown reranker type: {model_type}, using Jina")
        return JinaReranker(model_name=model_name, device=device)
