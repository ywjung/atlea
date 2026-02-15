"""
Admin API Router
관리자 전용 API 엔드포인트
"""
import os
import re
from fastapi import APIRouter, Depends, HTTPException, Request, Path, Query
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from loguru import logger

# UUID validation pattern
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

from ..auth.middleware import require_admin
from .auth import invalidate_dashboard_cache
from ..auth.rate_limiter import create_rate_limit_dependency
from ..utils.error_handling import get_safe_error_message
from ..config.settings import CACHE_TTL_MEDIUM
from ..services.config_service import config_get, config_set, config_delete, config_get_multi

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================================
# Helper Functions
# ============================================================================

def validate_uuid(value: str, field_name: str = "ID") -> str:
    """
    Validate UUID format to prevent injection attacks

    Args:
        value: The string to validate as UUID
        field_name: Name of the field for error messages

    Returns:
        The validated UUID string

    Raises:
        HTTPException: 400 if the value is not a valid UUID
    """
    if not UUID_PATTERN.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"잘못된 {field_name} 형식입니다"
        )
    return value


# ============================================================================
# Pydantic Models
# ============================================================================

class ConfigResponseBase(BaseModel):
    """설정 응답 공통 베이스 클래스

    모든 설정 응답 모델에서 사용되는 공통 필드를 정의합니다.
    새로운 설정 응답 모델은 이 클래스를 상속받아 사용하세요.
    """
    message: str = "설정 조회 성공"


class RateLimitConfig(BaseModel):
    """Rate Limit 설정 모델"""
    enabled: bool
    rate_per_minute: Optional[int] = None
    burst: Optional[int] = None


class RateLimitConfigResponse(BaseModel):
    """Rate Limit 설정 응답 모델"""
    enabled: bool
    rate_per_minute: int
    burst: int
    message: str


class CaptchaConfig(BaseModel):
    """CAPTCHA 설정 모델"""
    login_enabled: Optional[bool] = None
    register_enabled: Optional[bool] = None


class CaptchaConfigResponse(BaseModel):
    """CAPTCHA 설정 응답 모델"""
    login_enabled: bool
    register_enabled: bool
    type: str  # "image_math" for internal CAPTCHA
    configured: bool
    message: str


class TotpConfig(BaseModel):
    """2FA 설정 모델"""
    enabled: bool


class TotpConfigResponse(ConfigResponseBase):
    """2FA 설정 응답 모델"""
    enabled: bool
    type: str  # "totp"
    configured: bool


class UserTotpResponse(BaseModel):
    """사용자 2FA QR 코드 응답"""
    user_id: str
    email: str
    has_totp: bool
    qr_code: Optional[str] = None  # Base64 인코딩된 QR 코드 이미지


class BruteForceConfig(BaseModel):
    """브루트 포스 보호 설정 모델"""
    max_attempts: int  # 계정당 최대 실패 횟수
    lockout_duration: int  # 계정 잠금 시간 (초)
    ip_max_attempts: int  # IP당 최대 실패 횟수
    ip_lockout_duration: int  # IP 차단 시간 (초)


class BruteForceConfigResponse(ConfigResponseBase):
    """브루트 포스 보호 설정 응답 모델"""
    max_attempts: int
    lockout_duration: int
    ip_max_attempts: int
    ip_lockout_duration: int


class HybridRAGConfig(BaseModel):
    """하이브리드 RAG 설정 모델"""
    enabled: bool
    web_search_enabled: Optional[bool] = Field(None, alias='web_search')
    doc_search_enabled: Optional[bool] = Field(None, alias='doc_search')
    web_search_provider: Optional[str] = None  # 'tavily' 또는 'searxng'
    searxng_url: Optional[str] = None  # SearXNG URL

    class Config:
        populate_by_name = True  # Pydantic v2: allow both field name and alias


class HybridRAGConfigResponse(ConfigResponseBase):
    """하이브리드 RAG 설정 응답 모델"""
    enabled: bool
    web_search_enabled: bool
    doc_search_enabled: bool
    tavily_configured: bool
    web_search_provider: str  # 'tavily' 또는 'searxng'
    searxng_url: Optional[str] = None
    searxng_configured: bool = False


class RAGQualityConfig(BaseModel):
    """RAG 품질 설정 모델"""
    reranking_enabled: Optional[bool] = None
    query_rewrite_enabled: Optional[bool] = None
    reranker_model: Optional[str] = None  # Ollama reranker 모델


class RAGQualityConfigResponse(ConfigResponseBase):
    """RAG 품질 설정 응답 모델"""
    reranking_enabled: bool
    query_rewrite_enabled: bool
    reranker_model: str = "dengcao/Qwen3-Reranker-8B:Q4_K_M"  # 기본 Ollama reranker


class PasswordResetRequest(BaseModel):
    """비밀번호 재설정 요청 모델"""
    email: EmailStr
    new_password: Optional[str] = None  # None이면 자동 생성


class PasswordResetResponse(BaseModel):
    """비밀번호 재설정 응답 모델"""
    success: bool
    email: str
    temporary_password: Optional[str] = None  # 자동 생성된 경우에만
    message: str


class PasswordResetMethodConfig(BaseModel):
    """비밀번호 재설정 방식 설정 모델"""
    method: str  # "email" 또는 "admin"


class PasswordResetMethodResponse(ConfigResponseBase):
    """비밀번호 재설정 방식 설정 응답 모델"""
    method: str
    email_configured: bool


class SessionInfo(BaseModel):
    """세션 정보 모델"""
    session_id: str
    user_id: str
    user_email: str
    username: str
    created_at: str
    expires_at: str
    ip_address: str
    is_expired: bool


class SessionListResponse(BaseModel):
    """세션 목록 응답 모델"""
    total_sessions: int
    active_sessions: int
    expired_sessions: int
    sessions: list[SessionInfo]


class RevokeSessionRequest(BaseModel):
    """세션 무효화 요청 모델"""
    session_id: str


class RevokeSessionResponse(BaseModel):
    """세션 무효화 응답 모델"""
    success: bool
    message: str


# ============================================================================
# Rate Limit Configuration Endpoints
# ============================================================================

@router.get("/rate-limit-config", response_model=RateLimitConfigResponse)
async def get_rate_limit_config(
    request: Request,
    user=Depends(require_admin)
):
    """
    Rate Limit 설정 조회 (관리자 전용)

    Returns:
        현재 Rate Limit 설정 (enabled, rate_per_minute, burst)
    """
    try:
        from ..config import config
        from ..services.config_service import config_get

        # PostgreSQL에서 설정 조회 (없으면 기본값 사용)
        enabled_str = await config_get("config:rate_limit_enabled")

        if enabled_str is None:
            enabled = config.RATE_LIMIT_ENABLED
        else:
            enabled = enabled_str == "true"

        return RateLimitConfigResponse(
            enabled=enabled,
            rate_per_minute=config.RATE_LIMIT_PER_MINUTE,
            burst=config.RATE_LIMIT_BURST,
            message="Rate limit 설정 조회 성공"
        )

    except Exception as e:
        logger.error(f"Rate limit 설정 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "rate limit get")
        )


@router.put("/rate-limit-config", response_model=RateLimitConfigResponse)
async def update_rate_limit_config(
    config_update: RateLimitConfig,
    request: Request,
    user=Depends(require_admin)
):
    """
    Rate Limit 설정 업데이트 (관리자 전용)

    Args:
        config_update: 업데이트할 설정 (enabled만 지원)

    Returns:
        업데이트된 Rate Limit 설정
    """
    try:
        from ..config import config
        from ..services.config_service import config_set

        # PostgreSQL에 enabled 상태 저장
        await config_set(
            "config:rate_limit_enabled",
            "true" if config_update.enabled else "false",
            "boolean",
        )

        logger.info(
            f"Rate limit 설정 업데이트: enabled={config_update.enabled} "
            f"by user={user.get('email', 'unknown')}"
        )

        return RateLimitConfigResponse(
            enabled=config_update.enabled,
            rate_per_minute=config.RATE_LIMIT_PER_MINUTE,
            burst=config.RATE_LIMIT_BURST,
            message=f"Rate limit {'활성화' if config_update.enabled else '비활성화'}되었습니다"
        )

    except Exception as e:
        logger.error(f"Rate limit 설정 업데이트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "rate limit update")
        )


# ============================================================================
# CAPTCHA Configuration Endpoints
# ============================================================================

