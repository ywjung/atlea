"""Authentication API routes

FastAPI router for user registration, login, logout, and user management.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import time
import secrets
from loguru import logger
from ..auth.models import (
    UserCreate, UserLogin, LoginResponse, TokenPair,
    PasswordReset, PasswordResetConfirm, PasswordResetOTP, ProfileUpdate, PasswordChange, Session,
    WebhookCreate, WebhookUpdate, Webhook, WebhookEvent, WebhookTestRequest, WebhookDelivery
)
from ..auth.service import AuthService
from ..auth.webhook_service import WebhookService
from ..auth.middleware import get_current_active_user, require_admin
from ..auth.rate_limiter import create_rate_limit_dependency, RateLimitConfig

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============= Cache Invalidation Helper =============

async def invalidate_dashboard_cache(redis):
    """대시보드 캐시 무효화

    사용자 데이터가 변경되었을 때 모든 대시보드 캐시를 삭제합니다.

    Args:
        redis: Redis 클라이언트
    """
    try:
        from loguru import logger
        pattern = "dashboard_cache:*"
        cursor = 0
        invalidated_count = 0

        # 모든 대시보드 캐시 키 찾아서 삭제
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)

            for key in keys:
                await redis.delete(key)
                invalidated_count += 1

            if cursor == 0:
                break

        if invalidated_count > 0:
            logger.info(f"🗑️  Invalidated {invalidated_count} dashboard cache entries")
    except Exception as e:
        from loguru import logger
        logger.error(f"Failed to invalidate dashboard cache: {e}")


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
        # 비밀번호 재설정 링크 생성
        # 프로덕션에서는 실제 도메인으로 변경 필요
        reset_link = f"http://localhost:8000/static/reset-password.html?token={reset_token}"

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
        redis = request.app.state.cache_manager.redis
        totp_service = TOTPService(redis)

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
    from loguru import logger
    logger.debug(f"app.state has cache_manager: {hasattr(request.app.state, 'cache_manager')}")
    if hasattr(request.app.state, 'cache_manager'):
        logger.debug(f"cache_manager.redis is None: {request.app.state.cache_manager.redis is None}")

    auth_service = AuthService(request.app.state.cache_manager.redis)
    redis = request.app.state.cache_manager.redis

    # CAPTCHA 검증 (회원가입)
    from ..auth.captcha import SimpleCaptchaService
    captcha_service = SimpleCaptchaService(redis)
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
        await invalidate_dashboard_cache(redis)

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

    auth_service = AuthService(request.app.state.cache_manager.redis)
    redis = request.app.state.cache_manager.redis

    try:
        # IP 주소 추출
        ip_address = request.client.host if request.client else None

        # 디버깅: 받은 자격증명 로깅 (비밀번호는 길이만)
        logger.debug(f"🔍 Login attempt - email: {credentials.email}, password_length: {len(credentials.password)}, ip: {ip_address}")

        # CAPTCHA 검증 (로그인)
        from ..auth.captcha import SimpleCaptchaService
        captcha_service = SimpleCaptchaService(redis)
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
            time.sleep((min_response_time_ms - elapsed_ms) / 1000)


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

    auth_service = AuthService(request.app.state.cache_manager.redis)

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
                    blacklist = TokenBlacklist(request.app.state.cache_manager.redis)
                    blacklist.add_token(token, config.SECRET_KEY, reason="logout")

                    # 사용자의 모든 활성 세션 조회 및 삭제
                    session_ids = request.app.state.cache_manager.redis.smembers(
                        f"user:sessions:{user_id}"
                    )

                    for session_id in session_ids:
                        session_id_str = session_id.decode() if isinstance(session_id, bytes) else session_id
                        await auth_service.logout(
                            session_id_str,
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

    auth_service = AuthService(request.app.state.cache_manager.redis)

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

    auth_service = AuthService(request.app.state.cache_manager.redis)

    try:
        reset_token = await auth_service.request_password_reset(reset_request.email)

        # SMTP 설정 확인 및 이메일 전송
        from ..email_service import get_email_service

        redis = request.app.state.cache_manager.redis
        email_service = get_email_service(redis)

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
                # 이메일 전송 실패 시 토큰 반환 (폴백)
                logger.warning(f"Failed to send password reset email to {reset_request.email}, returning token")
                return {
                    "message": "이메일 전송에 실패했습니다. 아래 토큰을 사용하세요",
                    "reset_token": reset_token,
                    "email_sent": False
                }
        else:
            # SMTP 미설정 시 토큰 반환
            return {
                "message": "비밀번호 재설정 토큰이 발급되었습니다",
                "reset_token": reset_token,
                "email_sent": False
            }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    request: Request
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

    auth_service = AuthService(request.app.state.cache_manager.redis)

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
    request: Request
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

    redis = request.app.state.cache_manager.redis
    totp_service = TOTPService(redis)

    try:
        # 1. 이메일로 사용자 찾기
        user_id = redis.get(f"user:email:{reset_data.email}")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )

        user_id = user_id.decode() if isinstance(user_id, bytes) else user_id

        # 사용자 데이터 조회
        user_data = redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )

        # bytes를 문자열로 변환
        user = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in user_data.items()
        }

        # 2. 사용자에게 OTP가 설정되어 있는지 확인
        if not user.get("totp_secret"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="해당 계정에 OTP가 설정되지 않았습니다"
            )

        # 3. OTP 코드 검증
        is_valid = totp_service.verify_token(user["totp_secret"], reset_data.otp_code)
        if not is_valid:
            logger.warning(f"Invalid OTP attempt for user: {reset_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OTP 코드가 일치하지 않습니다"
            )

        # 4. 비밀번호 해싱 및 업데이트
        password_hash_value = hash_password(reset_data.new_password)
        redis.hset(f"user:{user_id}", "password_hash", password_hash_value)

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
            detail=f"비밀번호 재설정 중 오류가 발생했습니다: {str(e)}"
        )



@router.post("/verify-otp-for-reset")
async def verify_otp_for_reset(
    request: Request,
    verify_data: dict
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

    # Extract data from JSON body
    email = verify_data.get("email")
    otp_code = verify_data.get("otp_code")

    if not email or not otp_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이메일과 OTP 코드는 필수입니다"
        )

    redis = request.app.state.cache_manager.redis
    totp_service = TOTPService(redis)

    try:
        # 1. 이메일로 사용자 찾기
        user_id = redis.get(f"user:email:{email}")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )

        user_id = user_id.decode() if isinstance(user_id, bytes) else user_id

        # 사용자 데이터 조회
        user_data = redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )

        # bytes를 문자열로 변환
        user = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in user_data.items()
        }

        # 2. 사용자에게 OTP가 설정되어 있는지 확인
        if not user.get("totp_secret"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="해당 계정에 OTP가 설정되지 않았습니다"
            )

        # 3. OTP 코드 검증
        is_valid = totp_service.verify_token(user["totp_secret"], otp_code)
        if not is_valid:
            logger.warning(f"Invalid OTP attempt for password reset: {email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OTP 코드가 일치하지 않습니다"
            )

        # 4. 검증 성공 - 임시 토큰 생성 (5분 유효)
        reset_token = secrets.token_urlsafe(32)
        redis.setex(
            f"otp_reset_token:{reset_token}",
            300,  # 5분
            email
        )

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
            detail=f"OTP 검증 중 오류가 발생했습니다: {str(e)}"
        )



@router.post("/confirm-password-reset-otp")
async def confirm_password_reset_otp(
    request: Request,
    reset_data: dict
):
    """OTP 검증 후 비밀번호 재설정 (토큰 기반)

    Args:
        request: FastAPI Request
        reset_data: JSON body with reset_token and new_password

    Returns:
        성공 메시지

    Raises:
        HTTPException: 토큰 검증 실패 또는 비밀번호 업데이트 실패 시
    """
    from ..auth.models import validate_password_strength
    from ..auth.utils import hash_password

    # Extract data from JSON body
    reset_token = reset_data.get("reset_token")
    new_password = reset_data.get("new_password")

    if not reset_token or not new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="재설정 토큰과 새 비밀번호는 필수입니다"
        )

    redis = request.app.state.cache_manager.redis

    try:
        # 1. 토큰으로 이메일 조회
        email = redis.get(f"otp_reset_token:{reset_token}")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않거나 만료된 토큰입니다"
            )

        email = email.decode() if isinstance(email, bytes) else email

        # 2. 비밀번호 강도 검증
        try:
            validate_password_strength(new_password)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

        # 3. 사용자 찾기
        user_id = redis.get(f"user:email:{email}")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="사용자를 찾을 수 없습니다"
            )

        user_id = user_id.decode() if isinstance(user_id, bytes) else user_id

        # 4. 비밀번호 해싱 및 업데이트
        password_hash = hash_password(new_password)
        redis.hset(f"user:{user_id}", "password_hash", password_hash)

        # 5. 토큰 삭제 (일회용)
        redis.delete(f"otp_reset_token:{reset_token}")

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
            detail=f"비밀번호 재설정 중 오류가 발생했습니다: {str(e)}"
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

    auth_service = AuthService(request.app.state.cache_manager.redis)

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

    auth_service = AuthService(request.app.state.cache_manager.redis)

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

    auth_service = AuthService(request.app.state.cache_manager.redis)

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

    auth_service = AuthService(request.app.state.cache_manager.redis)

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

    auth_service = AuthService(request.app.state.cache_manager.redis)

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
    """관리자 대시보드 데이터 (통합 엔드포인트 - Redis 캐싱 적용)

    통계, 사용자 목록, 보안 로그를 한 번에 조회하여 네트워크 요청 최적화
    Redis 캐싱으로 대시보드 응답 속도 최적화 (TTL: 30초)

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

    auth_service = AuthService(request.app.state.cache_manager.redis)
    redis = request.app.state.cache_manager.redis

    # 캐시 키 생성 (페이지별로 캐싱)
    cache_key = f"dashboard_cache:page_{page}:size_{page_size}"
    cache_ttl = 30  # 30초 TTL

    # 1. 캐시 조회 시도
    try:
        cached_data = redis.get(cache_key)
        if cached_data:
            logger.info(f"✅ Dashboard cache HIT: {cache_key}")
            # Decode bytes to string if needed
            if isinstance(cached_data, bytes):
                cached_data = cached_data.decode('utf-8')
            return json.loads(cached_data)
        else:
            logger.info(f"❌ Dashboard cache MISS: {cache_key}")
    except Exception as e:
        logger.warning(f"Cache read failed, proceeding without cache: {e}")

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
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }

    # 3. 캐시 저장
    try:
        redis.setex(
            cache_key,
            cache_ttl,
            json.dumps(dashboard_data, ensure_ascii=False, default=str)
        )
        logger.info(f"💾 Dashboard cached: {cache_key} (TTL: {cache_ttl}s)")
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")

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
    auth_service = AuthService(request.app.state.cache_manager.redis)
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
    auth_service = AuthService(request.app.state.cache_manager.redis)
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
    auth_service = AuthService(request.app.state.cache_manager.redis)
    redis = request.app.state.cache_manager.redis

    try:
        user = await auth_service.update_user_status(
            user_id=user_id,
            is_active=is_active,
            admin_user_id=admin_user["user_id"]
        )

        # 대시보드 캐시 무효화 (사용자 상태 변경)
        await invalidate_dashboard_cache(redis)

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
    auth_service = AuthService(request.app.state.cache_manager.redis)
    redis = request.app.state.cache_manager.redis

    try:
        user = await auth_service.update_user_role(
            user_id=user_id,
            role=role,
            admin_user_id=admin_user["user_id"]
        )

        # 대시보드 캐시 무효화 (사용자 역할 변경)
        await invalidate_dashboard_cache(redis)

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

    auth_service = AuthService(request.app.state.cache_manager.redis)
    redis = request.app.state.cache_manager.redis

    try:
        await auth_service.delete_user(
            user_id=user_id,
            admin_user_id=admin_user["user_id"]
        )

        # 대시보드 캐시 무효화 (사용자 삭제)
        await invalidate_dashboard_cache(redis)

        return {
            "message": "사용자가 삭제되었습니다"
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
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
    auth_service = AuthService(request.app.state.cache_manager.redis)
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
    webhook_service = WebhookService(request.app.state.cache_manager.redis)
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
    webhook_service = WebhookService(request.app.state.cache_manager.redis)
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
    webhook_service = WebhookService(request.app.state.cache_manager.redis)
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
    webhook_service = WebhookService(request.app.state.cache_manager.redis)
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
    webhook_service = WebhookService(request.app.state.cache_manager.redis)
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
    webhook_service = WebhookService(request.app.state.cache_manager.redis)

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
    webhook_service = WebhookService(request.app.state.cache_manager.redis)
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

        redis = request.app.state.cache_manager.redis
        captcha_service = SimpleCaptchaService(redis)

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

