"""
Admin API Router
관리자 전용 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from ..auth.middleware import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================================
# Pydantic Models
# ============================================================================

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
    enabled: bool


class CaptchaConfigResponse(BaseModel):
    """CAPTCHA 설정 응답 모델"""
    enabled: bool
    site_key: str
    configured: bool
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
            enabled=config["enabled"],
            site_key=config["site_key"],
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
        config_update: 업데이트할 설정 (enabled)

    Returns:
        업데이트된 CAPTCHA 설정
    """
    try:
        from ..auth.captcha import set_captcha_enabled, get_captcha_config

        # CacheManager (Redis) 가져오기
        cache_manager = request.app.state.cache_manager

        # Redis에 enabled 상태 저장
        success = set_captcha_enabled(
            cache_manager.redis,
            config_update.enabled
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="CAPTCHA 설정 업데이트에 실패했습니다"
            )

        logger.info(
            f"CAPTCHA 설정 업데이트: enabled={config_update.enabled} "
            f"by user={user.get('email', 'unknown')}"
        )

        # 업데이트된 설정 반환
        config = get_captcha_config(cache_manager.redis)

        return CaptchaConfigResponse(
            enabled=config["enabled"],
            site_key=config["site_key"],
            configured=config["configured"],
            message=f"CAPTCHA {'활성화' if config_update.enabled else '비활성화'}되었습니다"
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