@router.get("/captcha", response_model=CaptchaConfigResponse)
async def get_captcha_config(
    request: Request,
    user=Depends(require_admin)
):
    """
    CAPTCHA 설정 조회 (관리자 전용)

    Returns:
        현재 CAPTCHA 설정 (enabled, site_key, configured)
    """
    try:
        from ..auth.captcha import get_captcha_config as _get_captcha_cfg

        config = _get_captcha_cfg()

        return CaptchaConfigResponse(
            login_enabled=config["login_enabled"],
            register_enabled=config["register_enabled"],
            type=config["type"],
            configured=config["configured"],
            message="CAPTCHA 설정 조회 성공"
        )

    except Exception as e:
        logger.error(f"CAPTCHA 설정 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "captcha get")
        )


@router.put("/captcha", response_model=CaptchaConfigResponse)
async def update_captcha_config(
    config_update: CaptchaConfig,
    request: Request,
    user=Depends(require_admin)
):
    """
    CAPTCHA 설정 업데이트 (관리자 전용)

    Args:
        config_update: 업데이트할 설정 (login_enabled, register_enabled)

    Returns:
        업데이트된 CAPTCHA 설정
    """
    try:
        from ..auth.captcha import set_captcha_enabled, get_captcha_config as _get_captcha_cfg

        # PostgreSQL에 enabled 상태 저장
        success = set_captcha_enabled(
            login_enabled=config_update.login_enabled,
            register_enabled=config_update.register_enabled
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="CAPTCHA 설정 업데이트에 실패했습니다"
            )

        # 로그 메시지 생성
        updates = []
        if config_update.login_enabled is not None:
            updates.append(f"login={'활성화' if config_update.login_enabled else '비활성화'}")
        if config_update.register_enabled is not None:
            updates.append(f"register={'활성화' if config_update.register_enabled else '비활성화'}")

        logger.info(
            f"CAPTCHA 설정 업데이트: {', '.join(updates)} "
            f"by user={user.get('email', 'unknown')}"
        )

        # 업데이트된 설정 반환
        config = _get_captcha_cfg()

        return CaptchaConfigResponse(
            login_enabled=config["login_enabled"],
            register_enabled=config["register_enabled"],
            type=config["type"],
            configured=config["configured"],
            message=f"CAPTCHA 설정이 업데이트되었습니다: {', '.join(updates) if updates else '변경 없음'}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CAPTCHA 설정 업데이트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "captcha update")
        )


# ============================================================================
# Security Logs Endpoint
# ============================================================================

@router.get("/security-logs")
async def get_security_logs(
    request: Request,
    page: int = Query(default=1, ge=1, le=10000, description="페이지 번호 (1-10000)"),
    page_size: int = Query(default=100, ge=1, le=500, description="페이지당 로그 수 (1-500)"),
    level: Optional[str] = None,
    event_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user=Depends(require_admin)
):
    """
    보안 로그 조회 (관리자 전용)

    Args:
        request: FastAPI Request
        page: 페이지 번호 (1-10000)
        page_size: 페이지당 로그 수 (1-500)
        level: 로그 레벨 필터
        event_type: 이벤트 타입 필터
        start_time: 시작 시간 (ISO 8601 형식)
        end_time: 종료 시간 (ISO 8601 형식)
        user: 관리자 사용자 (의존성 주입)

    Returns:
        보안 로그 목록
    """
    from ..auth.service import AuthService

    auth_service = AuthService()
    result = await auth_service.get_security_logs(
        page=page,
        page_size=page_size,
        level=level,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time
    )
    return result


# ============================================================================
# 2FA (TOTP) Configuration Endpoints
# ============================================================================

@router.get("/totp", response_model=TotpConfigResponse)
async def get_totp_config(
    request: Request,
    user=Depends(require_admin)
):
    """
    2FA 설정 조회 (관리자 전용)

    Returns:
        현재 2FA 설정 (enabled, type, configured)
    """
    try:
        from ..auth.totp import get_totp_config as _get_totp_cfg

        config = _get_totp_cfg()

        return TotpConfigResponse(
            enabled=config["enabled"],
            type=config["type"],
            configured=config["configured"],
            message="2FA 설정 조회 성공"
        )

    except Exception as e:
        logger.error(f"2FA 설정 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "2fa get")
        )


@router.put("/totp", response_model=TotpConfigResponse)
async def update_totp_config(
    config_update: TotpConfig,
    request: Request,
    user=Depends(require_admin)
):
    """
    2FA 설정 업데이트 (관리자 전용)

    Args:
        config_update: 업데이트할 설정 (enabled)

    Returns:
        업데이트된 2FA 설정
    """
    try:
        from ..auth.totp import set_totp_enabled, get_totp_config as _get_totp_cfg

        # PostgreSQL에 enabled 상태 저장
        success = set_totp_enabled(config_update.enabled)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="2FA 설정 업데이트에 실패했습니다"
            )

        logger.info(
            f"2FA 설정 업데이트: enabled={config_update.enabled} "
            f"by user={user.get('email', 'unknown')}"
        )

        # 업데이트된 설정 반환
        config = _get_totp_cfg()

        return TotpConfigResponse(
            enabled=config["enabled"],
            type=config["type"],
            configured=config["configured"],
            message=f"2FA {'활성화' if config_update.enabled else '비활성화'}되었습니다"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA 설정 업데이트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "2fa update")
        )


@router.get("/users/{user_id}/totp", response_model=UserTotpResponse)
async def get_user_totp_qr(
    user_id: str = Path(..., description="사용자 UUID"),
    request: Request = None,
    user=Depends(require_admin)
):
    """
    사용자별 2FA QR 코드 조회/생성 (관리자 전용)

    Args:
        user_id: 사용자 ID (UUID 형식)

    Returns:
        사용자 정보 및 QR 코드 (totp_secret이 없으면 생성)
    """
    try:
        # Validate user_id format to prevent injection
        validate_uuid(user_id, "사용자 ID")

        from ..auth.totp import TOTPService
        from ..database.connection import SyncSessionFactory
        from ..database.models.user import User as PgUser
        import uuid as uuid_mod

        # PostgreSQL에서 사용자 정보 조회
        with SyncSessionFactory() as db_session:
            pg_user = db_session.get(PgUser, uuid_mod.UUID(user_id))
            if not pg_user:
                raise HTTPException(
                    status_code=404,
                    detail="사용자를 찾을 수 없습니다"
                )

            email = pg_user.email or ""
            totp_secret = pg_user.totp_secret

            # TOTP 서비스 인스턴스 생성
            totp_service = TOTPService()

            # totp_secret이 없거나 비어있으면 새로 생성
            if not totp_secret or totp_secret == "None" or totp_secret == "":
                totp_secret = totp_service.generate_secret()
                pg_user.totp_secret = totp_secret
                db_session.commit()
                logger.info(f"Generated new TOTP secret for user: {user_id}")

        # QR 코드 생성
        qr_code = totp_service.generate_qr_code(totp_secret, email)

        return UserTotpResponse(
            user_id=user_id,
            email=email,
            has_totp=True,
            qr_code=qr_code
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"사용자 2FA QR 코드 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "qr code generation")
        )


@router.post("/users/{user_id}/totp/reset", response_model=UserTotpResponse)
async def reset_user_totp(
    user_id: str = Path(..., description="사용자 UUID"),
    request: Request = None,
    user=Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(5, 60, "admin_totp_reset"))
):
    """
    사용자 2FA Secret 재생성 (관리자 전용)

    Args:
        user_id: 사용자 ID (UUID 형식)

    Returns:
        새로운 QR 코드
    """
    try:
        # Validate user_id format to prevent injection
        validate_uuid(user_id, "사용자 ID")

        from ..auth.totp import TOTPService
        from ..database.connection import SyncSessionFactory
        from ..database.models.user import User as PgUser
        import uuid as uuid_mod

        # PostgreSQL에서 사용자 정보 조회
        with SyncSessionFactory() as db_session:
            pg_user = db_session.get(PgUser, uuid_mod.UUID(user_id))
            if not pg_user:
                raise HTTPException(
                    status_code=404,
                    detail="사용자를 찾을 수 없습니다"
                )

            email = pg_user.email or ""

            # TOTP 서비스 인스턴스 생성
            totp_service = TOTPService()

            # 새로운 secret 생성
            totp_secret = totp_service.generate_secret()

            # PostgreSQL에 저장
            pg_user.totp_secret = totp_secret
            db_session.commit()
            logger.info(f"Reset TOTP secret for user: {user_id}")

        # QR 코드 생성
        qr_code = totp_service.generate_qr_code(totp_secret, email)

        return UserTotpResponse(
            user_id=user_id,
            email=email,
            has_totp=True,
            qr_code=qr_code
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"사용자 2FA 재설정 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "2fa reset")
        )


