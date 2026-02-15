"""Security Event Logger

보안 관련 이벤트를 체계적으로 로깅합니다.
민감한 정보는 로깅하지 않으며, 감사(audit) 로그를 생성합니다.
PostgreSQL 기반 저장.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from loguru import logger
import json
import asyncio


class SecurityEventType:
    """보안 이벤트 타입"""

    # 인증 이벤트
    LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    LOGIN_FAILED = "AUTH_LOGIN_FAILED"
    LOGOUT = "AUTH_LOGOUT"

    # 계정 관리
    USER_REGISTERED = "ACCOUNT_REGISTERED"
    USER_CREATED = "ACCOUNT_CREATED"
    USER_DELETED = "ACCOUNT_DELETED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED"
    USER_STATUS_CHANGED = "ACCOUNT_STATUS_CHANGED"
    USER_ROLE_CHANGED = "ACCOUNT_ROLE_CHANGED"

    # 비밀번호 관련
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_COMPLETED = "PASSWORD_RESET_COMPLETED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET_BY_ADMIN = "PASSWORD_RESET_BY_ADMIN"

    # 토큰 관련
    TOKEN_ISSUED = "TOKEN_ISSUED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"

    # 보안 위협
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    BRUTE_FORCE_ATTEMPT = "BRUTE_FORCE_ATTEMPT"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"
    CSP_VIOLATION = "CSP_VIOLATION"

    # 권한 관련
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    PERMISSION_DENIED = "PERMISSION_DENIED"


class SecurityEventLevel:
    """보안 이벤트 레벨"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SecurityLogger:
    """보안 이벤트 로거

    모든 보안 관련 이벤트를 구조화된 형식으로 로깅합니다.
    """

    @classmethod
    def initialize(cls):
        """Initialize SecurityLogger."""
        pass

    @staticmethod
    def _sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """민감한 정보 제거"""
        sensitive_fields = [
            "password",
            "password_hash",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "api_key",
            "credentials"
        ]

        sanitized = {}
        for key, value in data.items():
            if key.lower() in sensitive_fields:
                sanitized[key] = "***REDACTED***"
            elif key.lower() == "email" and isinstance(value, str) and "@" in value:
                local, domain = value.split("@")
                if len(local) > 3:
                    sanitized[key] = f"{local[:3]}***@{domain}"
                else:
                    sanitized[key] = f"***@{domain}"
            else:
                sanitized[key] = value

        return sanitized

    @classmethod
    def log_event(
        cls,
        event_type: str,
        level: str = SecurityEventLevel.INFO,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        message: Optional[str] = None,
        **extra_data
    ):
        """보안 이벤트 로깅 (PostgreSQL + 파일 하이브리드)"""
        sanitized_data = cls._sanitize_data(extra_data)

        event_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "level": level,
            "user_id": user_id or "anonymous",
            "ip_address": ip_address or "unknown",
            "message": message or "",
            **sanitized_data
        }

        # 1. 파일 로깅
        log_message = f"SECURITY_EVENT: {json.dumps(event_data, ensure_ascii=False)}"

        if level == SecurityEventLevel.CRITICAL:
            logger.critical(log_message)
        elif level == SecurityEventLevel.ERROR:
            logger.error(log_message)
        elif level == SecurityEventLevel.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)

        # 2. PostgreSQL 저장 (비동기 백그라운드)
        try:
            cls._store_to_pg(event_data)
        except Exception as e:
            logger.error(f"Failed to store to PostgreSQL: {e}")

        # 3. 웹훅 트리거
        try:
            from .models import WebhookEvent
            try:
                webhook_event = WebhookEvent(event_type)
                asyncio.create_task(cls._trigger_webhooks(webhook_event, event_data))
            except ValueError:
                pass
        except Exception as e:
            logger.error(f"Failed to trigger webhooks: {e}")

        # 4. 실시간 알림 전송
        try:
            from .alert_system import alert_manager
            asyncio.create_task(alert_manager.send_alert(event_data))
        except Exception as e:
            logger.error(f"Failed to send real-time alert: {e}")

    @classmethod
    def _store_to_pg(cls, event_data: Dict[str, Any]):
        """PostgreSQL에 보안 로그 저장 (동기)"""
        try:
            from ..database.connection import SyncSessionFactory
            from ..database.models.security_log import SecurityLog

            with SyncSessionFactory() as session:
                log_entry = SecurityLog(
                    level=event_data.get("level", "INFO"),
                    event_type=event_data.get("event_type", "UNKNOWN"),
                    message=event_data.get("message", ""),
                    details={
                        k: v for k, v in event_data.items()
                        if k not in ("level", "event_type", "message", "ip_address", "user_id", "timestamp")
                    },
                    ip_address=event_data.get("ip_address"),
                    user_id=event_data.get("user_id"),
                )
                session.add(log_entry)
                session.commit()

        except Exception as e:
            logger.error(f"PostgreSQL storage failed: {e}")

    @classmethod
    async def _trigger_webhooks(cls, event: 'WebhookEvent', payload: Dict[str, Any]):
        """웹훅 트리거 (비동기)"""
        try:
            from .webhook_service import WebhookService

            webhook_service = WebhookService()
            await webhook_service.trigger_event(event, payload)

        except Exception as e:
            logger.error(f"Webhook trigger failed: {e}")

    # 편의 메서드들

    @staticmethod
    def log_login_success(user_id: str, ip_address: Optional[str] = None, **extra):
        SecurityLogger.log_event(
            SecurityEventType.LOGIN_SUCCESS,
            SecurityEventLevel.INFO,
            user_id=user_id,
            ip_address=ip_address,
            message="User logged in successfully",
            **extra
        )

    @staticmethod
    def log_login_failed(
        email: str,
        ip_address: Optional[str] = None,
        reason: str = "Invalid credentials",
        **extra
    ):
        SecurityLogger.log_event(
            SecurityEventType.LOGIN_FAILED,
            SecurityEventLevel.WARNING,
            ip_address=ip_address,
            message=f"Login failed: {reason}",
            email=email,
            reason=reason,
            **extra
        )

    @staticmethod
    def log_logout(user_id: str, ip_address: Optional[str] = None, **extra):
        SecurityLogger.log_event(
            SecurityEventType.LOGOUT,
            SecurityEventLevel.INFO,
            user_id=user_id,
            ip_address=ip_address,
            message="User logged out",
            **extra
        )

    @staticmethod
    def log_user_registered(user_id: str, email: str, ip_address: Optional[str] = None, **extra):
        SecurityLogger.log_event(
            SecurityEventType.USER_REGISTERED,
            SecurityEventLevel.INFO,
            user_id=user_id,
            ip_address=ip_address,
            message="New user registered",
            email=email,
            **extra
        )

    @staticmethod
    def log_account_locked(
        user_id: str,
        ip_address: Optional[str] = None,
        reason: str = "Too many failed login attempts",
        failed_attempts: int = 0,
        **extra
    ):
        SecurityLogger.log_event(
            SecurityEventType.ACCOUNT_LOCKED,
            SecurityEventLevel.CRITICAL,
            user_id=user_id,
            ip_address=ip_address,
            message=f"Account locked: {reason}",
            reason=reason,
            failed_attempts=failed_attempts,
            **extra
        )

    @staticmethod
    def log_account_unlocked(user_id: str, **extra):
        SecurityLogger.log_event(
            SecurityEventType.ACCOUNT_UNLOCKED,
            SecurityEventLevel.INFO,
            user_id=user_id,
            message="Account unlocked",
            **extra
        )

    @staticmethod
    def log_token_issued(user_id: str, token_type: str = "access", **extra):
        SecurityLogger.log_event(
            SecurityEventType.TOKEN_ISSUED,
            SecurityEventLevel.INFO,
            user_id=user_id,
            message=f"{token_type.capitalize()} token issued",
            token_type=token_type,
            **extra
        )

    @staticmethod
    def log_token_invalid(
        ip_address: Optional[str] = None,
        reason: str = "Invalid token",
        **extra
    ):
        SecurityLogger.log_event(
            SecurityEventType.TOKEN_INVALID,
            SecurityEventLevel.WARNING,
            ip_address=ip_address,
            message=f"Invalid token attempt: {reason}",
            reason=reason,
            **extra
        )

    @staticmethod
    def log_token_expired(user_id: Optional[str] = None, **extra):
        SecurityLogger.log_event(
            SecurityEventType.TOKEN_EXPIRED,
            SecurityEventLevel.INFO,
            user_id=user_id,
            message="Expired token used",
            **extra
        )

    @staticmethod
    def log_rate_limit_exceeded(
        ip_address: str,
        endpoint: str,
        limit: int,
        **extra
    ):
        SecurityLogger.log_event(
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            SecurityEventLevel.WARNING,
            ip_address=ip_address,
            message=f"Rate limit exceeded for {endpoint}",
            endpoint=endpoint,
            limit=limit,
            **extra
        )

    @staticmethod
    def log_brute_force_attempt(
        email: str,
        ip_address: str,
        attempts: int,
        **extra
    ):
        SecurityLogger.log_event(
            SecurityEventType.BRUTE_FORCE_ATTEMPT,
            SecurityEventLevel.CRITICAL,
            ip_address=ip_address,
            message="Potential brute force attack detected",
            email=email,
            attempts=attempts,
            **extra
        )

    @staticmethod
    def log_unauthorized_access(
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource: str = "",
        **extra
    ):
        SecurityLogger.log_event(
            SecurityEventType.UNAUTHORIZED_ACCESS,
            SecurityEventLevel.ERROR,
            user_id=user_id,
            ip_address=ip_address,
            message=f"Unauthorized access attempt to {resource}",
            resource=resource,
            **extra
        )

    @staticmethod
    def log_permission_denied(
        user_id: str,
        ip_address: Optional[str] = None,
        required_permission: str = "",
        resource: str = "",
        **extra
    ):
        SecurityLogger.log_event(
            SecurityEventType.PERMISSION_DENIED,
            SecurityEventLevel.WARNING,
            user_id=user_id,
            ip_address=ip_address,
            message=f"Permission denied for {resource}",
            required_permission=required_permission,
            resource=resource,
            **extra
        )

    @staticmethod
    def log_csp_violation(
        ip_address: str,
        blocked_uri: str,
        violated_directive: str,
        document_uri: str = "",
        **extra
    ):
        SecurityLogger.log_event(
            SecurityEventType.CSP_VIOLATION,
            SecurityEventLevel.WARNING,
            ip_address=ip_address,
            message=f"CSP violation: {violated_directive} blocked {blocked_uri}",
            blocked_uri=blocked_uri,
            violated_directive=violated_directive,
            document_uri=document_uri,
            **extra
        )
