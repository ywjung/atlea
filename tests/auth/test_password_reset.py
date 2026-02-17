"""Tests for Password Reset

비밀번호 재설정 기능 테스트.
"""

import pytest
import time
import uuid as _uuid
from datetime import timedelta
from fastapi.testclient import TestClient
from unittest.mock import Mock
from src.auth.service import AuthService
from src.auth.models import UserCreate
from src.auth.password_reset import (
    create_password_reset_token,
    verify_password_reset_token,
    PasswordResetService,
    RESET_TOKEN_EXPIRE_MINUTES
)
from src.auth.utils import create_access_token, verify_password


def _get_pg_user(user_id: str):
    """Read user from SQLite/PG test database."""
    from src.database.connection import SyncSessionFactory
    from src.database.models.user import User as PgUser
    try:
        uid = _uuid.UUID(user_id)
    except ValueError:
        return None
    with SyncSessionFactory() as session:
        return session.get(PgUser, uid)


def _get_pg_sessions(user_id: str):
    """Read active sessions for a user from SQLite/PG test database."""
    from src.database.connection import SyncSessionFactory
    from src.database.models.session import Session as PgSession
    from sqlalchemy import select
    try:
        uid = _uuid.UUID(user_id)
    except ValueError:
        return []
    with SyncSessionFactory() as session:
        result = session.execute(
            select(PgSession).where(PgSession.user_id == uid, PgSession.is_active == True)
        )
        return result.scalars().all()


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

    def exists(self, key):
        return 1 if key in self.data else 0

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


class TestPasswordResetToken:
    """비밀번호 재설정 토큰 테스트"""

    def test_create_reset_token(self):
        """재설정 토큰 생성"""
        email = "test@example.com"
        token = create_password_reset_token(email)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_reset_token(self):
        """유효한 재설정 토큰 검증"""
        email = "test@example.com"
        token = create_password_reset_token(email)

        verified_email = verify_password_reset_token(token)

        assert verified_email == email

    def test_verify_invalid_reset_token(self):
        """유효하지 않은 재설정 토큰"""
        result = verify_password_reset_token("invalid_token")

        assert result is None

    def test_verify_wrong_token_type(self):
        """잘못된 타입의 토큰"""
        # Access token 생성
        access_token = create_access_token(data={"user_id": "test123"})

        result = verify_password_reset_token(access_token)

        assert result is None

    def test_verify_expired_token(self):
        """만료된 재설정 토큰"""
        email = "test@example.com"

        # 만료된 토큰 생성 (과거 시간)
        from jose import jwt
        from datetime import datetime
        import os

        SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
        ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

        expire = datetime.utcnow() + timedelta(seconds=-10)
        to_encode = {
            "sub": email,
            "exp": expire,
            "type": "password_reset"
        }
        expired_token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

        result = verify_password_reset_token(expired_token)

        assert result is None