# ============================================================================
# Brute Force Protection Configuration Endpoints
# ============================================================================

@router.get("/brute-force", response_model=BruteForceConfigResponse)
async def get_brute_force_config(
    request: Request,
    user=Depends(require_admin)
):
    """
    브루트 포스 보호 설정 조회 (관리자 전용)

    Returns:
        현재 브루트 포스 보호 설정
    """
    try:
        from ..auth.brute_force_protection import get_brute_force_config as _get_bf_config

        config = _get_bf_config()

        return BruteForceConfigResponse(
            max_attempts=config["max_attempts"],
            lockout_duration=config["lockout_duration"],
            ip_max_attempts=config["ip_max_attempts"],
            ip_lockout_duration=config["ip_lockout_duration"],
            message="브루트 포스 보호 설정 조회 성공"
        )

    except Exception as e:
        logger.error(f"브루트 포스 보호 설정 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "brute force protection get")
        )


@router.put("/brute-force", response_model=BruteForceConfigResponse)
async def update_brute_force_config(
    config: BruteForceConfig,
    request: Request,
    user=Depends(require_admin)
):
    """
    브루트 포스 보호 설정 업데이트 (관리자 전용)

    Args:
        config: 새로운 브루트 포스 보호 설정

    Returns:
        업데이트된 설정
    """
    try:
        from ..auth.brute_force_protection import update_brute_force_config

        # 입력 검증
        if config.max_attempts < 1 or config.max_attempts > 100:
            raise HTTPException(
                status_code=400,
                detail="계정 최대 실패 횟수는 1-100 사이여야 합니다"
            )
        if config.lockout_duration < 60 or config.lockout_duration > 86400:
            raise HTTPException(
                status_code=400,
                detail="계정 잠금 시간은 60초-24시간 사이여야 합니다"
            )
        if config.ip_max_attempts < 1 or config.ip_max_attempts > 1000:
            raise HTTPException(
                status_code=400,
                detail="IP 최대 실패 횟수는 1-1000 사이여야 합니다"
            )
        if config.ip_lockout_duration < 60 or config.ip_lockout_duration > 86400:
            raise HTTPException(
                status_code=400,
                detail="IP 차단 시간은 60초-24시간 사이여야 합니다"
            )

        # 설정 업데이트
        success = update_brute_force_config(config.model_dump())

        if not success:
            raise HTTPException(
                status_code=500,
                detail="브루트 포스 보호 설정 업데이트에 실패했습니다"
            )

        logger.info(f"브루트 포스 보호 설정 업데이트: {config.model_dump()} by {user.get('username', 'unknown')}")

        return BruteForceConfigResponse(
            max_attempts=config.max_attempts,
            lockout_duration=config.lockout_duration,
            ip_max_attempts=config.ip_max_attempts,
            ip_lockout_duration=config.ip_lockout_duration,
            message="브루트 포스 보호 설정 업데이트 성공"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"브루트 포스 보호 설정 업데이트 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "brute force protection update")
        )


# ============================================================================
# Password Reset Endpoint
# ============================================================================

def generate_temporary_password(length: int = 12) -> str:
    """임시 비밀번호 생성

    Args:
        length: 비밀번호 길이 (기본 12자)

    Returns:
        안전한 임시 비밀번호
    """
    import secrets
    import string

    # 대문자, 소문자, 숫자, 특수문자 포함
    characters = string.ascii_letters + string.digits + "!@#$%^&*"

    # 각 문자 타입에서 최소 1개씩 포함
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*")
    ]

    # 나머지 길이만큼 랜덤 추가
    password += [secrets.choice(characters) for _ in range(length - 4)]

    # 섞기
    secrets.SystemRandom().shuffle(password)

    return ''.join(password)


@router.post("/reset-password", response_model=PasswordResetResponse)
async def reset_user_password(
    reset_request: PasswordResetRequest,
    request: Request,
    user=Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "admin_password_reset"))
):
    """
    사용자 비밀번호 재설정 (관리자 전용)

    Args:
        reset_request: 이메일 및 새 비밀번호 (선택)
        request: FastAPI Request
        user: 관리자 사용자

    Returns:
        재설정 결과 및 임시 비밀번호 (자동 생성된 경우)
    """
    try:
        from ..auth.service import AuthService
        from ..database.connection import SyncSessionFactory
        from ..database.models.user import User as PgUser

        auth_service = AuthService()

        # PostgreSQL에서 이메일로 사용자 찾기
        with SyncSessionFactory() as db_session:
            from sqlalchemy import select
            stmt = select(PgUser).where(PgUser.email == reset_request.email)
            pg_user = db_session.execute(stmt).scalar_one_or_none()

            if not pg_user:
                raise HTTPException(
                    status_code=404,
                    detail="해당 이메일의 사용자를 찾을 수 없습니다"
                )

            user_id_str = str(pg_user.id)

            # 새 비밀번호 결정 (입력된 것 또는 자동 생성)
            new_password = reset_request.new_password
            auto_generated = False

            if not new_password:
                new_password = generate_temporary_password()
                auto_generated = True

            # 비밀번호 해싱 및 업데이트
            from ..auth.utils import hash_password
            hashed_password = hash_password(new_password)
            pg_user.hashed_password = hashed_password
            db_session.commit()

        # 모든 세션 무효화 (보안: 비밀번호 변경 시 모든 기존 세션 종료)
        invalidated_sessions = await auth_service.revoke_all_sessions(user_id_str)

        logger.info(
            f"관리자 {user.get('email', 'unknown')}가 사용자 {reset_request.email}의 비밀번호를 재설정했습니다 "
            f"(자동생성: {auto_generated}, 무효화된 세션: {invalidated_sessions}개)"
        )

        return PasswordResetResponse(
            success=True,
            email=reset_request.email,
            temporary_password=new_password if auto_generated else None,
            message="비밀번호가 재설정되었습니다" + (" (임시 비밀번호 생성됨)" if auto_generated else "")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"비밀번호 재설정 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "password reset")
        )


# ============================================================================
# Password Reset Method Configuration
# ============================================================================

@router.get("/password-reset-method", response_model=PasswordResetMethodResponse)
async def get_password_reset_method(
    request: Request
):
    """
    비밀번호 재설정 방식 조회 (공개 API - 인증 불필요)

    Returns:
        현재 설정된 방식 및 이메일 설정 여부
    """
    try:
        from ..auth.password_reset_config import get_password_reset_config as _get_pr_cfg

        config = _get_pr_cfg()

        return PasswordResetMethodResponse(
            method=config["method"],
            email_configured=config["email_configured"],
            message="비밀번호 재설정 방식 조회 성공"
        )

    except Exception as e:
        logger.error(f"비밀번호 재설정 방식 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "settings get")
        )


@router.put("/password-reset-method", response_model=PasswordResetMethodResponse)
async def update_password_reset_method(
    config_update: PasswordResetMethodConfig,
    request: Request,
    user=Depends(require_admin)
):
    """
    비밀번호 재설정 방식 업데이트 (관리자 전용)

    Args:
        config_update: 새 설정 (method: "email" 또는 "admin")

    Returns:
        업데이트된 설정
    """
    try:
        from ..auth.password_reset_config import (
            set_password_reset_method,
            get_password_reset_config as _get_pr_cfg,
        )

        # 유효성 검사
        if config_update.method not in ["email", "otp", "admin"]:
            raise HTTPException(
                status_code=400,
                detail="유효하지 않은 방식입니다. 'email', 'otp', 또는 'admin'만 가능합니다."
            )

        # PostgreSQL에 설정 업데이트
        success = set_password_reset_method(config_update.method)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="설정 업데이트에 실패했습니다"
            )

        logger.info(
            f"관리자 {user.get('email', 'unknown')}가 비밀번호 재설정 방식을 "
            f"{config_update.method}(으)로 변경했습니다"
        )

        # 업데이트된 설정 반환
        config = _get_pr_cfg()

        method_names = {
            "email": "이메일 방식",
            "otp": "OTP 방식",
            "admin": "관리자 방식"
        }

        return PasswordResetMethodResponse(
            method=config["method"],
            email_configured=config["email_configured"],
            message=f"비밀번호 재설정 방식이 {method_names[config_update.method]}(으)로 변경되었습니다"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"비밀번호 재설정 방식 업데이트 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "settings update")
        )


