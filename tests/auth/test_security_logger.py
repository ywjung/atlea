"""Tests for Security Logger

보안 이벤트 로깅 기능 테스트.
"""

import pytest
import json
from datetime import datetime
from unittest.mock import Mock, patch
from src.auth.security_logger import (
    SecurityLogger,
    SecurityEventType,
    SecurityEventLevel
)


class TestSanitizeData:
    """데이터 sanitization 테스트"""

    def test_sensitive_fields_redacted(self):
        """민감한 필드는 마스킹"""
        data = {
            "username": "testuser",
            "password": "secretpassword123",
            "email": "test@example.com",
            "access_token": "abc123token"
        }

        result = SecurityLogger._sanitize_data(data)

        assert result["username"] == "testuser"
        assert result["password"] == "***REDACTED***"
        assert result["access_token"] == "***REDACTED***"

    def test_email_partial_masking(self):
        """이메일은 부분 마스킹"""
        data = {"email": "testuser@example.com"}
        result = SecurityLogger._sanitize_data(data)
        assert result["email"] == "tes***@example.com"

    def test_short_email_masking(self):
        """짧은 이메일은 완전 마스킹"""
        data = {"email": "ab@example.com"}
        result = SecurityLogger._sanitize_data(data)
        assert result["email"] == "***@example.com"

    def test_all_sensitive_fields(self):
        """모든 민감한 필드 확인"""
        sensitive_fields = [
            "password", "password_hash", "token",
            "access_token", "refresh_token", "secret",
            "api_key", "credentials"
        ]

        for field in sensitive_fields:
            data = {field: "sensitive_value"}
            result = SecurityLogger._sanitize_data(data)
            assert result[field] == "***REDACTED***", f"{field} should be redacted"


class TestLogEvent:
    """보안 이벤트 로깅 테스트"""

    @patch('src.auth.security_logger.logger')
    def test_log_event_basic(self, mock_logger):
        """기본 이벤트 로깅"""
        SecurityLogger.log_event(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            level=SecurityEventLevel.INFO,
            user_id="user123",
            ip_address="192.168.1.100",
            message="Test event"
        )

        # 로거 호출 확인
        assert mock_logger.info.called
        call_args = mock_logger.info.call_args[0][0]
        assert "SECURITY_EVENT" in call_args
        assert "LOGIN_SUCCESS" in call_args

    @patch('src.auth.security_logger.logger')
    def test_log_event_with_extra_data(self, mock_logger):
        """추가 데이터를 포함한 로깅"""
        SecurityLogger.log_event(
            event_type=SecurityEventType.LOGIN_FAILED,
            level=SecurityEventLevel.WARNING,
            user_id="user123",
            ip_address="192.168.1.100",
            message="Login failed",
            reason="Invalid password",
            attempts=3
        )

        call_args = mock_logger.warning.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        assert event_data["reason"] == "Invalid password"
        assert event_data["attempts"] == 3

    @patch('src.auth.security_logger.logger')
    def test_log_event_sanitizes_data(self, mock_logger):
        """민감한 데이터는 자동 sanitize"""
        SecurityLogger.log_event(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            level=SecurityEventLevel.INFO,
            user_id="user123",
            password="should_not_appear"
        )

        call_args = mock_logger.info.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        assert event_data["password"] == "***REDACTED***"

    @patch('src.auth.security_logger.logger')
    def test_log_levels(self, mock_logger):
        """다양한 로그 레벨 테스트"""
        # INFO
        SecurityLogger.log_event(
            SecurityEventType.LOGIN_SUCCESS,
            SecurityEventLevel.INFO
        )
        assert mock_logger.info.called

        # WARNING
        SecurityLogger.log_event(
            SecurityEventType.LOGIN_FAILED,
            SecurityEventLevel.WARNING
        )
        assert mock_logger.warning.called

        # ERROR
        SecurityLogger.log_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            SecurityEventLevel.ERROR
        )
        assert mock_logger.error.called

        # CRITICAL
        SecurityLogger.log_event(
            SecurityEventType.ACCOUNT_LOCKED,
            SecurityEventLevel.CRITICAL
        )
        assert mock_logger.critical.called


