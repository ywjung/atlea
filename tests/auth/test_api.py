"""API Integration Tests for Authentication

End-to-end tests for authentication API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing"""
    mock = MagicMock()
    mock.data = {}
    mock.sets = {}

    def mock_get(key):
        return mock.data.get(key)

    def mock_set(key, value):
        mock.data[key] = value
        return True

    def mock_hset(key, field=None, value=None, mapping=None):
        if key not in mock.data:
            mock.data[key] = {}
        if mapping:
            mock.data[key].update(mapping)
        elif field is not None:
            mock.data[key][field] = value
        return True

    def mock_hget(key, field):
        if key in mock.data and isinstance(mock.data[key], dict):
            return mock.data[key].get(field)
        return None

    def mock_hgetall(key):
        return mock.data.get(key, {})

    def mock_delete(key):
        if key in mock.data:
            del mock.data[key]
            return 1
        return 0

    def mock_expire(key, seconds):
        return True

    def mock_sadd(key, *values):
        if key not in mock.sets:
            mock.sets[key] = set()
        mock.sets[key].update(values)
        return len(values)

    def mock_smembers(key):
        # Return list to avoid "Set changed size during iteration" error
        return list(mock.sets.get(key, set()))

    def mock_srem(key, *values):
        if key in mock.sets:
            removed = 0
            for value in values:
                if value in mock.sets[key]:
                    mock.sets[key].remove(value)
                    removed += 1
            return removed
        return 0

    def mock_exists(key):
        return 1 if key in mock.data else 0

    def mock_setex(key, seconds, value):
        mock.data[key] = value
        return True

    def mock_ttl(key):
        return -2

    # Sorted set operations
    zsets = {}

    def mock_zadd(key, mapping):
        if key not in zsets:
            zsets[key] = {}
        zsets[key].update(mapping)
        return len(mapping)

    def mock_zremrangebyscore(key, min_score, max_score):
        if key in zsets:
            to_remove = [k for k, v in zsets[key].items() if min_score <= v <= max_score]
            for k in to_remove:
                del zsets[key][k]
            return len(to_remove)
        return 0

    def mock_zremrangebyrank(key, start, stop):
        return 0

    def mock_zcard(key):
        return len(zsets.get(key, {}))

    class MockPipeline:
        def __init__(self):
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
                    mock_hset(cmd[1], field=cmd[2], value=cmd[3], mapping=cmd[4])
                    results.append(True)
                elif cmd[0] == 'hgetall':
                    results.append(mock_hgetall(cmd[1]))
                elif cmd[0] == 'get':
                    results.append(mock_get(cmd[1]))
                elif cmd[0] == 'delete':
                    results.append(mock_delete(cmd[1]))
                elif cmd[0] == 'exists':
                    results.append(mock_exists(cmd[1]))
            self.commands = []
            return results

    def mock_pipeline():
        return MockPipeline()

    mock.get = mock_get
    mock.set = mock_set
    mock.setex = mock_setex
    mock.hset = mock_hset
    mock.hget = mock_hget
    mock.hgetall = mock_hgetall
    mock.delete = mock_delete
    mock.exists = mock_exists
    mock.expire = mock_expire
    mock.ttl = mock_ttl
    mock.sadd = mock_sadd
    mock.smembers = mock_smembers
    mock.srem = mock_srem
    mock.zadd = mock_zadd
    mock.zremrangebyscore = mock_zremrangebyscore
    mock.zremrangebyrank = mock_zremrangebyrank
    mock.zcard = mock_zcard
    mock.pipeline = mock_pipeline

    return mock


@pytest.fixture
def test_app(mock_redis):
    """Create test FastAPI application"""
    from fastapi import FastAPI
    from src.routers import auth

    app = FastAPI()
    app.include_router(auth.router)

    # Mock cache manager
    app.state.cache_manager = Mock()

    return app


@pytest.fixture
def client(test_app):
    """Create test client"""
    return TestClient(test_app)


