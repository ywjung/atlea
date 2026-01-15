"""Security Event Logger

보안 관련 이벤트를 체계적으로 로깅합니다.
민감한 정보는 로깅하지 않으며, 감사(audit) 로그를 생성합니다.
"""

from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger
import json
import asyncio
from redis import Redis


class SecurityEventType:
    """보안 이벤트 타입"""

    # 인증 이벤트
    LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    LOGIN_FAILED = "AUTH_LOGIN_FAILED"
    LOGOUT = "AUTH_LOGOUT"

    # 계정 관리
    USER_REGISTERED = "ACCOUNT_REGISTERED"
    USER_DELETED = "ACCOUNT_DELETED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED"

    # 토큰 관련
    TOKEN_ISSUED = "TOKEN_ISSUED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"

    # 보안 위협
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    BRUTE_FORCE_ATTEMPT = "BRUTE_FORCE_ATTEMPT"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"

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

    # 전역 Redis 인스턴스 (웹훅 트리거용)
    _redis: Optional[Redis] = None

    @classmethod
    def set_redis(cls, redis: Redis):
        """Redis 인스턴스 설정

        Args:
            redis: Redis 클라이언트
        """
        cls._redis = redis

    @staticmethod
    def _sanitize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """민감한 정보 제거

        Args:
            data: 로깅할 데이터

        Returns:
            민감한 정보가 제거된 데이터
        """
        # 절대 로깅하지 말아야 할 필드
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
            # 민감한 필드는 마스킹
            if key.lower() in sensitive_fields:
                sanitized[key] = "***REDACTED***"
            # 이메일은 부분 마스킹
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
        """보안 이벤트 로깅 (Redis + 파일 하이브리드)

        Args:
            event_type: 이벤트 타입 (SecurityEventType 상수 사용)
            level: 로그 레벨 (SecurityEventLevel 상수 사용)
            user_id: 사용자 ID
            ip_address: IP 주소
            message: 추가 메시지
            **extra_data: 추가 데이터 (민감한 정보는 자동 제거됨)
        """
        # 민감한 정보 제거
        sanitized_data = cls._sanitize_data(extra_data)

        # 보안 이벤트 데이터 구성
        event_data = {
            "timestamp": datetime.utcnow().isoformat() + 'Z',  # UTC with Z suffix for proper timezone handling
            "event_type": event_type,
            "level": level,
            "user_id": user_id or "anonymous",
            "ip_address": ip_address or "unknown",
            "message": message or "",
            **sanitized_data
        }

        # 1. 파일 로깅 (장기 보관 및 감사)
        log_message = f"SECURITY_EVENT: {json.dumps(event_data, ensure_ascii=False)}"

        # 레벨에 따라 적절한 로깅
        if level == SecurityEventLevel.CRITICAL:
            logger.critical(log_message)
        elif level == SecurityEventLevel.ERROR:
            logger.error(log_message)
        elif level == SecurityEventLevel.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)

        # 2. Redis 저장 (빠른 조회, 최근 7일)
        if cls._redis is not None:
            try:
                # Redis 저장 (동기)
                cls._store_to_redis(event_data)
            except Exception as e:
                logger.error(f"Failed to store to Redis: {e}")

        # 3. 웹훅 트리거 (비동기 - 백그라운드에서 실행)
        if cls._redis is not None:
            try:
                # WebhookEvent enum 값과 매핑
                from .models import WebhookEvent

                # 이벤트 타입을 WebhookEvent로 변환
                try:
                    webhook_event = WebhookEvent(event_type)

                    # 비동기 태스크로 웹훅 트리거 (블로킹하지 않음)
                    asyncio.create_task(cls._trigger_webhooks(webhook_event, event_data))
                except ValueError:
                    # WebhookEvent에 없는 이벤트 타입은 무시
                    pass
            except Exception as e:
                logger.error(f"Failed to trigger webhooks: {e}")

        # 4. 실시간 알림 전송 (WebSocket)
        try:
            from .alert_system import alert_manager
            asyncio.create_task(alert_manager.send_alert(event_data))
        except Exception as e:
            logger.error(f"Failed to send real-time alert: {e}")

    @classmethod
    def _store_to_redis(cls, event_data: Dict[str, Any]):
        """Redis에 보안 로그 저장 (동기)

        Args:
            event_data: 보안 이벤트 데이터
        """
        try:
            import time

            # Redis ZSET에 저장 (타임스탬프 기반 정렬)
            # 키 형식: security_logs:{level}
            key = f"security_logs:{event_data['level']}"
            score = time.time()  # Unix timestamp for scoring

            # JSON 직렬화
            log_json = json.dumps(event_data, ensure_ascii=False)

            # ZSET에 추가
            cls._redis.zadd(key, {log_json: score})

            # 전체 보안 로그 키 (레벨 무관)
            all_key = "security_logs:all"
            cls._redis.zadd(all_key, {log_json: score})

            # 7일 이상 된 로그 자동 삭제
            cutoff_score = score - (7 * 24 * 60 * 60)  # 7 days ago
            cls._redis.zremrangebyscore(key, 0, cutoff_score)
            cls._redis.zremrangebyscore(all_key, 0, cutoff_score)

        except Exception as e:
            logger.error(f"Redis storage failed: {e}")

    @classmethod
    async def _trigger_webhooks(cls, event: 'WebhookEvent', payload: Dict[str, Any]):
        """웹훅 트리거 (비동기)

        Args:
            event: 웹훅 이벤트
            payload: 페이로드 데이터
        """
        try:
            from .webhook_service import WebhookService

            webhook_service = WebhookService(cls._redis)
            await webhook_service.trigger_event(event, payload)

        except Exception as e:
            logger.error(f"Webhook trigger failed: {e}")

    # 편의 메서드들

    @staticmethod
    def log_login_success(user_id: str, ip_address: Optional[str] = None, **extra):
        """로그인 성공 로깅"""
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
        """로그인 실패 로깅"""
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
        """로그아웃 로깅"""
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
        """회원가입 로깅"""
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
        """계정 잠금 로깅"""
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
        """계정 잠금 해제 로깅"""
        SecurityLogger.log_event(
            SecurityEventType.ACCOUNT_UNLOCKED,
            SecurityEventLevel.INFO,
            user_id=user_id,
            message="Account unlocked",
            **extra
        )

    @staticmethod
    def log_token_issued(user_id: str, token_type: str = "access", **extra):
        """토큰 발급 로깅"""
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
        """유효하지 않은 토큰 로깅"""
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
        """만료된 토큰 로깅"""
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
        """Rate limit 초과 로깅"""
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
        """Brute force 공격 시도 로깅"""
        SecurityLogger.log_event(
            SecurityEventType.BRUTE_FORCE_ATTEMPT,
            SecurityEventLevel.CRITICAL,
            ip_address=ip_address,
            message=f"Potential brute force attack detected",
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
        """무단 접근 시도 로깅"""
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
        """권한 부족 로깅"""
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
