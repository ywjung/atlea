"""
Rate Limiting Middleware
API 남용 방지를 위한 속도 제한 미들웨어
"""
import time
from collections import defaultdict, deque
from typing import Dict, Deque, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from loguru import logger
from ..utils.ip_utils import IPValidator


class RateLimiter:
    """Token bucket 알고리즘 기반 Rate Limiter"""

    def __init__(self, rate: int = 60, burst: int = 10):
        """
        Args:
            rate: 분당 허용 요청 수
            burst: 버스트 허용 크기 (순간적으로 허용되는 추가 요청 수)
        """
        self.rate = rate  # requests per minute
        self.burst = burst
        self.window_size = 60.0  # 1 minute in seconds

        # {client_id: deque of request timestamps}
        self.requests: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=rate + burst))

    def is_allowed(self, client_id: str) -> Tuple[bool, Dict[str, int]]:
        """
        클라이언트 요청이 허용되는지 확인

        Returns:
            (allowed, info) tuple
            - allowed: 요청 허용 여부
            - info: {"limit": 분당 제한, "remaining": 남은 요청 수, "reset": 리셋까지 초}
        """
        current_time = time.time()
        client_requests = self.requests[client_id]

        # 오래된 요청 제거 (1분 이상 지난 요청)
        while client_requests and current_time - client_requests[0] > self.window_size:
            client_requests.popleft()

        # 현재 요청 수 확인
        request_count = len(client_requests)

        # 제한 체크
        if request_count >= self.rate + self.burst:
            # 가장 오래된 요청부터 리셋 시간 계산
            oldest_request = client_requests[0]
            reset_time = int(self.window_size - (current_time - oldest_request))

            info = {
                "limit": self.rate,
                "remaining": 0,
                "reset": max(reset_time, 0)
            }
            return False, info

        # 요청 허용 - 타임스탬프 추가
        client_requests.append(current_time)

        # 남은 요청 수 계산
        remaining = max(0, self.rate + self.burst - len(client_requests))

        info = {
            "limit": self.rate,
            "remaining": remaining,
            "reset": int(self.window_size)
        }
        return True, info

    def cleanup_old_entries(self):
        """메모리 정리: 오래된 클라이언트 엔트리 제거"""
        current_time = time.time()
        to_remove = []

        for client_id, requests in self.requests.items():
            if not requests or current_time - requests[-1] > self.window_size * 2:
                to_remove.append(client_id)

        for client_id in to_remove:
            del self.requests[client_id]

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} old rate limit entries")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting 미들웨어"""

    def __init__(self, app, rate: int = 60, burst: int = 10, enabled: bool = True):
        """
        Args:
            app: FastAPI application
            rate: 분당 허용 요청 수
            burst: 버스트 허용 크기
            enabled: Rate limiting 활성화 여부
        """
        super().__init__(app)
        self.limiter = RateLimiter(rate=rate, burst=burst)
        self.enabled = enabled
        self.cleanup_counter = 0

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
            "/api/auth/admin/"  # 관리자 API는 rate limit 제외
        ]

        return any(request.url.path.startswith(path) for path in exempt_paths)

    async def dispatch(self, request: Request, call_next):
        """요청 처리"""
        # Rate limiting 비활성화 또는 예외 경로
        if not self.enabled or self._is_exempt(request):
            return await call_next(request)

        # 클라이언트 ID 추출
        client_id = self._get_client_id(request)

        # Rate limit 확인
        allowed, info = self.limiter.is_allowed(client_id)

        # 주기적으로 메모리 정리 (1000 요청마다)
        self.cleanup_counter += 1
        if self.cleanup_counter % 1000 == 0:
            self.limiter.cleanup_old_entries()

        if not allowed:
            # Rate limit 초과
            logger.warning(
                f"Rate limit exceeded for {client_id} on {request.url.path} "
                f"(reset in {info['reset']}s)"
            )

            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Try again in {info['reset']} seconds.",
                    "limit": info["limit"],
                    "reset": info["reset"]
                },
                headers={
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info["reset"]),
                    "Retry-After": str(info["reset"])
                }
            )

        # 요청 허용 - Rate limit 헤더 추가
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response
