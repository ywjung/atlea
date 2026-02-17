"""Tests for authentication service layer

Tests for user creation, authentication, and session management.
"""

import pytest
import uuid as _uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from src.auth.service import AuthService
from src.auth.models import UserCreate, UserLogin, User


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
    """Mock Redis client for testing"""

    def __init__(self):
        self.data = {}
        self.sets = {}
        self.zsets = {}
        self.expires = {}

    def get(self, key):
        """Mock get operation"""
        return self.data.get(key)

    def set(self, key, value):
        """Mock set operation"""
        self.data[key] = value
        return True

    def setex(self, key, seconds, value):
        """Mock setex operation"""
        self.data[key] = value
        self.expires[key] = seconds
        return True

    def hset(self, key, field=None, value=None, mapping=None):
        """Mock hset operation"""
        if key not in self.data:
            self.data[key] = {}
        if mapping:
            self.data[key].update(mapping)
        elif field is not None:
            self.data[key][field] = value
        return True

    def hget(self, key, field):
        """Mock hget operation"""
        if key in self.data and isinstance(self.data[key], dict):
            return self.data[key].get(field)
        return None

    def hgetall(self, key):
        """Mock hgetall operation"""
        return self.data.get(key, {})

    def delete(self, key):
        """Mock delete operation"""
        if key in self.data:
            del self.data[key]
            return 1
        return 0

    def exists(self, key):
        """Mock exists operation"""
        return 1 if key in self.data else 0

    def expire(self, key, seconds):
        """Mock expire operation"""
        self.expires[key] = seconds
        return True

    def ttl(self, key):
        """Mock ttl operation"""
        return self.expires.get(key, -2)

    def sadd(self, key, *values):
        """Mock sadd operation"""
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].update(values)
        return len(values)

    def smembers(self, key):
        """Mock smembers operation"""
        return list(self.sets.get(key, set()))

    def srem(self, key, *values):
        """Mock srem operation"""
        if key in self.sets:
            removed = 0
            for value in values:
                if value in self.sets[key]:
                    self.sets[key].remove(value)
                    removed += 1
            return removed
        return 0

    def zadd(self, key, mapping):
        """Mock zadd operation"""
        if key not in self.zsets:
            self.zsets[key] = {}
        self.zsets[key].update(mapping)
        return len(mapping)

    def zremrangebyscore(self, key, min_score, max_score):
        """Mock zremrangebyscore operation"""
        if key in self.zsets:
            to_remove = [k for k, v in self.zsets[key].items() if min_score <= v <= max_score]
            for k in to_remove:
                del self.zsets[key][k]
            return len(to_remove)
        return 0

    def zremrangebyrank(self, key, start, stop):
        """Mock zremrangebyrank operation"""
        return 0

    def zcard(self, key):
        """Mock zcard operation"""
        return len(self.zsets.get(key, {}))

    def pipeline(self):
        """Mock pipeline operation"""
        return MockPipeline(self)

    def reset(self):
        """Reset all mock data"""
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
def redis_client():
    """Fixture providing a mock Redis client"""
    mock_redis = MockRedis()
    yield mock_redis
    mock_redis.reset()


@pytest.fixture
def auth_service(redis_client):
    """Fixture providing an AuthService instance"""
    return AuthService()


