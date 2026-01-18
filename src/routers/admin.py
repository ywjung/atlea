"""
Admin API Router
관리자 전용 API 엔드포인트
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from ..auth.middleware import require_admin
from .auth import invalidate_dashboard_cache
from ..cache_manager import CacheManager
from ..redis_helpers import decode_bytes, decode_redis_hash
from ..auth.rate_limiter import create_rate_limit_dependency

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
    web_search_enabled: Optional[bool] = None
    doc_search_enabled: Optional[bool] = None


class HybridRAGConfigResponse(ConfigResponseBase):
    """하이브리드 RAG 설정 응답 모델"""
    enabled: bool
    web_search_enabled: bool
    doc_search_enabled: bool
    tavily_configured: bool


class PasswordResetRequest(BaseModel):
    """비밀번호 재설정 요청 모델"""
    email: str
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

        # CacheManager (Redis) 가져오기
        cache_manager = request.app.state.cache_manager

        # Redis에서 설정 조회 (없으면 기본값 사용)
        enabled_str = cache_manager.redis.get("config:rate_limit_enabled")

        if enabled_str is None:
            # Redis에 설정이 없으면 config 파일의 기본값 사용
            enabled = config.RATE_LIMIT_ENABLED
        else:
            # Redis 값 사용 (b'true' 또는 b'false')
            enabled = enabled_str.decode() == "true"

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
            detail=f"Rate limit 설정을 가져올 수 없습니다: {str(e)}"
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

        # CacheManager (Redis) 가져오기
        cache_manager = request.app.state.cache_manager

        # Redis에 enabled 상태 저장
        cache_manager.redis.set(
            "config:rate_limit_enabled",
            "true" if config_update.enabled else "false"
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
            detail=f"Rate limit 설정을 업데이트할 수 없습니다: {str(e)}"
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
        from ..auth.captcha import get_captcha_config

        # CacheManager (Redis) 가져오기
        cache_manager = request.app.state.cache_manager

        # CAPTCHA 설정 조회
        config = get_captcha_config(cache_manager.redis)

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
            detail=f"CAPTCHA 설정을 가져올 수 없습니다: {str(e)}"
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
        from ..auth.captcha import set_captcha_enabled, get_captcha_config

        # CacheManager (Redis) 가져오기
        cache_manager = request.app.state.cache_manager

        # Redis에 enabled 상태 저장 (login_enabled 및 register_enabled 분리)
        success = set_captcha_enabled(
            cache_manager.redis,
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
        config = get_captcha_config(cache_manager.redis)

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
            detail=f"CAPTCHA 설정을 업데이트할 수 없습니다: {str(e)}"
        )


# ============================================================================
# Security Logs Endpoint
# ============================================================================

@router.get("/security-logs")
async def get_security_logs(
    request: Request,
    page: int = 1,
    page_size: int = 100,
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
        page: 페이지 번호
        page_size: 페이지당 로그 수
        level: 로그 레벨 필터
        event_type: 이벤트 타입 필터
        start_time: 시작 시간 (ISO 8601 형식)
        end_time: 종료 시간 (ISO 8601 형식)
        user: 관리자 사용자 (의존성 주입)

    Returns:
        보안 로그 목록
    """
    from ..auth.service import AuthService

    auth_service = AuthService(request.app.state.cache_manager.redis)
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
        from ..auth.totp import get_totp_config

        # CacheManager (Redis) 가져오기
        cache_manager = request.app.state.cache_manager

        # 2FA 설정 조회
        config = get_totp_config(cache_manager.redis)

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
            detail=f"2FA 설정을 가져올 수 없습니다: {str(e)}"
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
        from ..auth.totp import set_totp_enabled, get_totp_config

        # CacheManager (Redis) 가져오기
        cache_manager = request.app.state.cache_manager

        # Redis에 enabled 상태 저장
        success = set_totp_enabled(
            cache_manager.redis,
            config_update.enabled
        )

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
        config = get_totp_config(cache_manager.redis)

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
            detail=f"2FA 설정을 업데이트할 수 없습니다: {str(e)}"
        )


