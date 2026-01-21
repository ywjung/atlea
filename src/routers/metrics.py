"""
Metrics & Performance Monitoring Router

Handles performance metrics and monitoring including:
- Metrics summary (global, today, 24h, trends, daily, hourly)
- Recent search history
- Source performance comparison
- Old data cleanup

Admin privileges required for all endpoints.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from loguru import logger

from ..utils.error_handling import get_safe_error_message

# Create router with prefix and tags
router = APIRouter(prefix="/api/admin", tags=["Admin", "Metrics"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

cache_manager = None


def inject_dependencies(cache_mgr):
    """
    Inject dependencies from main application

    Args:
        cache_mgr: CacheManager instance for Redis access
    """
    global cache_manager
    cache_manager = cache_mgr


# ============================================================================
# Metrics API Endpoints
# ============================================================================

@router.get("/metrics/summary", tags=["Metrics"])
async def get_metrics_summary(request: Request):
    """
    성능 메트릭 종합 요약 조회 (관리자 전용)

    Returns:
        전체, 오늘, 최근 24시간, 추세, 일별/시간별 통계
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # MetricsCollector 초기화
        from ..metrics_collector import MetricsCollector
        metrics = MetricsCollector(redis_client)

        # 메트릭 수집 - get_summary()가 모든 통계를 제공
        summary = metrics.get_summary()
        daily_stats = metrics.get_daily_stats(days=30)
        hourly_stats = metrics.get_hourly_stats()

        return {
            "global": summary.get("global", {}),
            "today": summary.get("today", {}),
            "recent_24h": summary.get("recent_24h", {}),
            "trend": summary.get("trend", {}),
            "daily": daily_stats,
            "hourly": hourly_stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metrics summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics summary")


@router.get("/metrics/recent", tags=["Metrics"])
async def get_recent_searches(request: Request, limit: int = 100):
    """
    최근 검색 기록 조회 (관리자 전용)

    Args:
        limit: 조회할 검색 기록 수 (최대 1000)

    Returns:
        최근 검색 기록 목록
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # Limit 값 검증
        limit = min(limit, 1000)

        # MetricsCollector 초기화
        from ..metrics_collector import MetricsCollector
        metrics = MetricsCollector(redis_client)

        # 최근 검색 기록 조회
        recent_searches = metrics.get_recent_searches(limit=limit)

        return {
            "searches": recent_searches,
            "count": len(recent_searches),
            "limit": limit
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recent searches: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve recent searches")


@router.get("/metrics/source-performance", tags=["Metrics"])
async def get_source_performance(request: Request):
    """
    소스별 성능 비교 (관리자 전용)

    Returns:
        로컬 문서, 웹 검색, 문서 검색 소스별 성능 통계
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # MetricsCollector 초기화
        from ..metrics_collector import MetricsCollector
        metrics = MetricsCollector(redis_client)

        # 소스별 성능 통계 - get_source_performance()가 모든 소스 통계를 반환
        source_performance = metrics.get_source_performance()

        return {
            "local": source_performance.get("local", {}),
            "web": source_performance.get("web", {}),
            "docs": source_performance.get("docs", {})
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get source performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve source performance")


@router.delete("/metrics/cleanup", tags=["Metrics"])
async def cleanup_old_metrics(request: Request, days: int = 30):
    """
    오래된 메트릭 데이터 삭제 (관리자 전용)

    Args:
        days: 보관 기간 (일)

    Returns:
        삭제된 데이터 수
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # MetricsCollector 초기화
        from ..metrics_collector import MetricsCollector
        metrics = MetricsCollector(redis_client)

        # 오래된 데이터 삭제
        deleted_count = metrics.clear_old_data(days=days)

        logger.info(f"Cleaned up {deleted_count} old metrics entries (older than {days} days)")

        return {
            "deleted": deleted_count,
            "retention_days": days,
            "message": f"{deleted_count}개의 오래된 메트릭이 삭제되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cleanup old metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup old metrics")