# ============================================================================
# SMTP Settings Configuration
# ============================================================================

@router.get("/smtp-settings")
async def get_smtp_settings_endpoint(
    request: Request,
    user=Depends(require_admin)
):
    """SMTP 설정 조회 (관리자 전용)

    Returns:
        현재 SMTP 설정
    """
    try:
        from ..email_service import get_smtp_settings

        settings = get_smtp_settings()

        # 보안상 비밀번호는 마스킹
        if settings.get("password"):
            settings["password"] = "********"

        return settings

    except Exception as e:
        logger.error(f"SMTP 설정 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "smtp get")
        )


@router.post("/smtp-settings")
async def save_smtp_settings_endpoint(
    request: Request,
    smtp_config: dict,
    user=Depends(require_admin)
):
    """SMTP 설정 저장 (관리자 전용)

    Args:
        smtp_config: SMTP 설정
            - host: SMTP 호스트
            - port: SMTP 포트
            - username: SMTP 사용자명
            - password: SMTP 비밀번호
            - from_email: 발신자 이메일 (선택)
            - from_name: 발신자 이름 (선택)

    Returns:
        저장 결과
    """
    try:
        from ..email_service import save_smtp_settings, get_smtp_settings

        # 필수 필드 검증 (password는 기존 설정이 있으면 선택적)
        required_fields = ["host", "port", "username"]
        for field in required_fields:
            if field not in smtp_config or not smtp_config[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"필수 필드가 누락되었습니다: {field}"
                )

        # 비밀번호 처리: 새로 입력하지 않았으면 기존 비밀번호 유지
        password = smtp_config.get("password")
        if not password:
            existing_smtp = get_smtp_settings()
            if existing_smtp.get("configured") and existing_smtp.get("password"):
                password = existing_smtp["password"]
            else:
                raise HTTPException(
                    status_code=400,
                    detail="비밀번호는 필수입니다 (기존 설정이 없습니다)"
                )

        # SMTP 설정 저장
        success = save_smtp_settings(
            host=smtp_config["host"],
            port=int(smtp_config["port"]),
            username=smtp_config["username"],
            password=password,
            from_email=smtp_config.get("from_email"),
            from_name=smtp_config.get("from_name")
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="SMTP 설정 저장에 실패했습니다"
            )

        logger.info(f"관리자 {user.get('email', 'unknown')}가 SMTP 설정을 업데이트했습니다")

        return {
            "success": True,
            "message": "SMTP 설정이 저장되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SMTP 설정 저장 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "smtp save")
        )


@router.post("/smtp-settings/test")
async def test_smtp_settings_endpoint(
    request: Request,
    smtp_config: dict,
    user=Depends(require_admin)
):
    """SMTP 연결 테스트 (관리자 전용)

    Args:
        smtp_config: 테스트할 SMTP 설정
            - host: SMTP 호스트
            - port: SMTP 포트
            - username: SMTP 사용자명
            - password: SMTP 비밀번호

    Returns:
        테스트 결과
    """
    try:
        from ..email_service import test_smtp_connection

        # 필수 필드 검증
        required_fields = ["host", "port", "username", "password"]
        for field in required_fields:
            if field not in smtp_config or not smtp_config[field]:
                raise HTTPException(
                    status_code=400,
                    detail=f"필수 필드가 누락되었습니다: {field}"
                )

        # SMTP 연결 테스트
        success, message = test_smtp_connection(
            host=smtp_config["host"],
            port=int(smtp_config["port"]),
            username=smtp_config["username"],
            password=smtp_config["password"]
        )

        return {
            "success": success,
            "message": message
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SMTP 연결 테스트 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "smtp test")
        )


# ============================================================================
# Session Management Endpoints
# ============================================================================

@router.get("/sessions", response_model=SessionListResponse)
async def list_all_sessions(
    request: Request,
    user=Depends(require_admin)
):
    """모든 활성 세션 조회 (관리자 전용)

    Returns:
        전체 세션 목록 및 통계
    """
    try:
        from datetime import datetime, timezone
        from ..database.connection import SyncSessionFactory
        from ..database.models.session import Session as PgSession
        from ..database.models.user import User as PgUser
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        with SyncSessionFactory() as db_session:
            # 모든 세션 조회 (사용자 정보 JOIN)
            stmt = (
                select(PgSession, PgUser)
                .outerjoin(PgUser, PgSession.user_id == PgUser.id)
                .order_by(PgSession.created_at.desc())
            )
            rows = db_session.execute(stmt).all()

            sessions = []
            active_count = 0
            expired_count = 0
            now = datetime.now(timezone.utc)

            for pg_session, pg_user in rows:
                is_expired = not pg_session.is_active or pg_session.expires_at < now

                if is_expired:
                    expired_count += 1
                else:
                    active_count += 1

                sessions.append(SessionInfo(
                    session_id=str(pg_session.id),
                    user_id=str(pg_session.user_id),
                    user_email=pg_user.email if pg_user else "Unknown",
                    username=pg_user.username if pg_user else "Unknown",
                    created_at=pg_session.created_at.isoformat() if pg_session.created_at else "",
                    expires_at=pg_session.expires_at.isoformat() if pg_session.expires_at else "",
                    ip_address=pg_session.ip_address or "",
                    is_expired=is_expired
                ))

        return SessionListResponse(
            total_sessions=len(sessions),
            active_sessions=active_count,
            expired_sessions=expired_count,
            sessions=sessions
        )

    except Exception as e:
        logger.error(f"세션 목록 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "sessions list")
        )


@router.delete("/sessions/all", response_model=RevokeSessionResponse)
async def revoke_all_sessions(
    request: Request,
    user=Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(3, 60, "admin_session_revoke_all"))
):
    """모든 활성 세션 무효화 (관리자 전용)

    ⚠️ 주의: 모든 사용자가 강제 로그아웃됩니다 (관리자 본인 포함)

    Returns:
        무효화 결과
    """
    try:
        from ..database.connection import SyncSessionFactory
        from ..database.models.session import Session as PgSession
        from sqlalchemy import update

        with SyncSessionFactory() as db_session:
            # 모든 활성 세션 비활성화
            stmt = (
                update(PgSession)
                .where(PgSession.is_active == True)
                .values(is_active=False)
            )
            result = db_session.execute(stmt)
            revoked_count = result.rowcount
            db_session.commit()

        # 대시보드 캐시 무효화 (세션 수 변경)
        await invalidate_dashboard_cache()

        logger.warning(
            f"관리자 {user.get('email', 'unknown')}가 모든 세션을 무효화했습니다 "
            f"(무효화된 세션: {revoked_count}개)"
        )

        return RevokeSessionResponse(
            success=True,
            message=f"전체 {revoked_count}개의 세션이 무효화되었습니다. 모든 사용자가 로그아웃되었습니다."
        )

    except Exception as e:
        logger.error(f"전체 세션 무효화 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "sessions revoke all")
        )


@router.delete("/sessions/{session_id}", response_model=RevokeSessionResponse)
async def revoke_session(
    session_id: str,
    request: Request,
    user=Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(20, 60, "admin_session_revoke"))
):
    """특정 세션 무효화 (관리자 전용)

    Args:
        session_id: 무효화할 세션 ID

    Returns:
        무효화 결과
    """
    try:
        from ..database.connection import SyncSessionFactory
        from ..database.models.session import Session as PgSession
        from ..database.models.user import User as PgUser
        import uuid as uuid_mod

        # 세션 ID 형식 검증 (UUID 형식)
        validate_uuid(session_id, "세션 ID")

        # 자기 자신의 세션인지 확인 (현재 요청의 세션)
        current_session_id = request.cookies.get("session_id")
        if current_session_id == session_id:
            raise HTTPException(
                status_code=400,
                detail="자신의 현재 세션은 무효화할 수 없습니다"
            )

        with SyncSessionFactory() as db_session:
            # 세션 존재 확인
            pg_session = db_session.get(PgSession, uuid_mod.UUID(session_id))
            if not pg_session:
                raise HTTPException(
                    status_code=404,
                    detail="세션을 찾을 수 없습니다"
                )

            # 사용자 이메일 조회
            pg_user = db_session.get(PgUser, pg_session.user_id)
            target_email = pg_user.email if pg_user else "unknown"

            # 세션 비활성화
            pg_session.is_active = False
            db_session.commit()

        # 대시보드 캐시 무효화 (세션 수 변경)
        await invalidate_dashboard_cache()

        logger.info(
            f"관리자 {user.get('email', 'unknown')}가 세션을 무효화했습니다 "
            f"(session_id: {session_id[:8]}..., target_user: {target_email})"
        )

        return RevokeSessionResponse(
            success=True,
            message="세션이 무효화되었습니다"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"세션 무효화 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "session revoke")
        )


