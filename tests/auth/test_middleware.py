"""Tests for authentication middleware

Tests for JWT authentication and authorization middleware.
"""

import uuid
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from unittest.mock import Mock
from src.auth.middleware import get_current_user, get_current_active_user, require_admin
from src.auth.utils import create_access_token
from datetime import datetime, timezone


def _create_pg_user(user_id: str, email: str, username: str,
                    role: str = "user", is_active: bool = True):
    """Insert a user directly into the SQLite/PG test database."""
    from src.database.connection import SyncSessionFactory
    from src.database.models.user import User as PgUser
    from src.auth.utils import hash_password

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        uid = uuid.uuid4()

    with SyncSessionFactory() as session:
        pg_user = PgUser(
            id=uid,
            email=email,
            username=username,
            hashed_password=hash_password("Test1234!@"),
            role=role,
            is_active=is_active,
        )
        session.add(pg_user)
        session.commit()

    return str(uid)


@pytest.fixture
def mock_request():
    """Fixture providing mock FastAPI Request"""
    request = Mock()
    request.app = Mock()
    request.app.state = Mock()
    request.app.state.cache_manager = Mock()
    return request


@pytest.fixture
def valid_user_id():
    """Create a valid test user in the database and return its ID."""
    return _create_pg_user(
        user_id=str(uuid.uuid4()),
        email="test@example.com",
        username="testuser",
        role="user",
        is_active=True,
    )


@pytest.fixture
def admin_user_id():
    """Create an admin user in the database and return its ID."""
    return _create_pg_user(
        user_id=str(uuid.uuid4()),
        email="admin@example.com",
        username="adminuser",
        role="admin",
        is_active=True,
    )


@pytest.fixture
def inactive_user_id():
    """Create an inactive user in the database and return its ID."""
    return _create_pg_user(
        user_id=str(uuid.uuid4()),
        email="inactive@example.com",
        username="inactiveuser",
        role="user",
        is_active=False,
    )


class TestGetCurrentUser:
    """get_current_user 미들웨어 테스트"""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_request, valid_user_id):
        """정상적인 사용자 인증"""
        token = create_access_token({"user_id": valid_user_id})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        result = await get_current_user(mock_request, credentials)

        assert result["user_id"] == valid_user_id
        assert result["email"] == "test@example.com"
        assert result["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self, mock_request):
        """인증 정보 없음"""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, None)

        assert exc_info.value.status_code == 401
        assert "인증이 필요합니다" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_request):
        """유효하지 않은 토큰"""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid.token.here"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)

        assert exc_info.value.status_code == 401
        assert "유효하지 않은 토큰입니다" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, mock_request):
        """만료된 토큰"""
        from datetime import timedelta

        token = create_access_token(
            {"user_id": "test-user"},
            expires_delta=timedelta(seconds=-10)
        )
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)

        assert exc_info.value.status_code == 401
        assert "유효하지 않은 토큰입니다" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_not_found(self, mock_request):
        """존재하지 않는 사용자"""
        token = create_access_token({"user_id": str(uuid.uuid4())})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)

        assert exc_info.value.status_code == 401
        assert "사용자를 찾을 수 없습니다" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_wrong_token_type(self, mock_request):
        """잘못된 토큰 타입 (refresh 토큰)"""
        from src.auth.utils import create_refresh_token

        token = create_refresh_token({"user_id": "test-user"})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials)

        assert exc_info.value.status_code == 401
        assert "유효하지 않은 토큰입니다" in exc_info.value.detail


