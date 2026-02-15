"""Captcha Challenge Repository"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.captcha_challenge import CaptchaChallenge
from .base import BaseRepository


class CaptchaRepository(BaseRepository[CaptchaChallenge]):
    model = CaptchaChallenge

    async def store_challenge(
        self, captcha_id: uuid.UUID, answer: str, expires_at: datetime
    ) -> CaptchaChallenge:
        challenge = CaptchaChallenge(
            id=captcha_id,
            answer=answer,
            expires_at=expires_at,
        )
        self.session.add(challenge)
        await self.session.flush()
        return challenge

    async def verify_and_consume(
        self, captcha_id: uuid.UUID, answer: str
    ) -> bool | None:
        """Verify answer and mark used. Returns True/False/None(not found or expired)."""
        now = datetime.now(timezone.utc)
        stmt = select(CaptchaChallenge).where(
            CaptchaChallenge.id == captcha_id,
            CaptchaChallenge.used == False,
            CaptchaChallenge.expires_at > now,
        )
        result = await self.session.execute(stmt)
        challenge = result.scalar_one_or_none()

        if challenge is None:
            return None

        if challenge.answer != answer:
            return False

        challenge.used = True
        await self.session.flush()
        return True

    async def delete_expired(self) -> int:
        stmt = delete(CaptchaChallenge).where(
            CaptchaChallenge.expires_at < datetime.now(timezone.utc)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
