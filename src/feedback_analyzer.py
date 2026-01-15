"""
Feedback Analyzer - 사용자 피드백 분석 및 학습 시스템

📝 Changelog:
- 2025-12-30: Added Redis persistence for feedback data
  - Automatic save/load from Redis
  - Backup/restore functionality
  - Statistics persistence
"""

import re
import json
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from datetime import datetime, timedelta
from loguru import logger


class FeedbackAnalyzer:
    """사용자 피드백 분석 및 패턴 학습 (Redis 영구 저장 지원)"""

    def __init__(self, redis_client=None):
        """
        초기화

        Args:
            redis_client: Redis 클라이언트 (선택사항, None이면 메모리만 사용)
        """
        self.redis = redis_client
        self.redis_key_prefix = "feedback"

        # 피드백 데이터 저장
        self.feedback_history = []  # List[Dict]

        # 통계 데이터
        self.stats = {
            'total_feedbacks': 0,
            'positive_count': 0,
            'negative_count': 0,
            'feedback_by_confidence': defaultdict(lambda: {'positive': 0, 'negative': 0}),
            'feedback_by_sources': defaultdict(lambda: {'positive': 0, 'negative': 0}),
            'feedback_by_length': defaultdict(lambda: {'positive': 0, 'negative': 0}),
        }

        # 학습된 패턴
        self.learned_patterns = {
            'optimal_answer_length': None,
            'optimal_source_count': None,
            'preferred_confidence_level': None,
            'common_negative_patterns': [],
            'common_positive_patterns': []
        }

        # Redis에서 데이터 로드 시도
        if self.redis:
            self._load_from_redis()
            logger.info(f"✅ FeedbackAnalyzer initialized with Redis persistence (loaded {len(self.feedback_history)} feedbacks)")

    def record_feedback(
        self,
        feedback_type: str,
        answer: str,
        context: List[Dict],
        confidence: Optional[Dict] = None,
        question: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        피드백 기록 및 분석

        Args:
            feedback_type: 'positive' or 'negative'
            answer: AI 응답 텍스트
            context: 사용된 컨텍스트
            confidence: 신뢰도 정보
            question: 사용자 질문
            metadata: 추가 메타데이터

        Returns:
            분석 결과 및 통계
        """
        # 피드백 데이터 구성
        feedback_data = {
            'timestamp': datetime.now().isoformat(),
            'feedback_type': feedback_type,
            'answer_length': len(answer),
            'source_count': len(context),
            'confidence': confidence,
            'question': question,
            'metadata': metadata or {},
            'answer': answer[:500]  # 첫 500자만 저장
        }

        # 히스토리에 추가
        self.feedback_history.append(feedback_data)

        # 통계 업데이트
        self._update_statistics(feedback_data)

        # 패턴 학습 (100개 피드백마다)
        if len(self.feedback_history) % 100 == 0:
            self._learn_patterns()

        # Redis에 저장
        if self.redis:
            self._save_to_redis()

        logger.info(f"📝 피드백 기록: {feedback_type} (총 {len(self.feedback_history)}개)")

        return {
            'recorded': True,
            'total_feedbacks': len(self.feedback_history),
            'current_patterns': self.learned_patterns
        }

    def _update_statistics(self, feedback_data: Dict):
        """통계 업데이트"""
        feedback_type = feedback_data['feedback_type']

        # 전체 통계
        self.stats['total_feedbacks'] += 1
        if feedback_type == 'positive':
            self.stats['positive_count'] += 1
        else:
            self.stats['negative_count'] += 1

        # 신뢰도별 통계
        if feedback_data.get('confidence'):
            conf_level = feedback_data['confidence'].get('level', 'unknown')
            self.stats['feedback_by_confidence'][conf_level][feedback_type] += 1

        # 출처 수별 통계 (1개, 2-3개, 4개 이상으로 그룹화)
        source_count = feedback_data['source_count']
        if source_count == 1:
            source_group = '1개'
        elif source_count <= 3:
            source_group = '2-3개'
        else:
            source_group = '4개 이상'
        self.stats['feedback_by_sources'][source_group][feedback_type] += 1

        # 답변 길이별 통계 (짧음: <200, 보통: 200-1000, 김: >1000)
        answer_length = feedback_data['answer_length']
        if answer_length < 200:
            length_group = '짧음(<200자)'
        elif answer_length <= 1000:
            length_group = '보통(200-1000자)'
        else:
            length_group = '김(>1000자)'
        self.stats['feedback_by_length'][length_group][feedback_type] += 1

    def _learn_patterns(self):
        """피드백 데이터로부터 패턴 학습"""
        if len(self.feedback_history) < 10:
            return

        logger.info("🧠 피드백 패턴 학습 시작...")

        # 긍정/부정 피드백 분리
        positive_feedbacks = [f for f in self.feedback_history if f['feedback_type'] == 'positive']
        negative_feedbacks = [f for f in self.feedback_history if f['feedback_type'] == 'negative']

        # 1. 최적 답변 길이 학습
        if positive_feedbacks:
            avg_positive_length = sum(f['answer_length'] for f in positive_feedbacks) / len(positive_feedbacks)
            self.learned_patterns['optimal_answer_length'] = int(avg_positive_length)

        # 2. 최적 출처 수 학습
        if positive_feedbacks:
            avg_positive_sources = sum(f['source_count'] for f in positive_feedbacks) / len(positive_feedbacks)
            self.learned_patterns['optimal_source_count'] = round(avg_positive_sources, 1)

        # 3. 선호되는 신뢰도 레벨
        conf_levels = {'high': 0, 'medium': 0, 'low': 0}
        for f in positive_feedbacks:
            if f.get('confidence'):
                level = f['confidence'].get('level', 'unknown')
                if level in conf_levels:
                    conf_levels[level] += 1
        if conf_levels:
            self.learned_patterns['preferred_confidence_level'] = max(conf_levels, key=conf_levels.get)

        # 4. 부정 피드백 공통 패턴 추출
        negative_patterns = self._extract_patterns(negative_feedbacks)
        self.learned_patterns['common_negative_patterns'] = negative_patterns[:5]  # 상위 5개

        # 5. 긍정 피드백 공통 패턴 추출
        positive_patterns = self._extract_patterns(positive_feedbacks)
        self.learned_patterns['common_positive_patterns'] = positive_patterns[:5]  # 상위 5개

        logger.success(f"✅ 패턴 학습 완료 - 긍정: {len(positive_feedbacks)}개, 부정: {len(negative_feedbacks)}개")

    def _extract_patterns(self, feedbacks: List[Dict]) -> List[str]:
        """피드백에서 공통 패턴 추출"""
        patterns = []

        if not feedbacks:
            return patterns

        # 답변 길이 패턴
        avg_length = sum(f['answer_length'] for f in feedbacks) / len(feedbacks)
        if avg_length < 200:
            patterns.append("짧은 답변 (<200자)")
        elif avg_length > 1000:
            patterns.append("긴 답변 (>1000자)")

        # 출처 수 패턴
        avg_sources = sum(f['source_count'] for f in feedbacks) / len(feedbacks)
        if avg_sources < 2:
            patterns.append("출처 부족 (<2개)")
        elif avg_sources >= 3:
            patterns.append("충분한 출처 (≥3개)")

        # 신뢰도 패턴
        conf_counts = defaultdict(int)
        for f in feedbacks:
            if f.get('confidence'):
                level = f['confidence'].get('level', 'unknown')
                conf_counts[level] += 1
        if conf_counts:
            dominant_level = max(conf_counts, key=conf_counts.get)
            patterns.append(f"주로 {dominant_level} 신뢰도")

        return patterns

    def get_recommendations(self, context: List[Dict], answer: str, confidence: Dict) -> List[str]:
        """
        학습된 패턴을 기반으로 개선 권장사항 제공

        Args:
            context: 현재 사용된 컨텍스트
            answer: 현재 답변
            confidence: 현재 신뢰도 정보

        Returns:
            개선 권장사항 리스트
        """
        recommendations = []

        # 학습 데이터가 부족한 경우
        if len(self.feedback_history) < 10:
            return recommendations

        # 1. 답변 길이 비교
        optimal_length = self.learned_patterns.get('optimal_answer_length')
        if optimal_length:
            current_length = len(answer)
            if current_length < optimal_length * 0.7:
                recommendations.append(f"답변이 짧습니다. 권장 길이: 약 {optimal_length}자")
            elif current_length > optimal_length * 1.5:
                recommendations.append(f"답변이 깁니다. 권장 길이: 약 {optimal_length}자")

        # 2. 출처 수 비교
        optimal_sources = self.learned_patterns.get('optimal_source_count')
        if optimal_sources:
            current_sources = len(context)
            if current_sources < optimal_sources * 0.7:
                recommendations.append(f"출처가 부족합니다. 권장 출처 수: 약 {optimal_sources}개")

        # 3. 신뢰도 레벨 비교
        preferred_level = self.learned_patterns.get('preferred_confidence_level')
        if preferred_level:
            current_level = confidence.get('level')
            if current_level and current_level != preferred_level:
                recommendations.append(f"신뢰도를 높이세요. 선호 레벨: {preferred_level}")

        # 4. 부정 패턴 회피
        negative_patterns = self.learned_patterns.get('common_negative_patterns', [])
        for pattern in negative_patterns:
            if "짧은 답변" in pattern and len(answer) < 200:
                recommendations.append("짧은 답변은 부정 피드백이 많습니다.")
            elif "출처 부족" in pattern and len(context) < 2:
                recommendations.append("출처가 부족하면 부정 피드백이 많습니다.")

        return recommendations

    def get_analytics(self, days: int = 7) -> Dict:
        """
        피드백 분석 리포트 생성

        Args:
            days: 분석 기간 (일)

        Returns:
            분석 리포트
        """
        # 기간 필터링
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_feedbacks = [
            f for f in self.feedback_history
            if datetime.fromisoformat(f['timestamp']) > cutoff_date
        ]

        if not recent_feedbacks:
            return {
                'period_days': days,
                'total_feedbacks': 0,
                'message': '피드백 데이터가 없습니다.'
            }

        # 통계 계산
        total = len(recent_feedbacks)
        positive = sum(1 for f in recent_feedbacks if f['feedback_type'] == 'positive')
        negative = total - positive
        satisfaction_rate = (positive / total * 100) if total > 0 else 0

        # 신뢰도별 만족도
        conf_satisfaction = {}
        for level in ['high', 'medium', 'low']:
            level_feedbacks = [
                f for f in recent_feedbacks
                if f.get('confidence', {}).get('level') == level
            ]
            if level_feedbacks:
                level_positive = sum(1 for f in level_feedbacks if f['feedback_type'] == 'positive')
                conf_satisfaction[level] = {
                    'total': len(level_feedbacks),
                    'positive': level_positive,
                    'satisfaction_rate': round(level_positive / len(level_feedbacks) * 100, 1)
                }

        return {
            'period_days': days,
            'total_feedbacks': total,
            'positive_count': positive,
            'negative_count': negative,
            'satisfaction_rate': round(satisfaction_rate, 1),
            'confidence_satisfaction': conf_satisfaction,
            'learned_patterns': self.learned_patterns,
            'recommendations': self._generate_system_recommendations()
        }

    def _generate_system_recommendations(self) -> List[str]:
        """시스템 개선을 위한 권장사항 생성"""
        recommendations = []

        if self.stats['total_feedbacks'] < 10:
            return ["피드백 데이터가 부족합니다. 더 많은 데이터가 필요합니다."]

        # 만족도 분석
        total = self.stats['total_feedbacks']
        positive_rate = (self.stats['positive_count'] / total * 100) if total > 0 else 0

        if positive_rate < 50:
            recommendations.append("⚠️ 만족도가 낮습니다. 답변 품질 개선이 필요합니다.")
        elif positive_rate > 80:
            recommendations.append("✅ 만족도가 높습니다. 현재 전략을 유지하세요.")

        # 신뢰도별 분석
        for level, counts in self.stats['feedback_by_confidence'].items():
            total_level = counts['positive'] + counts['negative']
            if total_level > 5:
                positive_rate_level = (counts['positive'] / total_level * 100)
                if positive_rate_level < 50:
                    recommendations.append(f"⚠️ {level} 신뢰도 응답의 만족도가 낮습니다.")

        # 출처 수 분석
        for source_group, counts in self.stats['feedback_by_sources'].items():
            total_sources = counts['positive'] + counts['negative']
            if total_sources > 5:
                positive_rate_sources = (counts['positive'] / total_sources * 100)
                if positive_rate_sources < 50:
                    recommendations.append(f"⚠️ 출처 {source_group}일 때 만족도가 낮습니다.")

        return recommendations

    def get_statistics(self) -> Dict:
        """전체 통계 반환"""
        total = self.stats['total_feedbacks']
        satisfaction_rate = (self.stats['positive_count'] / total * 100) if total > 0 else 0

        return {
            'total_feedbacks': total,
            'positive_count': self.stats['positive_count'],
            'negative_count': self.stats['negative_count'],
            'satisfaction_rate': round(satisfaction_rate, 1),
            'feedback_by_confidence': dict(self.stats['feedback_by_confidence']),
            'feedback_by_sources': dict(self.stats['feedback_by_sources']),
            'feedback_by_length': dict(self.stats['feedback_by_length']),
            'learned_patterns': self.learned_patterns
        }

    def reset_statistics(self):
        """통계 초기화"""
        self.feedback_history.clear()
        self.stats = {
            'total_feedbacks': 0,
            'positive_count': 0,
            'negative_count': 0,
            'feedback_by_confidence': defaultdict(lambda: {'positive': 0, 'negative': 0}),
            'feedback_by_sources': defaultdict(lambda: {'positive': 0, 'negative': 0}),
            'feedback_by_length': defaultdict(lambda: {'positive': 0, 'negative': 0}),
        }
        self.learned_patterns = {
            'optimal_answer_length': None,
            'optimal_source_count': None,
            'preferred_confidence_level': None,
            'common_negative_patterns': [],
            'common_positive_patterns': []
        }

        # Redis에서도 삭제
        if self.redis:
            try:
                self.redis.delete(f"{self.redis_key_prefix}:history")
                self.redis.delete(f"{self.redis_key_prefix}:stats")
                self.redis.delete(f"{self.redis_key_prefix}:patterns")
                logger.info("📊 피드백 통계 초기화됨 (Redis 포함)")
            except Exception as e:
                logger.error(f"Redis 초기화 실패: {e}")
        else:
            logger.info("📊 피드백 통계 초기화됨")

    def _save_to_redis(self):
        """Redis에 피드백 데이터 저장"""
        if not self.redis:
            return

        try:
            # 피드백 히스토리 저장
            history_json = json.dumps(self.feedback_history, ensure_ascii=False)
            self.redis.set(f"{self.redis_key_prefix}:history", history_json)

            # 통계 저장 (defaultdict를 일반 dict로 변환)
            stats_serializable = {
                'total_feedbacks': self.stats['total_feedbacks'],
                'positive_count': self.stats['positive_count'],
                'negative_count': self.stats['negative_count'],
                'feedback_by_confidence': dict(self.stats['feedback_by_confidence']),
                'feedback_by_sources': dict(self.stats['feedback_by_sources']),
                'feedback_by_length': dict(self.stats['feedback_by_length']),
            }
            stats_json = json.dumps(stats_serializable, ensure_ascii=False)
            self.redis.set(f"{self.redis_key_prefix}:stats", stats_json)

            # 학습 패턴 저장
            patterns_json = json.dumps(self.learned_patterns, ensure_ascii=False)
            self.redis.set(f"{self.redis_key_prefix}:patterns", patterns_json)

            logger.debug("💾 피드백 데이터 Redis 저장 완료")
        except Exception as e:
            logger.error(f"Redis 저장 실패: {e}")

    def _load_from_redis(self):
        """Redis에서 피드백 데이터 로드"""
        if not self.redis:
            return

        try:
            # 피드백 히스토리 로드
            history_data = self.redis.get(f"{self.redis_key_prefix}:history")
            if history_data:
                self.feedback_history = json.loads(history_data)

            # 통계 로드
            stats_data = self.redis.get(f"{self.redis_key_prefix}:stats")
            if stats_data:
                stats = json.loads(stats_data)
                self.stats['total_feedbacks'] = stats.get('total_feedbacks', 0)
                self.stats['positive_count'] = stats.get('positive_count', 0)
                self.stats['negative_count'] = stats.get('negative_count', 0)

                # defaultdict 복원
                for conf_level, counts in stats.get('feedback_by_confidence', {}).items():
                    self.stats['feedback_by_confidence'][conf_level] = counts
                for source_group, counts in stats.get('feedback_by_sources', {}).items():
                    self.stats['feedback_by_sources'][source_group] = counts
                for length_group, counts in stats.get('feedback_by_length', {}).items():
                    self.stats['feedback_by_length'][length_group] = counts

            # 학습 패턴 로드
            patterns_data = self.redis.get(f"{self.redis_key_prefix}:patterns")
            if patterns_data:
                self.learned_patterns = json.loads(patterns_data)

            logger.info(f"📂 Redis에서 피드백 데이터 로드 완료: {len(self.feedback_history)}개")
        except Exception as e:
            logger.error(f"Redis 로드 실패: {e}")
            logger.info("기본값으로 초기화합니다.")


# 전역 인스턴스 (Redis는 나중에 주입)
feedback_analyzer = FeedbackAnalyzer()


# Export
__all__ = ['FeedbackAnalyzer', 'feedback_analyzer']
