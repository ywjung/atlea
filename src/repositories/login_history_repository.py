"""Login History Repository"""

import uuid
from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.login_history import LoginHistory
from .base import BaseRepository


class LoginHistoryRepository(BaseRepository[LoginHistory]):
    model = LoginHistory

    async def get_by_user(
        self, user_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> Sequence[LoginHistory]:
        stmt = (
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(LoginHistory.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_recent_failures(
        self, user_id: uuid.UUID, since: "datetime"
    ) -> int:
        from datetime import datetime
        stmt = (
            select(func.count())
            .select_from(LoginHistory)
            .where(
                LoginHistory.user_id == user_id,
                LoginHistory.success == False,
                LoginHistory.created_at >= since,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
