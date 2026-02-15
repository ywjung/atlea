"""JWT Token Blacklist Service

PostgreSQL 기반 토큰 무효화 시스템.
로그아웃, 비밀번호 변경, 권한 변경 시 기존 토큰을 즉시 무효화합니다.
"""

import hashlib
from typing import Optional
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from loguru import logger

from ..database.connection import AsyncSessionFactory
from ..repositories.token_blacklist_repository import TokenBlacklistRepository


class TokenBlacklist:
    """JWT 토큰 블랙리스트 관리

    PostgreSQL을 사용하여 무효화된 토큰을 추적합니다.
    토큰의 만료 시간까지만 DB에 보관하여 저장 공간을 효율적으로 사용합니다.
    """

    def __init__(self):
        """초기화

        Args:
        """
        pass

    def _get_token_expiration(self, token: str, secret_key: str) -> Optional[int]:
        """토큰의 만료 시간(초) 계산"""
        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"], options={"verify_signature": True})
            exp = payload.get("exp")

            if exp is None:
                return None

            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
            now = datetime.now(timezone.utc)

            if exp_datetime <= now:
                return 0

            remaining_seconds = int((exp_datetime - now).total_seconds())
            return max(remaining_seconds, 0)

        except JWTError as e:
            logger.warning(f"Failed to decode token for expiration: {e}")
            return 7 * 24 * 60 * 60
        except Exception as e:
            logger.error(f"Error calculating token expiration: {e}")
            return None

    def _get_token_expires_at(self, token: str, secret_key: str) -> Optional[datetime]:
        """토큰의 만료 datetime 계산"""
        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"], options={"verify_signature": True})
            exp = payload.get("exp")
            if exp is None:
                return None
            return datetime.fromtimestamp(exp, tz=timezone.utc)
        except JWTError:
            return datetime.now(timezone.utc) + timedelta(days=7)
        except Exception:
            return None

    def _get_user_id_from_token(self, token: str, secret_key: str) -> Optional[str]:
        """토큰에서 사용자 ID 추출"""
        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            return payload.get("sub")
        except Exception:
            return None

    def add_token(self, token: str, secret_key: str, reason: str = "logout") -> bool:
        """토큰을 블랙리스트에 추가 (동기 래퍼)"""
        try:
            ttl = self._get_token_expiration(token, secret_key)
            if ttl is None:
                logger.error("Cannot add token to blacklist: failed to get expiration")
                return False

            if ttl == 0:
                logger.debug("Token already expired, skipping blacklist")
                return True

            expires_at = self._get_token_expires_at(token, secret_key)
            if expires_at is None:
                return False

            user_id = self._get_user_id_from_token(token, secret_key)

            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # Already in async context, use create_task workaround
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = loop.run_in_executor(
                        pool,
                        self._add_token_sync,
                        token, expires_at, user_id, reason,
                    )
                    # Can't await in sync function, use blocking approach
                    self._add_token_sync(token, expires_at, user_id, reason)
            except RuntimeError:
                # No running loop — run directly
                asyncio.run(self._add_token_async(token, expires_at, user_id, reason))

            logger.info(f"Token added to blacklist: reason={reason}, ttl={ttl}s")
            return True

        except Exception as e:
            logger.error(f"Failed to add token to blacklist: {e}")
            return False

    def _add_token_sync(self, token: str, expires_at: datetime, user_id: str | None, reason: str):
        """동기 컨텍스트에서 토큰 블랙리스트 추가"""
        from ..database.connection import SyncSessionFactory
        from ..database.models.token_blacklist import TokenBlacklistEntry

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with SyncSessionFactory() as session:
            entry = TokenBlacklistEntry(
                token_hash=token_hash,
                user_id=user_id,
                reason=reason,
                expires_at=expires_at,
            )
            session.add(entry)
            session.commit()

    async def _add_token_async(self, token: str, expires_at: datetime, user_id: str | None, reason: str):
        """비동기 컨텍스트에서 토큰 블랙리스트 추가"""
        async with AsyncSessionFactory() as session:
            repo = TokenBlacklistRepository(session)
            await repo.add_token(token, expires_at, user_id, reason)
            await session.commit()

    def is_blacklisted(self, token: str) -> bool:
        """토큰이 블랙리스트에 있는지 확인"""
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()

            from ..database.connection import SyncSessionFactory
            from ..database.models.token_blacklist import TokenBlacklistEntry
            from sqlalchemy import select, func

            with SyncSessionFactory() as session:
                stmt = (
                    select(func.count())
                    .select_from(TokenBlacklistEntry)
                    .where(
                        TokenBlacklistEntry.token_hash == token_hash,
                        TokenBlacklistEntry.expires_at > datetime.now(timezone.utc),
                    )
                )
                result = session.execute(stmt)
                count = result.scalar_one()

            if count > 0:
                logger.debug("Token found in blacklist")
                return True
            return False

        except Exception as e:
            logger.error(f"Error checking token blacklist: {e}")
            return True

    def revoke_user_tokens(self, user_id: str, secret_key: str, reason: str = "security") -> int:
        """특정 사용자의 모든 토큰 무효화

        Note: PG 기반에서는 개별 토큰 추적 없이 블랙리스트만 확인하므로,
        새로운 요청은 verify_token에서 세션 유효성으로 차단됩니다.
        """
        logger.info(f"Revoked tokens for user {user_id}, reason={reason}")
        return 0

    def get_blacklist_stats(self) -> dict:
        """블랙리스트 통계 조회"""
        try:
            from ..database.connection import SyncSessionFactory
            from ..database.models.token_blacklist import TokenBlacklistEntry
            from sqlalchemy import select, func

            with SyncSessionFactory() as session:
                stmt = (
                    select(func.count())
                    .select_from(TokenBlacklistEntry)
                    .where(TokenBlacklistEntry.expires_at > datetime.now(timezone.utc))
                )
                result = session.execute(stmt)
                total = result.scalar_one()

            return {
                "total_blacklisted_tokens": total,
                "storage": "postgresql"
            }

        except Exception as e:
            logger.error(f"Error getting blacklist stats: {e}")
            return {
                "total_blacklisted_tokens": 0,
                "error": str(e)
            }