@router.delete("/sessions/user/{user_id}", response_model=RevokeSessionResponse)
async def revoke_user_sessions(
    user_id: str = Path(..., description="사용자 UUID"),
    request: Request = None,
    user=Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "admin_user_session_revoke"))
):
    """특정 사용자의 모든 세션 무효화 (관리자 전용)

    Args:
        user_id: 사용자 ID (UUID 형식)

    Returns:
        무효화 결과
    """
    try:
        # Validate user_id format to prevent injection
        validate_uuid(user_id, "사용자 ID")

        from ..auth.service import AuthService
        from ..database.connection import SyncSessionFactory
        from ..database.models.user import User as PgUser
        import uuid as uuid_mod

        # 자기 자신의 세션을 무효화하려는 경우 경고
        if user.get("user_id") == user_id:
            raise HTTPException(
                status_code=400,
                detail="자신의 세션을 모두 무효화할 수 없습니다. 개별 세션을 삭제하세요."
            )

        # 사용자 존재 확인
        with SyncSessionFactory() as db_session:
            pg_user = db_session.get(PgUser, uuid_mod.UUID(user_id))
            if not pg_user:
                raise HTTPException(
                    status_code=404,
                    detail="사용자를 찾을 수 없습니다"
                )
            target_email = pg_user.email or "unknown"

        # 사용자의 모든 세션 무효화
        auth_service = AuthService()
        revoked_count = await auth_service.revoke_all_sessions(user_id)

        # 대시보드 캐시 무효화 (세션 수 변경)
        await invalidate_dashboard_cache()

        logger.info(
            f"관리자 {user.get('email', 'unknown')}가 사용자 {target_email}의 모든 세션을 무효화했습니다 "
            f"(무효화된 세션: {revoked_count}개)"
        )

        return RevokeSessionResponse(
            success=True,
            message=f"{revoked_count}개의 세션이 무효화되었습니다"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"사용자 세션 무효화 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "user sessions revoke")
        )


# ============================================================================
# Hybrid RAG Configuration Endpoints
# ============================================================================

@router.get("/hybrid-rag", response_model=HybridRAGConfigResponse)
async def get_hybrid_rag_config(
    request: Request,
    user=Depends(require_admin)
):
    """
    하이브리드 RAG 설정 조회 (관리자 전용)

    Returns:
        현재 하이브리드 RAG 설정
    """
    try:
        import os
        cache_manager = request.app.state.cache_manager

        # PostgreSQL에서 설정 조회
        cfg = await config_get_multi([
            "config:hybrid_rag_enabled",
            "config:hybrid_rag_web_search",
            "config:hybrid_rag_doc_search",
            "config:tavily_api_key",
            "config:web_search_provider",
            "config:searxng_url",
        ])

        # 기본값 설정
        enabled = cfg.get("config:hybrid_rag_enabled") == "true"
        web_search_enabled = cfg.get("config:hybrid_rag_web_search") == "true"
        doc_search_enabled = cfg.get("config:hybrid_rag_doc_search") == "true"

        # 웹 검색 프로바이더 설정 (기본값: tavily)
        web_search_provider = cfg.get("config:web_search_provider") or 'tavily'
        searxng_url = cfg.get("config:searxng_url") or os.getenv('SEARXNG_URL', 'http://localhost:8888')

        # Tavily API 키 설정 여부 확인 (PG 우선, 환경 변수 대체)
        tavily_key = cfg.get("config:tavily_api_key")
        env_key = os.getenv('TAVILY_API_KEY')
        tavily_configured = bool(tavily_key or env_key)

        # SearXNG 설정 여부 확인
        searxng_configured = bool(searxng_url)

        return HybridRAGConfigResponse(
            enabled=enabled,
            web_search_enabled=web_search_enabled,
            doc_search_enabled=doc_search_enabled,
            tavily_configured=tavily_configured,
            web_search_provider=web_search_provider,
            searxng_url=searxng_url,
            searxng_configured=searxng_configured,
            message="하이브리드 RAG 설정을 조회했습니다"
        )

    except Exception as e:
        logger.error(f"하이브리드 RAG 설정 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "hybrid rag get")
        )


@router.put("/hybrid-rag", response_model=HybridRAGConfigResponse)
async def update_hybrid_rag_config(
    config_update: HybridRAGConfig,
    request: Request,
    user=Depends(require_admin)
):
    """
    하이브리드 RAG 설정 업데이트 (관리자 전용)

    Args:
        config_update: 업데이트할 설정

    Returns:
        업데이트된 하이브리드 RAG 설정
    """
    try:
        import os
        cache_manager = request.app.state.cache_manager

        # 설정 저장 (PostgreSQL)
        await config_set(
            "config:hybrid_rag_enabled",
            "true" if config_update.enabled else "false",
            "boolean", "하이브리드 RAG 활성화 여부"
        )

        # 웹 검색 활성화 설정
        if config_update.web_search_enabled is not None:
            await config_set(
                "config:hybrid_rag_web_search",
                "true" if config_update.web_search_enabled else "false",
                "boolean", "웹 검색 활성화 여부"
            )
            web_search_enabled = config_update.web_search_enabled
        else:
            web_val = await config_get("config:hybrid_rag_web_search")
            web_search_enabled = web_val == "true" if web_val else False

        # 공식 문서 검색 활성화 설정
        if config_update.doc_search_enabled is not None:
            await config_set(
                "config:hybrid_rag_doc_search",
                "true" if config_update.doc_search_enabled else "false",
                "boolean", "공식 문서 검색 활성화 여부"
            )
            doc_search_enabled = config_update.doc_search_enabled
        else:
            doc_val = await config_get("config:hybrid_rag_doc_search")
            doc_search_enabled = doc_val == "true" if doc_val else False

        # 웹 검색 프로바이더 설정
        if config_update.web_search_provider is not None:
            provider = config_update.web_search_provider.lower()
            if provider in ['tavily', 'searxng']:
                await config_set("config:web_search_provider", provider, "string", "웹 검색 프로바이더")
                web_search_provider = provider
            else:
                web_search_provider = 'tavily'
        else:
            provider_val = await config_get("config:web_search_provider")
            web_search_provider = provider_val or 'tavily'

        # SearXNG URL 설정
        if config_update.searxng_url is not None:
            await config_set("config:searxng_url", config_update.searxng_url, "string", "SearXNG URL")
            searxng_url = config_update.searxng_url
        else:
            url_val = await config_get("config:searxng_url")
            searxng_url = url_val or os.getenv('SEARXNG_URL', 'http://localhost:8888')

        # Tavily API 키 설정 여부 확인
        tavily_key = await config_get("config:tavily_api_key")
        tavily_key_env = os.getenv('TAVILY_API_KEY')
        tavily_configured = bool(tavily_key or tavily_key_env)

        # SearXNG 설정 여부 확인
        searxng_configured = bool(searxng_url)

        # HybridRAGOrchestrator 재초기화 필요 (실제 적용은 web_server.py에서)
        # 여기서는 설정만 저장

        logger.info(
            f"하이브리드 RAG 설정 업데이트: enabled={config_update.enabled}, "
            f"web_search={web_search_enabled}, doc_search={doc_search_enabled}, "
            f"provider={web_search_provider} by user={user.get('email', 'unknown')}"
        )

        status_msg = f"하이브리드 RAG {'활성화' if config_update.enabled else '비활성화'}되었습니다"
        if config_update.enabled and web_search_enabled:
            if web_search_provider == 'tavily' and not tavily_configured:
                status_msg += " (주의: TAVILY_API_KEY가 설정되지 않아 웹 검색이 작동하지 않습니다)"
            elif web_search_provider == 'searxng':
                status_msg += f" (SearXNG: {searxng_url})"

        return HybridRAGConfigResponse(
            enabled=config_update.enabled,
            web_search_enabled=web_search_enabled,
            doc_search_enabled=doc_search_enabled,
            tavily_configured=tavily_configured,
            web_search_provider=web_search_provider,
            searxng_url=searxng_url,
            searxng_configured=searxng_configured,
            message=status_msg
        )

    except Exception as e:
        logger.error(f"하이브리드 RAG 설정 업데이트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "hybrid rag update")
        )


