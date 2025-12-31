"""Google reCAPTCHA v3 Verification

봇 공격 방지를 위한 CAPTCHA 검증 시스템.
관리자 페이지에서 활성화/비활성화 가능.
"""

import os
import httpx
from typing import Optional
from redis import Redis
from loguru import logger


class CaptchaService:
    """Google reCAPTCHA v3 검증 서비스"""

    # Google reCAPTCHA 검증 API
    VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

    # reCAPTCHA v3 점수 임계값 (0.0 ~ 1.0)
    # 0.5 이상: 사람일 가능성이 높음
    # 0.3 ~ 0.5: 의심스러운 활동
    # 0.3 미만: 봇일 가능성이 높음
    SCORE_THRESHOLD = 0.5

    def __init__(self, redis_client: Redis):
        """초기화

        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client
        self.secret_key = os.getenv("RECAPTCHA_SECRET_KEY")

        if not self.secret_key:
            logger.warning(
                "RECAPTCHA_SECRET_KEY not configured. "
                "CAPTCHA verification will be disabled."
            )

    def is_enabled(self) -> bool:
        """CAPTCHA 활성화 여부 확인 (Redis 설정)

        Returns:
            bool: CAPTCHA 활성화 여부
        """
        try:
            enabled_str = self.redis.get("config:captcha_enabled")
            if enabled_str is not None:
                return enabled_str.decode() == "true"

            # 기본값: 비활성화 (관리자가 명시적으로 활성화해야 함)
            return False

        except Exception as e:
            logger.warning(f"Failed to check CAPTCHA enabled status: {e}")
            # Redis 오류 시 안전을 위해 비활성화
            return False

    async def verify_token(
        self,
        token: str,
        remote_ip: Optional[str] = None,
        action: str = "login"
    ) -> tuple[bool, Optional[str]]:
        """reCAPTCHA 토큰 검증

        Args:
            token: 클라이언트에서 받은 reCAPTCHA 토큰
            remote_ip: 클라이언트 IP 주소 (선택)
            action: 검증할 액션 (login, register 등)

        Returns:
            (success, error_message) tuple
            - success: 검증 성공 여부
            - error_message: 실패 시 에러 메시지, 성공 시 None
        """
        # CAPTCHA 비활성화 상태면 항상 성공
        if not self.is_enabled():
            logger.debug("CAPTCHA is disabled, skipping verification")
            return True, None

        # Secret key 미설정 시 실패
        if not self.secret_key:
            logger.error("RECAPTCHA_SECRET_KEY not configured")
            return False, "CAPTCHA 설정이 올바르지 않습니다"

        # 토큰 없음
        if not token:
            logger.warning("CAPTCHA token is missing")
            return False, "CAPTCHA 토큰이 필요합니다"

        try:
            # Google reCAPTCHA API 호출
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.VERIFY_URL,
                    data={
                        "secret": self.secret_key,
                        "response": token,
                        "remoteip": remote_ip
                    },
                    timeout=5.0
                )

                if response.status_code != 200:
                    logger.error(
                        f"reCAPTCHA API error: {response.status_code}"
                    )
                    return False, "CAPTCHA 검증 중 오류가 발생했습니다"

                result = response.json()

                # 검증 실패
                if not result.get("success"):
                    error_codes = result.get("error-codes", [])
                    logger.warning(
                        f"reCAPTCHA verification failed: {error_codes}"
                    )
                    return False, "CAPTCHA 검증에 실패했습니다"

                # 점수 확인 (v3만 해당)
                score = result.get("score", 0.0)
                if score < self.SCORE_THRESHOLD:
                    logger.warning(
                        f"reCAPTCHA score too low: {score} "
                        f"(threshold: {self.SCORE_THRESHOLD})"
                    )
                    return False, "의심스러운 활동이 감지되었습니다"

                # 액션 확인 (v3만 해당)
                response_action = result.get("action", "")
                if response_action != action:
                    logger.warning(
                        f"reCAPTCHA action mismatch: "
                        f"expected={action}, got={response_action}"
                    )
                    return False, "CAPTCHA 검증에 실패했습니다"

                logger.info(
                    f"reCAPTCHA verification successful: "
                    f"score={score}, action={action}"
                )
                return True, None

        except httpx.TimeoutException:
            logger.error("reCAPTCHA API timeout")
            # 타임아웃 시 일시적 오류로 처리 (fail-open 정책)
            return True, None

        except Exception as e:
            logger.error(f"reCAPTCHA verification error: {e}", exc_info=True)
            # 예외 발생 시 일시적 오류로 처리 (fail-open 정책)
            return True, None


# CAPTCHA 설정 헬퍼 함수
def set_captcha_enabled(redis_client: Redis, enabled: bool) -> bool:
    """CAPTCHA 활성화 상태 설정

    Args:
        redis_client: Redis 클라이언트
        enabled: 활성화 여부

    Returns:
        성공 여부
    """
    try:
        redis_client.set(
            "config:captcha_enabled",
            "true" if enabled else "false"
        )
        logger.info(f"CAPTCHA enabled status set to: {enabled}")
        return True

    except Exception as e:
        logger.error(f"Failed to set CAPTCHA enabled status: {e}")
        return False


def get_captcha_config(redis_client: Redis) -> dict:
    """CAPTCHA 설정 조회

    Args:
        redis_client: Redis 클라이언트

    Returns:
        {
            "enabled": bool,
            "site_key": str (환경변수에서 가져옴)
        }
    """
    try:
        enabled_str = redis_client.get("config:captcha_enabled")
        enabled = enabled_str.decode() == "true" if enabled_str else False

        site_key = os.getenv("RECAPTCHA_SITE_KEY", "")

        return {
            "enabled": enabled,
            "site_key": site_key,
            "configured": bool(os.getenv("RECAPTCHA_SECRET_KEY"))
        }

    except Exception as e:
        logger.error(f"Failed to get CAPTCHA config: {e}")
        return {
            "enabled": False,
            "site_key": "",
            "configured": False
        }
