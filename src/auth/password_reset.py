"""Password Reset Service

비밀번호 재설정 토큰 생성 및 검증. PostgreSQL 기반.
"""

import hashlib
from typing import Optional
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

from .utils import SECRET_KEY, ALGORITHM

RESET_TOKEN_EXPIRE_MINUTES = 30  # 30분


def create_password_reset_token(email: str) -> str:
    """비밀번호 재설정 토큰 생성"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": email,
        "exp": expire,
        "type": "password_reset"
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password_reset_token(token: str) -> Optional[str]:
    """비밀번호 재설정 토큰 검증"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

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

    def __init__(self):
        """초기화

        Args:
        """
        pass

    async def create_reset_token(self, user_id: str, email: str) -> str:
        """재설정 토큰 생성"""
        token = create_password_reset_token(email)

        # PostgreSQL에 토큰과 user_id 매핑 저장 (30분 TTL)
        from ..database.connection import AsyncSessionFactory
        from ..repositories.password_reset_repository import PasswordResetRepository

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
        async with AsyncSessionFactory() as session:
            repo = PasswordResetRepository(session)
            await repo.store_token(token, user_id, expires_at)
            await session.commit()

        return token

    async def verify_reset_token(self, token: str) -> Optional[str]:
        """재설정 토큰 검증"""
        # JWT 검증
        email = verify_password_reset_token(token)
        if not email:
            return None

        # PostgreSQL에서 user_id 조회 및 토큰 소비
        from ..database.connection import AsyncSessionFactory
        from ..repositories.password_reset_repository import PasswordResetRepository

        async with AsyncSessionFactory() as session:
            repo = PasswordResetRepository(session)
            user_id = await repo.verify_and_consume(token)
            await session.commit()

        return user_id
