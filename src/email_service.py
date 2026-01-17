"""Email Service for Password Reset

이메일 전송 서비스 (SMTP)
"""
import smtplib
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from loguru import logger
from redis import Redis


# SMTP 설정 캐시 (TTL 기반)
_smtp_settings_cache: dict = {}
_smtp_settings_cache_time: float = 0
SMTP_SETTINGS_CACHE_TTL = 300  # 5분 캐시


class EmailService:
    """이메일 전송 서비스"""

    def __init__(self, redis_client: Optional[Redis] = None):
        """SMTP 설정 로드 (Redis 우선, 환경 변수 대체)

        Args:
            redis_client: Redis 클라이언트 (선택적)
        """
        self.redis = redis_client
        self._load_settings()

    def _load_settings(self):
        """SMTP 설정 로드 (Redis > 환경 변수)"""
        # Redis에서 설정 로드 시도
        if self.redis:
            try:
                smtp_settings = self.redis.hgetall("smtp:settings")
                if smtp_settings:
                    # Redis에서 로드
                    self.smtp_host = smtp_settings.get(b"host", b"smtp.gmail.com").decode()
                    self.smtp_port = int(smtp_settings.get(b"port", b"587").decode())
                    self.smtp_username = smtp_settings.get(b"username", b"").decode()
                    self.smtp_password = smtp_settings.get(b"password", b"").decode()
                    self.from_email = smtp_settings.get(b"from_email", self.smtp_username.encode()).decode()
                    self.from_name = smtp_settings.get(b"from_name", b"AI Chatbot").decode()
                    logger.info("SMTP 설정을 Redis에서 로드했습니다")
                    return
            except Exception as e:
                logger.warning(f"Redis에서 SMTP 설정 로드 실패, 환경 변수 사용: {e}")

        # 환경 변수에서 로드 (대체)
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_username)
        self.from_name = os.getenv("SMTP_FROM_NAME", "AI Chatbot")

    def reload_settings(self):
        """설정 다시 로드"""
        self._load_settings()

    def is_configured(self) -> bool:
        """SMTP 설정이 완료되었는지 확인

        Returns:
            설정 완료 여부
        """
        return bool(self.smtp_username and self.smtp_password)

    def send_password_reset_otp(self, to_email: str, otp_code: str) -> bool:
        """비밀번호 재설정 OTP 이메일 전송

        Args:
            to_email: 수신자 이메일
            otp_code: OTP 코드

        Returns:
            전송 성공 여부
        """
        if not self.is_configured():
            logger.warning("SMTP가 설정되지 않아 이메일을 전송할 수 없습니다")
            return False

        subject = "비밀번호 재설정 인증 코드"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px; text-align: center;">
                <h1 style="color: white; margin: 0;">🔐 비밀번호 재설정</h1>
            </div>

            <div style="background: #f8f9fa; padding: 30px; border-radius: 10px; margin-top: 20px;">
                <p style="font-size: 16px; color: #333;">비밀번호 재설정을 요청하셨습니다.</p>
                <p style="font-size: 16px; color: #333;">아래 인증 코드를 입력하여 비밀번호를 재설정하세요:</p>

                <div style="background: white; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <div style="font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                        {otp_code}
                    </div>
                </div>

                <p style="font-size: 14px; color: #666;">
                    ⏰ 이 코드는 <strong>10분간</strong> 유효합니다.
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

        try:
            return self._send_email(to_email, subject, html_body)
        except Exception as e:
            logger.error(f"OTP 이메일 전송 실패: {e}")
            return False

    def _send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        """이메일 전송 (내부 메서드)

        Args:
            to_email: 수신자 이메일
            subject: 제목
            html_body: HTML 본문

        Returns:
            전송 성공 여부
        """
        try:
            # 메시지 생성
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email

            # HTML 본문 추가
            html_part = MIMEText(html_body, "html", "utf-8")
            message.attach(html_part)

            # SMTP 서버 연결 및 전송
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()  # TLS 암호화
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(message)

            logger.info(f"이메일 전송 성공: {to_email}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP 인증 실패: 사용자명 또는 비밀번호를 확인하세요")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP 에러: {e}")
            return False
        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False


# 싱글톤 인스턴스
_email_service = None


