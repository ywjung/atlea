"""Token Blacklist Repository"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.token_blacklist import TokenBlacklistEntry
from .base import BaseRepository


class TokenBlacklistRepository(BaseRepository[TokenBlacklistEntry]):
    model = TokenBlacklistEntry

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def add_token(
        self,
        token: str,
        expires_at: datetime,
        user_id: str | None = None,
        reason: str = "logout",
    ) -> TokenBlacklistEntry:
        entry = TokenBlacklistEntry(
            token_hash=self.hash_token(token),
            user_id=user_id,
            reason=reason,
            expires_at=expires_at,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def is_blacklisted(self, token: str) -> bool:
        token_hash = self.hash_token(token)
        stmt = (
            select(func.count())
            .select_from(TokenBlacklistEntry)
            .where(
                TokenBlacklistEntry.token_hash == token_hash,
                TokenBlacklistEntry.expires_at > datetime.now(timezone.utc),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def delete_expired(self) -> int:
        stmt = delete(TokenBlacklistEntry).where(
            TokenBlacklistEntry.expires_at < datetime.now(timezone.utc)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count_active(self) -> int:
        stmt = (
            select(func.count())
            .select_from(TokenBlacklistEntry)
            .where(TokenBlacklistEntry.expires_at > datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def revoke_user_tokens(self, user_id: str) -> int:
        """Count tokens blacklisted for a user (for stats)."""
        stmt = (
            select(func.count())
            .select_from(TokenBlacklistEntry)
            .where(
                TokenBlacklistEntry.user_id == user_id,
                TokenBlacklistEntry.expires_at > datetime.now(timezone.utc),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