class TestCreateUser:
    """사용자 생성 테스트"""

    @pytest.mark.asyncio
    async def test_create_user_success(self, auth_service, redis_client):
        """정상적인 사용자 생성"""
        user_data = UserCreate(
            email="test@example.com",
            username="testuser",
            password="Test1234!"
        )

        user = await auth_service.create_user(user_data)

        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.user_id is not None
        assert user.is_active is True
        assert user.role == "user"

        # PG에 데이터가 저장되었는지 확인
        pg_user = _get_pg_user(user.user_id)
        assert pg_user is not None
        assert pg_user.email == user_data.email
        assert pg_user.username == user_data.username

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, auth_service, redis_client):
        """중복 이메일로 사용자 생성 시 실패"""
        user_data = UserCreate(
            email="duplicate@example.com",
            username="user1",
            password="Test1234!"
        )

        # 첫 번째 사용자 생성
        await auth_service.create_user(user_data)

        # 같은 이메일로 두 번째 사용자 생성 시도
        duplicate_data = UserCreate(
            email="duplicate@example.com",
            username="user2",
            password="Test5678!"
        )

        with pytest.raises(ValueError, match="이미 사용 중인 이메일입니다"):
            await auth_service.create_user(duplicate_data)

    @pytest.mark.asyncio
    async def test_create_user_with_special_characters(self, auth_service):
        """특수문자 포함 비밀번호로 사용자 생성"""
        user_data = UserCreate(
            email="special@example.com",
            username="specialuser",
            password="P@ssw0rd!#$%"
        )

        user = await auth_service.create_user(user_data)

        assert user.email == "special@example.com"
        assert user.username == "specialuser"

    @pytest.mark.asyncio
    async def test_create_user_stores_hashed_password(self, auth_service, redis_client):
        """비밀번호가 해시되어 저장되는지 확인"""
        user_data = UserCreate(
            email="hash@example.com",
            username="hashuser",
            password="PlainPassword123!"
        )

        user = await auth_service.create_user(user_data)

        # PG에서 해시된 비밀번호 확인
        pg_user = _get_pg_user(user.user_id)

        # 해시된 비밀번호는 원본과 달라야 함
        assert pg_user.hashed_password != "PlainPassword123!"
        # bcrypt 해시 형식 확인
        assert pg_user.hashed_password.startswith("$2b$")


class TestAuthenticateUser:
    """사용자 인증 테스트"""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, auth_service):
        """정상적인 로그인"""
        # 사용자 생성
        user_data = UserCreate(
            email="login@example.com",
            username="loginuser",
            password="Test1234!"
        )
        await auth_service.create_user(user_data)

        # 로그인 시도
        credentials = UserLogin(
            email="login@example.com",
            password="Test1234!"
        )
        result = await auth_service.authenticate_user(credentials)

        assert "user" in result
        assert "tokens" in result
        assert "session_id" in result
        assert result["user"].email == "login@example.com"
        assert result["tokens"]["access_token"] is not None
        assert result["tokens"]["refresh_token"] is not None

    @pytest.mark.asyncio
    async def test_authenticate_invalid_email(self, auth_service):
        """존재하지 않는 이메일로 로그인"""
        credentials = UserLogin(
            email="nonexistent@example.com",
            password="Test1234!"
        )

        with pytest.raises(ValueError, match="유효하지 않은 이메일 또는 비밀번호입니다"):
            await auth_service.authenticate_user(credentials)

    @pytest.mark.asyncio
    async def test_authenticate_invalid_password(self, auth_service):
        """잘못된 비밀번호로 로그인"""
        # 사용자 생성
        user_data = UserCreate(
            email="wrong@example.com",
            username="wronguser",
            password="Correct1234!"
        )
        await auth_service.create_user(user_data)

        # 잘못된 비밀번호로 로그인 시도
        credentials = UserLogin(
            email="wrong@example.com",
            password="Wrong1234!"
        )

        with pytest.raises(ValueError, match="유효하지 않은 이메일 또는 비밀번호입니다"):
            await auth_service.authenticate_user(credentials)

    @pytest.mark.asyncio
    async def test_authenticate_account_lockout(self, auth_service):
        """5회 로그인 실패 시 계정 잠김"""
        # 사용자 생성
        user_data = UserCreate(
            email="lockout@example.com",
            username="lockoutuser",
            password="Correct1234!"
        )
        await auth_service.create_user(user_data)

        # 5회 잘못된 비밀번호로 로그인 시도
        credentials = UserLogin(
            email="lockout@example.com",
            password="Wrong1234!"
        )

        for i in range(5):
            with pytest.raises(ValueError, match="유효하지 않은 이메일 또는 비밀번호입니다"):
                await auth_service.authenticate_user(credentials)

        # 6번째 시도에서 계정 잠김 확인
        with pytest.raises(ValueError, match="계정이 잠겼습니다"):
            await auth_service.authenticate_user(credentials)

        # 올바른 비밀번호로도 로그인 불가
        correct_credentials = UserLogin(
            email="lockout@example.com",
            password="Correct1234!"
        )

        with pytest.raises(ValueError, match="계정이 잠겼습니다"):
            await auth_service.authenticate_user(correct_credentials)

    @pytest.mark.asyncio
    async def test_authenticate_resets_failed_attempts_on_success(self, auth_service, redis_client):
        """로그인 성공 시 실패 횟수 리셋"""
        # 사용자 생성
        user_data = UserCreate(
            email="reset@example.com",
            username="resetuser",
            password="Correct1234!"
        )
        created_user = await auth_service.create_user(user_data)

        # 2회 잘못된 비밀번호로 로그인 시도
        wrong_credentials = UserLogin(
            email="reset@example.com",
            password="Wrong1234!"
        )

        for i in range(2):
            with pytest.raises(ValueError):
                await auth_service.authenticate_user(wrong_credentials)

        # 올바른 비밀번호로 로그인
        correct_credentials = UserLogin(
            email="reset@example.com",
            password="Correct1234!"
        )
        result = await auth_service.authenticate_user(correct_credentials)

        assert result is not None

        # 실패 횟수가 0으로 리셋되었는지 확인
        pg_user = _get_pg_user(created_user.user_id)
        assert pg_user.failed_login_attempts == 0


