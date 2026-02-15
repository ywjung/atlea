"""Security Log Repository"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.security_log import SecurityLog
from .base import BaseRepository


class SecurityLogRepository(BaseRepository[SecurityLog]):
    model = SecurityLog

    async def search(
        self,
        *,
        level: str | None = None,
        event_type: str | None = None,
        user_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[SecurityLog], int]:
        stmt = select(SecurityLog)
        count_stmt = select(func.count()).select_from(SecurityLog)

        if level:
            stmt = stmt.where(SecurityLog.level == level)
            count_stmt = count_stmt.where(SecurityLog.level == level)
        if event_type:
            stmt = stmt.where(SecurityLog.event_type == event_type)
            count_stmt = count_stmt.where(SecurityLog.event_type == event_type)
        if user_id:
            stmt = stmt.where(SecurityLog.user_id == user_id)
            count_stmt = count_stmt.where(SecurityLog.user_id == user_id)
        if start_date:
            stmt = stmt.where(SecurityLog.created_at >= start_date)
            count_stmt = count_stmt.where(SecurityLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(SecurityLog.created_at <= end_date)
            count_stmt = count_stmt.where(SecurityLog.created_at <= end_date)

        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(SecurityLog.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def delete_before(self, cutoff: datetime) -> int:
        stmt = delete(SecurityLog).where(SecurityLog.created_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