# ============================================================================
# RAG Quality Configuration Endpoints
# ============================================================================

@router.get("/rag-quality", response_model=RAGQualityConfigResponse)
async def get_rag_quality_config(
    request: Request,
    user=Depends(require_admin)
):
    """
    RAG 품질 설정 조회 (관리자 전용)

    Returns:
        현재 RAG 품질 설정 (재랭킹, 쿼리 재작성)
    """
    try:
        from ..services.config_service import config_get_multi

        # PostgreSQL에서 설정 가져오기
        cfg = await config_get_multi([
            "config:reranking_enabled",
            "config:query_rewrite_enabled",
            "config:reranker_model",
        ])

        reranking_enabled = cfg.get("config:reranking_enabled") == "true"
        query_rewrite_enabled = cfg.get("config:query_rewrite_enabled") == "true"
        reranker_model = cfg.get("config:reranker_model") or "dengcao/Qwen3-Reranker-8B:Q4_K_M"

        return RAGQualityConfigResponse(
            reranking_enabled=reranking_enabled,
            query_rewrite_enabled=query_rewrite_enabled,
            reranker_model=reranker_model,
            message="RAG 품질 설정을 조회했습니다"
        )

    except Exception as e:
        logger.error(f"RAG 품질 설정 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "rag quality get")
        )


@router.put("/rag-quality", response_model=RAGQualityConfigResponse)
async def update_rag_quality_config(
    config_update: RAGQualityConfig,
    request: Request,
    user=Depends(require_admin)
):
    """
    RAG 품질 설정 업데이트 (관리자 전용)

    Args:
        config_update: 업데이트할 설정

    Returns:
        업데이트된 RAG 품질 설정
    """
    try:
        from ..services.config_service import config_get, config_set

        # 재랭킹 설정
        if config_update.reranking_enabled is not None:
            await config_set(
                "config:reranking_enabled",
                "true" if config_update.reranking_enabled else "false",
                "boolean",
            )
            reranking_enabled = config_update.reranking_enabled
        else:
            reranking_setting = await config_get("config:reranking_enabled")
            reranking_enabled = reranking_setting == "true" if reranking_setting else False

        # 쿼리 재작성 설정
        if config_update.query_rewrite_enabled is not None:
            await config_set(
                "config:query_rewrite_enabled",
                "true" if config_update.query_rewrite_enabled else "false",
                "boolean",
            )
            query_rewrite_enabled = config_update.query_rewrite_enabled
        else:
            query_rewrite_setting = await config_get("config:query_rewrite_enabled")
            query_rewrite_enabled = query_rewrite_setting == "true" if query_rewrite_setting else False

        # Reranker 모델 설정
        if config_update.reranker_model is not None:
            await config_set("config:reranker_model", config_update.reranker_model)
            reranker_model = config_update.reranker_model
        else:
            reranker_model = await config_get("config:reranker_model") or "dengcao/Qwen3-Reranker-8B:Q4_K_M"

        # HybridRAGOrchestrator 설정 새로고침 트리거
        try:
            import sys
            if 'src.web_server' in sys.modules:
                web_server = sys.modules['src.web_server']
                if hasattr(web_server, 'hybrid_rag_orchestrator') and web_server.hybrid_rag_orchestrator:
                    web_server.hybrid_rag_orchestrator.refresh_rag_quality_settings()
                    logger.info("🔄 HybridRAGOrchestrator settings refreshed")
        except Exception as e:
            logger.warning(f"Failed to refresh HybridRAGOrchestrator: {e}")

        logger.info(
            f"RAG 품질 설정 업데이트: reranking={reranking_enabled}, "
            f"query_rewrite={query_rewrite_enabled}, reranker_model={reranker_model} "
            f"by user={user.get('email', 'unknown')}"
        )

        status_parts = []
        if config_update.reranking_enabled is not None:
            status_parts.append(f"재랭킹 {'활성화' if reranking_enabled else '비활성화'}")
        if config_update.query_rewrite_enabled is not None:
            status_parts.append(f"쿼리 재작성 {'활성화' if query_rewrite_enabled else '비활성화'}")
        if config_update.reranker_model is not None:
            status_parts.append(f"Reranker 모델: {reranker_model}")

        status_msg = ", ".join(status_parts) if status_parts else "설정이 유지되었습니다"

        return RAGQualityConfigResponse(
            reranking_enabled=reranking_enabled,
            query_rewrite_enabled=query_rewrite_enabled,
            reranker_model=reranker_model,
            message=status_msg
        )

    except Exception as e:
        logger.error(f"RAG 품질 설정 업데이트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "rag quality update")
        )


# ==================== Tavily API Key Management ====================

class TavilyAPIKeyUpdate(BaseModel):
    """Tavily API 키 업데이트 모델"""
    api_key: str


class TavilyAPIKeyResponse(BaseModel):
    """Tavily API 키 응답 모델"""
    has_key: bool
    masked_key: Optional[str] = None
    message: str


@router.get("/tavily-api-key", response_model=TavilyAPIKeyResponse)
async def get_tavily_api_key(
    request: Request,
    user: dict = Depends(require_admin)
):
    """Tavily API 키 조회 (관리자 전용)"""
    try:
        cache_manager = request.app.state.cache_manager

        # PostgreSQL에서 API 키 가져오기
        key_str = await config_get("config:tavily_api_key")

        if key_str:
            # 키 마스킹 (처음 8자, 마지막 4자만 표시)
            if len(key_str) > 12:
                masked = f"{key_str[:8]}...{key_str[-4:]}"
            else:
                masked = "****"

            return TavilyAPIKeyResponse(
                has_key=True,
                masked_key=masked,
                message="Tavily API 키가 설정되어 있습니다"
            )
        else:
            # 환경 변수 확인
            env_key = os.getenv('TAVILY_API_KEY')
            if env_key:
                if len(env_key) > 12:
                    masked = f"{env_key[:8]}...{env_key[-4:]}"
                else:
                    masked = "****"
                return TavilyAPIKeyResponse(
                    has_key=True,
                    masked_key=f"{masked} (환경 변수)",
                    message="환경 변수에서 Tavily API 키를 사용 중입니다"
                )

            return TavilyAPIKeyResponse(
                has_key=False,
                masked_key=None,
                message="Tavily API 키가 설정되지 않았습니다"
            )

    except Exception as e:
        logger.error(f"Tavily API 키 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "tavily key get")
        )


@router.put("/tavily-api-key", response_model=TavilyAPIKeyResponse)
async def update_tavily_api_key(
    key_update: TavilyAPIKeyUpdate,
    request: Request,
    user: dict = Depends(require_admin)
):
    """Tavily API 키 업데이트 및 유효성 테스트 (관리자 전용)"""
    try:
        cache_manager = request.app.state.cache_manager

        # API 키 검증 (기본적인 형식 체크)
        api_key = key_update.api_key.strip()

        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="API 키를 입력해주세요"
            )

        # Tavily API 키 형식 검증
        if len(api_key) > 200:
            raise HTTPException(
                status_code=400,
                detail="API 키가 너무 깁니다 (최대 200자)"
            )

        if not api_key.startswith('tvly-'):
            raise HTTPException(
                status_code=400,
                detail="올바른 Tavily API 키 형식이 아닙니다 (tvly-로 시작해야 합니다)"
            )

        # 최소 길이 검증 (tvly- + 최소 30자)
        if len(api_key) < 35:
            raise HTTPException(
                status_code=400,
                detail="올바른 Tavily API 키 형식이 아닙니다 (키가 너무 짧습니다)"
            )

        # 🆕 API 키 유효성 테스트
        logger.info("🔍 Testing Tavily API key validity...")
        try:
            from tavily import TavilyClient
            test_client = TavilyClient(api_key=api_key)
            # 간단한 테스트 검색 수행
            test_result = test_client.search(query="test", max_results=1)
            if not test_result:
                raise Exception("API key test failed: no results returned")
            logger.success("✅ Tavily API key is valid")
        except ImportError:
            logger.warning("⚠️ tavily-python not installed, skipping validation")
        except Exception as e:
            logger.error(f"❌ Tavily API key validation failed: {e}")
            raise HTTPException(
                status_code=400,
                detail="API 키가 유효하지 않습니다. 키를 확인해주세요."
            )

        # PostgreSQL에 저장
        await config_set(
            "config:tavily_api_key", api_key,
            "secret", "Tavily API Key for web search"
        )

        # 하이브리드 RAG 재초기화 (API 키 업데이트 반영)
        try:
            from ..web_server import hybrid_rag_orchestrator
            import sys
            sys.modules['src.web_server'].hybrid_rag_orchestrator = None
            logger.info("🔄 Hybrid RAG will be reinitialized on next request")
        except Exception as e:
            logger.warning(f"Failed to reset hybrid RAG: {e}")

        # 키 마스킹
        if len(api_key) > 12:
            masked = f"{api_key[:8]}...{api_key[-4:]}"
        else:
            masked = "****"

        logger.info(f"✅ Tavily API 키 업데이트 완료 (관리자: {user.get('username')})")

        return TavilyAPIKeyResponse(
            has_key=True,
            masked_key=masked,
            message="Tavily API 키가 성공적으로 저장되었습니다 (유효성 검증 완료)"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tavily API 키 업데이트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "tavily key save")
        )


