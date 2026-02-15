"""
Rate Limiting Middleware
인메모리 Token Bucket 알고리즘 Rate Limiter (단일 프로세스용).
분산 환경은 PostgreSQL 기반 ip_rate_limits 테이블로 확장 가능.
"""
import time
from typing import Dict, Tuple, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from loguru import logger
from ..utils.ip_utils import IPValidator


# 인메모리 슬라이딩 윈도우 저장소
_buckets: Dict[str, list] = {}
_BUCKET_CLEANUP_INTERVAL = 120
_last_bucket_cleanup = 0


def _cleanup_buckets(window_size: float):
    global _last_bucket_cleanup
    now = time.time()
    if now - _last_bucket_cleanup < _BUCKET_CLEANUP_INTERVAL:
        return
    _last_bucket_cleanup = now
    cutoff = now - (window_size * 2)
    empty_keys = []
    for key, timestamps in _buckets.items():
        _buckets[key] = [t for t in timestamps if t > cutoff]
        if not _buckets[key]:
            empty_keys.append(key)
    for key in empty_keys:
        del _buckets[key]


class InMemoryRateLimiter:
    """인메모리 Token Bucket 알고리즘 Rate Limiter"""

    def __init__(self, rate: int = 60, burst: int = 10):
        """
        Args:

            rate: 분당 허용 요청 수
            burst: 버스트 허용 크기
        """
        self.rate = rate
        self.burst = burst
        self.window_size = 60.0

    def is_allowed(self, client_id: str) -> Tuple[bool, Dict[str, int]]:
        """클라이언트 요청이 허용되는지 확인"""
        try:
            now = time.time()
            key = f"rate_limit:{client_id}"
            cutoff = now - self.window_size

            _cleanup_buckets(self.window_size)

            # 슬라이딩 윈도우: 오래된 요청 제거
            if key not in _buckets:
                _buckets[key] = []

            _buckets[key] = [t for t in _buckets[key] if t > cutoff]
            count = len(_buckets[key])

            limit = self.rate + self.burst

            if count >= limit:
                # 리셋 시간 계산
                if _buckets[key]:
                    oldest = min(_buckets[key])
                    reset_time = int(self.window_size - (now - oldest))
                else:
                    reset_time = int(self.window_size)
                return False, {"limit": self.rate, "remaining": 0, "reset": max(reset_time, 1)}

            # 요청 허용
            _buckets[key].append(now)
            remaining = limit - count - 1

            return True, {
                "limit": self.rate,
                "remaining": max(remaining, 0),
                "reset": int(self.window_size),
            }

        except Exception as e:
            logger.error(f"Rate limiter error: {e}")

            import os
            env = os.getenv("ENV", "development")

            if env == "production":
                logger.critical("Rate limiter failed in production - blocking request")
                return False, {"limit": self.rate, "remaining": 0, "reset": 60}
            else:
                logger.warning("Rate limiter failed in development - allowing request")
                return True, {"limit": self.rate, "remaining": self.rate, "reset": 60}

    def cleanup_old_entries(self):
        _cleanup_buckets(self.window_size)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate Limiting 미들웨어"""

    def __init__(self, app, rate: int = 60, burst: int = 10, enabled: bool = True):
        super().__init__(app)
        self.rate = rate
        self.burst = burst
        self.enabled = enabled
        self._limiter: Optional[InMemoryRateLimiter] = None
        self._enabled_cache = {"value": None, "timestamp": 0, "ttl": 10}

    def _get_limiter(self, request: Request) -> Optional[InMemoryRateLimiter]:
        if self._limiter is None:
            self._limiter = InMemoryRateLimiter(rate=self.rate, burst=self.burst)
        return self._limiter

    def _get_client_id(self, request: Request) -> str:
        return IPValidator.get_client_ip(request, trust_proxy=True)

    def _is_exempt(self, request: Request) -> bool:
        exempt_paths = [
            "/static/",
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        return any(request.url.path.startswith(path) for path in exempt_paths)

    def _is_rate_limit_enabled(self, request: Request) -> bool:
        now = time.time()
        if (self._enabled_cache["value"] is not None and
                now - self._enabled_cache["timestamp"] < self._enabled_cache["ttl"]):
            return self._enabled_cache["value"]

        try:
            from ..services.config_service import config_get_sync
            enabled_str = config_get_sync("config:rate_limit_enabled")
            if enabled_str is not None:
                result = enabled_str == "true"
                self._enabled_cache["value"] = result
                self._enabled_cache["timestamp"] = now
                return result

            self._enabled_cache["value"] = self.enabled
            self._enabled_cache["timestamp"] = now
            return self.enabled

        except Exception as e:
            logger.warning(f"Failed to check rate limit status: {e}")
            self._enabled_cache["value"] = self.enabled
            self._enabled_cache["timestamp"] = now
            return self.enabled

    async def dispatch(self, request: Request, call_next):
        enabled = self._is_rate_limit_enabled(request)

        if not enabled or self._is_exempt(request):
            return await call_next(request)

        limiter = self._get_limiter(request)
        if not limiter:
            return await call_next(request)

        client_id = self._get_client_id(request)
        allowed, info = limiter.is_allowed(client_id)

        response = None
        if allowed:
            response = await call_next(request)
        else:
            from ..auth.security_logger import SecurityLogger
            SecurityLogger.log_rate_limit_exceeded(
                ip_address=client_id,
                endpoint=request.url.path,
                limit=info["limit"]
            )

            response = JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"요청이 너무 많습니다. {info['reset']}초 후에 다시 시도하세요."
                }
            )

        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response
