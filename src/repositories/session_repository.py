"""Session Repository"""

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.session import Session
from .base import BaseRepository


class SessionRepository(BaseRepository[Session]):
    model = Session

    async def get_active_by_user(self, user_id: uuid.UUID) -> Sequence[Session]:
        stmt = (
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.is_active == True,
                Session.expires_at > datetime.now(timezone.utc),
            )
            .order_by(Session.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def deactivate(self, session_id: uuid.UUID) -> bool:
        stmt = (
            update(Session)
            .where(Session.id == session_id)
            .values(is_active=False)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def deactivate_all_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            update(Session)
            .where(Session.user_id == user_id, Session.is_active == True)
            .values(is_active=False)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def delete_expired(self) -> int:
        stmt = delete(Session).where(Session.expires_at < datetime.now(timezone.utc))
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count_active_by_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Session)
            .where(
                Session.user_id == user_id,
                Session.is_active == True,
                Session.expires_at > datetime.now(timezone.utc),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
