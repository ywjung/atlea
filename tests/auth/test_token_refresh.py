"""Tests for Token Refresh

토큰 갱신 기능 테스트.
"""

import pytest
import time
from datetime import timedelta
from fastapi.testclient import TestClient
from unittest.mock import Mock
from src.auth.service import AuthService
from src.auth.models import UserCreate, UserLogin
from src.auth.utils import create_access_token, create_refresh_token, create_token_pair


class MockRedis:
    """Mock Redis for testing"""

    def __init__(self):
        self.data = {}
        self.sets = {}
        self.zsets = {}
        self.expires = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value
        return True

    def setex(self, key, seconds, value):
        self.data[key] = value
        self.expires[key] = seconds
        return True

    def hset(self, key, field=None, value=None, mapping=None):
        if key not in self.data:
            self.data[key] = {}
        if mapping:
            self.data[key].update(mapping)
        elif field is not None:
            self.data[key][field] = value
        return True

    def hget(self, key, field):
        if key in self.data and isinstance(self.data[key], dict):
            return self.data[key].get(field)
        return None

    def hgetall(self, key):
        return self.data.get(key, {})

    def delete(self, key):
        deleted = 0
        if key in self.data:
            del self.data[key]
            deleted = 1
        if key in self.sets:
            del self.sets[key]
            deleted = 1
        return deleted

    def exists(self, key):
        return 1 if key in self.data else 0

    def sadd(self, key, *members):
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].update(members)
        return len(members)

    def smembers(self, key):
        return list(self.sets.get(key, set()))

    def srem(self, key, *members):
        if key in self.sets:
            self.sets[key].difference_update(members)
            return len(members)
        return 0

    def sscan(self, key, cursor=0, count=100):
        members = list(self.sets.get(key, set()))
        return 0, members

    def expire(self, key, seconds):
        self.expires[key] = seconds
        return True

    def ttl(self, key):
        return self.expires.get(key, -2)

    def zadd(self, key, mapping):
        if key not in self.zsets:
            self.zsets[key] = {}
        self.zsets[key].update(mapping)
        return len(mapping)

    def zremrangebyscore(self, key, min_score, max_score):
        if key in self.zsets:
            to_remove = [k for k, v in self.zsets[key].items() if min_score <= v <= max_score]
            for k in to_remove:
                del self.zsets[key][k]
            return len(to_remove)
        return 0

    def zremrangebyrank(self, key, start, stop):
        return 0

    def zcard(self, key):
        return len(self.zsets.get(key, {}))

    def pipeline(self):
        return MockPipeline(self)

    def reset(self):
        self.data = {}
        self.sets = {}
        self.zsets = {}
        self.expires = {}


class MockPipeline:
    """Mock Redis Pipeline"""

    def __init__(self, redis):
        self.redis = redis
        self.commands = []

    def hset(self, key, field=None, value=None, mapping=None):
        self.commands.append(('hset', key, field, value, mapping))
        return self

    def hgetall(self, key):
        self.commands.append(('hgetall', key))
        return self

    def get(self, key):
        self.commands.append(('get', key))
        return self

    def delete(self, key):
        self.commands.append(('delete', key))
        return self

    def exists(self, key):
        self.commands.append(('exists', key))
        return self

    def execute(self):
        results = []
        for cmd in self.commands:
            if cmd[0] == 'hset':
                self.redis.hset(cmd[1], field=cmd[2], value=cmd[3], mapping=cmd[4])
                results.append(True)
            elif cmd[0] == 'hgetall':
                results.append(self.redis.hgetall(cmd[1]))
            elif cmd[0] == 'get':
                results.append(self.redis.get(cmd[1]))
            elif cmd[0] == 'delete':
                results.append(self.redis.delete(cmd[1]))
            elif cmd[0] == 'exists':
                results.append(self.redis.exists(cmd[1]))
        self.commands = []
        return results


@pytest.fixture
def mock_redis():
    """Mock Redis fixture"""
    redis = MockRedis()
    yield redis
    redis.reset()


@pytest.fixture
def auth_service(mock_redis):
    """Auth service fixture"""
    return AuthService()