def get_email_service(redis_client: Optional[Redis] = None) -> EmailService:
    """이메일 서비스 싱글톤 인스턴스 반환

    Args:
        redis_client: Redis 클라이언트 (선택적)

    Returns:
        EmailService 인스턴스
    """
    global _email_service
    if _email_service is None:
        _email_service = EmailService(redis_client)
    elif redis_client and _email_service.redis is None:
        _email_service.redis = redis_client
        _email_service.reload_settings()
    return _email_service


def save_smtp_settings(
    redis_client: Redis,
    host: str,
    port: int,
    username: str,
    password: str,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None
) -> bool:
    """SMTP 설정을 Redis에 저장

    Args:
        redis_client: Redis 클라이언트
        host: SMTP 호스트
        port: SMTP 포트
        username: SMTP 사용자명
        password: SMTP 비밀번호
        from_email: 발신자 이메일 (선택)
        from_name: 발신자 이름 (선택)

    Returns:
        저장 성공 여부
    """
    try:
        settings = {
            "host": host,
            "port": str(port),
            "username": username,
            "password": password,
            "from_email": from_email or username,
            "from_name": from_name or "AI Chatbot"
        }
        redis_client.hset("smtp:settings", mapping=settings)
        logger.info("SMTP 설정이 Redis에 저장되었습니다")

        # 캐시 무효화
        invalidate_smtp_settings_cache()

        # 싱글톤 인스턴스 설정 다시 로드
        global _email_service
        if _email_service:
            _email_service.reload_settings()

        return True
    except Exception as e:
        logger.error(f"SMTP 설정 저장 실패: {e}")
        return False


def invalidate_smtp_settings_cache():
    """SMTP 설정 캐시 무효화"""
    global _smtp_settings_cache, _smtp_settings_cache_time
    _smtp_settings_cache = {}
    _smtp_settings_cache_time = 0


def get_smtp_settings(redis_client: Redis) -> dict:
    """Redis에서 SMTP 설정 조회 (캐시 사용)

    Args:
        redis_client: Redis 클라이언트

    Returns:
        SMTP 설정 딕셔너리
    """
    global _smtp_settings_cache, _smtp_settings_cache_time

    # 캐시가 유효하면 캐시된 값 반환
    current_time = time.time()
    if _smtp_settings_cache and (current_time - _smtp_settings_cache_time) < SMTP_SETTINGS_CACHE_TTL:
        return _smtp_settings_cache

    try:
        smtp_settings = redis_client.hgetall("smtp:settings")
        if smtp_settings:
            result = {
                "host": smtp_settings.get(b"host", b"").decode(),
                "port": int(smtp_settings.get(b"port", b"587").decode()),
                "username": smtp_settings.get(b"username", b"").decode(),
                "password": smtp_settings.get(b"password", b"").decode(),
                "from_email": smtp_settings.get(b"from_email", b"").decode(),
                "from_name": smtp_settings.get(b"from_name", b"").decode(),
                "configured": True
            }
        else:
            # 환경 변수에서 로드
            result = {
                "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
                "port": int(os.getenv("SMTP_PORT", "587")),
                "username": os.getenv("SMTP_USERNAME", ""),
                "password": "",  # 보안상 비밀번호는 반환하지 않음
                "from_email": os.getenv("SMTP_FROM_EMAIL", ""),
                "from_name": os.getenv("SMTP_FROM_NAME", "AI Chatbot"),
                "configured": bool(os.getenv("SMTP_USERNAME"))
            }

        # 캐시 업데이트
        _smtp_settings_cache = result
        _smtp_settings_cache_time = current_time
        return result

    except Exception as e:
        logger.error(f"SMTP 설정 조회 실패: {e}")
        return {
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "",
            "password": "",
            "from_email": "",
            "from_name": "AI Chatbot",
            "configured": False
        }


def test_smtp_connection(
    host: str,
    port: int,
    username: str,
    password: str
) -> tuple[bool, str]:
    """SMTP 연결 테스트

    Args:
        host: SMTP 호스트
        port: SMTP 포트
        username: SMTP 사용자명
        password: SMTP 비밀번호

    Returns:
        (성공 여부, 메시지) 튜플
    """
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(username, password)
        return True, "SMTP 연결 테스트 성공"
    except smtplib.SMTPAuthenticationError:
        return False, "인증 실패: 사용자명 또는 비밀번호를 확인하세요"
    except smtplib.SMTPException as e:
        return False, f"SMTP 에러: {str(e)}"
    except Exception as e:
        return False, f"연결 실패: {str(e)}"
