"""Authentication API routes

FastAPI router for user registration, login, logout, and user management.
"""

import os
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import time
import secrets
from loguru import logger
from ..auth.models import (
    UserCreate, UserLogin, LoginResponse, TokenPair,
    PasswordReset, PasswordResetConfirm, PasswordResetOTP, PasswordResetOTPConfirm, OTPVerifyRequest,
    ProfileUpdate, PasswordChange, Session,
    WebhookCreate, WebhookUpdate, Webhook, WebhookEvent, WebhookTestRequest, WebhookDelivery
)
from ..auth.service import AuthService
from ..auth.webhook_service import WebhookService
from ..auth.middleware import get_current_active_user, require_admin
from ..auth.rate_limiter import create_rate_limit_dependency, RateLimitConfig
from ..utils.error_handling import get_safe_error_message

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============= Cache Invalidation Helper =============

# In-memory dashboard cache (max 100 entries)
_DASHBOARD_CACHE_MAX = 100
_dashboard_cache = {}


async def invalidate_dashboard_cache():
    """대시보드 캐시 무효화

    사용자 데이터가 변경되었을 때 인메모리 대시보드 캐시를 삭제합니다.

    Args:
        
    """
    global _dashboard_cache
    _dashboard_cache.clear()


async def send_password_reset_email(email_service, to_email: str, reset_token: str) -> bool:
    """비밀번호 재설정 이메일 발송

    Args:
        email_service: EmailService 인스턴스
        to_email: 수신자 이메일
        reset_token: 비밀번호 재설정 토큰

    Returns:
        발송 성공 여부
    """
    try:
        # 비밀번호 재설정 링크 생성 (config에서 BASE_URL 가져오기)
        from ..config.production import config
        reset_link = f"{config.BASE_URL}/static/reset-password.html?token={reset_token}"

        subject = "비밀번호 재설정 안내"
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px; text-align: center;">
                <h1 style="color: white; margin: 0;">🔐 비밀번호 재설정</h1>
            </div>

            <div style="background: #f8f9fa; padding: 30px; border-radius: 10px; margin-top: 20px;">
                <p style="font-size: 16px; color: #333;">비밀번호 재설정을 요청하셨습니다.</p>
                <p style="font-size: 16px; color: #333;">아래 버튼을 클릭하여 새로운 비밀번호를 설정하세요:</p>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_link}"
                       style="display: inline-block; padding: 15px 40px; background: #667eea; color: white;
                              text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: bold;">
                        비밀번호 재설정하기
                    </a>
                </div>

                <p style="font-size: 14px; color: #666;">
                    또는 아래 링크를 복사하여 브라우저에 붙여넣으세요:
                </p>
                <div style="background: white; padding: 15px; border-radius: 8px; word-break: break-all; font-family: monospace; font-size: 12px; color: #666;">
                    {reset_link}
                </div>

                <p style="font-size: 14px; color: #666; margin-top: 20px;">
                    ⏰ 이 링크는 <strong>1시간 동안</strong> 유효합니다.
                </p>

                <p style="font-size: 14px; color: #666;">
                    ⚠️ 본인이 요청하지 않았다면 이 이메일을 무시하세요.
                </p>
            </div>

            <div style="margin-top: 20px; text-align: center; color: #999; font-size: 12px;">
                <p>이 이메일은 자동으로 발송되었습니다. 회신하지 마세요.</p>
            </div>
        </body>
        </html>
        """

        return email_service._send_email(to_email, subject, html_body)

    except Exception as e:
        logger.error(f"비밀번호 재설정 이메일 발송 실패: {e}")
        return False


class RefreshTokenRequest(BaseModel):
    """토큰 갱신 요청"""
    refresh_token: str


# ============= CSRF Protection =============

from ..config.settings import CSRF_COOKIE_MAX_AGE

CSRF_COOKIE_NAME = "csrf_token"


@router.get("/csrf-token")
async def get_csrf_token(request: Request, response: Response):
    """
    CSRF 토큰 조회/생성

    쿠키 기반 인증 사용 시 CSRF 공격 방지를 위해 이 토큰을
    X-CSRF-Token 헤더에 포함하여 요청해야 합니다.

    Returns:
        {"csrf_token": str}
    """
    import secrets

    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=token,
            max_age=CSRF_COOKIE_MAX_AGE,
            httponly=False,  # JavaScript에서 읽을 수 있어야 함
            samesite="strict",
            secure=True,
        )
    return {"csrf_token": token}


@router.get("/totp/status")
async def get_totp_status(request: Request):
    """
    2FA 활성화 여부 확인 (공개 API)

    로그인 페이지에서 2FA 입력 필드 표시 여부를 결정하기 위해 사용

    Returns:
        {"enabled": bool}
    """
    try:
        from ..auth.totp import TOTPService
        totp_service = TOTPService()

        return {"enabled": totp_service.is_enabled()}
    except Exception as e:
        logger.error(f"2FA 상태 조회 실패: {e}")
        # 에러 시 false 반환 (안전한 기본값)
        return {"enabled": False}


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    _: bool = Depends(
        create_rate_limit_dependency(
            max_requests=RateLimitConfig.REGISTER_MAX_REQUESTS,
            window_seconds=RateLimitConfig.REGISTER_WINDOW_SECONDS,
            identifier="register"
        )
    )
):
    """회원가입

    Args:
        user_data: 사용자 생성 정보
        request: FastAPI Request

    Returns:
        생성된 사용자 정보

    Raises:
        HTTPException: 이메일 중복 또는 유효성 검사 실패 시 400
    """
    auth_service = AuthService()

    # CAPTCHA 검증 (회원가입)
    from ..auth.captcha import SimpleCaptchaService
    captcha_service = SimpleCaptchaService()
    if captcha_service.is_enabled("register"):
        success, error_msg = await captcha_service.verify_captcha(
            captcha_id=user_data.captcha_id or "",
            user_answer=user_data.captcha_answer or ""
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg or "CAPTCHA 검증에 실패했습니다"
            )

    try:
        user = await auth_service.create_user(user_data)

        # 대시보드 캐시 무효화 (새 사용자 등록)
        await invalidate_dashboard_cache()

        return {
            "message": "회원가입이 완료되었습니다",
            "user": user.model_dump()
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: UserLogin,
    request: Request,
    _: bool = Depends(
        create_rate_limit_dependency(
            max_requests=RateLimitConfig.LOGIN_MAX_REQUESTS,
            window_seconds=RateLimitConfig.LOGIN_WINDOW_SECONDS,
            identifier="login"
        )
    )
):
    """로그인

    Args:
        credentials: 로그인 정보 (이메일, 비밀번호)
        request: FastAPI Request

    Returns:
        사용자 정보 및 JWT 토큰

    Raises:
        HTTPException: 인증 실패 시 401
    """
    # 타이밍 공격 방지: 응답 시간을 일정하게 유지
    start_time = time.time()
    # 최소 응답 시간 (밀리초): 200-300ms 랜덤 (성공/실패 여부와 무관)
    min_response_time_ms = 200 + secrets.randbelow(100)

    auth_service = AuthService()

    try:
        # IP 주소 추출
        ip_address = request.client.host if request.client else None

        # 디버깅: 로그인 시도 로깅 (개인정보 제외)
        logger.debug(f"🔍 Login attempt - ip: {ip_address}")

        # CAPTCHA 검증 (로그인)
        from ..auth.captcha import SimpleCaptchaService
        captcha_service = SimpleCaptchaService()
        if captcha_service.is_enabled("login"):
            success, error_msg = await captcha_service.verify_captcha(
                captcha_id=credentials.captcha_id or "",
                user_answer=credentials.captcha_answer or ""
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg or "CAPTCHA 검증에 실패했습니다"
                )

        # User-Agent 추출
        user_agent = request.headers.get("User-Agent")

        result = await auth_service.authenticate_user(credentials, ip_address, user_agent)

        # 로그인 성공 감사 로그 기록
        audit_logger = getattr(request.app.state, "audit_logger", None)
        if audit_logger:
            from ..audit import AuditAction

            # 응답 시간 계산
            duration_ms = round((time.time() - start_time) * 1000, 2)

            audit_logger.log(
                action=AuditAction.LOGIN,
                user_id=result["user"].user_id,
                username=result["user"].username,
                ip_address=ip_address,
                user_agent=user_agent,
                resource=credentials.email,
                details={
                    "method": "POST",
                    "path": "/api/auth/login",
                    "email": credentials.email,
                    "duration_ms": duration_ms
                },
                success=True
            )

        return LoginResponse(
            user=result["user"],
            tokens=TokenPair(**result["tokens"]),
            session_id=result["session_id"]
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

    finally:
        # 타이밍 공격 방지: 성공/실패 여부와 관계없이 최소 응답 시간 보장
        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms < min_response_time_ms:
            await asyncio.sleep((min_response_time_ms - elapsed_ms) / 1000)


@router.post("/logout")
async def logout(
    request: Request
):
    """로그아웃

    토큰이 만료되어도 로그아웃을 처리합니다.

    Args:
        request: FastAPI Request

    Returns:
        로그아웃 성공 메시지
    """
    from ..auth.utils import extract_token_from_request, ALGORITHM
    import jwt
    from ..config import config

    auth_service = AuthService()

    # IP 주소 추출
    ip_address = request.client.host if request.client else None

    try:
        # 토큰 추출 (만료되어도 괜찮음)
        token = extract_token_from_request(request)

        if token:
            try:
                # 토큰 디코딩 (만료 체크 비활성화)
                payload = jwt.decode(
                    token,
                    config.SECRET_KEY,
                    algorithms=[ALGORITHM],
                    options={"verify_exp": False}  # 만료 체크 비활성화
                )

                user_id = payload.get("user_id")
                username = payload.get("sub")

                if user_id:
                    # 토큰을 블랙리스트에 추가
                    from ..auth.token_blacklist import TokenBlacklist
                    blacklist = TokenBlacklist()
                    blacklist.add_token(token, config.SECRET_KEY, reason="logout")

                    # 사용자의 모든 활성 세션 조회 및 삭제 (PG)
                    sessions = await auth_service.get_user_sessions(user_id)
                    for session in sessions:
                        await auth_service.logout(
                            session.session_id,
                            ip_address=ip_address,
                            username=username
                        )

            except jwt.InvalidTokenError as e:
                # 토큰이 완전히 잘못된 경우에도 그냥 성공 처리
                logger.warning(f"Invalid token during logout: {e}")
                pass

    except Exception as e:
        # 모든 에러를 무시하고 성공 처리
        logger.warning(f"Error during logout, but returning success: {e}")
        pass

    return {"message": "로그아웃되었습니다"}


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    token_request: RefreshTokenRequest,
    request: Request,
    _: bool = Depends(
        create_rate_limit_dependency(
            max_requests=RateLimitConfig.API_MAX_REQUESTS,
            window_seconds=RateLimitConfig.API_WINDOW_SECONDS,
            identifier="refresh"
        )
    )
):
    """토큰 갱신

    Args:
        token_request: Refresh Token
        request: FastAPI Request

    Returns:
        새로운 사용자 정보 및 JWT 토큰

    Raises:
        HTTPException: 토큰 검증 실패 시 401
    """

    auth_service = AuthService()

    try:
        # IP 주소 추출
        ip_address = request.client.host if request.client else None

        result = await auth_service.refresh_access_token(
            token_request.refresh_token,
            ip_address
        )

        return LoginResponse(
            user=result["user"],
            tokens=TokenPair(**result["tokens"])
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.get("/me")
async def get_current_user_info(
    current_user: dict = Depends(get_current_active_user)
):
    """현재 사용자 정보 조회

    Args:
        current_user: 현재 인증된 사용자

    Returns:
        사용자 정보
    """

    return {
        "user": current_user
    }


@router.post("/password-reset/request")
async def request_password_reset(
    reset_request: PasswordReset,
    request: Request,
    _: bool = Depends(
        create_rate_limit_dependency(
            max_requests=RateLimitConfig.PASSWORD_RESET_MAX_REQUESTS,
            window_seconds=RateLimitConfig.PASSWORD_RESET_WINDOW_SECONDS,
            identifier="password_reset"
        )
    )
):
    """비밀번호 재설정 요청

    Args:
        reset_request: 재설정 요청 (이메일)
        request: FastAPI Request

    Returns:
        재설정 토큰 (이메일로 전송) 또는 토큰 직접 반환

    Raises:
        HTTPException: 사용자를 찾을 수 없을 때 400
    """

    auth_service = AuthService()

    try:
        reset_token = await auth_service.request_password_reset(reset_request.email)

        # SMTP 설정 확인 및 이메일 전송
        from ..email_service import get_email_service

        email_service = get_email_service()

        if email_service.is_configured():
            # 이메일 발송
            success = await send_password_reset_email(
                email_service,
                reset_request.email,
                reset_token
            )

            if success:
                return {
                    "message": "비밀번호 재설정 링크가 이메일로 전송되었습니다",
                    "email_sent": True
                }
            else:
                # 이메일 전송 실패 - 보안을 위해 토큰 노출하지 않음
                logger.warning(f"Failed to send password reset email to {reset_request.email}")
                # 일반적인 성공 메시지 반환 (보안상 실패 여부를 노출하지 않음)
                return {
                    "message": "비밀번호 재설정 링크가 이메일로 전송되었습니다",
                    "email_sent": False
                }
        else:
            # SMTP 미설정 시 - 보안을 위해 토큰 노출하지 않음
            logger.warning(f"Password reset requested but SMTP not configured for {reset_request.email}")
            # 일반적인 성공 메시지 반환 (보안상 설정 상태를 노출하지 않음)
            return {
                "message": "비밀번호 재설정 링크가 이메일로 전송되었습니다",
                "email_sent": False
            }

    except ValueError as e:
        logger.warning(f"Password reset request failed: {e}")
        # 사용자 존재 여부를 노출하지 않도록 항상 동일한 응답 반환
        return {
            "message": "비밀번호 재설정 링크가 이메일로 전송되었습니다",
            "email_sent": False
        }


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    request: Request,
    _: bool = Depends(
        create_rate_limit_dependency(
            max_requests=5,
            window_seconds=300,
            identifier="password_reset_confirm"
        )
    )
):
    """비밀번호 재설정 확인

    Args:
        reset_confirm: 재설정 확인 (토큰, 새 비밀번호)
        request: FastAPI Request

    Returns:
        성공 메시지

    Raises:
        HTTPException: 토큰 검증 실패 시 401
    """

    auth_service = AuthService()

    try:
        await auth_service.reset_password(
            reset_confirm.token,
            reset_confirm.new_password
        )

        return {
            "message": "비밀번호가 성공적으로 재설정되었습니다"
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )



@router.post("/reset-password-with-otp")
async def reset_password_with_otp(
    reset_data: PasswordResetOTP,
    request: Request,
    _: bool = Depends(
        create_rate_limit_dependency(
            max_requests=5,
            window_seconds=300,
            identifier="otp_password_reset"
        )
    )
):
    """OTP 기반 비밀번호 재설정 (토큰 없이 직접 실행 - 하위 호환성)

    Args:
        reset_data: 이메일, OTP 코드, 새 비밀번호
        request: FastAPI Request

    Returns:
        성공 메시지

    Raises:
        HTTPException: OTP 검증 실패 또는 사용자 찾기 실패 시
    """
    from ..auth.totp import TOTPService
    from ..auth.utils import hash_password
    from ..database.connection import AsyncSessionFactory
    from ..repositories.user_repository import UserRepository

    totp_service = TOTPService()

    try:
        # 1. 이메일로 사용자 찾기 (PG)
        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_email(reset_data.email)

            if not pg_user or not pg_user.totp_secret:
                # Generic response to prevent user enumeration
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP 인증에 실패했습니다"
                )

            # OTP 코드 검증
            is_valid = totp_service.verify_token(pg_user.totp_secret, reset_data.otp_code)
            if not is_valid:
                logger.warning(f"Invalid OTP attempt for password reset")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP 인증에 실패했습니다"
                )

            # 4. 비밀번호 해싱 및 업데이트
            pg_user.password_hash = hash_password(reset_data.new_password)
            await session.commit()

        logger.info(f"Password reset successful via OTP for user: {reset_data.email}")

        return {
            "success": True,
            "message": "비밀번호가 성공적으로 재설정되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP password reset error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_safe_error_message(e, "password reset")
        )



@router.post("/verify-otp-for-reset")
async def verify_otp_for_reset(
    request: Request,
    verify_data: OTPVerifyRequest,
    _: bool = Depends(
        create_rate_limit_dependency(
            max_requests=5,
            window_seconds=300,
            identifier="otp_verify_reset"
        )
    )
):
    """비밀번호 재설정을 위한 OTP 검증 (비밀번호 변경 없이 검증만)

    Args:
        request: FastAPI Request
        verify_data: JSON body with email and otp_code

    Returns:
        검증 성공 시 임시 토큰 반환

    Raises:
        HTTPException: OTP 검증 실패 시
    """
    from ..auth.totp import TOTPService
    from ..database.connection import AsyncSessionFactory
    from ..repositories.user_repository import UserRepository
    from ..services.config_service import config_set_sync

    email = verify_data.email
    otp_code = verify_data.otp_code

    totp_service = TOTPService()

    try:
        # 1. 이메일로 사용자 찾기 (PG)
        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_email(email)

            if not pg_user or not pg_user.totp_secret:
                # Generic response to prevent user enumeration
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP 인증에 실패했습니다"
                )

            # OTP 코드 검증
            is_valid = totp_service.verify_token(pg_user.totp_secret, otp_code)
            if not is_valid:
                logger.warning(f"Invalid OTP attempt for password reset verification")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP 인증에 실패했습니다"
                )

        # 4. 검증 성공 - 임시 토큰 생성 (PG SystemConfig에 저장, 10분 만료)
        reset_token = secrets.token_urlsafe(32)
        import json as _json
        token_data = _json.dumps({"email": email, "expires_at": time.time() + 600})
        config_set_sync(f"otp_reset_token:{reset_token}", token_data)

        logger.info(f"OTP verified for password reset: {email}")

        return {
            "success": True,
            "message": "OTP 검증 성공",
            "reset_token": reset_token,
            "email": email
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_safe_error_message(e, "otp verification")
        )



@router.post("/confirm-password-reset-otp")
async def confirm_password_reset_otp(
    request: Request,
    reset_data: PasswordResetOTPConfirm,
    _: bool = Depends(
        create_rate_limit_dependency(
            max_requests=5,
            window_seconds=300,
            identifier="otp_confirm_reset"
        )
    )
):
    """OTP 검증 후 비밀번호 재설정 (토큰 기반)

    Args:
        request: FastAPI Request
        reset_data: Pydantic validated body with reset_token and new_password

    Returns:
        성공 메시지

    Raises:
        HTTPException: 토큰 검증 실패 또는 비밀번호 업데이트 실패 시
    """
    from ..auth.utils import hash_password
    from ..database.connection import AsyncSessionFactory
    from ..repositories.user_repository import UserRepository
    from ..services.config_service import config_get_sync, config_delete_sync

    # Pydantic 모델로 이미 검증됨 - reset_token과 new_password
    reset_token = reset_data.reset_token
    new_password = reset_data.new_password

    try:
        # 1. 토큰으로 이메일 조회 (PG SystemConfig) + TTL 검증
        import json as _json
        raw_token_data = config_get_sync(f"otp_reset_token:{reset_token}")
        if not raw_token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않거나 만료된 토큰입니다"
            )

        try:
            token_info = _json.loads(raw_token_data)
            email = token_info["email"]
            if time.time() > token_info.get("expires_at", 0):
                config_delete_sync(f"otp_reset_token:{reset_token}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="토큰이 만료되었습니다. 다시 OTP 인증을 해주세요."
                )
        except (_json.JSONDecodeError, KeyError):
            # 레거시 토큰 (plain email) 호환
            email = raw_token_data

        # 비밀번호 강도 검증은 Pydantic 모델에서 이미 수행됨

        # 2. 사용자 찾기 및 비밀번호 업데이트 (PG)
        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_email(email)

            if not pg_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="사용자를 찾을 수 없습니다"
                )

            # 비밀번호 해싱 및 업데이트
            pg_user.password_hash = hash_password(new_password)
            await session.commit()

        # 3. 토큰 삭제 (일회용)
        config_delete_sync(f"otp_reset_token:{reset_token}")

        logger.info(f"Password reset successful via OTP token for user: {email}")

        return {
            "success": True,
            "message": "비밀번호가 성공적으로 재설정되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP token password reset error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_safe_error_message(e, "password reset")
        )


@router.put("/profile")
async def update_profile(
    profile_data: ProfileUpdate,
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """프로필 업데이트

    Args:
        profile_data: 업데이트할 프로필 정보
        request: FastAPI Request
        current_user: 현재 인증된 사용자

    Returns:
        업데이트된 사용자 정보
    """

    auth_service = AuthService()

    try:
        user = await auth_service.update_profile(
            user_id=current_user["user_id"],
            username=profile_data.username
        )

        return {
            "message": "프로필이 업데이트되었습니다",
            "user": user.model_dump()
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """비밀번호 변경

    Args:
        password_data: 현재 비밀번호 및 새 비밀번호
        request: FastAPI Request
        current_user: 현재 인증된 사용자

    Returns:
        성공 메시지
    """

    auth_service = AuthService()

    try:
        await auth_service.change_password(
            user_id=current_user["user_id"],
            old_password=password_data.old_password,
            new_password=password_data.new_password
        )

        return {
            "message": "비밀번호가 변경되었습니다. 모든 세션이 로그아웃되었습니다."
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/sessions", response_model=dict)
async def get_sessions(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """사용자의 모든 활성 세션 조회

    Args:
        request: FastAPI Request
        current_user: 현재 인증된 사용자

    Returns:
        세션 목록
    """

    auth_service = AuthService()

    sessions = await auth_service.get_user_sessions(current_user["user_id"])

    return {
        "sessions": [session.model_dump() for session in sessions]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """특정 세션 무효화

    Args:
        session_id: 무효화할 세션 ID
        request: FastAPI Request
        current_user: 현재 인증된 사용자

    Returns:
        성공 메시지
    """

    auth_service = AuthService()

    try:
        success = await auth_service.revoke_session(
            user_id=current_user["user_id"],
            session_id=session_id
        )

        if success:
            return {
                "message": "세션이 무효화되었습니다"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="세션을 찾을 수 없습니다"
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.delete("/sessions")
async def revoke_all_sessions(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """사용자의 모든 세션 무효화

    Args:
        request: FastAPI Request
        current_user: 현재 인증된 사용자

    Returns:
        무효화된 세션 수
    """

    auth_service = AuthService()

    count = await auth_service.revoke_all_sessions(
        user_id=current_user["user_id"]
    )

    return {
        "message": f"모든 세션이 무효화되었습니다 ({count}개)",
        "revoked_count": count
    }


# ============= Admin Endpoints =============

@router.get("/admin/dashboard")
async def get_admin_dashboard(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    admin_user: dict = Depends(require_admin)
):
    """관리자 대시보드 데이터 (통합 엔드포인트 - 인메모리 캐싱 적용)

    통계, 사용자 목록, 보안 로그를 한 번에 조회하여 네트워크 요청 최적화
    인메모리 캐싱으로 대시보드 응답 속도 최적화 (TTL: 30초)

    Args:
        request: FastAPI Request
        page: 사용자 목록 페이지 번호
        page_size: 페이지당 사용자 수
        admin_user: 관리자 사용자

    Returns:
        통계, 사용자 목록, 보안 로그를 포함한 대시보드 데이터
    """
    import asyncio
    import json
    from loguru import logger

    auth_service = AuthService()

    # 인메모리 캐시 키 (관리자별 + 페이지별로 캐싱)
    admin_id = current_user.get("user_id", "unknown")
    cache_key = f"admin_{admin_id}:page_{page}:size_{page_size}"
    cache_ttl = 30  # 30초 TTL

    # 1. 인메모리 캐시 조회 시도
    cached_entry = _dashboard_cache.get(cache_key)
    if cached_entry:
        cached_time, cached_data = cached_entry
        if (time.time() - cached_time) < cache_ttl:
            return cached_data

    # 2. 캐시 미스 - 데이터 조회 (병렬 실행)
    stats_task = auth_service.get_system_stats()
    users_task = auth_service.get_all_users(page=page, page_size=page_size)
    logs_task = auth_service.get_security_logs(page=1, page_size=100)

    stats, users, logs = await asyncio.gather(stats_task, users_task, logs_task)

    dashboard_data = {
        "stats": stats,
        "users": users,
        "logs": logs,
        "cached": False,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # 3. 인메모리 캐시 저장 (evict oldest if over limit)
    if len(_dashboard_cache) >= _DASHBOARD_CACHE_MAX:
        oldest_key = min(_dashboard_cache, key=lambda k: _dashboard_cache[k][0])
        del _dashboard_cache[oldest_key]
    _dashboard_cache[cache_key] = (time.time(), dashboard_data)

    return dashboard_data


@router.get("/admin/stats")
async def get_admin_stats(
    request: Request,
    admin_user: dict = Depends(require_admin)
):
    """관리자 대시보드 통계

    Args:
        request: FastAPI Request
        admin_user: 관리자 사용자

    Returns:
        시스템 통계 정보
    """
    auth_service = AuthService()
    stats = await auth_service.get_system_stats()
    return stats


@router.get("/admin/users")
async def get_all_users_admin(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    admin_user: dict = Depends(require_admin)
):
    """모든 사용자 조회 (관리자용)

    Args:
        request: FastAPI Request
        page: 페이지 번호
        page_size: 페이지당 사용자 수
        admin_user: 관리자 사용자

    Returns:
        사용자 목록 및 페이지 정보
    """
    auth_service = AuthService()
    result = await auth_service.get_all_users(page=page, page_size=page_size)
    return result


@router.put("/admin/users/{user_id}/status")
async def update_user_status_admin(
    user_id: str,
    is_active: bool,
    request: Request,
    admin_user: dict = Depends(require_admin)
):
    """사용자 활성화 상태 변경 (관리자용)

    Args:
        user_id: 대상 사용자 ID
        is_active: 활성화 상태
        request: FastAPI Request
        admin_user: 관리자 사용자

    Returns:
        업데이트된 사용자 정보
    """
    auth_service = AuthService()
    try:
        user = await auth_service.update_user_status(
            user_id=user_id,
            is_active=is_active,
            admin_user_id=admin_user["user_id"]
        )

        # 대시보드 캐시 무효화 (사용자 상태 변경)
        await invalidate_dashboard_cache()

        return {
            "message": f"사용자가 {'활성화' if is_active else '비활성화'}되었습니다",
            "user": user.model_dump()
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/admin/users/{user_id}/role")
async def update_user_role_admin(
    user_id: str,
    role: str,
    request: Request,
    admin_user: dict = Depends(require_admin)
):
    """사용자 역할 변경 (관리자용)

    Args:
        user_id: 대상 사용자 ID
        role: 새 역할 (user/admin)
        request: FastAPI Request
        admin_user: 관리자 사용자

    Returns:
        업데이트된 사용자 정보
    """
    auth_service = AuthService()

    try:
        user = await auth_service.update_user_role(
            user_id=user_id,
            role=role,
            admin_user_id=admin_user["user_id"]
        )

        # 대시보드 캐시 무효화 (사용자 역할 변경)
        await invalidate_dashboard_cache()

        return {
            "message": "사용자 역할이 변경되었습니다",
            "user": user.model_dump()
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/admin/users/{user_id}")
async def delete_user_admin(
    user_id: str,
    request: Request,
    admin_user: dict = Depends(require_admin)
):
    """사용자 삭제 (관리자용)

    Args:
        user_id: 삭제할 사용자 ID
        request: FastAPI Request
        admin_user: 관리자 사용자

    Returns:
        성공 메시지
    """
    # 자기 자신 삭제 방지
    if user_id == admin_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자기 자신을 삭제할 수 없습니다"
        )

    auth_service = AuthService()

    try:
        await auth_service.delete_user(
            user_id=user_id,
            admin_user_id=admin_user["user_id"]
        )

        # 대시보드 캐시 무효화 (사용자 삭제)
        await invalidate_dashboard_cache()

        return {
            "message": "사용자가 삭제되었습니다"
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/admin/users/{user_id}/password")
async def reset_user_password_admin(
    user_id: str,
    password_data: dict,
    request: Request,
    admin_user: dict = Depends(require_admin)
):
    """사용자 비밀번호 강제 변경 (관리자용)

    Args:
        user_id: 대상 사용자 ID
        password_data: {"new_password": "새비밀번호"}
        request: FastAPI Request
        admin_user: 관리자 사용자

    Returns:
        성공 메시지
    """
    from ..auth.utils import hash_password
    from ..auth.password_policy import PasswordPolicy
    from ..auth.security_logger import SecurityLogger, SecurityEventType, SecurityEventLevel
    from ..utils.ip_utils import IPValidator

    # 자기 자신의 비밀번호 변경 방지 (보안상 일반 비밀번호 변경 사용 권장)
    if user_id == admin_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자기 자신의 비밀번호는 일반 비밀번호 변경 기능을 사용하세요"
        )

    try:
        # 새 비밀번호 가져오기
        new_password = password_data.get("new_password")
        if not new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="새 비밀번호를 입력해주세요"
            )

        # 비밀번호 유효성 검증
        is_valid, errors = PasswordPolicy.validate(new_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"비밀번호 요구사항을 충족하지 않습니다: {', '.join(errors)}"
            )

        # 사용자 존재 확인 및 비밀번호 업데이트 (PG)
        from ..database.connection import SyncSessionFactory
        from ..database.models.user import User as PgUser
        import uuid as uuid_mod

        with SyncSessionFactory() as db_session:
            pg_user = db_session.get(PgUser, uuid_mod.UUID(user_id))
            if not pg_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="사용자를 찾을 수 없습니다"
                )

            # 비밀번호 해싱 및 업데이트
            pg_user.password_hash = hash_password(new_password)
            user_email = pg_user.email or ""
            db_session.commit()
        ip_address = IPValidator.get_client_ip(request, trust_proxy=True)

        # 보안 로그 기록 (실패해도 비밀번호 변경 작업은 성공으로 처리)
        try:
            SecurityLogger.log_event(
                event_type=SecurityEventType.PASSWORD_RESET_BY_ADMIN,
                level=SecurityEventLevel.WARNING,
                user_id=user_id,
                ip_address=ip_address,
                message=f"Password reset by admin {admin_user['email']} for user {user_email}",
                admin_id=admin_user["user_id"],
                admin_email=admin_user["email"],
                target_user_email=user_email
            )
        except Exception as log_error:
            # 로깅 실패는 경고만 하고 계속 진행
            logger.warning(f"Failed to log security event: {log_error}")

        logger.info(f"Password reset by admin {admin_user['email']} for user {user_email}")

        return {
            "message": "사용자 비밀번호가 변경되었습니다",
            "user_email": user_email
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset user password: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_safe_error_message(e, "admin password reset")
        )


@router.get("/admin/security-logs")
async def get_security_logs_admin(
    request: Request,
    page: int = 1,
    page_size: int = 100,
    level: Optional[str] = None,
    event_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    admin_user: dict = Depends(require_admin)
):
    """보안 로그 조회 (관리자용)

    Args:
        request: FastAPI Request
        page: 페이지 번호
        page_size: 페이지당 로그 수
        level: 로그 레벨 필터
        event_type: 이벤트 타입 필터
        start_time: 시작 시간 (ISO 8601 형식, 기본: 24시간 전)
        end_time: 종료 시간 (ISO 8601 형식, 기본: 현재)
        admin_user: 관리자 사용자

    Returns:
        보안 로그 목록
    """
    from loguru import logger
    logger.debug(f"Security logs request - event_type: {event_type}, level: {level}, page: {page}")

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


@router.get("/admin/login-history")
async def get_login_history_admin(
    request: Request,
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    status: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    admin_user: dict = Depends(require_admin)
):
    """로그인 히스토리 조회 (관리자용)

    Args:
        request: FastAPI Request
        user_id: 사용자 ID (선택, None이면 전체 조회)
        page: 페이지 번호
        page_size: 페이지당 레코드 수
        status: 로그인 상태 필터 (success/failed/blocked)
        start_time: 시작 시간 (ISO 8601 형식, 기본: 7일 전)
        end_time: 종료 시간 (ISO 8601 형식, 기본: 현재)
        admin_user: 관리자 사용자

    Returns:
        로그인 히스토리 목록
    """
    auth_service = AuthService()
    result = await auth_service.get_login_history(
        user_id=user_id,
        page=page,
        page_size=page_size,
        status=status,
        start_time=start_time,
        end_time=end_time
    )
    return result


# ============================================================================
# 웹훅 관리 API
# ============================================================================

@router.post("/webhooks", response_model=Webhook, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    request: Request,
    webhook_data: WebhookCreate,
    current_user: dict = Depends(get_current_active_user)
):
    """웹훅 생성

    Args:
        request: FastAPI Request
        webhook_data: 웹훅 생성 데이터
        current_user: 현재 사용자

    Returns:
        생성된 웹훅
    """
    webhook_service = WebhookService()
    webhook = await webhook_service.create_webhook(
        webhook_data=webhook_data,
        user_id=current_user["user_id"]
    )
    return webhook


@router.get("/webhooks", response_model=List[Webhook])
async def list_webhooks(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """웹훅 목록 조회

    Args:
        request: FastAPI Request
        current_user: 현재 사용자

    Returns:
        웹훅 목록
    """
    webhook_service = WebhookService()
    webhooks = await webhook_service.list_webhooks(user_id=current_user["user_id"])
    return webhooks


@router.get("/webhooks/{webhook_id}", response_model=Webhook)
async def get_webhook(
    request: Request,
    webhook_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """웹훅 상세 조회

    Args:
        request: FastAPI Request
        webhook_id: 웹훅 ID
        current_user: 현재 사용자

    Returns:
        웹훅 상세 정보
    """
    webhook_service = WebhookService()
    webhook = await webhook_service.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="웹훅을 찾을 수 없습니다"
        )

    if webhook.created_by != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="웹훅에 대한 권한이 없습니다"
        )

    return webhook


@router.put("/webhooks/{webhook_id}", response_model=Webhook)
async def update_webhook(
    request: Request,
    webhook_id: str,
    webhook_data: WebhookUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    """웹훅 업데이트

    Args:
        request: FastAPI Request
        webhook_id: 웹훅 ID
        webhook_data: 업데이트 데이터
        current_user: 현재 사용자

    Returns:
        업데이트된 웹훅
    """
    webhook_service = WebhookService()
    webhook = await webhook_service.update_webhook(
        webhook_id=webhook_id,
        webhook_data=webhook_data,
        user_id=current_user["user_id"]
    )

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="웹훅을 찾을 수 없거나 권한이 없습니다"
        )

    return webhook


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    request: Request,
    webhook_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """웹훅 삭제

    Args:
        request: FastAPI Request
        webhook_id: 웹훅 ID
        current_user: 현재 사용자

    Returns:
        삭제 성공 메시지
    """
    webhook_service = WebhookService()
    deleted = await webhook_service.delete_webhook(
        webhook_id=webhook_id,
        user_id=current_user["user_id"]
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="웹훅을 찾을 수 없거나 권한이 없습니다"
        )

    return {"message": "웹훅이 삭제되었습니다"}


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookDelivery)
async def test_webhook(
    request: Request,
    webhook_id: str,
    test_data: WebhookTestRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """웹훅 테스트

    Args:
        request: FastAPI Request
        webhook_id: 웹훅 ID
        test_data: 테스트 데이터
        current_user: 현재 사용자

    Returns:
        전송 기록
    """
    webhook_service = WebhookService()

    try:
        delivery = await webhook_service.test_webhook(
            webhook_id=webhook_id,
            event_type=test_data.event_type,
            user_id=current_user["user_id"]
        )
        return delivery

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/webhooks/{webhook_id}/deliveries", response_model=List[WebhookDelivery])
async def get_webhook_deliveries(
    request: Request,
    webhook_id: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_active_user)
):
    """웹훅 전송 기록 조회

    Args:
        request: FastAPI Request
        webhook_id: 웹훅 ID
        limit: 최대 개수
        current_user: 현재 사용자

    Returns:
        전송 기록 목록
    """
    webhook_service = WebhookService()
    deliveries = await webhook_service.get_delivery_logs(
        webhook_id=webhook_id,
        user_id=current_user["user_id"],
        limit=limit
    )
    return deliveries


# ============= CAPTCHA Generation =============

@router.get("/captcha/generate")
async def generate_captcha(request: Request, action: str = "login"):
    """CAPTCHA 생성

    내부망용 이미지 기반 수학 문제 CAPTCHA를 생성합니다.

    Args:
        action: 'login' 또는 'register'

    Returns:
        {
            "captcha_id": str,   # CAPTCHA 고유 ID
            "image": str,        # Base64 인코딩된 이미지 (data:image/png;base64,...)
            "enabled": bool      # CAPTCHA 활성화 여부
        }
    """
    try:
        from ..auth.captcha import SimpleCaptchaService

        captcha_service = SimpleCaptchaService()

        # CAPTCHA 비활성화 시 빈 응답
        if not captcha_service.is_enabled(action):
            return {
                "captcha_id": "",
                "image": "",
                "enabled": False
            }

        # CAPTCHA 생성
        captcha = captcha_service.generate_captcha()

        return {
            "captcha_id": captcha["captcha_id"],
            "image": captcha["image"],
            "enabled": True
        }

    except Exception as e:
        logger.error(f"Failed to generate CAPTCHA: {e}")
        # 에러 시에도 CAPTCHA 비활성화로 처리 (fail-open)
        return {
            "captcha_id": "",
            "image": "",
            "enabled": False
        }