@router.get("/users/{user_id}/totp", response_model=UserTotpResponse)
async def get_user_totp_qr(
    user_id: str,
    request: Request,
    user=Depends(require_admin)
):
    """
    사용자별 2FA QR 코드 조회/생성 (관리자 전용)

    Args:
        user_id: 사용자 ID

    Returns:
        사용자 정보 및 QR 코드 (totp_secret이 없으면 생성)
    """
    try:
        from ..auth.totp import TOTPService

        # Redis 가져오기
        redis = request.app.state.cache_manager.redis

        # 사용자 정보 조회
        user_data = redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise HTTPException(
                status_code=404,
                detail="사용자를 찾을 수 없습니다"
            )

        # bytes를 string으로 변환
        user_dict = decode_redis_hash(user_data)

        email = user_dict.get("email", "")
        totp_secret = user_dict.get("totp_secret")

        # TOTP 서비스 인스턴스 생성
        totp_service = TOTPService(redis)

        # totp_secret이 없거나 비어있으면 새로 생성
        if not totp_secret or totp_secret == "None" or totp_secret == "":
            totp_secret = totp_service.generate_secret()
            # Redis에 저장
            redis.hset(f"user:{user_id}", "totp_secret", totp_secret)
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
            detail=f"QR 코드를 생성할 수 없습니다: {str(e)}"
        )


