"""Tests for authentication utilities

Tests for password hashing, JWT token generation and verification.
"""

import pytest
from datetime import datetime, timedelta
from src.auth.utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    create_token_pair
)


class TestPasswordHashing:
    """비밀번호 해싱 테스트"""

    def test_hash_password_creates_different_hashes(self):
        """같은 비밀번호도 다른 해시 생성 (salt 때문에)"""
        password = "Test1234!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert len(hash1) > 0
        assert len(hash2) > 0

    def test_verify_password_correct(self):
        """올바른 비밀번호 검증 성공"""
        password = "Test1234!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """틀린 비밀번호 검증 실패"""
        password = "Test1234!"
        wrong_password = "Wrong1234!"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_hash_password_with_special_characters(self):
        """특수문자 포함 비밀번호 해싱"""
        password = "P@ssw0rd!#$%"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_hash_password_with_unicode(self):
        """유니코드 문자 포함 비밀번호 해싱"""
        password = "테스트1234!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True


class TestJWTTokens:
    """JWT 토큰 생성 및 검증 테스트"""

    def test_create_access_token(self):
        """액세스 토큰 생성"""
        user_id = "test-user-123"
        token = create_access_token({"user_id": user_id})

        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)

    def test_create_refresh_token(self):
        """리프레시 토큰 생성"""
        user_id = "test-user-123"
        token = create_refresh_token({"user_id": user_id})

        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)

    def test_verify_access_token_valid(self):
        """유효한 액세스 토큰 검증"""
        user_id = "test-user-123"
        token = create_access_token({"user_id": user_id})
        payload = verify_token(token, expected_type="access")

        assert payload is not None
        assert payload["user_id"] == user_id
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_verify_refresh_token_valid(self):
        """유효한 리프레시 토큰 검증"""
        user_id = "test-user-123"
        token = create_refresh_token({"user_id": user_id})
        payload = verify_token(token, expected_type="refresh")

        assert payload is not None
        assert payload["user_id"] == user_id
        assert payload["type"] == "refresh"

    def test_verify_token_wrong_type(self):
        """잘못된 타입의 토큰 검증 실패"""
        user_id = "test-user-123"
        access_token = create_access_token({"user_id": user_id})

        # access 토큰을 refresh로 검증하면 실패해야 함
        payload = verify_token(access_token, expected_type="refresh")
        assert payload is None

    def test_verify_token_invalid(self):
        """유효하지 않은 토큰 검증 실패"""
        invalid_token = "invalid.token.here"
        payload = verify_token(invalid_token)

        assert payload is None

    def test_verify_token_expired(self):
        """만료된 토큰 검증 실패"""
        user_id = "test-user-123"
        # 이미 만료된 토큰 생성 (과거 시간)
        expired_token = create_access_token(
            {"user_id": user_id},
            expires_delta=timedelta(seconds=-10)
        )

        payload = verify_token(expired_token)
        assert payload is None

    def test_create_token_pair(self):
        """토큰 쌍 생성"""
        user_id = "test-user-123"
        tokens = create_token_pair(user_id)

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert "token_type" in tokens
        assert tokens["token_type"] == "bearer"

        # 두 토큰 모두 검증 가능
        access_payload = verify_token(tokens["access_token"], "access")
        refresh_payload = verify_token(tokens["refresh_token"], "refresh")

        assert access_payload is not None
        assert refresh_payload is not None
        assert access_payload["user_id"] == user_id
        assert refresh_payload["user_id"] == user_id

    def test_token_contains_expiration(self):
        """토큰에 만료 시간 포함 확인"""
        user_id = "test-user-123"
        token = create_access_token({"user_id": user_id})
        payload = verify_token(token)

        assert "exp" in payload
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp)

        # 만료 시간이 미래여야 함
        assert exp_datetime > datetime.utcnow()

    def test_custom_expiration_delta(self):
        """커스텀 만료 시간 설정"""
        user_id = "test-user-123"
        custom_delta = timedelta(minutes=30)
        token = create_access_token({"user_id": user_id}, expires_delta=custom_delta)
        payload = verify_token(token)

        assert payload is not None
        exp_datetime = datetime.utcfromtimestamp(payload["exp"])
        expected_exp = datetime.utcnow() + custom_delta

        # 약 30분 후 만료 (오차 범위 1분)
        time_diff = abs((exp_datetime - expected_exp).total_seconds())
        assert time_diff < 60
