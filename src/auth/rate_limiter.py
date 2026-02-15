"""Rate Limiting Implementation

IP 기반 요청 제한을 통한 Brute Force 공격 방지.
PostgreSQL 기반 + 인메모리 캐시.
"""

import time
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException, status
from loguru import logger
from .security_logger import SecurityLogger
from ..utils.ip_utils import IPValidator


# 인메모리 캐시 (프로세스 내 빠른 체크)
_rate_cache: dict[str, dict] = {}
_CACHE_CLEANUP_INTERVAL = 60
_last_cleanup = 0


def _cleanup_cache():
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CACHE_CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    expired = [k for k, v in _rate_cache.items() if v.get("expires", 0) < now]
    for k in expired:
        del _rate_cache[k]


class RateLimiter:
    """PostgreSQL + 인메모리 캐시 기반 Rate Limiter"""

    def __init__(self):
        """초기화

        Args:
        """
        pass

    def _get_client_ip(self, request: Request) -> str:
        return IPValidator.get_client_ip(request, trust_proxy=True)

    def check_rate_limit(
        self,
        request: Request,
        max_requests: int,
        window_seconds: int,
        identifier: Optional[str] = None
    ) -> bool:
        """Rate limit 체크 (인메모리 캐시 우선, PG 백업)"""
        # PostgreSQL에서 Rate Limit 활성화 상태 확인
        try:
            from ..services.config_service import config_get_sync
            enabled_str = config_get_sync("config:rate_limit_enabled")
            if enabled_str is not None and enabled_str == "false":
                logger.debug("Rate limiting is disabled via config")
                return True
        except Exception as e:
            logger.warning(f"Failed to check rate limit enabled status: {e}")

        client_ip = self._get_client_ip(request)

        # 키 생성
        key_parts = ["rate_limit", client_ip]
        if identifier:
            key_parts.append(identifier)
        key = ":".join(key_parts)

        try:
            _cleanup_cache()
            now = time.time()

            entry = _rate_cache.get(key)

            if entry is None or entry.get("expires", 0) < now:
                # 새 윈도우 시작
                _rate_cache[key] = {
                    "count": 1,
                    "expires": now + window_seconds,
                }
                return True

            if entry["count"] >= max_requests:
                ttl = int(entry["expires"] - now)
                logger.warning(
                    f"Rate limit exceeded: ip={client_ip}, "
                    f"identifier={identifier}, count={entry['count']}, "
                    f"retry_after={ttl}s"
                )

                SecurityLogger.log_rate_limit_exceeded(
                    ip_address=client_ip,
                    endpoint=identifier or "general",
                    limit=max_requests
                )

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"요청이 너무 많습니다. {ttl}초 후에 다시 시도하세요.",
                    headers={"Retry-After": str(ttl)}
                )

            entry["count"] += 1
            return True

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            return True

    def get_remaining_requests(
        self,
        request: Request,
        max_requests: int,
        identifier: Optional[str] = None
    ) -> dict:
        """남은 요청 수 확인"""
        client_ip = self._get_client_ip(request)

        key_parts = ["rate_limit", client_ip]
        if identifier:
            key_parts.append(identifier)
        key = ":".join(key_parts)

        try:
            now = time.time()
            entry = _rate_cache.get(key)

            if entry is None or entry.get("expires", 0) < now:
                return {
                    "limit": max_requests,
                    "remaining": max_requests,
                    "reset": 0
                }

            current_count = entry["count"]
            remaining = max(0, max_requests - current_count)
            ttl = int(entry["expires"] - now)

            return {
                "limit": max_requests,
                "remaining": remaining,
                "reset": ttl
            }

        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            return {
                "limit": max_requests,
                "remaining": max_requests,
                "reset": 0
            }

    def reset_rate_limit(
        self,
        request: Request,
        identifier: Optional[str] = None
    ) -> bool:
        """Rate limit 리셋 (관리자용)"""
        client_ip = self._get_client_ip(request)

        key_parts = ["rate_limit", client_ip]
        if identifier:
            key_parts.append(identifier)
        key = ":".join(key_parts)

        try:
            _rate_cache.pop(key, None)
            logger.info(f"Rate limit reset: ip={client_ip}, identifier={identifier}")
            return True
        except Exception as e:
            logger.error(f"Rate limiter reset error: {e}")
            return False


# Rate Limit 설정 (상수)
class RateLimitConfig:
    """Rate Limit 설정"""

    LOGIN_MAX_REQUESTS = 10
    LOGIN_WINDOW_SECONDS = 300

    REGISTER_MAX_REQUESTS = 5
    REGISTER_WINDOW_SECONDS = 3600

    API_MAX_REQUESTS = 60
    API_WINDOW_SECONDS = 60

    PASSWORD_RESET_MAX_REQUESTS = 5
    PASSWORD_RESET_WINDOW_SECONDS = 3600


def create_rate_limit_dependency(
    max_requests: int,
    window_seconds: int,
    identifier: Optional[str] = None
):
    """Rate Limit Dependency Factory"""
    async def rate_limit_dependency(request: Request) -> bool:
        rate_limiter = RateLimiter()
        return rate_limiter.check_rate_limit(
            request,
            max_requests,
            window_seconds,
            identifier
        )

    return rate_limit_dependency
