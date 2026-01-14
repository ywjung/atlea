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
import logging

# Configure logger
logger = logging.getLogger(__name__)

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
# Helper Functions
# ============================================================================

def get_safe_error_message(error: Exception, context: str = "") -> str:
    """
    Get sanitized error message for user display

    Prevents information disclosure by mapping exception types to
    generic user-friendly messages while logging the full error.

    Args:
        error: The exception that occurred
        context: Context string for logging (e.g., "metrics endpoint")

    Returns:
        Safe error message suitable for user display
    """
    error_type = type(error).__name__

    # Log full error for debugging
    logger.error(f"Error in {context}: {error_type}: {str(error)}")

    # Map exception types to safe messages
    error_messages = {
        "FileNotFoundError": "요청한 리소스를 찾을 수 없습니다.",
        "PermissionError": "접근 권한이 없습니다.",
        "ValueError": "잘못된 입력값입니다.",
        "ConnectionError": "서비스 연결에 실패했습니다.",
        "TimeoutError": "요청 시간이 초과되었습니다.",
    }

    # Return mapped message or generic message
    return error_messages.get(
        error_type,
        "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    )


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

        # 메트릭 수집
        global_metrics = metrics.get_global_metrics()
        today_metrics = metrics.get_today_metrics()
        recent_metrics = metrics.get_recent_metrics(hours=24)
        trend_data = metrics.get_metric_trends(days=7)
        daily_stats = metrics.get_daily_stats(days=30)
        hourly_stats = metrics.get_hourly_stats()

        return {
            "global": global_metrics,
            "today": today_metrics,
            "recent_24h": recent_metrics,
            "trend": trend_data,
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

        # 소스별 성능 통계
        local_stats = metrics.get_source_stats("local")
        web_stats = metrics.get_source_stats("web")
        docs_stats = metrics.get_source_stats("docs")

        return {
            "local": local_stats,
            "web": web_stats,
            "docs": docs_stats
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
