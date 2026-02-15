"""Audit Log Repository"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.audit_log import AuditLog
from .base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def search(
        self,
        *,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[AuditLog], int]:
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)

        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
            count_stmt = count_stmt.where(AuditLog.user_id == user_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
            count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)
        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
            count_stmt = count_stmt.where(AuditLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AuditLog.created_at <= end_date)
            count_stmt = count_stmt.where(AuditLog.created_at <= end_date)

        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def delete_before(self, cutoff: datetime) -> int:
        """Delete logs older than cutoff. Returns deleted count."""
        stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
