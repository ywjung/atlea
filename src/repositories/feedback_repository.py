"""Feedback Repository"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.feedback import FeedbackEntry
from .base import BaseRepository


class FeedbackRepository(BaseRepository[FeedbackEntry]):
    model = FeedbackEntry

    async def get_recent(self, *, limit: int = 100) -> Sequence[FeedbackEntry]:
        stmt = (
            select(FeedbackEntry)
            .order_by(FeedbackEntry.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_user(
        self, user_id: str, *, offset: int = 0, limit: int = 50
    ) -> Sequence[FeedbackEntry]:
        stmt = (
            select(FeedbackEntry)
            .where(FeedbackEntry.user_id == user_id)
            .order_by(FeedbackEntry.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def average_rating(self, since: datetime | None = None) -> float | None:
        stmt = select(func.avg(FeedbackEntry.rating))
        if since:
            stmt = stmt.where(FeedbackEntry.created_at >= since)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