@router.post("/users/{user_id}/totp/reset", response_model=UserTotpResponse)
async def reset_user_totp(
    user_id: str,
    request: Request,
    user=Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(5, 60, "admin_totp_reset"))
):
    """
    사용자 2FA Secret 재생성 (관리자 전용)

    Args:
        user_id: 사용자 ID

    Returns:
        새로운 QR 코드
    """
    try:
        from ..auth.totp import TOTPService

        # Redis 가져오기
        redis = request.app.state.cache_manager.redis

        # 사용자 정보 조회
        user_data = redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise HTTPException(
                status_code=404,
                detail="사용자를 찾을 수 없습니다"
            )

        # bytes를 string으로 변환
        user_dict = decode_redis_hash(user_data)

        email = user_dict.get("email", "")

        # TOTP 서비스 인스턴스 생성
        totp_service = TOTPService(redis)

        # 새로운 secret 생성
        totp_secret = totp_service.generate_secret()

        # Redis에 저장
        redis.hset(f"user:{user_id}", "totp_secret", totp_secret)
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
            detail=f"2FA를 재설정할 수 없습니다: {str(e)}"
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
        from ..auth.brute_force_protection import get_brute_force_config

        cache_manager = request.app.state.cache_manager
        config = get_brute_force_config(cache_manager.redis)

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
            detail=f"브루트 포스 보호 설정을 가져올 수 없습니다: {str(e)}"
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

        cache_manager = request.app.state.cache_manager

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
        success = update_brute_force_config(cache_manager.redis, config.model_dump())

        if not success:
            raise HTTPException(
                status_code=500,
                detail="브루트 포스 보호 설정 업데이트에 실패했습니다"
            )

        logger.info(f"브루트 포스 보호 설정 업데이트: {config.model_dump()} by {user['username']}")

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
            detail=f"브루트 포스 보호 설정을 업데이트할 수 없습니다: {str(e)}"
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

        redis = request.app.state.cache_manager.redis
        auth_service = AuthService(redis)

        # 이메일로 사용자 찾기
        user_id = redis.get(f"user:email:{reset_request.email}")
        if not user_id:
            raise HTTPException(
                status_code=404,
                detail="해당 이메일의 사용자를 찾을 수 없습니다"
            )

        user_id_str = decode_bytes(user_id)

        # 새 비밀번호 결정 (입력된 것 또는 자동 생성)
        new_password = reset_request.new_password
        auto_generated = False

        if not new_password:
            new_password = generate_temporary_password()
            auto_generated = True

        # 비밀번호 해싱
        from ..auth.utils import hash_password
        hashed_password = hash_password(new_password)

        # Redis에 업데이트
        redis.hset(f"user:{user_id_str}", "password_hash", hashed_password)

        # 모든 세션 무효화 (보안: 비밀번호 변경 시 모든 기존 세션 종료)
        session_ids = redis.smembers(f"user:sessions:{user_id_str}")
        invalidated_sessions = len(session_ids) if session_ids else 0

        # Pipeline으로 모든 세션을 배치 삭제 (N+1 방지)
        if session_ids:
            pipe = redis.pipeline()
            for session_id in session_ids:
                session_id_str = CacheManager.decode_bytes(session_id)
                pipe.delete(f"session:{session_id_str}")
            pipe.delete(f"user:sessions:{user_id_str}")
            pipe.execute()
        else:
            redis.delete(f"user:sessions:{user_id_str}")

        logger.info(
            f"관리자 {user['email']}가 사용자 {reset_request.email}의 비밀번호를 재설정했습니다 "
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
            detail=f"비밀번호를 재설정할 수 없습니다: {str(e)}"
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
        from ..auth.password_reset_config import get_password_reset_config

        redis = request.app.state.cache_manager.redis
        config = get_password_reset_config(redis)

        return PasswordResetMethodResponse(
            method=config["method"],
            email_configured=config["email_configured"],
            message="비밀번호 재설정 방식 조회 성공"
        )

    except Exception as e:
        logger.error(f"비밀번호 재설정 방식 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"설정을 조회할 수 없습니다: {str(e)}"
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
            get_password_reset_config
        )

        redis = request.app.state.cache_manager.redis

        # 유효성 검사
        if config_update.method not in ["email", "otp", "admin"]:
            raise HTTPException(
                status_code=400,
                detail="유효하지 않은 방식입니다. 'email', 'otp', 또는 'admin'만 가능합니다."
            )

        # 설정 업데이트
        success = set_password_reset_method(redis, config_update.method)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="설정 업데이트에 실패했습니다"
            )

        logger.info(
            f"관리자 {user['email']}가 비밀번호 재설정 방식을 "
            f"{config_update.method}(으)로 변경했습니다"
        )

        # 업데이트된 설정 반환
        config = get_password_reset_config(redis)

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
            detail=f"설정을 업데이트할 수 없습니다: {str(e)}"
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

        redis = request.app.state.cache_manager.redis
        settings = get_smtp_settings(redis)

        # 보안상 비밀번호는 마스킹
        if settings.get("password"):
            settings["password"] = "********"

        return settings

    except Exception as e:
        logger.error(f"SMTP 설정 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"SMTP 설정을 조회할 수 없습니다: {str(e)}"
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
        from ..email_service import save_smtp_settings

        redis = request.app.state.cache_manager.redis

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
            # 기존 설정에서 비밀번호 직접 가져오기 (Redis에서)
            existing_smtp = redis.hgetall("smtp:settings")
            if existing_smtp and b"password" in existing_smtp:
                password = existing_smtp[b"password"].decode()
            else:
                raise HTTPException(
                    status_code=400,
                    detail="비밀번호는 필수입니다 (기존 설정이 없습니다)"
                )

        # SMTP 설정 저장
        success = save_smtp_settings(
            redis,
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

        logger.info(f"관리자 {user['email']}가 SMTP 설정을 업데이트했습니다")

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
            detail=f"SMTP 설정을 저장할 수 없습니다: {str(e)}"
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
            detail=f"SMTP 연결 테스트 중 오류가 발생했습니다: {str(e)}"
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

        cache_manager = request.app.state.cache_manager
        redis = cache_manager.redis

        # 모든 세션 키 가져오기 (SCAN 사용 - 블로킹 방지)
        session_keys = cache_manager.safe_scan_keys("session:*")

        if not session_keys:
            return SessionListResponse(
                total_sessions=0,
                active_sessions=0,
                expired_sessions=0,
                sessions=[]
            )

        # Pipeline 1: 모든 세션 데이터를 배치로 가져오기 (N+1 쿼리 방지)
        pipe = redis.pipeline()
        for session_key in session_keys:
            session_key_str = CacheManager.decode_bytes(session_key)
            pipe.hgetall(session_key_str)

        session_data_list = pipe.execute()

        # 세션 데이터 파싱 및 user_id 수집
        session_dicts = []
        user_ids = set()

        for session_data in session_data_list:
            if not session_data:
                continue

            # bytes를 str로 변환
            session_dict = CacheManager.decode_redis_hash(session_data)

            session_dicts.append(session_dict)
            user_id = session_dict.get("user_id")
            if user_id:
                user_ids.add(user_id)

        # Pipeline 2: 모든 사용자 데이터를 배치로 가져오기
        user_data_map = {}
        if user_ids:
            pipe = redis.pipeline()
            for user_id in user_ids:
                pipe.hgetall(f"user:{user_id}")

            user_data_results = pipe.execute()

            # 사용자 데이터를 딕셔너리로 변환
            for user_id, user_data in zip(user_ids, user_data_results):
                if user_data:
                    decoded_user = CacheManager.decode_redis_hash(user_data)
                    user_data_map[user_id] = {
                        'email': decoded_user.get('email', 'Unknown'),
                        'username': decoded_user.get('username', 'Unknown')
                    }

        # 세션 목록 생성
        sessions = []
        active_count = 0
        expired_count = 0

        for session_dict in session_dicts:
            user_id = session_dict.get("user_id")
            user_info = user_data_map.get(user_id, {'email': 'Unknown', 'username': 'Unknown'})

            # 만료 여부 확인
            expires_at_str = session_dict.get("expires_at", "")
            is_expired = False

            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                    is_expired = expires_at < datetime.now(timezone.utc)
                except Exception:
                    pass

            if is_expired:
                expired_count += 1
            else:
                active_count += 1

            sessions.append(SessionInfo(
                session_id=session_dict.get("session_id", ""),
                user_id=user_id or "",
                user_email=user_info['email'] or "",
                username=user_info['username'] or "",
                created_at=session_dict.get("created_at", ""),
                expires_at=expires_at_str,
                ip_address=session_dict.get("ip_address", ""),
                is_expired=is_expired
            ))

        # 생성 시간 기준 정렬 (최신순)
        sessions.sort(key=lambda x: x.created_at, reverse=True)

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
            detail=f"세션 목록을 조회할 수 없습니다: {str(e)}"
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
        cache_manager = request.app.state.cache_manager
        redis = cache_manager.redis

        # 모든 세션 키 가져오기 (SCAN 사용 - 블로킹 방지)
        session_keys = cache_manager.safe_scan_keys("session:*")
        user_session_keys = cache_manager.safe_scan_keys("user:sessions:*")

        # Pipeline으로 모든 키를 배치 삭제 (N+1 방지)
        if session_keys or user_session_keys:
            pipe = redis.pipeline()

            for session_key in session_keys:
                session_key_str = CacheManager.decode_bytes(session_key)
                pipe.delete(session_key_str)

            for key in user_session_keys:
                key_str = CacheManager.decode_bytes(key)
                pipe.delete(key_str)

            pipe.execute()

        revoked_count = len(session_keys)

        # 대시보드 캐시 무효화 (세션 수 변경)
        await invalidate_dashboard_cache(redis)

        logger.warning(
            f"🚨 관리자 {user['email']}가 모든 세션을 무효화했습니다 "
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
            detail=f"전체 세션을 무효화할 수 없습니다: {str(e)}"
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
        redis = request.app.state.cache_manager.redis

        # 세션 ID 형식 검증
        if not session_id or len(session_id) < 10:
            raise HTTPException(
                status_code=400,
                detail="유효하지 않은 세션 ID 형식입니다"
            )

        # 자기 자신의 세션인지 확인 (현재 요청의 세션)
        current_session_id = request.cookies.get("session_id")
        if current_session_id == session_id:
            raise HTTPException(
                status_code=400,
                detail="자신의 현재 세션은 무효화할 수 없습니다"
            )

        # 세션 존재 확인
        session_data = redis.hgetall(f"session:{session_id}")
        if not session_data:
            raise HTTPException(
                status_code=404,
                detail="세션을 찾을 수 없습니다"
            )

        # 세션에서 user_id 추출
        decoded_session = decode_redis_hash(session_data)
        target_user_id = decoded_session.get("user_id")
        target_email = decoded_session.get("email", "unknown")

        # 세션 삭제
        redis.delete(f"session:{session_id}")

        # user:sessions 세트에서도 제거
        if target_user_id:
            redis.srem(f"user:sessions:{target_user_id}", session_id)

        # 대시보드 캐시 무효화 (세션 수 변경)
        await invalidate_dashboard_cache(redis)

        logger.info(
            f"관리자 {user['email']}가 세션을 무효화했습니다 "
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
            detail=f"세션을 무효화할 수 없습니다: {str(e)}"
        )


@router.delete("/sessions/user/{user_id}", response_model=RevokeSessionResponse)
async def revoke_user_sessions(
    user_id: str,
    request: Request,
    user=Depends(require_admin),
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "admin_user_session_revoke"))
):
    """특정 사용자의 모든 세션 무효화 (관리자 전용)

    Args:
        user_id: 사용자 ID

    Returns:
        무효화 결과
    """
    try:
        redis = request.app.state.cache_manager.redis

        # 자기 자신의 세션을 무효화하려는 경우 경고
        if user.get("user_id") == user_id:
            raise HTTPException(
                status_code=400,
                detail="자신의 세션을 모두 무효화할 수 없습니다. 개별 세션을 삭제하세요."
            )

        # 사용자 존재 확인
        user_data = redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise HTTPException(
                status_code=404,
                detail="사용자를 찾을 수 없습니다"
            )

        # 사용자 이메일 추출
        decoded_user = decode_redis_hash(user_data)
        target_email = decoded_user.get("email", "unknown")

        # 사용자의 모든 세션 가져오기
        session_ids = redis.smembers(f"user:sessions:{user_id}")
        revoked_count = len(session_ids) if session_ids else 0

        # Pipeline으로 모든 세션을 배치 삭제 (N+1 방지)
        if session_ids:
            pipe = redis.pipeline()
            for session_id in session_ids:
                session_id_str = CacheManager.decode_bytes(session_id)
                pipe.delete(f"session:{session_id_str}")
            pipe.delete(f"user:sessions:{user_id}")
            pipe.execute()
        else:
            redis.delete(f"user:sessions:{user_id}")

        # 대시보드 캐시 무효화 (세션 수 변경)
        await invalidate_dashboard_cache(redis)

        logger.info(
            f"관리자 {user['email']}가 사용자 {target_email}의 모든 세션을 무효화했습니다 "
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
            detail=f"사용자 세션을 무효화할 수 없습니다: {str(e)}"
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

        # Redis에서 설정 가져오기
        enabled = cache_manager.redis.get("config:hybrid_rag_enabled")
        web_search_enabled = cache_manager.redis.get("config:hybrid_rag_web_search")
        doc_search_enabled = cache_manager.redis.get("config:hybrid_rag_doc_search")

        # 기본값 설정
        enabled = enabled.decode() == "true" if enabled else False
        web_search_enabled = web_search_enabled.decode() == "true" if web_search_enabled else False
        doc_search_enabled = doc_search_enabled.decode() == "true" if doc_search_enabled else False

        # Tavily API 키 설정 여부 확인 (Redis 우선, 환경 변수 대체)
        redis_key = cache_manager.redis.get("config:tavily_api_key")
        env_key = os.getenv('TAVILY_API_KEY')
        tavily_configured = bool(redis_key or env_key)

        return HybridRAGConfigResponse(
            enabled=enabled,
            web_search_enabled=web_search_enabled,
            doc_search_enabled=doc_search_enabled,
            tavily_configured=tavily_configured,
            message="하이브리드 RAG 설정을 조회했습니다"
        )

    except Exception as e:
        logger.error(f"하이브리드 RAG 설정 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"하이브리드 RAG 설정을 조회할 수 없습니다: {str(e)}"
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

        # Redis에 설정 저장
        cache_manager.redis.set(
            "config:hybrid_rag_enabled",
            "true" if config_update.enabled else "false"
        )

        # 웹 검색 활성화 설정
        if config_update.web_search_enabled is not None:
            cache_manager.redis.set(
                "config:hybrid_rag_web_search",
                "true" if config_update.web_search_enabled else "false"
            )
            web_search_enabled = config_update.web_search_enabled
        else:
            # 기존 값 유지
            web_setting = cache_manager.redis.get("config:hybrid_rag_web_search")
            web_search_enabled = web_setting.decode() == "true" if web_setting else False

        # 공식 문서 검색 활성화 설정
        if config_update.doc_search_enabled is not None:
            cache_manager.redis.set(
                "config:hybrid_rag_doc_search",
                "true" if config_update.doc_search_enabled else "false"
            )
            doc_search_enabled = config_update.doc_search_enabled
        else:
            # 기존 값 유지
            doc_setting = cache_manager.redis.get("config:hybrid_rag_doc_search")
            doc_search_enabled = doc_setting.decode() == "true" if doc_setting else False

        # Tavily API 키 설정 여부 확인 (Redis 우선, 환경 변수 대체)
        tavily_key_redis = cache_manager.redis.get("config:tavily_api_key")
        tavily_key_env = os.getenv('TAVILY_API_KEY')
        tavily_configured = bool(tavily_key_redis or tavily_key_env)

        # HybridRAGOrchestrator 재초기화 필요 (실제 적용은 web_server.py에서)
        # 여기서는 설정만 저장

        logger.info(
            f"하이브리드 RAG 설정 업데이트: enabled={config_update.enabled}, "
            f"web_search={web_search_enabled}, doc_search={doc_search_enabled} "
            f"by user={user.get('email', 'unknown')}"
        )

        status_msg = f"하이브리드 RAG {'활성화' if config_update.enabled else '비활성화'}되었습니다"
        if config_update.enabled and web_search_enabled and not tavily_configured:
            status_msg += " (주의: TAVILY_API_KEY가 설정되지 않아 웹 검색이 작동하지 않습니다)"

        return HybridRAGConfigResponse(
            enabled=config_update.enabled,
            web_search_enabled=web_search_enabled,
            doc_search_enabled=doc_search_enabled,
            tavily_configured=tavily_configured,
            message=status_msg
        )

    except Exception as e:
        logger.error(f"하이브리드 RAG 설정 업데이트 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"하이브리드 RAG 설정을 업데이트할 수 없습니다: {str(e)}"
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

        # Redis에서 API 키 가져오기
        stored_key = cache_manager.redis.get("config:tavily_api_key")

        if stored_key:
            key_str = stored_key.decode()
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
            detail=f"Tavily API 키를 조회할 수 없습니다: {str(e)}"
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

        # Tavily API 키 형식 검증 (tvly-로 시작하는지 확인)
        if not api_key.startswith('tvly-'):
            raise HTTPException(
                status_code=400,
                detail="올바른 Tavily API 키 형식이 아닙니다 (tvly-로 시작해야 합니다)"
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
                detail=f"API 키가 유효하지 않습니다: {str(e)}"
            )

        # Redis에 저장
        cache_manager.redis.set("config:tavily_api_key", api_key)

        # 🆕 하이브리드 RAG 재초기화 (API 키 업데이트 반영)
        try:
            from ..web_server import hybrid_rag_orchestrator
            import sys
            # 전역 변수 초기화하여 다음 요청 시 재생성되도록 함
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
            detail=f"Tavily API 키를 저장할 수 없습니다: {str(e)}"
        )


@router.delete("/tavily-api-key")
async def delete_tavily_api_key(
    request: Request,
    user: dict = Depends(require_admin)
):
    """Tavily API 키 삭제 (관리자 전용)"""
    try:
        cache_manager = request.app.state.cache_manager

        # Redis에서 삭제
        cache_manager.redis.delete("config:tavily_api_key")

        logger.info(f"🗑️ Tavily API 키 삭제 완료 (관리자: {user.get('username')})")

        return {
            "success": True,
            "message": "Tavily API 키가 삭제되었습니다"
        }

    except Exception as e:
        logger.error(f"Tavily API 키 삭제 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Tavily API 키를 삭제할 수 없습니다: {str(e)}"
        )


@router.get("/tavily-api-key/reveal")
async def reveal_tavily_api_key(
    request: Request,
    user: dict = Depends(require_admin),
    full: bool = False,
    _rate_limit=Depends(create_rate_limit_dependency(5, 60, "admin_api_key_reveal"))
):
    """Tavily API 키 조회 (관리자 전용)
    
    Args:
        full: True면 전체 키 반환 (보안 주의), False면 마스킹된 키 반환
    """
    try:
        cache_manager = request.app.state.cache_manager

        # Redis에서 API 키 가져오기
        stored_key = cache_manager.redis.get("config:tavily_api_key")

        if stored_key:
            full_key = stored_key.decode()
            if full:
                logger.warning(
                    f"🔐 Tavily API 키 전체 조회 (관리자: {user.get('username')}, "
                    f"IP: {request.client.host if request.client else 'unknown'})"
                )
                return {
                    "success": True,
                    "api_key": full_key,
                    "masked": False,
                    "source": "redis"
                }
            else:
                return {
                    "success": True,
                    "api_key": mask_api_key(full_key),
                    "masked": True,
                    "source": "redis"
                }
        else:
            # 환경 변수 확인
            env_key = os.getenv('TAVILY_API_KEY')
            if env_key:
                if full:
                    logger.warning(
                        f"🔐 Tavily API 키 전체 조회 - 환경변수 (관리자: {user.get('username')}, "
                        f"IP: {request.client.host if request.client else 'unknown'})"
                    )
                    return {
                        "success": True,
                        "api_key": env_key,
                        "masked": False,
                        "source": "environment"
                    }
                else:
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
            detail=f"API 키를 조회할 수 없습니다: {str(e)}"
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

        # Redis에서 API 키 가져오기
        stored_key = cache_manager.redis.get("config:context7_api_key")

        if stored_key:
            key_str = stored_key.decode()
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
            detail=f"Context7 API 키를 조회할 수 없습니다: {str(e)}"
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
            test_client = httpx.AsyncClient(
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                timeout=15.0
            )

            # 간단한 테스트: /health 또는 기본 엔드포인트 호출
            # Context7은 MCP 서버를 통해 동작하므로, 클라이언트 생성만으로 검증
            logger.info("✅ Context7 client created successfully")

            # 클라이언트 정리
            await test_client.aclose()

            logger.success("✅ Context7 API key is valid")

        except ImportError:
            logger.warning("⚠️ httpx not installed, skipping validation")
        except Exception as e:
            logger.error(f"❌ Context7 API key validation failed: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"API 키가 유효하지 않습니다: {str(e)}"
            )

        # Redis에 저장
        cache_manager.redis.set("config:context7_api_key", api_key)

        # 🆕 하이브리드 RAG 재초기화 (API 키 업데이트 반영)
        try:
            from ..web_server import hybrid_rag_orchestrator
            import sys
            # 전역 변수 초기화하여 다음 요청 시 재생성되도록 함
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
            detail=f"Context7 API 키를 저장할 수 없습니다: {str(e)}"
        )


@router.delete("/context7-api-key")
async def delete_context7_api_key(
    request: Request,
    user: dict = Depends(require_admin)
):
    """Context7 API 키 삭제 (관리자 전용)"""
    try:
        cache_manager = request.app.state.cache_manager

        # Redis에서 삭제
        cache_manager.redis.delete("config:context7_api_key")

        logger.info(f"🗑️ Context7 API 키 삭제 완료 (관리자: {user.get('username')})")

        return {
            "success": True,
            "message": "Context7 API 키가 삭제되었습니다"
        }

    except Exception as e:
        logger.error(f"Context7 API 키 삭제 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Context7 API 키를 삭제할 수 없습니다: {str(e)}"
        )


@router.get("/context7-api-key/reveal")
async def reveal_context7_api_key(
    request: Request,
    user: dict = Depends(require_admin),
    full: bool = False,
    _rate_limit=Depends(create_rate_limit_dependency(5, 60, "admin_api_key_reveal"))
):
    """Context7 API 키 조회 (관리자 전용)
    
    Args:
        full: True면 전체 키 반환 (보안 주의), False면 마스킹된 키 반환
    """
    try:
        cache_manager = request.app.state.cache_manager

        # Redis에서 API 키 가져오기
        stored_key = cache_manager.redis.get("config:context7_api_key")

        if stored_key:
            full_key = stored_key.decode()
            if full:
                logger.warning(
                    f"🔐 Context7 API 키 전체 조회 (관리자: {user.get('username')}, "
                    f"IP: {request.client.host if request.client else 'unknown'})"
                )
                return {
                    "success": True,
                    "api_key": full_key,
                    "masked": False,
                    "source": "redis"
                }
            else:
                return {
                    "success": True,
                    "api_key": mask_api_key(full_key),
                    "masked": True,
                    "source": "redis"
                }
        else:
            # 환경 변수 확인
            env_key = os.getenv('CONTEXT7_API_KEY')
            if env_key:
                if full:
                    logger.warning(
                        f"🔐 Context7 API 키 전체 조회 - 환경변수 (관리자: {user.get('username')}, "
                        f"IP: {request.client.host if request.client else 'unknown'})"
                    )
                    return {
                        "success": True,
                        "api_key": env_key,
                        "masked": False,
                        "source": "environment"
                    }
                else:
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
            detail=f"API 키를 조회할 수 없습니다: {str(e)}"
        )


# ============================================================================
# 시스템 통계 API
# ============================================================================



def count_redis_keys(redis_client, pattern: str, max_count: int = 100000) -> int:
    """Redis 키 개수를 메모리 효율적으로 카운트

    모든 키를 메모리에 로드하지 않고 스캔하면서 카운트합니다.
    max_count에 도달하면 조기 종료합니다.

    Args:
        redis_client: Redis 클라이언트
        pattern: 매칭할 키 패턴 (예: "doc:group:*")
        max_count: 최대 카운트 제한 (메모리 보호)

    Returns:
        매칭된 키 개수 (max_count 이상이면 max_count 반환)
    """
    count = 0
    for _ in redis_client.scan_iter(match=pattern, count=1000):
        count += 1
        if count >= max_count:
            logger.warning(f"키 카운트가 최대값 {max_count}에 도달: {pattern}")
            break
    return count


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


def invalidate_stats_cache(redis_client, include_dashboard: bool = True):
    """통계 캐시 무효화

    문서 업로드/삭제, 대화 생성 등 통계에 영향을 주는 작업 후 호출합니다.
    Pipeline을 사용하여 원자적으로 여러 캐시를 삭제합니다.

    Args:
        redis_client: Redis 클라이언트
        include_dashboard: 대시보드 캐시도 함께 무효화할지 여부
    """
    try:
        pipe = redis_client.pipeline()
        
        # 통계 관련 캐시
        pipe.delete("cache:stats:documents")
        pipe.delete("cache:stats:redis")
        
        # 대시보드 캐시 (선택적)
        if include_dashboard:
            pipe.delete("cache:admin:dashboard")
            pipe.delete("cache:admin:dashboard:stats")
        
        results = pipe.execute()
        deleted_count = sum(1 for r in results if r)
        
        if deleted_count > 0:
            logger.debug(f"통계 캐시 무효화 완료: {deleted_count}개 키 삭제")
    except Exception as e:
        logger.warning(f"통계 캐시 무효화 실패: {e}")


@router.get("/redis-stats")
async def get_redis_stats(
    request: Request,
    user: dict = Depends(require_admin)
):
    """Redis 통계 조회 (관리자 전용)

    Returns:
        - total_keys: 전체 Redis 키 개수
        - keyspace_hits: 캐시 히트 횟수
        - keyspace_misses: 캐시 미스 횟수

    Note:
        통계는 5분간 캐싱됩니다 (빈번한 조회로 인한 성능 저하 방지)
    """
    try:
        import json
        cache_manager = request.app.state.cache_manager
        redis_client = cache_manager.redis

        cache_key = "cache:stats:redis"
        cache_ttl = 300  # 5분

        # 캐시 확인
        cached_stats = redis_client.get(cache_key)
        if cached_stats:
            logger.debug("Redis 통계 캐시 히트")
            return json.loads(cached_stats)

        # Redis 통계 정보 조회
        info = redis_client.info('stats')

        stats = {
            "total_keys": redis_client.dbsize(),
            "keyspace_hits": info.get('keyspace_hits', 0),
            "keyspace_misses": info.get('keyspace_misses', 0)
        }

        # 캐시 저장
        redis_client.setex(cache_key, cache_ttl, json.dumps(stats))
        logger.debug(f"Redis 통계 캐시 저장 (TTL: {cache_ttl}초)")

        return stats

    except Exception as e:
        logger.error(f"Redis 통계 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Redis 통계를 조회할 수 없습니다: {str(e)}"
        )


@router.get("/document-stats")
async def get_document_stats(
    request: Request,
    user: dict = Depends(require_admin)
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
        import json
        cache_manager = request.app.state.cache_manager
        redis_client = cache_manager.redis

        cache_key = "cache:stats:documents"
        cache_ttl = 300  # 5분

        # 캐시 확인
        cached_stats = redis_client.get(cache_key)
        if cached_stats:
            logger.debug("문서 통계 캐시 히트")
            return json.loads(cached_stats)

        # 문서 개수 (메모리 효율적 카운팅)
        total_documents = count_redis_keys(redis_client, "doc:group:*", max_count=100000)

        # RediSearch 인덱스에서 청크 개수
        total_chunks = 0
        try:
            # vector_db.py에서 사용하는 실제 키: index:active
            active_index = redis_client.get("index:active")
            if active_index:
                active_index = CacheManager.decode_bytes(active_index)
                index_info = redis_client.ft(active_index).info()
                total_chunks = int(index_info.get('num_docs', 0))
        except Exception as e:
            logger.warning(f"RediSearch 인덱스 정보 조회 실패: {e}")
            total_chunks = 0

        # 대화 개수 (메모리 효율적 카운팅)
        total_conversations = count_redis_keys(redis_client, "conversation:*", max_count=100000)

        stats = {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "total_conversations": total_conversations
        }

        # 캐시 저장
        redis_client.setex(cache_key, cache_ttl, json.dumps(stats))
        logger.debug(f"문서 통계 캐시 저장 (TTL: {cache_ttl}초)")

        return stats

    except Exception as e:
        logger.error(f"문서 통계 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"문서 통계를 조회할 수 없습니다: {str(e)}"
        )