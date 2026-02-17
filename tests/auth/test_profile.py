"""Tests for Profile Management

사용자 프로필 관리 기능 테스트.
"""

import pytest
import uuid as _uuid
from fastapi.testclient import TestClient
from unittest.mock import Mock
from src.auth.service import AuthService
from src.auth.models import UserCreate, UserLogin


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


class TestProfileUpdate:
    """프로필 업데이트 테스트"""

    @pytest.mark.asyncio
    async def test_update_username(self, auth_service, mock_redis):
        """사용자명 업데이트 성공"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="oldusername",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 사용자명 업데이트
        updated_user = await auth_service.update_profile(
            user_id=user.user_id,
            username="newusername"
        )

        assert updated_user.username == "newusername"
        assert updated_user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_update_profile_user_not_found(self, auth_service):
        """존재하지 않는 사용자"""
        with pytest.raises(ValueError) as exc_info:
            await auth_service.update_profile(
                user_id="nonexistent",
                username="newusername"
            )

        assert "사용자를 찾을 수 없습니다" in str(exc_info.value)


class TestPasswordChange:
    """비밀번호 변경 테스트"""

    @pytest.mark.asyncio
    async def test_change_password_success(self, auth_service, mock_redis):
        """비밀번호 변경 성공"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="OldPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 비밀번호 변경
        result = await auth_service.change_password(
            user_id=user.user_id,
            old_password="OldPass123!",
            new_password="NewPass123!"
        )

        # change_password returns None (no return statement)
        assert result is None

        # PG에서 새 비밀번호로 로그인 가능한지 확인
        from src.auth.utils import verify_password

        pg_user = _get_pg_user(user.user_id)
        assert verify_password("NewPass123!", pg_user.hashed_password)

    @pytest.mark.asyncio
    async def test_change_password_wrong_old_password(self, auth_service):
        """잘못된 현재 비밀번호"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="OldPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 잘못된 비밀번호로 변경 시도
        with pytest.raises(ValueError) as exc_info:
            await auth_service.change_password(
                user_id=user.user_id,
                old_password="WrongPassword123!",
                new_password="NewPass123!"
            )

        assert "현재 비밀번호가 일치하지 않습니다" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_change_password_invalidates_sessions(self, auth_service, mock_redis):
        """비밀번호 변경 시 모든 세션 무효화"""
        # 사용자 생성 및 로그인
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="OldPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 로그인하여 세션 생성
        credentials = UserLogin(email="test@example.com", password="OldPass123!")
        await auth_service.authenticate_user(credentials)

        # PG에서 세션이 존재하는지 확인
        sessions = _get_pg_sessions(user.user_id)
        assert len(sessions) > 0

        # 비밀번호 변경
        await auth_service.change_password(
            user_id=user.user_id,
            old_password="OldPass123!",
            new_password="NewPass123!"
        )

        # PG에서 세션이 모두 비활성화되었는지 확인
        sessions = _get_pg_sessions(user.user_id)
        assert len(sessions) == 0


class TestSessionManagement:
    """세션 관리 테스트"""

    @pytest.mark.asyncio
    async def test_get_user_sessions(self, auth_service, mock_redis):
        """사용자 세션 조회"""
        # 사용자 생성 및 로그인
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 로그인하여 세션 생성
        credentials = UserLogin(email="test@example.com", password="TestPass123!")
        result = await auth_service.authenticate_user(credentials)

        # 세션 조회
        sessions = await auth_service.get_user_sessions(user.user_id)

        assert len(sessions) == 1
        assert sessions[0].user_id == user.user_id
        assert sessions[0].session_id is not None

    @pytest.mark.asyncio
    async def test_revoke_session(self, auth_service, mock_redis):
        """세션 무효화 성공"""
        # 사용자 생성 및 로그인
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 로그인하여 세션 생성
        credentials = UserLogin(email="test@example.com", password="TestPass123!")
        result = await auth_service.authenticate_user(credentials)
        session_id = result["session_id"]

        # 세션 무효화
        success = await auth_service.revoke_session(
            user_id=user.user_id,
            session_id=session_id
        )

        assert success is True

        # 세션이 삭제되었는지 확인
        sessions = await auth_service.get_user_sessions(user.user_id)
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_revoke_session_not_found(self, auth_service, mock_redis):
        """존재하지 않는 세션"""
        # 사용자 생성
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="TestPass123!"
        )
        user = await auth_service.create_user(user_data)

        # 존재하지 않는 세션 무효화 시도 — source returns False
        result = await auth_service.revoke_session(
            user_id=user.user_id,
            session_id="nonexistent_session"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_session_unauthorized(self, auth_service, mock_redis):
        """다른 사용자의 세션 무효화 시도"""
        # 첫 번째 사용자 생성 및 로그인
        user1_data = UserCreate(
            email="user1@example.com",
            username="user1",
            password="TestPass123!"
        )
        user1 = await auth_service.create_user(user1_data)

        credentials1 = UserLogin(email="user1@example.com", password="TestPass123!")
        result1 = await auth_service.authenticate_user(credentials1)
        session1_id = result1["session_id"]

        # 두 번째 사용자 생성
        user2_data = UserCreate(
            email="user2@example.com",
            username="user2",
            password="TestPass123!"
        )
        user2 = await auth_service.create_user(user2_data)

        # user2가 user1의 세션 무효화 시도
        with pytest.raises(ValueError) as exc_info:
            await auth_service.revoke_session(
                user_id=user2.user_id,
                session_id=session1_id
            )

        assert "이 세션에 대한 권한이 없습니다" in str(exc_info.value)


class TestProfileAPI:
    """프로필 관리 API 테스트"""

    @pytest.mark.asyncio
    async def test_update_profile_endpoint(self, mock_redis):
        """프로필 업데이트 엔드포인트"""
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
                "username": "oldname",
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

        token = login_response.json()["tokens"]["access_token"]

        # 프로필 업데이트
        response = client.put(
            "/api/auth/profile",
            json={"username": "newname"},
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["username"] == "newname"

    @pytest.mark.asyncio
    async def test_change_password_endpoint(self, mock_redis):
        """비밀번호 변경 엔드포인트"""
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
                "password": "OldPass123!"
            }
        )

        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "OldPass123!"
            }
        )

        token = login_response.json()["tokens"]["access_token"]

        # 비밀번호 변경
        response = client.post(
            "/api/auth/change-password",
            json={
                "old_password": "OldPass123!",
                "new_password": "NewPass123!"
            },
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

        # 새 비밀번호로 로그인 가능한지 확인
        new_login_response = client.post(
            "/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "NewPass123!"
            }
        )

        assert new_login_response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_sessions_endpoint(self, mock_redis):
        """세션 조회 엔드포인트"""
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

        token = login_response.json()["tokens"]["access_token"]

        # 세션 조회
        response = client.get(
            "/api/auth/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 1

    @pytest.mark.asyncio
    async def test_revoke_session_endpoint(self, mock_redis):
        """세션 무효화 엔드포인트"""
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

        token = login_response.json()["tokens"]["access_token"]

        # 세션 조회
        sessions_response = client.get(
            "/api/auth/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        session_id = sessions_response.json()["sessions"][0]["session_id"]

        # 세션 무효화
        response = client.delete(
            f"/api/auth/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

        # 세션이 삭제되었는지 확인
        sessions_response = client.get(
            "/api/auth/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert len(sessions_response.json()["sessions"]) == 0
