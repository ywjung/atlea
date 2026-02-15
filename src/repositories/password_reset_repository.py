"""Password Reset Token Repository"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.password_reset_token import PasswordResetToken
from .base import BaseRepository


class PasswordResetRepository(BaseRepository[PasswordResetToken]):
    model = PasswordResetToken

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def store_token(
        self, token: str, user_id: str, expires_at: datetime
    ) -> PasswordResetToken:
        entry = PasswordResetToken(
            token_hash=self.hash_token(token),
            user_id=user_id,
            expires_at=expires_at,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def verify_and_consume(self, token: str) -> str | None:
        """Verify token and mark used. Returns user_id or None."""
        token_hash = self.hash_token(token)
        now = datetime.now(timezone.utc)

        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        )
        result = await self.session.execute(stmt)
        entry = result.scalar_one_or_none()

        if entry is None:
            return None

        entry.used = True
        await self.session.flush()
        return entry.user_id

    async def delete_expired(self) -> int:
        stmt = delete(PasswordResetToken).where(
            PasswordResetToken.expires_at < datetime.now(timezone.utc)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
