"""Password Reset Service

비밀번호 재설정 토큰 생성 및 검증.
"""

from typing import Optional
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from redis import Redis
import os

# JWT 설정
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY environment variable is required. "
        "Please set a strong secret key in your .env file."
    )

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
RESET_TOKEN_EXPIRE_MINUTES = 30  # 30분


def create_password_reset_token(email: str) -> str:
    """비밀번호 재설정 토큰 생성

    Args:
        email: 사용자 이메일

    Returns:
        JWT 재설정 토큰
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": email,
        "exp": expire,
        "type": "password_reset"
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password_reset_token(token: str) -> Optional[str]:
    """비밀번호 재설정 토큰 검증

    Args:
        token: JWT 재설정 토큰

    Returns:
        이메일 주소 (검증 실패 시 None)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 토큰 타입 확인
        if payload.get("type") != "password_reset":
            return None

        email: str = payload.get("sub")
        if email is None:
            return None

        return email

    except JWTError:
        return None


class PasswordResetService:
    """비밀번호 재설정 서비스 클래스"""

    def __init__(self, redis_client: Redis):
        """초기화

        Args:
            redis_client: Redis 클라이언트
        """
        self.redis = redis_client

    async def create_reset_token(self, user_id: str, email: str) -> str:
        """재설정 토큰 생성

        Args:
            user_id: 사용자 ID
            email: 이메일 주소

        Returns:
            재설정 토큰
        """
        token = create_password_reset_token(email)

        # Redis에 토큰과 user_id 매핑 저장 (30분 TTL)
        self.redis.setex(
            f"password_reset:{token}",
            RESET_TOKEN_EXPIRE_MINUTES * 60,
            user_id
        )

        return token

    async def verify_reset_token(self, token: str) -> Optional[str]:
        """재설정 토큰 검증

        Args:
            token: 재설정 토큰

        Returns:
            사용자 ID (검증 실패 시 None)
        """
        # JWT 검증
        email = verify_password_reset_token(token)
        if not email:
            return None

        # Redis에서 user_id 조회
        user_id = self.redis.get(f"password_reset:{token}")
        if not user_id:
            return None

        user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id

        # 토큰 사용 후 삭제 (일회용)
        self.redis.delete(f"password_reset:{token}")

        return user_id_str