class TestRegisterEndpoint:
    """회원가입 API 테스트"""

    def test_register_success(self, client):
        """정상적인 회원가입"""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "Test1234!"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "회원가입이 완료되었습니다"
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["username"] == "newuser"
        assert "password" not in data["user"]

    def test_register_duplicate_email(self, client):
        """중복 이메일로 회원가입 실패"""
        # 첫 번째 사용자 생성
        client.post(
            "/api/auth/register",
            json={
                "email": "duplicate@example.com",
                "username": "user1",
                "password": "Test1234!"
            }
        )

        # 같은 이메일로 두 번째 시도
        response = client.post(
            "/api/auth/register",
            json={
                "email": "duplicate@example.com",
                "username": "user2",
                "password": "Test5678!"
            }
        )

        assert response.status_code == 400
        assert "이미 사용 중인 이메일입니다" in response.json()["detail"]

    def test_register_invalid_email(self, client):
        """잘못된 이메일 형식"""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "invalid-email",
                "username": "testuser",
                "password": "Test1234!"
            }
        )

        assert response.status_code == 422  # Validation error

    def test_register_weak_password(self, client):
        """약한 비밀번호"""
        response = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "123"
            }
        )

        assert response.status_code == 422  # Validation error


class TestLoginEndpoint:
    """로그인 API 테스트"""

    def test_login_success(self, client):
        """정상적인 로그인"""
        # 회원가입
        client.post(
            "/api/auth/register",
            json={
                "email": "login@example.com",
                "username": "loginuser",
                "password": "Test1234!"
            }
        )

        # 로그인
        response = client.post(
            "/api/auth/login",
            json={
                "email": "login@example.com",
                "password": "Test1234!"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "tokens" in data
        assert data["user"]["email"] == "login@example.com"
        assert data["tokens"]["access_token"] is not None
        assert data["tokens"]["refresh_token"] is not None
        assert data["tokens"]["token_type"] == "bearer"

    def test_login_invalid_email(self, client):
        """존재하지 않는 이메일로 로그인"""
        response = client.post(
            "/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "Test1234!"
            }
        )

        assert response.status_code == 401
        assert "유효하지 않은 이메일 또는 비밀번호입니다" in response.json()["detail"]

    def test_login_invalid_password(self, client):
        """잘못된 비밀번호로 로그인"""
        # 회원가입
        client.post(
            "/api/auth/register",
            json={
                "email": "wrongpw@example.com",
                "username": "wrongpwuser",
                "password": "Correct1234!"
            }
        )

        # 잘못된 비밀번호로 로그인
        response = client.post(
            "/api/auth/login",
            json={
                "email": "wrongpw@example.com",
                "password": "Wrong1234!"
            }
        )

        assert response.status_code == 401
        assert "유효하지 않은 이메일 또는 비밀번호입니다" in response.json()["detail"]

    def test_login_account_lockout(self, client):
        """5회 실패 후 계정 잠김"""
        # 회원가입
        client.post(
            "/api/auth/register",
            json={
                "email": "lockout@example.com",
                "username": "lockoutuser",
                "password": "Correct1234!"
            }
        )

        # 5회 잘못된 비밀번호로 로그인 시도 (5번째에서 잠금 설정됨)
        for i in range(5):
            response = client.post(
                "/api/auth/login",
                json={
                    "email": "lockout@example.com",
                    "password": "Wrong1234!"
                }
            )
            assert response.status_code == 401
            assert "유효하지 않은 이메일 또는 비밀번호입니다" in response.json()["detail"]

        # 6번째 시도에서 계정 잠김 확인
        response = client.post(
            "/api/auth/login",
            json={
                "email": "lockout@example.com",
                "password": "Wrong1234!"
            }
        )
        assert response.status_code == 401
        assert "계정이 잠겼습니다" in response.json()["detail"]


class TestLogoutEndpoint:
    """로그아웃 API 테스트"""

    def test_logout_success(self, client):
        """정상적인 로그아웃"""
        # 회원가입 및 로그인
        client.post(
            "/api/auth/register",
            json={
                "email": "logout@example.com",
                "username": "logoutuser",
                "password": "Test1234!"
            }
        )

        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "logout@example.com",
                "password": "Test1234!"
            }
        )

        access_token = login_response.json()["tokens"]["access_token"]

        # 로그아웃
        response = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200
        assert response.json()["message"] == "로그아웃되었습니다"

    def test_logout_without_auth(self, client):
        """인증 없이 로그아웃 시도 — 소스는 항상 200 반환"""
        response = client.post("/api/auth/logout")

        assert response.status_code == 200

    def test_logout_with_invalid_token(self, client):
        """유효하지 않은 토큰으로 로그아웃 — 소스는 항상 200 반환"""
        response = client.post(
            "/api/auth/logout",
            headers={"Authorization": "Bearer invalid.token.here"}
        )

        assert response.status_code == 200