class TestSession:
    """세션 관리 테스트"""

    @pytest.mark.asyncio
    async def test_create_session_via_authenticate(self, auth_service, redis_client):
        """인증을 통한 세션 생성"""
        # 사용자 생성
        user_data = UserCreate(
            email="session@example.com",
            username="sessionuser",
            password="Test1234!"
        )
        await auth_service.create_user(user_data)

        # 로그인하면 세션이 생성됨
        credentials = UserLogin(
            email="session@example.com",
            password="Test1234!"
        )
        result = await auth_service.authenticate_user(credentials)

        assert "session_id" in result
        session_id = result["session_id"]
        assert session_id is not None

        # PG에 세션이 저장되었는지 확인
        sessions = _get_pg_sessions(result["user"].user_id)
        assert len(sessions) > 0

    @pytest.mark.asyncio
    async def test_logout(self, auth_service, redis_client):
        """로그아웃"""
        # 사용자 생성 및 로그인
        user_data = UserCreate(
            email="logout@example.com",
            username="logoutuser",
            password="Test1234!"
        )
        await auth_service.create_user(user_data)

        credentials = UserLogin(
            email="logout@example.com",
            password="Test1234!"
        )
        result = await auth_service.authenticate_user(credentials)
        session_id = result["session_id"]

        # 로그아웃 (returns None, not True/False)
        await auth_service.logout(session_id)

        # 세션이 삭제되었는지 확인
        session_key = f"session:{session_id}"
        assert redis_client.hgetall(session_key) == {}

    @pytest.mark.asyncio
    async def test_logout_nonexistent_session(self, auth_service):
        """존재하지 않는 세션 로그아웃"""
        # logout returns None for nonexistent sessions (no return value)
        result = await auth_service.logout("nonexistent-session-id")

        assert result is None


class TestGetUserById:
    """사용자 조회 테스트"""

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self, auth_service):
        """사용자 ID로 조회 성공"""
        # 사용자 생성
        user_data = UserCreate(
            email="getuser@example.com",
            username="getuser",
            password="Test1234!"
        )
        created_user = await auth_service.create_user(user_data)

        # 사용자 조회
        user = await auth_service.get_user_by_id(created_user.user_id)

        assert user is not None
        assert user.user_id == created_user.user_id
        assert user.email == "getuser@example.com"
        assert user.username == "getuser"

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, auth_service):
        """존재하지 않는 사용자 조회"""
        user = await auth_service.get_user_by_id("nonexistent-user-id")

        assert user is None
