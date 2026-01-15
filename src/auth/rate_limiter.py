"""Rate Limiting Implementation

IP 기반 요청 제한을 통한 Brute Force 공격 방지.
"""

from typing import Optional
from datetime import datetime, timedelta
import redis
from fastapi import Request, HTTPException, status
from loguru import logger
from .security_logger import SecurityLogger
from ..utils.ip_utils import IPValidator


class RateLimiter:
    """Redis 기반 Rate Limiter

    IP 주소별로 요청 횟수를 제한합니다.
    """

    def __init__(self, redis_client: redis.Redis):
        """초기화

        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client

    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 주소 추출 (IP 스푸핑 방지)

        Args:
            request: FastAPI Request 객체

        Returns:
            클라이언트 IP 주소 (검증됨)
        """
        # IPValidator를 사용하여 안전하게 IP 추출
        return IPValidator.get_client_ip(request, trust_proxy=True)

    def check_rate_limit(
        self,
        request: Request,
        max_requests: int,
        window_seconds: int,
        identifier: Optional[str] = None
    ) -> bool:
        """Rate limit 체크

        Args:
            request: FastAPI Request 객체
            max_requests: 시간 윈도우 내 최대 요청 수
            window_seconds: 시간 윈도우 (초)
            identifier: 추가 식별자 (예: endpoint 이름)

        Returns:
            True if allowed, False if rate limited

        Raises:
            HTTPException: Rate limit 초과 시 429
        """
        # Redis에서 Rate Limit 활성화 상태 확인
        try:
            enabled_str = self.redis.get("config:rate_limit_enabled")
            if enabled_str is not None and enabled_str.decode() == "false":
                # Rate Limit이 비활성화된 경우 모든 요청 허용
                logger.debug("Rate limiting is disabled via Redis config")
                return True
        except Exception as e:
            logger.warning(f"Failed to check rate limit enabled status: {e}")
            # Redis 확인 실패 시 기본 동작 (rate limit 적용)

        client_ip = self._get_client_ip(request)

        # Redis 키 생성
        key_parts = ["rate_limit", client_ip]
        if identifier:
            key_parts.append(identifier)
        key = ":".join(key_parts)

        try:
            # 현재 요청 수 확인
            current = self.redis.get(key)

            if current is None:
                # 첫 요청: 카운터 초기화
                self.redis.setex(key, window_seconds, 1)
                return True

            current_count = int(current)

            if current_count >= max_requests:
                # Rate limit 초과
                ttl = self.redis.ttl(key)
                logger.warning(
                    f"Rate limit exceeded: ip={client_ip}, "
                    f"identifier={identifier}, count={current_count}, "
                    f"retry_after={ttl}s"
                )

                # 보안 로깅
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

            # 카운터 증가
            self.redis.incr(key)
            return True

        except HTTPException:
            raise
        except Exception as e:
            # Redis 오류 시 요청 허용 (fail-open)
            logger.error(f"Rate limiter error: {e}")
            return True

    def get_remaining_requests(
        self,
        request: Request,
        max_requests: int,
        identifier: Optional[str] = None
    ) -> dict:
        """남은 요청 수 확인

        Args:
            request: FastAPI Request 객체
            max_requests: 최대 요청 수
            identifier: 추가 식별자

        Returns:
            {
                "limit": 최대 요청 수,
                "remaining": 남은 요청 수,
                "reset": 리셋까지 남은 시간 (초)
            }
        """
        client_ip = self._get_client_ip(request)

        key_parts = ["rate_limit", client_ip]
        if identifier:
            key_parts.append(identifier)
        key = ":".join(key_parts)

        try:
            current = self.redis.get(key)

            if current is None:
                return {
                    "limit": max_requests,
                    "remaining": max_requests,
                    "reset": 0
                }

            current_count = int(current)
            remaining = max(0, max_requests - current_count)
            ttl = self.redis.ttl(key)

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
        """Rate limit 리셋 (관리자용)

        Args:
            request: FastAPI Request 객체
            identifier: 추가 식별자

        Returns:
            성공 여부
        """
        client_ip = self._get_client_ip(request)

        key_parts = ["rate_limit", client_ip]
        if identifier:
            key_parts.append(identifier)
        key = ":".join(key_parts)

        try:
            self.redis.delete(key)
            logger.info(f"Rate limit reset: ip={client_ip}, identifier={identifier}")
            return True
        except Exception as e:
            logger.error(f"Rate limiter reset error: {e}")
            return False


# Rate Limit 설정 (상수)
class RateLimitConfig:
    """Rate Limit 설정"""

    # 로그인 엔드포인트: 5분에 10회 (개발 환경 고려)
    LOGIN_MAX_REQUESTS = 10
    LOGIN_WINDOW_SECONDS = 300  # 5분

    # 회원가입 엔드포인트: 1시간에 5회 (자동 가입 방지)
    REGISTER_MAX_REQUESTS = 5
    REGISTER_WINDOW_SECONDS = 3600  # 1시간

    # 일반 API: 1분에 60회
    API_MAX_REQUESTS = 60
    API_WINDOW_SECONDS = 60  # 1분

    # 비밀번호 재설정 요청: 1시간에 5회
    PASSWORD_RESET_MAX_REQUESTS = 5
    PASSWORD_RESET_WINDOW_SECONDS = 3600  # 1시간


def create_rate_limit_dependency(
    max_requests: int,
    window_seconds: int,
    identifier: Optional[str] = None
):
    """Rate Limit Dependency Factory

    FastAPI dependency로 사용할 수 있는 rate limiter를 생성합니다.

    Args:
        max_requests: 최대 요청 수
        window_seconds: 시간 윈도우 (초)
        identifier: 엔드포인트 식별자

    Returns:
        FastAPI dependency function

    Example:
        ```python
        @router.post("/login")
        async def login(
            request: Request,
            _: bool = Depends(
                create_rate_limit_dependency(
                    max_requests=5,
                    window_seconds=300,
                    identifier="login"
                )
            )
        ):
            # 로그인 로직
            pass
        ```
    """
    async def rate_limit_dependency(request: Request) -> bool:
        """Rate limit 체크 dependency"""
        rate_limiter = RateLimiter(request.app.state.cache_manager.redis)
        return rate_limiter.check_rate_limit(
            request,
            max_requests,
            window_seconds,
            identifier
        )

    return rate_limit_dependency