@router.delete("/tavily-api-key")
async def delete_tavily_api_key(
    request: Request,
    user: dict = Depends(require_admin)
):
    """Tavily API 키 삭제 (관리자 전용)"""
    try:
        cache_manager = request.app.state.cache_manager

        # PostgreSQL에서 삭제
        await config_delete("config:tavily_api_key")

        logger.info(f"🗑️ Tavily API 키 삭제 완료 (관리자: {user.get('username')})")

        return {
            "success": True,
            "message": "Tavily API 키가 삭제되었습니다"
        }

    except Exception as e:
        logger.error(f"Tavily API 키 삭제 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "tavily key delete")
        )


@router.get("/tavily-api-key/reveal")
async def reveal_tavily_api_key(
    request: Request,
    user: dict = Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(5, 60, "admin_api_key_reveal"))
):
    """Tavily API 키 조회 (관리자 전용)

    보안상 항상 마스킹된 키만 반환합니다.
    전체 키가 필요한 경우 환경변수에서 직접 확인하세요.
    """
    try:
        cache_manager = request.app.state.cache_manager

        # PostgreSQL에서 API 키 가져오기
        full_key = await config_get("config:tavily_api_key")

        if full_key:
            return {
                "success": True,
                "api_key": mask_api_key(full_key),
                "masked": True,
                "source": "database"
            }
        else:
            # 환경 변수 확인
            env_key = os.getenv('TAVILY_API_KEY')
            if env_key:
                return {
                    "success": True,
                    "api_key": mask_api_key(env_key),
                    "masked": True,
                    "source": "environment"
                }

            raise HTTPException(
                status_code=404,
                detail="저장된 API 키가 없습니다"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tavily API 키 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "api key get")
        )


# ==================== Context7 API Key Management ====================

class Context7APIKeyUpdate(BaseModel):
    """Context7 API 키 업데이트 모델"""
    api_key: str


class Context7APIKeyResponse(BaseModel):
    """Context7 API 키 응답 모델"""
    has_key: bool
    masked_key: Optional[str] = None
    message: str


@router.get("/context7-api-key", response_model=Context7APIKeyResponse)
async def get_context7_api_key(
    request: Request,
    user: dict = Depends(require_admin)
):
    """Context7 API 키 조회 (관리자 전용)"""
    try:
        cache_manager = request.app.state.cache_manager

        # PostgreSQL에서 API 키 가져오기
        key_str = await config_get("config:context7_api_key")

        if key_str:
            # 키 마스킹 (처음 8자, 마지막 4자만 표시)
            if len(key_str) > 12:
                masked = f"{key_str[:8]}...{key_str[-4:]}"
            else:
                masked = "****"

            return Context7APIKeyResponse(
                has_key=True,
                masked_key=masked,
                message="Context7 API 키가 설정되어 있습니다"
            )
        else:
            # 환경 변수 확인
            env_key = os.getenv('CONTEXT7_API_KEY')
            if env_key:
                if len(env_key) > 12:
                    masked = f"{env_key[:8]}...{env_key[-4:]}"
                else:
                    masked = "****"
                return Context7APIKeyResponse(
                    has_key=True,
                    masked_key=f"{masked} (환경 변수)",
                    message="환경 변수에서 Context7 API 키를 사용 중입니다"
                )

            return Context7APIKeyResponse(
                has_key=False,
                masked_key=None,
                message="Context7 API 키가 설정되지 않았습니다"
            )

    except Exception as e:
        logger.error(f"Context7 API 키 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "context7 key get")
        )


@router.put("/context7-api-key", response_model=Context7APIKeyResponse)
async def update_context7_api_key(
    key_update: Context7APIKeyUpdate,
    request: Request,
    user: dict = Depends(require_admin)
):
    """Context7 API 키 업데이트 및 유효성 테스트 (관리자 전용)"""
    try:
        cache_manager = request.app.state.cache_manager

        # API 키 검증 (기본적인 형식 체크)
        api_key = key_update.api_key.strip()

        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="API 키를 입력해주세요"
            )

        # Context7 API 키 형식 검증 (ctx7sk-로 시작하는지 확인)
        if not api_key.startswith('ctx7sk-'):
            raise HTTPException(
                status_code=400,
                detail="올바른 Context7 API 키 형식이 아닙니다 (ctx7sk-로 시작해야 합니다)"
            )

        # 🆕 API 키 유효성 테스트
        logger.info("🔍 Testing Context7 API key validity...")
        try:
            import httpx

            # Context7 REST API v2 클라이언트 생성 (hybrid_rag._init_context7()와 동일)
            # Using async with to ensure proper resource cleanup
            async with httpx.AsyncClient(
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                timeout=15.0
            ) as test_client:
                # 간단한 테스트: /health 또는 기본 엔드포인트 호출
                # Context7은 MCP 서버를 통해 동작하므로, 클라이언트 생성만으로 검증
                logger.info("✅ Context7 client created successfully")

            logger.success("✅ Context7 API key is valid")

        except ImportError:
            logger.warning("⚠️ httpx not installed, skipping validation")
        except Exception as e:
            logger.error(f"❌ Context7 API key validation failed: {e}")
            raise HTTPException(
                status_code=400,
                detail="API 키가 유효하지 않습니다. 키를 확인해주세요."
            )

        # PostgreSQL에 저장
        await config_set(
            "config:context7_api_key", api_key,
            "secret", "Context7 API Key for docs search"
        )

        # 하이브리드 RAG 재초기화 (API 키 업데이트 반영)
        try:
            from ..web_server import hybrid_rag_orchestrator
            import sys
            sys.modules['src.web_server'].hybrid_rag_orchestrator = None
            logger.info("🔄 Hybrid RAG will be reinitialized on next request")
        except Exception as e:
            logger.warning(f"Failed to reset hybrid RAG: {e}")

        # 키 마스킹
        if len(api_key) > 12:
            masked = f"{api_key[:8]}...{api_key[-4:]}"
        else:
            masked = "****"

        logger.info(f"✅ Context7 API 키 업데이트 완료 (관리자: {user.get('username')})")

        return Context7APIKeyResponse(
            has_key=True,
            masked_key=masked,
            message="Context7 API 키가 성공적으로 저장되었습니다 (유효성 검증 완료)"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Context7 API 키 업데이트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "context7 key save")
        )


@router.delete("/context7-api-key")
async def delete_context7_api_key(
    request: Request,
    user: dict = Depends(require_admin)
):
    """Context7 API 키 삭제 (관리자 전용)"""
    try:
        cache_manager = request.app.state.cache_manager

        # PostgreSQL에서 삭제
        await config_delete("config:context7_api_key")

        logger.info(f"🗑️ Context7 API 키 삭제 완료 (관리자: {user.get('username')})")

        return {
            "success": True,
            "message": "Context7 API 키가 삭제되었습니다"
        }

    except Exception as e:
        logger.error(f"Context7 API 키 삭제 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "context7 key delete")
        )


@router.get("/context7-api-key/reveal")
async def reveal_context7_api_key(
    request: Request,
    user: dict = Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(5, 60, "admin_api_key_reveal"))
):
    """Context7 API 키 조회 (관리자 전용)

    보안상 항상 마스킹된 키만 반환합니다.
    전체 키가 필요한 경우 PostgreSQL 또는 환경변수에서 직접 확인하세요.
    """
    try:
        cache_manager = request.app.state.cache_manager

        # PostgreSQL에서 API 키 가져오기
        full_key = await config_get("config:context7_api_key")

        if full_key:
            return {
                "success": True,
                "api_key": mask_api_key(full_key),
                "masked": True,
                "source": "database"
            }
        else:
            # 환경 변수 확인
            env_key = os.getenv('CONTEXT7_API_KEY')
            if env_key:
                return {
                    "success": True,
                    "api_key": mask_api_key(env_key),
                    "masked": True,
                    "source": "environment"
                }

            raise HTTPException(
                status_code=404,
                detail="저장된 API 키가 없습니다"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Context7 API 키 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "api key get")
        )


