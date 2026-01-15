"""TOTP (Time-based One-Time Password) Service

Google Authenticator 호환 2차 인증 시스템.
"""

import pyotp
import qrcode
import io
import base64
from typing import Optional, Tuple
from redis import Redis
from loguru import logger


class TOTPService:
    """TOTP 기반 2차 인증 서비스

    Features:
    - Secret key 생성 및 관리
    - QR 코드 생성 (Google Authenticator 호환)
    - TOTP 코드 검증
    - Redis 기반 2FA 활성화 설정
    """

    def __init__(self, redis_client: Redis):
        """초기화

        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client

    def is_enabled(self) -> bool:
        """2FA 활성화 여부 확인 (Redis 설정)

        Returns:
            bool: 2FA 활성화 여부
        """
        try:
            enabled_str = self.redis.get("config:totp_enabled")
            if enabled_str is not None:
                return enabled_str.decode() == "true"

            # 기본값: 비활성화
            return False

        except Exception as e:
            logger.warning(f"Failed to check 2FA enabled status: {e}")
            return False

    def generate_secret(self) -> str:
        """TOTP Secret Key 생성

        Returns:
            str: Base32 인코딩된 Secret Key
        """
        return pyotp.random_base32()

    def generate_qr_code(
        self,
        secret: str,
        email: str,
        issuer: str = "AI Chatbot"
    ) -> str:
        """QR 코드 생성

        Args:
            secret: TOTP Secret Key
            email: 사용자 이메일
            issuer: 발급자 이름 (앱에 표시됨)

        Returns:
            Base64로 인코딩된 QR 코드 이미지 (data:image/png;base64,...)
        """
        try:
            # TOTP URI 생성
            totp = pyotp.TOTP(secret)
            uri = totp.provisioning_uri(
                name=email,
                issuer_name=issuer
            )

            # QR 코드 생성
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(uri)
            qr.make(fit=True)

            # 이미지 생성
            img = qr.make_image(fill_color="black", back_color="white")

            # Base64 인코딩
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return f"data:image/png;base64,{img_base64}"

        except Exception as e:
            logger.error(f"Failed to generate QR code: {e}", exc_info=True)
            return ""

    def verify_token(
        self,
        secret: str,
        token: str,
        window: int = 1
    ) -> bool:
        """TOTP 토큰 검증

        Args:
            secret: TOTP Secret Key
            token: 사용자가 입력한 6자리 코드
            window: 허용할 시간 창 (기본 1 = ±30초)

        Returns:
            bool: 검증 성공 여부
        """
        try:
            if not secret or not token:
                return False

            totp = pyotp.TOTP(secret)

            # 토큰 검증 (시간 오차 허용)
            return totp.verify(token, valid_window=window)

        except Exception as e:
            logger.error(f"Failed to verify TOTP token: {e}")
            return False

    def get_current_token(self, secret: str) -> str:
        """현재 TOTP 토큰 생성 (테스트용)

        Args:
            secret: TOTP Secret Key

        Returns:
            str: 현재 6자리 TOTP 코드
        """
        try:
            totp = pyotp.TOTP(secret)
            return totp.now()
        except Exception as e:
            logger.error(f"Failed to generate current token: {e}")
            return ""


# TOTP 설정 헬퍼 함수
def set_totp_enabled(redis_client: Redis, enabled: bool) -> bool:
    """2FA 활성화 상태 설정

    Args:
        redis_client: Redis 클라이언트
        enabled: 2FA 활성화 여부

    Returns:
        성공 여부
    """
    try:
        redis_client.set(
            "config:totp_enabled",
            "true" if enabled else "false"
        )
        logger.info(f"2FA enabled status set to: {enabled}")
        return True

    except Exception as e:
        logger.error(f"Failed to set 2FA enabled status: {e}")
        return False


def get_totp_config(redis_client: Redis) -> dict:
    """2FA 설정 조회

    Args:
        redis_client: Redis 클라이언트

    Returns:
        {
            "enabled": bool,
            "type": "totp",
            "configured": bool
        }
    """
    try:
        enabled_str = redis_client.get("config:totp_enabled")
        enabled = enabled_str.decode() == "true" if enabled_str else False

        return {
            "enabled": enabled,
            "type": "totp",
            "configured": True  # TOTP는 항상 설정 가능
        }

    except Exception as e:
        logger.error(f"Failed to get 2FA config: {e}")
        return {
            "enabled": False,
            "type": "totp",
            "configured": False
        }
