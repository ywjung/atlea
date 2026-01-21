"""
Cache Management Router

Handles cache statistics, clearing, and enable/disable operations.
This module provides endpoints for:
- Cache statistics retrieval
- Cache clearing (admin only)
- Cache enabled status management

All endpoints require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from loguru import logger
from ..auth.middleware import get_current_active_user
from ..routers.admin import require_admin
from ..utils.error_handling import get_safe_error_message

# Create router with prefix and tags
router = APIRouter(prefix="/api", tags=["Cache"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

cache_manager = None
redis_client = None


def inject_dependencies(cache_mgr, redis):
    """
    Inject dependencies from main application

    Args:
        cache_mgr: CacheManager instance for cache operations
        redis: Redis client for admin validation
    """
    global cache_manager, redis_client
    cache_manager = cache_mgr
    redis_client = redis


# ============================================================================
# Pydantic Models
# ============================================================================

class CacheEnabledRequest(BaseModel):
    """Cache enable/disable request model"""
    enabled: bool


# ============================================================================
# Cache API Endpoints
# ============================================================================

@router.get("/cache/stats", tags=["Cache"])
async def get_cache_stats(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get cache statistics (로그인 필요)

    Returns cache performance metrics including:
    - Total cache entries
    - Total queries
    - Cache hits
    - Cache misses
    - Hit rate
    - Average response time

    Args:
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Cache statistics

    Raises:
        HTTPException: 503 if cache manager not initialized
        HTTPException: 500 if error occurs
    """
    try:
        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        stats = cache_manager.get_cache_stats()
        return stats
    except HTTPException:
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "cache stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/cache/clear", tags=["Cache"])
async def clear_cache(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Clear all cached responses (관리자 전용)

    Removes all entries from the cache. This is useful for:
    - Forcing fresh responses after data updates
    - Troubleshooting cache-related issues
    - Clearing stale cached data

    Requires admin privileges.

    Args:
        request: FastAPI request object (for admin validation)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Success message and number of entries cleared

    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 503 if cache manager not initialized
        HTTPException: 500 if error occurs
    """
    try:
        # 관리자 권한 확인
        require_admin(request, redis_client)

        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        count = cache_manager.clear_cache()
        logger.info(f"Cache cleared by admin {current_user.get('user_id')}: {count} entries")

        return {
            "message": "Cache cleared successfully",
            "entries_cleared": count
        }
    except HTTPException:
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "clear cache endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.get("/cache/enabled", tags=["Cache"])
async def get_cache_enabled(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get cache enabled status (로그인 필요)

    Returns whether the cache is currently enabled or disabled.
    When disabled, all queries bypass the cache.

    Args:
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Cache enabled status {"enabled": bool}

    Raises:
        HTTPException: 503 if cache manager not initialized
        HTTPException: 500 if error occurs
    """
    try:
        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        return {
            "enabled": cache_manager.is_enabled()
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "get cache enabled endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/cache/enabled", tags=["Cache"])
async def set_cache_enabled(
    request: CacheEnabledRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Enable or disable cache (로그인 필요)

    Allows dynamic cache enable/disable without server restart.
    Useful for:
    - Debugging issues without cache interference
    - Performance testing with/without cache
    - Temporarily disabling cache during data updates

    Args:
        request: CacheEnabledRequest with enabled boolean
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Success message and new enabled status

    Raises:
        HTTPException: 503 if cache manager not initialized
        HTTPException: 500 if failed to set state or other error occurs
    """
    try:
        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        success = cache_manager.set_enabled(request.enabled)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set cache enabled state")

        action = "enabled" if request.enabled else "disabled"
        logger.info(f"Cache {action} by user {current_user.get('user_id')}")

        return {
            "message": f"Cache {action} successfully",
            "enabled": request.enabled
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "set cache enabled endpoint")
        raise HTTPException(status_code=500, detail=safe_message)
