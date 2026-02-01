"""
Redis-based Rate Limiting Middleware
분산 환경 지원 및 영구적인 속도 제한
"""
import time
from typing import Dict, Tuple, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from redis import Redis
from loguru import logger
from ..utils.ip_utils import IPValidator


class RedisRateLimiter:
    """Redis 기반 Token Bucket 알고리즘 Rate Limiter (분산 환경 지원)"""

    # Lua 스크립트: 원자적 연산 보장
    LUA_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local burst = tonumber(ARGV[4])

    -- 오래된 요청 제거 (sliding window)
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

    -- 현재 요청 수 확인
    local count = redis.call('ZCARD', key)

    -- 제한 초과 확인
    if count >= limit + burst then
        -- 가장 오래된 요청으로 리셋 시간 계산
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local reset_time = 0
        if #oldest > 0 then
            reset_time = math.ceil(window - (now - tonumber(oldest[2])))
        end
        return {0, 0, reset_time}
    end

    -- 요청 허용 - 타임스탬프 추가
    redis.call('ZADD', key, now, now .. ':' .. math.random())
    redis.call('EXPIRE', key, window * 2)  -- 안전 마진을 위해 2배

    -- 남은 요청 수 계산
    local remaining = limit + burst - count - 1

    return {1, remaining, window}
    """

    def __init__(self, redis: Redis, rate: int = 60, burst: int = 10):
        """
        Args:
            redis: Redis 클라이언트
            rate: 분당 허용 요청 수
            burst: 버스트 허용 크기 (순간적 추가 요청)
        """
        self.redis = redis
        self.rate = rate
        self.burst = burst
        self.window_size = 60.0  # 1 minute in seconds
        self.script_sha: Optional[str] = None

    def _load_script(self):
        """Lua 스크립트를 Redis에 로드 (최초 1회)"""
        if not self.script_sha:
            self.script_sha = self.redis.script_load(self.LUA_SCRIPT)

    def is_allowed(self, client_id: str) -> Tuple[bool, Dict[str, int]]:
        """
        클라이언트 요청이 허용되는지 확인

        Args:
            client_id: 클라이언트 식별자 (IP 주소 등)

        Returns:
            (allowed, info) tuple
            - allowed: 요청 허용 여부
            - info: {"limit": 분당 제한, "remaining": 남은 요청 수, "reset": 리셋까지 초}
        """
        try:
            self._load_script()

            key = f"rate_limit:{client_id}"
            now = time.time()

            # Lua 스크립트 실행 (원자적 연산)
            result = self.redis.evalsha(
                self.script_sha,
                1,  # key count
                key,
                now,
                self.window_size,
                self.rate,
                self.burst
            )

            allowed = bool(result[0])
            remaining = int(result[1])
            reset_time = int(result[2])

            info = {
                "limit": self.rate,
                "remaining": remaining,
                "reset": reset_time
            }

            return allowed, info

        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            # Redis 오류 시 요청 허용 (Fail-open)
            return True, {"limit": self.rate, "remaining": self.rate, "reset": 60}

    def cleanup_old_entries(self):
        """메모리 정리: 오래된 클라이언트 엔트리 제거"""
        try:
            # Redis SCAN으로 rate_limit:* 키 찾기
            cursor = 0
            pattern = "rate_limit:*"
            now = time.time()
            cutoff = now - (self.window_size * 2)

            while True:
                cursor, keys = self.redis.scan(cursor, match=pattern, count=100)

                for key in keys:
                    # 오래된 요청 제거
                    self.redis.zremrangebyscore(key, 0, cutoff)

                    # 비어있으면 키 삭제
                    count = self.redis.zcard(key)
                    if count == 0:
                        self.redis.delete(key)

                if cursor == 0:
                    break

        except Exception as e:
            logger.error(f"Cleanup error: {e}")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate Limiting 미들웨어 (Redis 기반)"""

    def __init__(self, app, rate: int = 60, burst: int = 10, enabled: bool = True):
        super().__init__(app)
        self.rate = rate
        self.burst = burst
        self.enabled = enabled
        self._limiter: Optional[RedisRateLimiter] = None
        # rate limit enabled 상태 인메모리 캐시
        self._enabled_cache = {"value": None, "timestamp": 0, "ttl": 10}

    def _get_limiter(self, request: Request) -> Optional[RedisRateLimiter]:
        """Redis 인스턴스를 app.state에서 가져와 limiter 생성"""
        if self._limiter is None:
            # app.state에서 Redis 가져오기
            redis = getattr(request.app.state, 'cache_manager', None)
            if redis and hasattr(redis, 'redis'):
                self._limiter = RedisRateLimiter(redis.redis, self.rate, self.burst)
        return self._limiter

    def _get_client_id(self, request: Request) -> str:
        """클라이언트 식별자 추출 (IP 스푸핑 방지)"""
        # IPValidator를 사용하여 안전하게 IP 추출
        return IPValidator.get_client_ip(request, trust_proxy=True)

    def _is_exempt(self, request: Request) -> bool:
        """Rate limiting 예외 경로 확인"""
        # 정적 파일, health check 등은 제외
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
        """
        Rate limiting 활성화 상태 확인 (인메모리 캐시 + Redis)

        Returns:
            bool: Rate limiting 활성화 여부
        """
        # 인메모리 캐시 확인
        now = time.time()
        if (self._enabled_cache["value"] is not None and
                now - self._enabled_cache["timestamp"] < self._enabled_cache["ttl"]):
            return self._enabled_cache["value"]

        try:
            # Redis에서 설정 확인
            redis = getattr(request.app.state, 'cache_manager', None)
            if redis and hasattr(redis, 'redis'):
                enabled_str = redis.redis.get("config:rate_limit_enabled")
                if enabled_str is not None:
                    result = enabled_str.decode() == "true"
                    self._enabled_cache["value"] = result
                    self._enabled_cache["timestamp"] = now
                    return result

            # Redis 설정이 없으면 기본값 사용
            self._enabled_cache["value"] = self.enabled
            self._enabled_cache["timestamp"] = now
            return self.enabled

        except Exception as e:
            logger.warning(f"Failed to check rate limit status from Redis: {e}")
            self._enabled_cache["value"] = self.enabled
            self._enabled_cache["timestamp"] = now
            return self.enabled

    async def dispatch(self, request: Request, call_next):
        """요청 처리"""
        # 동적으로 Redis에서 enabled 상태 확인
        enabled = self._is_rate_limit_enabled(request)

        # Rate limiting 비활성화 또는 예외 경로
        if not enabled or self._is_exempt(request):
            return await call_next(request)

        # Limiter 가져오기 (Redis 사용 가능할 때까지 대기)
        limiter = self._get_limiter(request)
        if not limiter:
            # Redis 미사용 시 요청 허용
            logger.warning("Redis not available, rate limiting disabled")
            return await call_next(request)

        # 클라이언트 식별
        client_id = self._get_client_id(request)

        # Rate limit 체크
        allowed, info = limiter.is_allowed(client_id)

        # 응답 헤더에 Rate limit 정보 추가
        response = None
        if allowed:
            response = await call_next(request)
        else:
            # Rate limit 초과 시 로깅
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

        # Rate limit 정보 헤더 추가
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response