class TestPasswordResetService:
    """비밀번호 재설정 서비스 테스트"""

    @pytest.mark.asyncio
    async def test_request_password_reset_success(self, auth_service, mock_redis):
        """비밀번호 재설정 요청 성공"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="OldPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 재설정 요청
        reset_token = await auth_service.request_password_reset("test@example.com")

        assert reset_token is not None
        assert isinstance(reset_token, str)

        # 토큰 검증
        email = verify_password_reset_token(reset_token)
        assert email == "test@example.com"

    @pytest.mark.asyncio
    async def test_request_password_reset_invalid_email(self, auth_service):
        """존재하지 않는 이메일"""
        with pytest.raises(ValueError) as exc_info:
            await auth_service.request_password_reset("nonexistent@example.com")

        assert "사용자를 찾을 수 없습니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_password_success(self, auth_service, mock_redis):
        """비밀번호 재설정 성공"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="OldPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 서비스를 통해 재설정 토큰 생성 (PG에 저장)
        reset_token = await auth_service.request_password_reset("test@example.com")

        # 비밀번호 재설정
        new_password = "NewPass123!"
        await auth_service.reset_password(reset_token, new_password)

        # 새 비밀번호로 로그인 가능한지 PG에서 확인
        pg_user = _get_pg_user(user.user_id)
        assert verify_password(new_password, pg_user.hashed_password)

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, auth_service):
        """유효하지 않은 토큰"""
        with pytest.raises(ValueError) as exc_info:
            await auth_service.reset_password("invalid_token", "NewPass123!")

        assert "유효하지 않거나 만료된 토큰입니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_password_invalidates_sessions(self, auth_service, mock_redis):
        """비밀번호 재설정 시 모든 세션 무효화"""
        # 사용자 생성 및 로그인
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="OldPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 세션 생성
        from src.auth.models import UserLogin
        credentials = UserLogin(email="test@example.com", password="OldPass123!")
        result = await auth_service.authenticate_user(credentials)

        # PG에서 세션이 존재하는지 확인
        sessions = _get_pg_sessions(user.user_id)
        assert len(sessions) > 0

        # 서비스를 통해 재설정 토큰 생성 (PG에 저장)
        reset_token = await auth_service.request_password_reset("test@example.com")
        await auth_service.reset_password(reset_token, "NewPass123!")

        # PG에서 세션이 모두 비활성화되었는지 확인
        sessions = _get_pg_sessions(user.user_id)
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_reset_password_changes_password_hash(self, auth_service, mock_redis):
        """비밀번호 재설정 시 비밀번호 해시가 변경되는지 확인"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="OldPass123!"
        )
        user = await auth_service.create_user(user_data)

        # PG에서 기존 비밀번호 해시 저장
        pg_user_before = _get_pg_user(user.user_id)
        old_hash = pg_user_before.hashed_password

        # 서비스를 통해 재설정 토큰 생성 (PG에 저장)
        reset_token = await auth_service.request_password_reset("test@example.com")
        await auth_service.reset_password(reset_token, "NewPass123!")

        # PG에서 비밀번호 해시가 변경되었는지 확인
        pg_user_after = _get_pg_user(user.user_id)
        assert pg_user_after.hashed_password != old_hash

        # 새 비밀번호로 검증 가능한지 확인
        assert verify_password("NewPass123!", pg_user_after.hashed_password)


class TestPasswordResetAPI:
    """비밀번호 재설정 API 테스트"""

    @pytest.mark.asyncio
    async def test_request_reset_endpoint_success(self, mock_redis):
        """재설정 요청 엔드포인트 성공"""
        from src.web_server import app
        from src.cache_manager import CacheManager

        cache_manager = Mock(spec=CacheManager)
        app.state.cache_manager = cache_manager

        client = TestClient(app)

        # 사용자 등록
        client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "OldPass123!"
            }
        )

        # 재설정 요청 — 보안상 토큰은 이메일로만 전송되고 응답에 포함되지 않음
        response = client.post(
            "/api/auth/password-reset/request",
            json={"email": "test@example.com"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "이메일" in data["message"]

    @pytest.mark.asyncio
    async def test_request_reset_invalid_email(self, mock_redis):
        """존재하지 않는 이메일로 재설정 요청"""
        from src.web_server import app
        from src.cache_manager import CacheManager

        cache_manager = Mock(spec=CacheManager)
        app.state.cache_manager = cache_manager

        client = TestClient(app)

        response = client.post(
            "/api/auth/password-reset/request",
            json={"email": "nonexistent@example.com"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_reset_endpoint_success(self, mock_redis):
        """재설정 확인 엔드포인트 성공"""
        from src.web_server import app
        from src.cache_manager import CacheManager

        cache_manager = Mock(spec=CacheManager)
        app.state.cache_manager = cache_manager

        client = TestClient(app)

        # 사용자 등록
        register_resp = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "OldPass123!"
            }
        )
        user_id = register_resp.json()["user"]["user_id"]

        # 재설정 토큰을 PG에 저장하여 생성 (서비스 사용)
        reset_service = PasswordResetService()
        reset_token = await reset_service.create_reset_token(user_id, "test@example.com")

        # 비밀번호 재설정
        confirm_response = client.post(
            "/api/auth/password-reset/confirm",
            json={
                "token": reset_token,
                "new_password": "NewPass123!"
            }
        )

        assert confirm_response.status_code == 200
        assert "성공적으로 재설정" in confirm_response.json()["message"]

        # 새 비밀번호로 로그인 가능한지 확인
        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "NewPass123!"
            }
        )

        assert login_response.status_code == 200

    @pytest.mark.asyncio
    async def test_confirm_reset_invalid_token(self, mock_redis):
        """유효하지 않은 토큰으로 재설정 시도"""
        from src.web_server import app
        from src.cache_manager import CacheManager

        cache_manager = Mock(spec=CacheManager)
        app.state.cache_manager = cache_manager

        client = TestClient(app)

        response = client.post(
            "/api/auth/password-reset/confirm",
            json={
                "token": "invalid_token",
                "new_password": "NewPass123!"
            }
        )

        assert response.status_code == 401
