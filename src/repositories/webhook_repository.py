"""Webhook Repository"""

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.webhook import Webhook
from .base import BaseRepository


class WebhookRepository(BaseRepository[Webhook]):
    model = Webhook

    async def get_by_user(self, user_id: uuid.UUID) -> Sequence[Webhook]:
        stmt = (
            select(Webhook)
            .where(Webhook.user_id == user_id)
            .order_by(Webhook.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_active_by_event(self, event_name: str) -> Sequence[Webhook]:
        """Get active webhooks that subscribe to a specific event."""
        stmt = (
            select(Webhook)
            .where(
                Webhook.is_active == True,
                Webhook.events.op("@>")(f'["{event_name}"]'),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