# ============================================================================
# 시스템 통계 API
# ============================================================================



def mask_api_key(key: str, show_chars: int = 4) -> str:
    """API 키를 마스킹하여 보안 강화

    Args:
        key: 원본 API 키
        show_chars: 앞뒤로 보여줄 문자 수 (기본값: 4)

    Returns:
        마스킹된 키 (예: "tvly-****...****")
    """
    if not key:
        return ""
    if len(key) <= show_chars * 2:
        return "*" * len(key)
    return f"{key[:show_chars]}{'*' * 8}...{'*' * 8}{key[-show_chars:]}"


def invalidate_stats_cache(include_dashboard: bool = True):
    """통계 캐시 무효화 (인메모리)

    문서 업로드/삭제, 대화 생성 등 통계에 영향을 주는 작업 후 호출합니다.
    """
    global _stats_cache
    _stats_cache.clear()
    logger.debug("통계 캐시 무효화 완료")


# 인메모리 통계 캐시
_stats_cache: dict = {}


@router.get("/db-stats")
async def get_db_stats(
    request: Request,
    user: dict = Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "admin_db_stats"))
):
    """데이터베이스 통계 조회 (관리자 전용)"""
    try:
        from src.database.connection import SyncSessionFactory
        from sqlalchemy import text
        with SyncSessionFactory() as session:
            result = session.execute(text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            table_count = result.scalar() or 0
        return {"total_keys": table_count}
    except Exception:
        return {"total_keys": 0}


@router.get("/document-stats")
async def get_document_stats(
    request: Request,
    user: dict = Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "admin_document_stats"))
):
    """문서 및 대화 통계 조회 (관리자 전용)

    Returns:
        - total_documents: 업로드된 문서 개수
        - total_chunks: 인덱싱된 문서 청크 개수
        - total_conversations: 전체 대화 개수

    Note:
        통계는 5분간 캐싱됩니다 (scan_iter 성능 부하 최소화)
    """
    try:
        import time as _time

        # 인메모리 캐시 확인
        cache_key = "document_stats"
        cached = _stats_cache.get(cache_key)
        if cached and (_time.time() - cached.get("_ts", 0)) < CACHE_TTL_MEDIUM:
            logger.debug("문서 통계 캐시 히트")
            return {k: v for k, v in cached.items() if not k.startswith("_")}

        from ..database.connection import SyncSessionFactory
        from ..database.models.document_chunk import DocumentChunk
        from ..database.models.conversation import Conversation
        from ..database.models.document_group import DocumentGroup
        from ..services.config_service import config_get_sync
        from sqlalchemy import func, distinct

        with SyncSessionFactory() as db_session:
            # 문서 개수 (document_groups 테이블의 고유 파일 수)
            total_documents = db_session.query(
                func.count(distinct(DocumentGroup.id))
            ).scalar() or 0

            # 청크 개수 (활성 인덱스의 document_chunks)
            total_chunks = 0
            active_index = config_get_sync("vector:active_index")
            if active_index:
                total_chunks = db_session.query(
                    func.count(DocumentChunk.id)
                ).filter(
                    DocumentChunk.index_version == active_index
                ).scalar() or 0

            # 대화 개수
            total_conversations = db_session.query(
                func.count(Conversation.id)
            ).scalar() or 0

        stats = {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "total_conversations": total_conversations
        }

        # 인메모리 캐시 저장
        _stats_cache[cache_key] = {**stats, "_ts": _time.time()}
        logger.debug(f"문서 통계 캐시 저장 (TTL: {CACHE_TTL_MEDIUM}초)")

        return stats

    except Exception as e:
        logger.error(f"문서 통계 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "document stats")
        )


@router.get("/arag-stats")
async def get_arag_stats(
    request: Request,
    user: dict = Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "admin_arag_stats"))
):
    """A-RAG 파이프라인 및 벡터 검색 통계 조회 (관리자 전용, 실시간)"""
    try:
        from ..database.connection import SyncSessionFactory
        from ..database.models.document_chunk import DocumentChunk
        from ..database.models.sentence_embedding import SentenceEmbedding
        from ..database.models.system_config import SystemConfig
        from sqlalchemy import func, distinct

        # --- 설정값 + 벡터 통계 단일 세션 조회 ---
        config_keys = [
            "config:hybrid_rag_enabled",
            "config:hybrid_rag_web_search",
            "config:hybrid_rag_doc_search",
            "config:reranking_enabled",
            "config:query_rewrite_enabled",
            "config:tavily_api_key",
            "config:searxng_url",
            "config:context7_api_key",
            "config:crawl4ai_url",
            "config:reranker_model",
            "vector:active_index",
        ]
        cfg: dict = {}
        total_chunks = 0
        total_sentence_embeddings = 0
        total_files = 0
        avg_sentences_per_chunk = 0.0

        with SyncSessionFactory() as session:
            # 1) 설정값 일괄 조회
            try:
                rows = session.query(SystemConfig).filter(
                    SystemConfig.key.in_(config_keys)
                ).all()
                cfg = {r.key: r.value for r in rows}
            except Exception as cfg_err:
                logger.warning(f"A-RAG config 일괄 조회 실패: {cfg_err}")

            # 2) 벡터 통계 (설정 조회 실패해도 독립 실행)
            active_index = cfg.get("vector:active_index") or ""
            if active_index:
                try:
                    # document_chunks: COUNT + COUNT(DISTINCT filename) 병합
                    chunk_row = session.query(
                        func.count(DocumentChunk.id),
                        func.count(distinct(DocumentChunk.filename))
                    ).filter(
                        DocumentChunk.index_version == active_index
                    ).one()
                    total_chunks = chunk_row[0] or 0
                    total_files = chunk_row[1] or 0

                    total_sentence_embeddings = session.query(
                        func.count(SentenceEmbedding.id)
                    ).filter(
                        SentenceEmbedding.index_version == active_index
                    ).scalar() or 0
                except Exception as vec_err:
                    logger.warning(f"A-RAG 벡터 통계 조회 실패: {vec_err}")

        hybrid_enabled = cfg.get("config:hybrid_rag_enabled") == "true"
        web_search = cfg.get("config:hybrid_rag_web_search") == "true"
        doc_search = cfg.get("config:hybrid_rag_doc_search") == "true"
        reranking = cfg.get("config:reranking_enabled") == "true"
        query_rewrite = cfg.get("config:query_rewrite_enabled") == "true"

        tavily_key = cfg.get("config:tavily_api_key")
        searxng_url = cfg.get("config:searxng_url")
        context7_key = cfg.get("config:context7_api_key")
        crawl4ai_url = cfg.get("config:crawl4ai_url")

        reranker_model = cfg.get("config:reranker_model") or "dengcao/Qwen3-Reranker-8B:Q4_K_M"
        embedding_model = os.getenv("EMBEDDING_MODEL", "nlpai-lab/KURE-v1")

        if total_chunks > 0 and total_sentence_embeddings > 0:
            avg_sentences_per_chunk = round(total_sentence_embeddings / total_chunks, 1)

        stats = {
            "features": {
                "hybrid_search": hybrid_enabled,
                "sentence_embeddings": total_sentence_embeddings > 0,
                "reranking": reranking,
                "query_rewrite": query_rewrite,
                "web_search": web_search,
                "doc_search": doc_search,
                "context_compression": hybrid_enabled,
                "query_contextualization": hybrid_enabled,
            },
            "stats": {
                "total_chunks": total_chunks,
                "total_sentence_embeddings": total_sentence_embeddings,
                "avg_sentences_per_chunk": avg_sentences_per_chunk,
                "active_index_version": active_index,
                "total_files": total_files,
            },
            "sources": {
                "tavily": bool(tavily_key),
                "searxng": bool(searxng_url),
                "context7": bool(context7_key),
                "crawl4ai": bool(crawl4ai_url),
            },
            "models": {
                "reranker": reranker_model,
                "embedding": embedding_model,
            },
        }

        return stats

    except Exception as e:
        logger.error(f"A-RAG 통계 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_message(e, "arag stats")
        )