class TestConvenienceMethods:
    """편의 메서드 테스트"""

    @patch('src.auth.security_logger.logger')
    def test_log_login_success(self, mock_logger):
        """로그인 성공 로깅"""
        SecurityLogger.log_login_success(
            user_id="user123",
            ip_address="192.168.1.100"
        )

        call_args = mock_logger.info.call_args[0][0]
        assert "LOGIN_SUCCESS" in call_args
        assert "user123" in call_args

    @patch('src.auth.security_logger.logger')
    def test_log_login_failed(self, mock_logger):
        """로그인 실패 로깅"""
        SecurityLogger.log_login_failed(
            email="test@example.com",
            ip_address="192.168.1.100",
            reason="Invalid credentials"
        )

        call_args = mock_logger.warning.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        assert event_data["event_type"] == SecurityEventType.LOGIN_FAILED
        assert "tes***@example.com" in event_data["email"]  # 이메일 마스킹 확인

    @patch('src.auth.security_logger.logger')
    def test_log_logout(self, mock_logger):
        """로그아웃 로깅"""
        SecurityLogger.log_logout(
            user_id="user123",
            ip_address="192.168.1.100"
        )

        call_args = mock_logger.info.call_args[0][0]
        assert "LOGOUT" in call_args

    @patch('src.auth.security_logger.logger')
    def test_log_user_registered(self, mock_logger):
        """회원가입 로깅"""
        SecurityLogger.log_user_registered(
            user_id="user123",
            email="newuser@example.com",
            ip_address="192.168.1.100"
        )

        call_args = mock_logger.info.call_args[0][0]
        assert "ACCOUNT_REGISTERED" in call_args

    @patch('src.auth.security_logger.logger')
    def test_log_account_locked(self, mock_logger):
        """계정 잠금 로깅"""
        SecurityLogger.log_account_locked(
            user_id="user123",
            ip_address="192.168.1.100",
            failed_attempts=5
        )

        call_args = mock_logger.critical.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        assert event_data["event_type"] == SecurityEventType.ACCOUNT_LOCKED
        assert event_data["failed_attempts"] == 5

    @patch('src.auth.security_logger.logger')
    def test_log_account_unlocked(self, mock_logger):
        """계정 잠금 해제 로깅"""
        SecurityLogger.log_account_unlocked(user_id="user123")

        call_args = mock_logger.info.call_args[0][0]
        assert "ACCOUNT_UNLOCKED" in call_args

    @patch('src.auth.security_logger.logger')
    def test_log_rate_limit_exceeded(self, mock_logger):
        """Rate limit 초과 로깅"""
        SecurityLogger.log_rate_limit_exceeded(
            ip_address="192.168.1.100",
            endpoint="/api/auth/login",
            limit=5
        )

        call_args = mock_logger.warning.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        assert event_data["event_type"] == SecurityEventType.RATE_LIMIT_EXCEEDED
        assert event_data["endpoint"] == "/api/auth/login"
        assert event_data["limit"] == 5

    @patch('src.auth.security_logger.logger')
    def test_log_brute_force_attempt(self, mock_logger):
        """Brute force 공격 시도 로깅"""
        SecurityLogger.log_brute_force_attempt(
            email="attacker@example.com",
            ip_address="10.0.0.1",
            attempts=10
        )

        call_args = mock_logger.critical.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        assert event_data["event_type"] == SecurityEventType.BRUTE_FORCE_ATTEMPT
        assert event_data["attempts"] == 10

    @patch('src.auth.security_logger.logger')
    def test_log_unauthorized_access(self, mock_logger):
        """무단 접근 시도 로깅"""
        SecurityLogger.log_unauthorized_access(
            user_id="user123",
            ip_address="192.168.1.100",
            resource="/admin/panel"
        )

        # Find the SECURITY_EVENT call (may have additional error calls from async alert failures)
        security_calls = [c for c in mock_logger.error.call_args_list if "SECURITY_EVENT" in c[0][0]]
        assert len(security_calls) > 0
        call_args = security_calls[0][0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        assert event_data["event_type"] == SecurityEventType.UNAUTHORIZED_ACCESS
        assert event_data["resource"] == "/admin/panel"


class TestEventDataStructure:
    """이벤트 데이터 구조 테스트"""

    @patch('src.auth.security_logger.logger')
    def test_event_has_required_fields(self, mock_logger):
        """모든 이벤트는 필수 필드를 포함"""
        SecurityLogger.log_event(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            level=SecurityEventLevel.INFO,
            user_id="user123"
        )

        call_args = mock_logger.info.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        # 필수 필드 확인
        assert "timestamp" in event_data
        assert "event_type" in event_data
        assert "level" in event_data
        assert "user_id" in event_data
        assert "ip_address" in event_data
        assert "message" in event_data

    @patch('src.auth.security_logger.logger')
    def test_timestamp_format(self, mock_logger):
        """타임스탬프는 ISO 형식"""
        SecurityLogger.log_event(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            level=SecurityEventLevel.INFO
        )

        call_args = mock_logger.info.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        # ISO 형식으로 파싱 가능한지 확인
        timestamp = datetime.fromisoformat(event_data["timestamp"])
        assert isinstance(timestamp, datetime)

    @patch('src.auth.security_logger.logger')
    def test_default_values(self, mock_logger):
        """기본값 확인"""
        SecurityLogger.log_event(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            level=SecurityEventLevel.INFO
        )

        call_args = mock_logger.info.call_args[0][0]
        event_data = json.loads(call_args.split("SECURITY_EVENT: ")[1])

        # user_id와 ip_address는 기본값 사용
        assert event_data["user_id"] == "anonymous"
        assert event_data["ip_address"] == "unknown"
        assert event_data["message"] == ""