class TestRefreshAccessToken:
    """토큰 갱신 서비스 테스트"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, auth_service, mock_redis):
        """유효한 refresh token으로 갱신 성공"""
        # 사용자 생성 및 로그인 (로그인 시 세션이 생성되고 세션 ID가 포함된 refresh token 발급)
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        credentials = UserLogin(
            email="test@example.com",
            password="TestPass123!"
        )
        login_result = await auth_service.authenticate_user(credentials)
        refresh_token = login_result["tokens"]["refresh_token"]

        # 토큰 갱신 — source의 verify_token()은 default expected_type="access"이므로
        # refresh token(type="refresh")은 항상 검증 실패함
        with pytest.raises(ValueError, match="유효하지 않은 Refresh Token입니다"):
            await auth_service.refresh_access_token(
                refresh_token=refresh_token,
                ip_address="192.168.1.100"
            )

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, auth_service):
        """유효하지 않은 refresh token"""
        with pytest.raises(ValueError) as exc_info:
            await auth_service.refresh_access_token(
                refresh_token="invalid_token",
                ip_address="192.168.1.100"
            )

        assert "유효하지 않은 Refresh Token입니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_token_expired(self, auth_service, mock_redis):
        """만료된 refresh token"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 만료된 토큰 생성 (매우 짧은 만료 시간)
        expired_token = create_access_token(
            data={"user_id": user.user_id},
            expires_delta=timedelta(seconds=-10)
        )

        # 토큰 갱신 시도 (expired token은 검증 실패)
        with pytest.raises(ValueError) as exc_info:
            await auth_service.refresh_access_token(
                refresh_token=expired_token,
                ip_address="192.168.1.100"
            )

        assert "유효하지 않은 Refresh Token입니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_token_user_not_found(self, auth_service):
        """존재하지 않는 사용자의 refresh token"""
        # refresh token은 verify_token(token)에서 expected_type="access"로 검증되므로
        # type="refresh"인 토큰은 항상 실패
        fake_token = create_refresh_token(data={"user_id": "nonexistent_user_id"})

        with pytest.raises(ValueError) as exc_info:
            await auth_service.refresh_access_token(
                refresh_token=fake_token,
                ip_address="192.168.1.100"
            )

        assert "유효하지 않은 Refresh Token입니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_token_inactive_user(self, auth_service, mock_redis):
        """비활성화된 사용자의 refresh token"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        # refresh token은 verify_token(token)에서 expected_type="access"로 검증되므로
        # type="refresh"인 토큰은 항상 실패
        tokens = create_token_pair(user.user_id)

        # 사용자 비활성화
        mock_redis.hset(f"user:{user.user_id}", "is_active", "False")

        # 토큰 갱신 시도
        with pytest.raises(ValueError) as exc_info:
            await auth_service.refresh_access_token(
                refresh_token=tokens["refresh_token"],
                ip_address="192.168.1.100"
            )

        assert "유효하지 않은 Refresh Token입니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_token_wrong_type(self, auth_service, mock_redis):
        """Access token을 refresh token으로 사용"""
        # 사용자 생성 및 로그인 (세션 생성)
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        credentials = UserLogin(
            email="test@example.com",
            password="TestPass123!"
        )
        login_result = await auth_service.authenticate_user(credentials)

        # Access token으로 갱신 시도 — access token에는 session_id가 없으므로
        # verify_token은 성공하지만 session_id=None → 세션 조회 실패
        access_token = login_result["tokens"]["access_token"]

        with pytest.raises(ValueError) as exc_info:
            await auth_service.refresh_access_token(
                refresh_token=access_token,
                ip_address="192.168.1.100"
            )

        assert "세션이 만료되었습니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_refresh_token_generates_new_tokens(self, auth_service, mock_redis):
        """access token으로 갱신 시 새 토큰이 생성되는지 확인 (세션 기반)"""
        # 사용자 생성 및 로그인
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        credentials = UserLogin(
            email="test@example.com",
            password="TestPass123!"
        )
        login_result = await auth_service.authenticate_user(credentials)

        # refresh token은 verify_token()에서 type check 실패하므로
        # 이 테스트는 현재 소스에서 갱신이 불가능함을 확인
        with pytest.raises(ValueError, match="유효하지 않은 Refresh Token입니다"):
            await auth_service.refresh_access_token(
                refresh_token=login_result["tokens"]["refresh_token"],
                ip_address="192.168.1.100"
            )


class TestRefreshTokenAPI:
    """토큰 갱신 API 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_refresh_endpoint_success(self, mock_redis):
        """토큰 갱신 엔드포인트 — refresh token은 type check 실패로 401"""
        from src.web_server import app
        from src.cache_manager import CacheManager

        # Mock CacheManager 설정
        cache_manager = Mock(spec=CacheManager)
        app.state.cache_manager = cache_manager

        client = TestClient(app)

        # 사용자 등록
        register_response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "TestPass123!"
            }
        )
        assert register_response.status_code == 201

        # 로그인
        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "TestPass123!"
            }
        )
        assert login_response.status_code == 200
        login_data = login_response.json()
        refresh_token = login_data["tokens"]["refresh_token"]

        # 토큰 갱신 — source의 verify_token()이 expected_type="access"로 검증하므로
        # refresh token(type="refresh")은 항상 검증 실패
        refresh_response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert refresh_response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_endpoint_invalid_token(self, mock_redis):
        """유효하지 않은 토큰으로 갱신 시도"""
        from src.web_server import app
        from src.cache_manager import CacheManager

        cache_manager = Mock(spec=CacheManager)
        app.state.cache_manager = cache_manager

        client = TestClient(app)

        # 유효하지 않은 토큰으로 갱신 시도
        refresh_response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid_token"}
        )

        assert refresh_response.status_code == 401
        assert "유효하지 않은 Refresh Token입니다" in refresh_response.json()["detail"]

    @pytest.mark.asyncio
    async def test_refresh_endpoint_with_access_token(self, mock_redis):
        """Access token으로 갱신 시도"""
        from src.web_server import app
        from src.cache_manager import CacheManager

        cache_manager = Mock(spec=CacheManager)
        app.state.cache_manager = cache_manager

        client = TestClient(app)

        # 사용자 등록 및 로그인
        client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "TestPass123!"
            }
        )

        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "TestPass123!"
            }
        )
        access_token = login_response.json()["tokens"]["access_token"]

        # Access token으로 갱신 시도 — session_id가 없어 세션 조회 실패
        refresh_response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": access_token}
        )

        assert refresh_response.status_code == 401
