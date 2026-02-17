"""Tests for Rate Limiter

IP 기반 요청 제한 테스트.
"""

import pytest
from fastapi import Request, HTTPException
from unittest.mock import Mock, MagicMock
from src.auth.rate_limiter import RateLimiter, RateLimitConfig


class MockRedis:
    """Mock Redis for testing"""

    def __init__(self):
        self.data = {}
        self.ttls = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, seconds, value):
        self.data[key] = str(value).encode() if isinstance(value, (int, str)) else value
        self.ttls[key] = seconds
        return True

    def incr(self, key):
        current = self.data.get(key, b'0')
        if isinstance(current, bytes):
            current = int(current.decode())
        else:
            current = int(current)
        new_value = current + 1
        self.data[key] = str(new_value).encode()
        return new_value

    def ttl(self, key):
        return self.ttls.get(key, -1)

    def delete(self, key):
        if key in self.data:
            del self.data[key]
            if key in self.ttls:
                del self.ttls[key]
            return 1
        return 0

    def reset(self):
        self.data = {}
        self.ttls = {}


@pytest.fixture
def mock_redis():
    """Mock Redis fixture"""
    redis = MockRedis()
    yield redis
    redis.reset()


@pytest.fixture
def rate_limiter(mock_redis):
    """Rate limiter fixture"""
    return RateLimiter()


@pytest.fixture
def mock_request():
    """Mock FastAPI Request"""
    request = Mock(spec=Request)
    request.client = Mock()
    request.client.host = "192.168.1.100"
    request.headers = {}
    return request


class TestRateLimiter:
    """Rate Limiter 기본 테스트"""

    def test_get_client_ip_direct(self, rate_limiter, mock_request):
        """직접 연결 IP 추출"""
        ip = rate_limiter._get_client_ip(mock_request)
        assert ip == "192.168.1.100"

    def test_get_client_ip_forwarded(self, rate_limiter, mock_request):
        """프록시를 통한 IP 추출 (X-Forwarded-For)"""
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.100"}
        ip = rate_limiter._get_client_ip(mock_request)
        assert ip == "10.0.0.1"  # 첫 번째 IP 사용

    def test_get_client_ip_no_client(self, rate_limiter):
        """클라이언트 정보 없을 때"""
        request = Mock(spec=Request)
        request.client = None
        request.headers = {}
        ip = rate_limiter._get_client_ip(request)
        assert ip == "unknown"

    def test_first_request_allowed(self, rate_limiter, mock_request):
        """첫 요청은 허용"""
        result = rate_limiter.check_rate_limit(
            mock_request,
            max_requests=5,
            window_seconds=60
        )
        assert result is True

    def test_requests_within_limit(self, rate_limiter, mock_request):
        """제한 내 요청은 모두 허용"""
        max_requests = 5

        for i in range(max_requests):
            result = rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )
            assert result is True

    def test_requests_exceed_limit(self, rate_limiter, mock_request):
        """제한 초과 시 HTTPException 발생"""
        max_requests = 3

        # 3번 요청 (허용)
        for i in range(max_requests):
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )

        # 4번째 요청 (거부)
        with pytest.raises(HTTPException) as exc_info:
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )

        assert exc_info.value.status_code == 429
        assert "요청이 너무 많습니다" in exc_info.value.detail

    def test_rate_limit_with_identifier(self, rate_limiter, mock_request):
        """식별자별로 독립적인 rate limit"""
        max_requests = 3

        # login 엔드포인트에 3번 요청
        for i in range(max_requests):
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60,
                identifier="login"
            )

        # register 엔드포인트는 아직 여유 있음
        result = rate_limiter.check_rate_limit(
            mock_request,
            max_requests=max_requests,
            window_seconds=60,
            identifier="register"
        )
        assert result is True

        # login 엔드포인트는 이미 초과
        with pytest.raises(HTTPException):
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60,
                identifier="login"
            )

    def test_different_ips_independent(self, rate_limiter):
        """서로 다른 IP는 독립적으로 제한"""
        request1 = Mock(spec=Request)
        request1.client = Mock()
        request1.client.host = "192.168.1.100"
        request1.headers = {}

        request2 = Mock(spec=Request)
        request2.client = Mock()
        request2.client.host = "192.168.1.200"
        request2.headers = {}

        max_requests = 2

        # IP1에서 2번 요청 (한계 도달)
        for i in range(max_requests):
            rate_limiter.check_rate_limit(
                request1,
                max_requests=max_requests,
                window_seconds=60
            )

        # IP1은 초과
        with pytest.raises(HTTPException):
            rate_limiter.check_rate_limit(
                request1,
                max_requests=max_requests,
                window_seconds=60
            )

        # IP2는 아직 여유 있음
        result = rate_limiter.check_rate_limit(
            request2,
            max_requests=max_requests,
            window_seconds=60
        )
        assert result is True


