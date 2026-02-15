"""
RAG Evaluator - RAG 파이프라인 품질 평가 서비스

A-RAG 패턴 참고: LLM 기반 정확도 + contain-match 정확도 평가.
테스트 세트(질문-정답 쌍)에 대해 RAG 응답을 평가합니다.

📝 Changelog:
- 2026-02-13: 초기 구현
  - LLM 기반 정확도 평가
  - Contain-match 정확도 평가
  - 비동기 배치 평가
"""

import asyncio
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class EvalCase:
    """평가 케이스 — 질문 + 기대 정답"""
    question: str
    expected_answer: str
    keywords: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class EvalResult:
    """개별 평가 결과"""
    question: str
    expected_answer: str
    actual_answer: str
    contain_match: bool
    keyword_recall: float
    llm_score: float  # 0.0 ~ 1.0
    latency_ms: float
    metadata: Dict = field(default_factory=dict)


class RAGEvaluator:
    """
    RAG 품질 평가기

    두 가지 평가 방식:
    1. Contain-match: 기대 정답의 키워드가 실제 응답에 포함되는지 검사
    2. LLM-based: LLM에게 정답과 응답의 일치도를 0~1로 평가 요청
    """

    LLM_EVAL_PROMPT = """당신은 RAG 시스템의 답변 품질을 평가하는 전문가입니다.

## 평가 기준
질문에 대한 기대 정답과 실제 답변을 비교하여 정확도를 0.0~1.0 사이 점수로 평가하세요.

- 1.0: 기대 정답의 핵심 내용이 모두 포함되어 있음
- 0.8: 핵심 내용의 대부분이 포함됨 (80% 이상)
- 0.5: 부분적으로 일치하지만 누락된 핵심 정보가 있음
- 0.3: 관련은 있지만 핵심 정보가 많이 누락됨
- 0.0: 관련 없거나 완전히 틀린 답변

## 질문
{question}

## 기대 정답
{expected}

## 실제 답변
{actual}

숫자만 출력하세요 (예: 0.8). 설명은 포함하지 마세요.
점수:"""

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM 클라이언트 (OllamaLLM 등). None이면 contain-match만 수행.
        """
        self.llm_client = llm_client

    async def evaluate_single(
        self,
        case: EvalCase,
        rag_answer_fn,
    ) -> EvalResult:
        """
        단일 케이스 평가

        Args:
            case: 평가 케이스
            rag_answer_fn: async callable(question: str) -> str — RAG 답변 함수
        """
        start_time = time.time()

        try:
            actual_answer = await rag_answer_fn(case.question)
        except Exception as e:
            logger.error(f"RAG answer failed for '{case.question[:50]}': {e}")
            actual_answer = ""

        latency_ms = (time.time() - start_time) * 1000

        # 1. Contain-match 평가
        contain_match = self._check_contain_match(
            case.expected_answer, actual_answer
        )

        # 2. 키워드 리콜 평가
        keyword_recall = self._check_keyword_recall(
            case.keywords or self._extract_keywords(case.expected_answer),
            actual_answer
        )

        # 3. LLM 기반 평가
        llm_score = 0.0
        if self.llm_client:
            llm_score = await self._llm_evaluate(
                case.question, case.expected_answer, actual_answer
            )

        return EvalResult(
            question=case.question,
            expected_answer=case.expected_answer,
            actual_answer=actual_answer,
            contain_match=contain_match,
            keyword_recall=keyword_recall,
            llm_score=llm_score,
            latency_ms=round(latency_ms, 2),
            metadata=case.metadata
        )

    async def evaluate_batch(
        self,
        cases: List[EvalCase],
        rag_answer_fn,
        concurrency: int = 3
    ) -> Dict:
        """
        배치 평가 — 여러 케이스를 동시에 평가

        Args:
            cases: 평가 케이스 목록
            rag_answer_fn: async callable(question: str) -> str
            concurrency: 동시 실행 수

        Returns:
            요약 통계 및 개별 결과
        """
        start_time = time.time()
        results: List[EvalResult] = []
        semaphore = asyncio.Semaphore(concurrency)

        async def eval_with_limit(case):
            async with semaphore:
                return await self.evaluate_single(case, rag_answer_fn)

        tasks = [eval_with_limit(c) for c in cases]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외 필터링
        valid_results = [r for r in results if isinstance(r, EvalResult)]
        errors = [r for r in results if isinstance(r, Exception)]

        total_time = (time.time() - start_time) * 1000

        # 통계 계산
        if valid_results:
            contain_accuracy = sum(1 for r in valid_results if r.contain_match) / len(valid_results)
            avg_keyword_recall = sum(r.keyword_recall for r in valid_results) / len(valid_results)
            avg_llm_score = sum(r.llm_score for r in valid_results) / len(valid_results)
            avg_latency = sum(r.latency_ms for r in valid_results) / len(valid_results)
        else:
            contain_accuracy = avg_keyword_recall = avg_llm_score = avg_latency = 0.0

        summary = {
            'total_cases': len(cases),
            'evaluated': len(valid_results),
            'errors': len(errors),
            'contain_match_accuracy': round(contain_accuracy, 4),
            'avg_keyword_recall': round(avg_keyword_recall, 4),
            'avg_llm_score': round(avg_llm_score, 4),
            'avg_latency_ms': round(avg_latency, 2),
            'total_time_ms': round(total_time, 2),
            'results': [
                {
                    'question': r.question,
                    'contain_match': r.contain_match,
                    'keyword_recall': round(r.keyword_recall, 4),
                    'llm_score': round(r.llm_score, 4),
                    'latency_ms': round(r.latency_ms, 2),
                }
                for r in valid_results
            ]
        }

        logger.info(
            f"📊 RAG Evaluation: {len(valid_results)}/{len(cases)} cases | "
            f"contain={contain_accuracy:.1%}, keyword={avg_keyword_recall:.1%}, "
            f"llm={avg_llm_score:.2f}, avg_latency={avg_latency:.0f}ms"
        )

        return summary

    def _check_contain_match(self, expected: str, actual: str) -> bool:
        """기대 정답의 핵심 부분이 실제 답변에 포함되는지 검사"""
        if not expected or not actual:
            return False

        expected_lower = expected.lower().strip()
        actual_lower = actual.lower().strip()

        # 기대 정답이 짧으면 전체 포함 검사
        if len(expected_lower) < 50:
            return expected_lower in actual_lower

        # 긴 정답은 문장 단위로 50% 이상 포함되면 매치
        sentences = [s.strip() for s in expected_lower.split('.') if len(s.strip()) > 5]
        if not sentences:
            return expected_lower in actual_lower

        matched = sum(1 for s in sentences if s in actual_lower)
        return matched / len(sentences) >= 0.5

    def _check_keyword_recall(self, keywords: List[str], actual: str) -> float:
        """키워드 리콜 — 키워드 중 몇 %가 답변에 포함되는지"""
        if not keywords or not actual:
            return 0.0

        actual_lower = actual.lower()
        matched = sum(1 for kw in keywords if kw.lower() in actual_lower)
        return matched / len(keywords)

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """텍스트에서 간단한 키워드 추출 (공백 토큰화, 2글자 이상)"""
        if not text:
            return []
        tokens = text.replace(',', ' ').replace('.', ' ').split()
        return [t for t in tokens if len(t) >= 2]

    async def _llm_evaluate(
        self,
        question: str,
        expected: str,
        actual: str
    ) -> float:
        """LLM 기반 정확도 평가"""
        if not self.llm_client or not hasattr(self.llm_client, '_generate_response'):
            return 0.0

        try:
            prompt = self.LLM_EVAL_PROMPT.format(
                question=question[:500],
                expected=expected[:500],
                actual=actual[:500]
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.llm_client._generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                    temperature=0.0
                )
            )

            # 숫자 파싱
            score_text = response.strip()
            score = float(score_text)
            return max(0.0, min(1.0, score))

        except (ValueError, TypeError):
            logger.debug(f"LLM eval score parse failed: '{response.strip()}'")
            return 0.0
        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}")
            return 0.0
