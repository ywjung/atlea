"""Password Reset Configuration

비밀번호 재설정 방식 설정 관리
"""
from redis import Redis
from typing import Literal, Dict
from loguru import logger

PasswordResetMethod = Literal["email", "otp", "admin"]


def get_password_reset_config(redis_client: Redis) -> Dict[str, any]:
    """비밀번호 재설정 설정 조회

    Args:
        redis_client: Redis 클라이언트

    Returns:
        설정 정보 딕셔너리
    """
    # Redis에서 설정 조회 (기본값: admin)
    method_bytes = redis_client.get("config:password_reset:method")
    method = method_bytes.decode() if method_bytes else "admin"

    # 이메일 방식 사용 가능 여부 확인
    from ..email_service import get_email_service
    email_service = get_email_service()
    email_configured = email_service.is_configured()

    return {
        "method": method,  # "email", "otp", 또는 "admin"
        "email_configured": email_configured,
        "description": {
            "email": "이메일로 재설정 링크 전송",
            "otp": "구글 OTP로 본인 인증 후 재설정",
            "admin": "관리자가 임시 비밀번호를 생성하여 사용자에게 전달"
        }
    }


def set_password_reset_method(
    redis_client: Redis,
    method: PasswordResetMethod
) -> bool:
    """비밀번호 재설정 방식 설정

    Args:
        redis_client: Redis 클라이언트
        method: 재설정 방식 ("email", "otp", 또는 "admin")

    Returns:
        설정 성공 여부
    """
    if method not in ["email", "otp", "admin"]:
        logger.error(f"잘못된 비밀번호 재설정 방식: {method}")
        return False

    # 이메일 방식인데 SMTP가 설정되지 않았으면 경고
    if method == "email":
        from ..email_service import get_email_service
        email_service = get_email_service()
        if not email_service.is_configured():
            logger.warning(
                "SMTP가 설정되지 않았습니다. "
                "이메일 방식을 사용하려면 환경 변수를 설정하세요"
            )
            # 그래도 설정은 저장 (나중에 SMTP 설정 후 사용 가능)

    try:
        redis_client.set("config:password_reset:method", method)
        logger.info(f"비밀번호 재설정 방식 설정: {method}")
        return True
    except Exception as e:
        logger.error(f"비밀번호 재설정 방식 설정 실패: {e}")
        return False