class TestMeEndpoint:
    """사용자 정보 조회 API 테스트"""

    def test_get_current_user_success(self, client):
        """정상적인 사용자 정보 조회"""
        # 회원가입 및 로그인
        client.post(
            "/api/auth/register",
            json={
                "email": "me@example.com",
                "username": "meuser",
                "password": "Test1234!"
            }
        )

        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "me@example.com",
                "password": "Test1234!"
            }
        )

        access_token = login_response.json()["tokens"]["access_token"]

        # 사용자 정보 조회
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == "me@example.com"
        assert data["user"]["username"] == "meuser"

    def test_get_current_user_without_auth(self, client):
        """인증 없이 사용자 정보 조회"""
        response = client.get("/api/auth/me")

        assert response.status_code == 401

    def test_get_current_user_with_invalid_token(self, client):
        """유효하지 않은 토큰으로 사용자 정보 조회"""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )

        assert response.status_code == 401


class TestAuthenticationFlow:
    """전체 인증 플로우 통합 테스트"""

    def test_full_authentication_flow(self, client):
        """회원가입 → 로그인 → 인증 API 호출 → 로그아웃"""
        # 1. 회원가입
        register_response = client.post(
            "/api/auth/register",
            json={
                "email": "flow@example.com",
                "username": "flowuser",
                "password": "Test1234!"
            }
        )
        assert register_response.status_code == 201

        # 2. 로그인
        login_response = client.post(
            "/api/auth/login",
            json={
                "email": "flow@example.com",
                "password": "Test1234!"
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["tokens"]["access_token"]

        # 3. 인증이 필요한 API 호출 (사용자 정보 조회)
        me_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert me_response.status_code == 200
        assert me_response.json()["user"]["email"] == "flow@example.com"

        # 4. 로그아웃
        logout_response = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert logout_response.status_code == 200

    def test_multiple_login_sessions(self, client):
        """동일 사용자의 여러 세션 생성"""
        import time

        # 회원가입
        client.post(
            "/api/auth/register",
            json={
                "email": "multi@example.com",
                "username": "multiuser",
                "password": "Test1234!"
            }
        )

        # 첫 번째 로그인
        login1 = client.post(
            "/api/auth/login",
            json={
                "email": "multi@example.com",
                "password": "Test1234!"
            }
        )
        token1 = login1.json()["tokens"]["access_token"]

        # 토큰이 다르게 생성되도록 1초 대기
        time.sleep(1)

        # 두 번째 로그인
        login2 = client.post(
            "/api/auth/login",
            json={
                "email": "multi@example.com",
                "password": "Test1234!"
            }
        )
        token2 = login2.json()["tokens"]["access_token"]

        # 두 토큰 모두 유효
        me1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
        me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})

        assert me1.status_code == 200
        assert me2.status_code == 200
        assert me1.json()["user"]["email"] == "multi@example.com"
        assert me2.json()["user"]["email"] == "multi@example.com"

    def test_token_expiration_handling(self, client):
        """만료된 토큰 처리"""
        from datetime import timedelta
        from src.auth.utils import create_access_token

        # 이미 만료된 토큰 생성
        expired_token = create_access_token(
            {"user_id": "test-user"},
            expires_delta=timedelta(seconds=-10)
        )

        # 만료된 토큰으로 API 호출
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401
