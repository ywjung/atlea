"""
Confidence Scorer - AI 답변 신뢰도 점수 계산
"""

import re
from typing import List, Dict, Tuple
from loguru import logger


class ConfidenceScorer:
    """답변 신뢰도 점수 계산"""

    def __init__(self):
        """초기화"""
        self.score_weights = {
            'relevance': 0.40,      # 문서 관련도 (40%)
            'coverage': 0.25,       # 답변 완성도 (25%)
            'sources': 0.20,        # 출처 수 (20%)
            'specificity': 0.15     # 구체성 (15%)
        }

    def calculate_confidence(self, answer: str, context: List[Dict],
                           question: str) -> Dict:
        """
        답변 신뢰도 종합 점수 계산

        Args:
            answer: AI 답변 텍스트
            context: 사용된 문서 컨텍스트
            question: 사용자 질문

        Returns:
            {
                'score': 0.85,           # 0-1 사이 종합 점수
                'level': 'high',         # low/medium/high
                'percentage': 85,        # 백분율
                'factors': {...},        # 세부 요소별 점수
                'recommendation': '...'  # 사용자 권장사항
            }
        """
        # 1. 문서 관련도 점수
        relevance_score = self._calculate_relevance_score(context)

        # 2. 답변 완성도 점수
        coverage_score = self._calculate_coverage_score(answer, question)

        # 3. 출처 수 점수
        sources_score = self._calculate_sources_score(context, answer)

        # 4. 구체성 점수
        specificity_score = self._calculate_specificity_score(answer)

        # 가중 평균 계산
        total_score = (
            relevance_score * self.score_weights['relevance'] +
            coverage_score * self.score_weights['coverage'] +
            sources_score * self.score_weights['sources'] +
            specificity_score * self.score_weights['specificity']
        )

        # 신뢰도 레벨 결정
        level = self._get_confidence_level(total_score)

        # 권장사항 생성
        recommendation = self._generate_recommendation(
            total_score,
            relevance_score,
            coverage_score,
            sources_score
        )

        result = {
            'score': round(total_score, 2),
            'percentage': int(total_score * 100),
            'level': level,
            'factors': {
                'relevance': round(relevance_score, 2),
                'coverage': round(coverage_score, 2),
                'sources': round(sources_score, 2),
                'specificity': round(specificity_score, 2)
            },
            'recommendation': recommendation,
            'details': {
                'num_sources': len(context),
                'answer_length': len(answer),
                'has_code': self._has_code_blocks(answer),
                'has_examples': self._has_examples(answer)
            }
        }

        logger.debug(f"📊 신뢰도 점수: {result['percentage']}% ({level})")

        return result

    def _calculate_relevance_score(self, context: List[Dict]) -> float:
        """문서 관련도 점수 (평균 relevance score)"""
        if not context:
            return 0.0

        # 컨텍스트 문서들의 관련도 평균
        scores = [doc.get('score', 0.0) for doc in context]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # 정규화 (0.5-1.0 범위를 0-1로 매핑)
        normalized = max(0, (avg_score - 0.5) / 0.5)

        return min(1.0, normalized)

    def _calculate_coverage_score(self, answer: str, question: str) -> float:
        """답변 완성도 점수"""
        score = 0.0

        # 1. 답변 길이 적절성 (50자-2000자가 최적)
        answer_length = len(answer)
        if answer_length < 50:
            length_score = answer_length / 50 * 0.3
        elif answer_length > 2000:
            length_score = max(0.3, 1.0 - (answer_length - 2000) / 2000 * 0.7)
        else:
            length_score = 1.0

        score += length_score * 0.4

        # 2. 구조화 여부 (마크다운 헤더, 리스트 등)
        has_structure = bool(
            re.search(r'#{1,3}\s', answer) or  # 헤더
            re.search(r'^\s*[-*]\s', answer, re.MULTILINE) or  # 리스트
            re.search(r'^\d+\.\s', answer, re.MULTILINE)  # 번호 리스트
        )
        if has_structure:
            score += 0.3

        # 3. 질문 키워드 포함 여부
        question_keywords = set(re.findall(r'\b\w{2,}\b', question.lower()))
        answer_keywords = set(re.findall(r'\b\w{2,}\b', answer.lower()))
        keyword_overlap = len(question_keywords & answer_keywords) / max(len(question_keywords), 1)
        score += keyword_overlap * 0.3

        return min(1.0, score)

    def _calculate_sources_score(self, context: List[Dict], answer: str) -> float:
        """출처 수 및 인용 점수"""
        num_sources = len(context)

        # 1. 출처 수 점수
        if num_sources == 0:
            sources_count_score = 0.0
        elif num_sources == 1:
            sources_count_score = 0.5
        elif num_sources == 2:
            sources_count_score = 0.7
        elif num_sources >= 3:
            sources_count_score = 1.0

        # 2. 실제 파일명 인용 여부
        cited_sources = 0
        for doc in context:
            filename = doc.get('filename', '')
            if filename and filename in answer:
                cited_sources += 1

        citation_score = cited_sources / max(num_sources, 1)

        # 가중 평균
        return sources_count_score * 0.6 + citation_score * 0.4

    def _calculate_specificity_score(self, answer: str) -> float:
        """답변 구체성 점수"""
        score = 0.0

        # 1. 코드 블록 포함 (구체적 예시)
        if self._has_code_blocks(answer):
            score += 0.3

        # 2. 숫자/날짜/버전 정보 포함
        has_numbers = bool(re.search(r'\d+\.?\d*', answer))
        if has_numbers:
            score += 0.2

        # 3. 예시/예제 포함
        if self._has_examples(answer):
            score += 0.3

        # 4. 구체적 용어 사용 (vs 모호한 표현)
        vague_words = ['아마도', '대략', '일반적으로', '보통', '~것 같', '~인 듯']
        vague_count = sum(1 for word in vague_words if word in answer)
        if vague_count == 0:
            score += 0.2
        else:
            score += max(0, 0.2 - vague_count * 0.05)

        return min(1.0, score)

    def _has_code_blocks(self, text: str) -> bool:
        """코드 블록 포함 여부"""
        return bool(re.search(r'```[\s\S]*?```', text))

    def _has_examples(self, text: str) -> bool:
        """예시 포함 여부"""
        example_indicators = ['예시', '예제', '예:', 'example', 'for example', '다음과 같']
        return any(indicator in text.lower() for indicator in example_indicators)

    def _get_confidence_level(self, score: float) -> str:
        """점수를 레벨로 변환"""
        if score >= 0.75:
            return 'high'
        elif score >= 0.50:
            return 'medium'
        else:
            return 'low'

    def _generate_recommendation(self, total_score: float,
                                relevance: float,
                                coverage: float,
                                sources: float) -> str:
        """신뢰도 기반 권장사항 생성"""
        if total_score >= 0.75:
            return "답변의 신뢰도가 높습니다. 제공된 정보를 신뢰하고 사용하셔도 좋습니다."

        recommendations = []

        if relevance < 0.6:
            recommendations.append("문서 관련도가 낮습니다. 더 구체적인 질문을 하시거나 관련 문서를 추가로 업로드해보세요.")

        if coverage < 0.5:
            recommendations.append("답변이 불완전할 수 있습니다. 추가 질문으로 더 자세한 정보를 요청해보세요.")

        if sources < 0.5:
            recommendations.append("참조 문서가 부족합니다. 관련 문서를 더 업로드하면 더 정확한 답변을 받을 수 있습니다.")

        if not recommendations:
            recommendations.append("답변 신뢰도가 중간 수준입니다. 중요한 결정에는 추가 확인이 권장됩니다.")

        return " ".join(recommendations)


# 전역 인스턴스
confidence_scorer = ConfidenceScorer()


# Export
__all__ = ['ConfidenceScorer', 'confidence_scorer']
