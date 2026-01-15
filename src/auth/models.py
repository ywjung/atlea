"""Authentication data models

Pydantic models for user authentication, registration, and session management.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum
import re
from .password_policy import validate_password_strength


class UserCreate(BaseModel):
    """회원가입 요청"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    username: str = Field(..., min_length=2, max_length=50)
    captcha_id: Optional[str] = None
    captcha_answer: Optional[str] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """비밀번호 강도 검증"""
        return validate_password_strength(v)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """사용자명 검증"""
        if not re.match(r'^[a-zA-Z0-9가-힣_]+$', v):
            raise ValueError('사용자명은 영문, 숫자, 한글, 언더스코어만 가능합니다')
        return v


class UserLogin(BaseModel):
    """로그인 요청"""
    email: EmailStr
    password: str
    captcha_id: Optional[str] = None
    captcha_answer: Optional[str] = None
    totp_token: Optional[str] = None  # 2FA 코드 (6자리)


class User(BaseModel):
    """사용자 모델"""
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z' if v else None
        }
    )

    user_id: str
    email: EmailStr
    username: str
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    role: str = "user"  # user, admin (system-level role)

    # Organization fields
    org_id: str = "default"  # Organization ID (required)
    org_role: str = "user"  # user, org_admin (organization-level role)

    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    totp_secret: Optional[str] = None  # TOTP Secret Key (Base32)


class TokenPair(BaseModel):
    """토큰 쌍"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """로그인 응답"""
    user: User
    tokens: TokenPair
    session_id: str  # 현재 세션 ID (세션 무효화 감지용)


class Session(BaseModel):
    """세션 모델"""
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() + 'Z' if v else None
        }
    )

    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class PasswordReset(BaseModel):
    """비밀번호 재설정 요청"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """비밀번호 재설정 확인"""
    token: str
    new_password: str = Field(..., min_length=8)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """비밀번호 강도 검증"""
        return validate_password_strength(v)


class PasswordResetOTP(BaseModel):
    """OTP 기반 비밀번호 재설정"""
    email: str
    otp_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """비밀번호 강도 검증"""
        return validate_password_strength(v)

    @field_validator('otp_code')
    @classmethod
    def validate_otp_code(cls, v: str) -> str:
        """OTP 코드는 6자리 숫자여야 함"""
        if not v.isdigit():
            raise ValueError("OTP 코드는 숫자만 입력 가능합니다")
        if len(v) != 6:
            raise ValueError("OTP 코드는 6자리여야 합니다")
        return v


class ProfileUpdate(BaseModel):
    """프로필 업데이트"""
    username: Optional[str] = Field(None, min_length=2, max_length=50)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        """사용자명 검증"""
        if v is not None and not re.match(r'^[a-zA-Z0-9가-힣_]+$', v):
            raise ValueError('사용자명은 영문, 숫자, 한글, 언더스코어만 가능합니다')
        return v


class SystemSettings(BaseModel):
    """시스템 설정"""
    inactivity_timeout: int = Field(
        default=30,
        ge=5,
        le=480,
        description="비활성 타임아웃 (분): 5-480분"
    )
    warning_time: int = Field(
        default=5,
        ge=1,
        le=60,
        description="경고 시간 (분): 1-60분"
    )
    check_interval: int = Field(
        default=1,
        ge=1,
        le=10,
        description="체크 간격 (분): 1-10분"
    )

    @field_validator('warning_time')
    @classmethod
    def validate_warning_time(cls, v: int, info) -> int:
        """경고 시간이 비활성 타임아웃보다 작은지 검증"""
        # inactivity_timeout은 이미 검증됨
        return v

    class Config:
        """Pydantic 설정"""
        json_schema_extra = {
            "example": {
                "inactivity_timeout": 30,
                "warning_time": 5,
                "check_interval": 1
            }
        }


class PasswordChange(BaseModel):
    """비밀번호 변경"""
    old_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """비밀번호 강도 검증"""
        return validate_password_strength(v)


# ============================================================================
# 웹훅 모델
# ============================================================================

class WebhookEvent(str, Enum):
    """웹훅 이벤트 타입"""
    # 인증 이벤트
    AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILED = "AUTH_LOGIN_FAILED"
    AUTH_LOGOUT = "AUTH_LOGOUT"

    # 보안 이벤트
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    BRUTE_FORCE_ATTEMPT = "BRUTE_FORCE_ATTEMPT"
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    TOKEN_INVALID = "TOKEN_INVALID"

    # 시스템 이벤트
    SYSTEM_ERROR = "SYSTEM_ERROR"
    SYSTEM_WARNING = "SYSTEM_WARNING"

    # 작업 완료 이벤트
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"


class WebhookCreate(BaseModel):
    """웹훅 생성 요청"""
    name: str = Field(..., min_length=1, max_length=100, description="웹훅 이름")
    url: str = Field(..., description="웹훅 URL (HTTP/HTTPS)")
    events: List[WebhookEvent] = Field(..., min_items=1, description="구독할 이벤트 목록")
    secret: Optional[str] = Field(None, min_length=10, description="HMAC 서명용 비밀키")
    is_active: bool = Field(True, description="활성화 여부")
    retry_count: int = Field(3, ge=0, le=10, description="재시도 횟수")
    timeout_seconds: int = Field(30, ge=1, le=120, description="타임아웃 (초)")

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """URL 검증"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL은 http:// 또는 https://로 시작해야 합니다')
        return v


class WebhookUpdate(BaseModel):
    """웹훅 업데이트 요청"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = None
    events: Optional[List[WebhookEvent]] = Field(None, min_items=1)
    secret: Optional[str] = Field(None, min_length=10)
    is_active: Optional[bool] = None
    retry_count: Optional[int] = Field(None, ge=0, le=10)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=120)

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """URL 검증"""
        if v is not None and not v.startswith(('http://', 'https://')):
            raise ValueError('URL은 http:// 또는 https://로 시작해야 합니다')
        return v


class Webhook(BaseModel):
    """웹훅 모델"""
    webhook_id: str
    name: str
    url: str
    events: List[WebhookEvent]
    secret: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: str  # user_id

    # 통계
    total_deliveries: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0
    last_delivery_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None

    retry_count: int = 3
    timeout_seconds: int = 30


class WebhookDelivery(BaseModel):
    """웹훅 전송 기록"""
    delivery_id: str
    webhook_id: str
    event_type: WebhookEvent
    payload: dict
    status: str  # pending, success, failed
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    delivered_at: Optional[datetime] = None
    retry_count: int = 0


class WebhookTestRequest(BaseModel):
    """웹훅 테스트 요청"""
    event_type: WebhookEvent = Field(WebhookEvent.AUTH_LOGIN_SUCCESS, description="테스트할 이벤트 타입")