class TestGetCurrentActiveUser:
    """get_current_active_user 미들웨어 테스트"""

    @pytest.mark.asyncio
    async def test_get_current_active_user_success(self):
        """활성 사용자 검증 성공"""
        current_user = {
            "user_id": "test-user-123",
            "email": "test@example.com",
            "is_active": True,
            "role": "user"
        }

        result = await get_current_active_user(current_user)

        assert result == current_user

    @pytest.mark.asyncio
    async def test_get_current_active_user_inactive(self):
        """비활성 사용자 거부"""
        current_user = {
            "user_id": "inactive-user",
            "email": "inactive@example.com",
            "is_active": False,
            "role": "user"
        }

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(current_user)

        assert exc_info.value.status_code == 403
        assert "비활성화된 계정입니다" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_active_user_missing_is_active(self):
        """is_active 필드 없음"""
        current_user = {
            "user_id": "test-user",
            "email": "test@example.com",
            "role": "user"
        }

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(current_user)

        assert exc_info.value.status_code == 403


class TestRequireAdmin:
    """require_admin 미들웨어 테스트"""

    @pytest.mark.asyncio
    async def test_require_admin_success(self):
        """관리자 권한 검증 성공"""
        current_user = {
            "user_id": "admin-user",
            "email": "admin@example.com",
            "is_active": True,
            "role": "admin"
        }

        result = await require_admin(current_user)

        assert result == current_user

    @pytest.mark.asyncio
    async def test_require_admin_not_admin(self):
        """관리자 아닌 사용자 거부"""
        current_user = {
            "user_id": "regular-user",
            "email": "user@example.com",
            "is_active": True,
            "role": "user"
        }

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(current_user)

        assert exc_info.value.status_code == 403
        assert "관리자 권한이 필요합니다" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_admin_missing_role(self):
        """role 필드 없음"""
        current_user = {
            "user_id": "test-user",
            "email": "test@example.com",
            "is_active": True
        }

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(current_user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_admin_moderator_denied(self):
        """moderator 역할도 거부"""
        current_user = {
            "user_id": "mod-user",
            "email": "mod@example.com",
            "is_active": True,
            "role": "moderator"
        }

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(current_user)

        assert exc_info.value.status_code == 403
        assert "관리자 권한이 필요합니다" in exc_info.value.detail


class TestMiddlewareIntegration:
    """미들웨어 통합 테스트"""

    @pytest.mark.asyncio
    async def test_full_auth_flow(self, mock_request, valid_user_id):
        """전체 인증 흐름 테스트"""
        token = create_access_token({"user_id": valid_user_id})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        # get_current_user 통과
        current_user = await get_current_user(mock_request, credentials)
        assert current_user["user_id"] == valid_user_id

        # get_current_active_user 통과
        active_user = await get_current_active_user(current_user)
        assert active_user["is_active"] is True

    @pytest.mark.asyncio
    async def test_full_admin_flow(self, mock_request, admin_user_id):
        """전체 관리자 인증 흐름 테스트"""
        token = create_access_token({"user_id": admin_user_id})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        current_user = await get_current_user(mock_request, credentials)
        assert current_user["user_id"] == admin_user_id

        active_user = await get_current_active_user(current_user)
        assert active_user["is_active"] is True

        admin_user = await require_admin(active_user)
        assert admin_user["role"] == "admin"

    @pytest.mark.asyncio
    async def test_inactive_user_blocked(self, mock_request, inactive_user_id):
        """비활성 사용자 차단 테스트"""
        token = create_access_token({"user_id": inactive_user_id})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        # get_current_user는 통과
        current_user = await get_current_user(mock_request, credentials)
        assert current_user["user_id"] == inactive_user_id

        # get_current_active_user에서 차단
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(current_user)

        assert exc_info.value.status_code == 403
        assert "비활성화된 계정입니다" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_regular_user_admin_blocked(self, mock_request, valid_user_id):
        """일반 사용자 관리자 기능 차단 테스트"""
        token = create_access_token({"user_id": valid_user_id})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        current_user = await get_current_user(mock_request, credentials)
        active_user = await get_current_active_user(current_user)

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(active_user)

        assert exc_info.value.status_code == 403
        assert "관리자 권한이 필요합니다" in exc_info.value.detail
