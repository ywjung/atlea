"""
Performance Metrics Collector - 하이브리드 RAG 성능 모니터링

📝 Changelog:
- 2025-01-05: 성능 메트릭 수집 시스템 구현
  - 검색 응답 시간 추적
  - 소스별 성능 측정
  - Redis 기반 time-series 데이터 저장
  - 실시간 집계 및 통계
"""

import time
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from loguru import logger
import redis


class MetricsCollector:
    """하이브리드 RAG 성능 메트릭 수집 및 분석"""

    def __init__(self, redis_client: redis.Redis):
        """
        메트릭 수집기 초기화

        Args:
            redis_client: Redis 클라이언트
        """
        self.redis = redis_client
        self.metrics_prefix = "metrics:hybrid_rag"
        logger.info("📊 MetricsCollector initialized")

    def record_search(
        self,
        query: str,
        search_mode: str,
        sources_used: List[str],
        local_count: int,
        web_count: int,
        docs_count: int,
        response_time: float,
        cache_hit: bool = False,
        user_id: Optional[str] = None
    ):
        """
        검색 메트릭 기록

        Args:
            query: 검색 쿼리
            search_mode: 검색 모드 (smart, local-only, web-enhanced, comprehensive)
            sources_used: 사용된 소스 리스트 ['local', 'web', 'docs']
            local_count: 로컬 검색 결과 수
            web_count: 웹 검색 결과 수
            docs_count: 공식 문서 검색 결과 수
            response_time: 응답 시간 (초)
            cache_hit: 캐시 히트 여부
            user_id: 사용자 ID (옵션)
        """
        try:
            timestamp = datetime.now()
            timestamp_str = timestamp.isoformat()
            date_key = timestamp.strftime("%Y-%m-%d")
            hour_key = timestamp.strftime("%Y-%m-%d:%H")

            # 메트릭 데이터 구조
            metric_data = {
                'timestamp': timestamp_str,
                'query': query[:100],  # 처음 100자만 저장
                'search_mode': search_mode,
                'sources_used': sources_used,
                'local_count': local_count,
                'web_count': web_count,
                'docs_count': docs_count,
                'total_count': local_count + web_count + docs_count,
                'response_time': round(response_time, 3),
                'cache_hit': cache_hit,
                'user_id': user_id
            }

            # 1. 개별 검색 기록 저장 (최근 1000개 유지)
            key = f"{self.metrics_prefix}:searches"
            self.redis.lpush(key, json.dumps(metric_data))
            self.redis.ltrim(key, 0, 999)  # 최근 1000개만 유지

            # 2. 일별 집계 업데이트
            self._update_daily_stats(date_key, metric_data)

            # 3. 시간별 집계 업데이트
            self._update_hourly_stats(hour_key, metric_data)

            # 4. 전체 통계 업데이트
            self._update_global_stats(metric_data)

            logger.debug(f"📊 Metric recorded: {response_time:.3f}s, sources={sources_used}")

        except Exception as e:
            logger.error(f"❌ Failed to record metric: {e}")

    def _update_daily_stats(self, date_key: str, metric: Dict):
        """일별 통계 업데이트"""
        key = f"{self.metrics_prefix}:daily:{date_key}"

        pipe = self.redis.pipeline()

        # 카운터 증가
        pipe.hincrby(key, 'total_searches', 1)
        pipe.hincrby(key, f"mode:{metric['search_mode']}", 1)

        # 캐시 히트 카운트
        if metric['cache_hit']:
            pipe.hincrby(key, 'cache_hits', 1)

        # 소스별 사용 카운트
        for source in metric['sources_used']:
            pipe.hincrby(key, f'source:{source}', 1)

        # 응답 시간 합계 (평균 계산용)
        pipe.hincrbyfloat(key, 'total_response_time', metric['response_time'])

        # 결과 수 합계
        pipe.hincrby(key, 'total_results', metric['total_count'])

        # 만료 시간 설정 (30일)
        pipe.expire(key, 30 * 24 * 60 * 60)

        pipe.execute()

    def _update_hourly_stats(self, hour_key: str, metric: Dict):
        """시간별 통계 업데이트"""
        key = f"{self.metrics_prefix}:hourly:{hour_key}"

        pipe = self.redis.pipeline()

        # 카운터 증가
        pipe.hincrby(key, 'total_searches', 1)

        # 응답 시간 합계
        pipe.hincrbyfloat(key, 'total_response_time', metric['response_time'])

        # 만료 시간 설정 (7일)
        pipe.expire(key, 7 * 24 * 60 * 60)

        pipe.execute()

    def _update_global_stats(self, metric: Dict):
        """전체 통계 업데이트"""
        key = f"{self.metrics_prefix}:global"

        pipe = self.redis.pipeline()

        # 총 검색 수
        pipe.hincrby(key, 'total_searches', 1)

        # 모드별 카운트
        pipe.hincrby(key, f"mode:{metric['search_mode']}", 1)

        # 소스별 사용 카운트
        for source in metric['sources_used']:
            pipe.hincrby(key, f'source:{source}', 1)

        # 캐시 히트
        if metric['cache_hit']:
            pipe.hincrby(key, 'cache_hits', 1)

        pipe.execute()

    def get_recent_searches(self, limit: int = 100) -> List[Dict]:
        """
        최근 검색 기록 조회

        Args:
            limit: 조회할 개수

        Returns:
            최근 검색 메트릭 리스트
        """
        try:
            key = f"{self.metrics_prefix}:searches"
            raw_data = self.redis.lrange(key, 0, limit - 1)

            searches = []
            for item in raw_data:
                try:
                    searches.append(json.loads(item))
                except:
                    continue

            return searches

        except Exception as e:
            logger.error(f"❌ Failed to get recent searches: {e}")
            return []

    def get_daily_stats(self, days: int = 7) -> Dict:
        """
        일별 통계 조회

        Args:
            days: 조회할 일수

        Returns:
            일별 통계 데이터
        """
        try:
            stats = {}
            today = datetime.now()

            for i in range(days):
                date = today - timedelta(days=i)
                date_key = date.strftime("%Y-%m-%d")
                key = f"{self.metrics_prefix}:daily:{date_key}"

                raw_stats = self.redis.hgetall(key)
                if raw_stats:
                    # bytes to str 변환
                    day_stats = {
                        k.decode() if isinstance(k, bytes) else k:
                        v.decode() if isinstance(v, bytes) else v
                        for k, v in raw_stats.items()
                    }

                    # 평균 응답 시간 계산
                    total_searches = int(day_stats.get('total_searches', 0))
                    if total_searches > 0:
                        total_time = float(day_stats.get('total_response_time', 0))
                        day_stats['avg_response_time'] = round(total_time / total_searches, 3)

                    stats[date_key] = day_stats
                else:
                    stats[date_key] = {'total_searches': 0}

            return stats

        except Exception as e:
            logger.error(f"❌ Failed to get daily stats: {e}")
            return {}

    def get_hourly_stats(self, hours: int = 24) -> Dict:
        """
        시간별 통계 조회

        Args:
            hours: 조회할 시간 수

        Returns:
            시간별 통계 데이터
        """
        try:
            stats = {}
            now = datetime.now()

            for i in range(hours):
                hour_time = now - timedelta(hours=i)
                hour_key = hour_time.strftime("%Y-%m-%d:%H")
                key = f"{self.metrics_prefix}:hourly:{hour_key}"

                raw_stats = self.redis.hgetall(key)
                if raw_stats:
                    # bytes to str 변환
                    hour_stats = {
                        k.decode() if isinstance(k, bytes) else k:
                        v.decode() if isinstance(v, bytes) else v
                        for k, v in raw_stats.items()
                    }

                    # 평균 응답 시간 계산
                    total_searches = int(hour_stats.get('total_searches', 0))
                    if total_searches > 0:
                        total_time = float(hour_stats.get('total_response_time', 0))
                        hour_stats['avg_response_time'] = round(total_time / total_searches, 3)

                    stats[hour_key] = hour_stats
                else:
                    stats[hour_key] = {'total_searches': 0}

            return stats

        except Exception as e:
            logger.error(f"❌ Failed to get hourly stats: {e}")
            return {}

    def get_global_stats(self) -> Dict:
        """
        전체 통계 조회

        Returns:
            전체 통계 데이터
        """
        try:
            key = f"{self.metrics_prefix}:global"
            raw_stats = self.redis.hgetall(key)

            if not raw_stats:
                return {
                    'total_searches': 0,
                    'cache_hits': 0,
                    'cache_hit_rate': 0.0
                }

            # bytes to str 변환
            stats = {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in raw_stats.items()
            }

            # 캐시 히트율 계산
            total_searches = int(stats.get('total_searches', 0))
            cache_hits = int(stats.get('cache_hits', 0))

            if total_searches > 0:
                stats['cache_hit_rate'] = round(cache_hits / total_searches * 100, 2)
            else:
                stats['cache_hit_rate'] = 0.0

            return stats

        except Exception as e:
            logger.error(f"❌ Failed to get global stats: {e}")
            return {}

    def get_summary(self) -> Dict:
        """
        종합 통계 요약

        Returns:
            {
                'global': 전체 통계,
                'today': 오늘 통계,
                'recent_24h': 최근 24시간 통계,
                'trend': 트렌드 분석
            }
        """
        try:
            global_stats = self.get_global_stats()
            daily_stats = self.get_daily_stats(days=7)
            hourly_stats = self.get_hourly_stats(hours=24)

            # 오늘 통계
            today_key = datetime.now().strftime("%Y-%m-%d")
            today_stats = daily_stats.get(today_key, {'total_searches': 0})

            # 최근 24시간 합계
            total_24h = sum(
                int(h.get('total_searches', 0))
                for h in hourly_stats.values()
            )

            # 트렌드 분석 (지난 7일 평균 vs 오늘)
            week_avg = sum(
                int(d.get('total_searches', 0))
                for d in daily_stats.values()
            ) / max(len(daily_stats), 1)

            today_count = int(today_stats.get('total_searches', 0))
            trend = 'up' if today_count > week_avg else 'down' if today_count < week_avg else 'stable'

            return {
                'global': global_stats,
                'today': today_stats,
                'recent_24h': {
                    'total_searches': total_24h
                },
                'trend': {
                    'direction': trend,
                    'week_avg': round(week_avg, 1),
                    'today_count': today_count
                },
                'daily': daily_stats,
                'hourly': hourly_stats
            }

        except Exception as e:
            logger.error(f"❌ Failed to get summary: {e}")
            return {}

    def get_source_performance(self) -> Dict:
        """
        소스별 성능 비교

        Returns:
            소스별 사용 빈도 및 성능 통계
        """
        try:
            recent_searches = self.get_recent_searches(limit=500)

            # 소스별 데이터 수집
            source_stats = {
                'local': {'count': 0, 'total_time': 0, 'results': []},
                'web': {'count': 0, 'total_time': 0, 'results': []},
                'docs': {'count': 0, 'total_time': 0, 'results': []}
            }

            for search in recent_searches:
                sources = search.get('sources_used', [])
                response_time = search.get('response_time', 0)

                for source in sources:
                    if source in source_stats:
                        source_stats[source]['count'] += 1
                        source_stats[source]['total_time'] += response_time
                        source_stats[source]['results'].append(
                            search.get(f'{source}_count', 0)
                        )

            # 평균 계산
            for source, stats in source_stats.items():
                count = stats['count']
                if count > 0:
                    stats['avg_time'] = round(stats['total_time'] / count, 3)
                    stats['avg_results'] = round(
                        sum(stats['results']) / len(stats['results']), 1
                    ) if stats['results'] else 0
                else:
                    stats['avg_time'] = 0
                    stats['avg_results'] = 0

                # 불필요한 raw 데이터 제거
                del stats['total_time']
                del stats['results']

            return source_stats

        except Exception as e:
            logger.error(f"❌ Failed to get source performance: {e}")
            return {}

    def clear_old_data(self, days: int = 30):
        """
        오래된 메트릭 데이터 삭제

        Args:
            days: 보관 기간 (일)
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            # 오래된 일별 통계 키 삭제
            pattern = f"{self.metrics_prefix}:daily:*"
            for key in self.redis.scan_iter(pattern):
                key_str = key.decode() if isinstance(key, bytes) else key
                date_part = key_str.split(':')[-1]

                try:
                    key_date = datetime.strptime(date_part, "%Y-%m-%d")
                    if key_date < cutoff_date:
                        self.redis.delete(key)
                        logger.debug(f"🗑️ Deleted old metric: {key_str}")
                except:
                    continue

            logger.info(f"✅ Old metrics cleaned (older than {days} days)")

        except Exception as e:
            logger.error(f"❌ Failed to clear old data: {e}")

    def get_system_metrics(self) -> Dict:
        """
        시스템 전체 메트릭 조회

        Returns:
            시스템 메트릭 딕셔너리
        """
        try:
            metrics = {}

            # Redis 메모리 정보
            redis_info = self.redis.info('memory')
            metrics['redis'] = {
                'used_memory': redis_info.get('used_memory_human', 'N/A'),
                'used_memory_rss': redis_info.get('used_memory_rss_human', 'N/A'),
                'maxmemory': redis_info.get('maxmemory_human', 'N/A'),
                'mem_fragmentation_ratio': round(redis_info.get('mem_fragmentation_ratio', 0), 2),
                'evicted_keys': redis_info.get('evicted_keys', 0)
            }

            # Redis 통계
            redis_stats = self.redis.info('stats')
            metrics['redis_stats'] = {
                'total_connections_received': redis_stats.get('total_connections_received', 0),
                'total_commands_processed': redis_stats.get('total_commands_processed', 0),
                'instantaneous_ops_per_sec': redis_stats.get('instantaneous_ops_per_sec', 0),
                'rejected_connections': redis_stats.get('rejected_connections', 0),
                'expired_keys': redis_stats.get('expired_keys', 0)
            }

            # 성능 추적기 통계 (슬로우 쿼리)
            try:
                from .performance_utils import performance_tracker
                perf_stats = performance_tracker.get_stats()
                metrics['performance'] = perf_stats
            except:
                metrics['performance'] = None

            # 캐시 통계 (전역 통계에서 가져오기)
            global_stats = self.get_global_stats()
            metrics['cache'] = {
                'total_searches': global_stats.get('total_searches', 0),
                'cache_hits': global_stats.get('cache_hits', 0),
                'cache_hit_rate': global_stats.get('cache_hit_rate', 0.0)
            }

            return metrics

        except Exception as e:
            logger.error(f"❌ Failed to get system metrics: {e}")
            return {}