class TestGetRemainingRequests:
    """남은 요청 수 확인 테스트"""

    def test_no_requests_yet(self, rate_limiter, mock_request):
        """아직 요청하지 않은 경우"""
        info = rate_limiter.get_remaining_requests(
            mock_request,
            max_requests=5
        )

        assert info["limit"] == 5
        assert info["remaining"] == 5
        assert info["reset"] == 0

    def test_some_requests_made(self, rate_limiter, mock_request):
        """일부 요청 후 남은 수 확인"""
        max_requests = 5

        # 2번 요청
        for i in range(2):
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )

        info = rate_limiter.get_remaining_requests(
            mock_request,
            max_requests=max_requests
        )

        assert info["limit"] == 5
        assert info["remaining"] == 3  # 5 - 2 = 3
        assert info["reset"] > 0

    def test_all_requests_used(self, rate_limiter, mock_request):
        """모든 요청 소진"""
        max_requests = 3

        # 3번 요청
        for i in range(max_requests):
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )

        info = rate_limiter.get_remaining_requests(
            mock_request,
            max_requests=max_requests
        )

        assert info["limit"] == 3
        assert info["remaining"] == 0


class TestResetRateLimit:
    """Rate limit 리셋 테스트"""

    def test_reset_rate_limit(self, rate_limiter, mock_request):
        """Rate limit 리셋 성공"""
        max_requests = 3

        # 3번 요청 (한계 도달)
        for i in range(max_requests):
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )

        # 리셋
        result = rate_limiter.reset_rate_limit(mock_request)
        assert result is True

        # 다시 요청 가능
        result = rate_limiter.check_rate_limit(
            mock_request,
            max_requests=max_requests,
            window_seconds=60
        )
        assert result is True


class TestRateLimitConfig:
    """Rate Limit 설정값 테스트"""

    def test_config_values(self):
        """설정값이 적절한지 확인"""
        # 로그인: 5분에 10회
        assert RateLimitConfig.LOGIN_MAX_REQUESTS == 10
        assert RateLimitConfig.LOGIN_WINDOW_SECONDS == 300

        # 회원가입: 1시간에 5회
        assert RateLimitConfig.REGISTER_MAX_REQUESTS == 5
        assert RateLimitConfig.REGISTER_WINDOW_SECONDS == 3600

        # 일반 API: 1분에 60회
        assert RateLimitConfig.API_MAX_REQUESTS == 60
        assert RateLimitConfig.API_WINDOW_SECONDS == 60


class TestRateLimiterEdgeCases:
    """Rate Limiter 엣지 케이스 테스트"""

    def test_concurrent_requests_from_same_ip(self, rate_limiter, mock_request):
        """동일 IP에서 동시 요청"""
        max_requests = 5

        # 동시에 여러 요청 (실제로는 순차적이지만 동일 시점으로 간주)
        for i in range(max_requests):
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )

        # 다음 요청은 거부되어야 함
        with pytest.raises(HTTPException):
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )

    def test_retry_after_header(self, rate_limiter, mock_request):
        """Retry-After 헤더가 포함되는지 확인"""
        max_requests = 1

        # 1번 요청
        rate_limiter.check_rate_limit(
            mock_request,
            max_requests=max_requests,
            window_seconds=60
        )

        # 2번째 요청 (거부)
        with pytest.raises(HTTPException) as exc_info:
            rate_limiter.check_rate_limit(
                mock_request,
                max_requests=max_requests,
                window_seconds=60
            )

        # Retry-After 헤더 확인
        assert "Retry-After" in exc_info.value.headers
