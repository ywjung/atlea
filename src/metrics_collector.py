"""
Performance Metrics Collector - 하이브리드 RAG 성능 모니터링

PostgreSQL 기반 저장.
"""

import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from loguru import logger

from sqlalchemy import select, func, delete, case

from .database.connection import SyncSessionFactory
from .database.models.search_metric import SearchMetric


class MetricsCollector:
    """하이브리드 RAG 성능 메트릭 수집 및 분석 (PostgreSQL 기반)"""

    def __init__(self):
        """
        메트릭 수집기 초기화

        Args:
        """
        logger.info("MetricsCollector initialized")

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
        """검색 메트릭 기록"""
        try:
            with SyncSessionFactory() as db:
                entry = SearchMetric(
                    query=query[:100],
                    search_mode=search_mode,
                    sources_used=sources_used,
                    local_count=local_count,
                    web_count=web_count,
                    docs_count=docs_count,
                    total_count=local_count + web_count + docs_count,
                    response_time=round(response_time, 3),
                    cache_hit=cache_hit,
                    user_id=user_id,
                )
                db.add(entry)
                db.commit()

            logger.debug(f"Metric recorded: {response_time:.3f}s, sources={sources_used}")

        except Exception as e:
            logger.error(f"Failed to record metric: {e}")

    def get_recent_searches(self, limit: int = 100) -> List[Dict]:
        """최근 검색 기록 조회"""
        try:
            with SyncSessionFactory() as db:
                stmt = (
                    select(SearchMetric)
                    .order_by(SearchMetric.created_at.desc())
                    .limit(limit)
                )
                rows = db.execute(stmt).scalars().all()

            searches = []
            for row in rows:
                searches.append({
                    'timestamp': row.created_at.isoformat() if row.created_at else '',
                    'query': row.query,
                    'search_mode': row.search_mode,
                    'sources_used': row.sources_used or [],
                    'local_count': row.local_count,
                    'web_count': row.web_count,
                    'docs_count': row.docs_count,
                    'total_count': row.total_count,
                    'response_time': row.response_time,
                    'cache_hit': row.cache_hit,
                    'user_id': row.user_id,
                })
            return searches

        except Exception as e:
            logger.error(f"Failed to get recent searches: {e}")
            return []

    def get_daily_stats(self, days: int = 7) -> Dict:
        """일별 통계 조회"""
        try:
            now = datetime.now()
            cutoff = now - timedelta(days=days)

            with SyncSessionFactory() as db:
                date_col = func.date(SearchMetric.created_at)
                stmt = (
                    select(
                        date_col.label("metric_date"),
                        func.count().label("total_searches"),
                        func.sum(SearchMetric.response_time).label("total_response_time"),
                        func.sum(SearchMetric.total_count).label("total_results"),
                        func.sum(
                            case((SearchMetric.cache_hit.is_(True), 1), else_=0)
                        ).label("cache_hits"),
                    )
                    .where(SearchMetric.created_at >= cutoff)
                    .group_by(date_col)
                    .order_by(date_col.desc())
                )
                rows = db.execute(stmt).all()

                # Also get mode and source breakdowns per day
                mode_stmt = (
                    select(
                        date_col.label("metric_date"),
                        SearchMetric.search_mode,
                        func.count().label("cnt"),
                    )
                    .where(SearchMetric.created_at >= cutoff)
                    .group_by(date_col, SearchMetric.search_mode)
                )
                mode_rows = db.execute(mode_stmt).all()

            # Build stats dict
            stats = {}

            # Initialize all days
            for i in range(days):
                d = now - timedelta(days=i)
                date_key = d.strftime("%Y-%m-%d")
                stats[date_key] = {'total_searches': 0}

            for row in rows:
                date_key = str(row.metric_date)
                total_searches = row.total_searches
                day_stats = {
                    'total_searches': total_searches,
                    'total_response_time': float(row.total_response_time or 0),
                    'total_results': int(row.total_results or 0),
                    'cache_hits': int(row.cache_hits or 0),
                }
                if total_searches > 0:
                    day_stats['avg_response_time'] = round(
                        float(row.total_response_time or 0) / total_searches, 3
                    )
                stats[date_key] = day_stats

            for row in mode_rows:
                date_key = str(row.metric_date)
                if date_key in stats:
                    stats[date_key][f'mode:{row.search_mode}'] = row.cnt

            return stats

        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return {}

    def get_hourly_stats(self, hours: int = 24) -> Dict:
        """시간별 통계 조회"""
        try:
            now = datetime.now()
            cutoff = now - timedelta(hours=hours)

            with SyncSessionFactory() as db:
                stmt = (
                    select(SearchMetric)
                    .where(SearchMetric.created_at >= cutoff)
                    .order_by(SearchMetric.created_at.desc())
                )
                rows = db.execute(stmt).scalars().all()

            # Group by hour in Python (avoids dialect-specific DATE_TRUNC)
            stats = {}
            for i in range(hours):
                hour_time = now - timedelta(hours=i)
                hour_key = hour_time.strftime("%Y-%m-%d:%H")
                stats[hour_key] = {'total_searches': 0}

            for row in rows:
                if row.created_at:
                    hour_key = row.created_at.strftime("%Y-%m-%d:%H")
                    if hour_key not in stats:
                        stats[hour_key] = {'total_searches': 0, 'total_response_time': 0}

                    s = stats[hour_key]
                    s['total_searches'] = s.get('total_searches', 0) + 1
                    s['total_response_time'] = s.get('total_response_time', 0) + row.response_time

            # Compute averages
            for hour_key, s in stats.items():
                total = s.get('total_searches', 0)
                if total > 0:
                    s['avg_response_time'] = round(
                        s.get('total_response_time', 0) / total, 3
                    )

            return stats

        except Exception as e:
            logger.error(f"Failed to get hourly stats: {e}")
            return {}

    def get_global_stats(self) -> Dict:
        """전체 통계 조회"""
        try:
            with SyncSessionFactory() as db:
                stmt = select(
                    func.count().label("total_searches"),
                    func.sum(
                        case((SearchMetric.cache_hit.is_(True), 1), else_=0)
                    ).label("cache_hits"),
                )
                row = db.execute(stmt).one()

                # Mode counts
                mode_stmt = (
                    select(
                        SearchMetric.search_mode,
                        func.count().label("cnt"),
                    )
                    .group_by(SearchMetric.search_mode)
                )
                mode_rows = db.execute(mode_stmt).all()

            total_searches = row.total_searches or 0
            cache_hits = int(row.cache_hits or 0)
            cache_hit_rate = round(
                cache_hits / total_searches * 100, 2
            ) if total_searches > 0 else 0.0

            stats = {
                'total_searches': total_searches,
                'cache_hits': cache_hits,
                'cache_hit_rate': cache_hit_rate,
            }

            for mrow in mode_rows:
                stats[f'mode:{mrow.search_mode}'] = mrow.cnt

            return stats

        except Exception as e:
            logger.error(f"Failed to get global stats: {e}")
            return {'total_searches': 0, 'cache_hits': 0, 'cache_hit_rate': 0.0}

    def get_summary(self) -> Dict:
        """종합 통계 요약"""
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

            # 트렌드 분석
            week_avg = sum(
                int(d.get('total_searches', 0))
                for d in daily_stats.values()
            ) / max(len(daily_stats), 1)

            today_count = int(today_stats.get('total_searches', 0))
            if today_count > week_avg:
                trend = 'up'
            elif today_count < week_avg:
                trend = 'down'
            else:
                trend = 'stable'

            return {
                'global': global_stats,
                'today': today_stats,
                'recent_24h': {'total_searches': total_24h},
                'trend': {
                    'direction': trend,
                    'week_avg': round(week_avg, 1),
                    'today_count': today_count,
                },
                'daily': daily_stats,
                'hourly': hourly_stats,
            }

        except Exception as e:
            logger.error(f"Failed to get summary: {e}")
            return {}

    def get_source_performance(self) -> Dict:
        """소스별 성능 비교"""
        try:
            recent_searches = self.get_recent_searches(limit=500)

            source_stats = {
                'local': {'count': 0, 'total_time': 0, 'results': []},
                'web': {'count': 0, 'total_time': 0, 'results': []},
                'docs': {'count': 0, 'total_time': 0, 'results': []},
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

                del stats['total_time']
                del stats['results']

            return source_stats

        except Exception as e:
            logger.error(f"Failed to get source performance: {e}")
            return {}

    def clear_old_data(self, days: int = 30):
        """오래된 메트릭 데이터 삭제"""
        try:
            cutoff = datetime.now() - timedelta(days=days)

            with SyncSessionFactory() as db:
                stmt = delete(SearchMetric).where(SearchMetric.created_at < cutoff)
                result = db.execute(stmt)
                deleted = result.rowcount
                db.commit()

            logger.info(f"Old metrics cleaned: {deleted} entries (older than {days} days)")
            return deleted

        except Exception as e:
            logger.error(f"Failed to clear old data: {e}")
            return 0

    def get_system_metrics(self) -> Dict:
        """시스템 전체 메트릭 조회"""
        try:
            metrics = {}

            # 성능 추적기 통계
            try:
                from .performance_utils import performance_tracker
                perf_stats = performance_tracker.get_stats()
                metrics['performance'] = perf_stats
            except Exception:
                metrics['performance'] = None

            # 캐시 통계
            global_stats = self.get_global_stats()
            metrics['cache'] = {
                'total_searches': global_stats.get('total_searches', 0),
                'cache_hits': global_stats.get('cache_hits', 0),
                'cache_hit_rate': global_stats.get('cache_hit_rate', 0.0),
            }

            return metrics

        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {}
