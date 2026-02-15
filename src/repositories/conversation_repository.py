"""Repository for Conversation and ConversationMessage models."""

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .base import BaseRepository
from ..database.models.conversation import Conversation
from ..database.models.conversation_message import ConversationMessage


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    async def list_recent(
        self, *, offset: int = 0, limit: int = 50
    ) -> Sequence[Conversation]:
        """List conversations ordered by most recently updated."""
        stmt = (
            select(Conversation)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_bookmarked(
        self, *, offset: int = 0, limit: int = 50
    ) -> Sequence[Conversation]:
        """List bookmarked conversations ordered by most recently updated."""
        stmt = (
            select(Conversation)
            .where(Conversation.is_bookmarked == True)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_bookmarked(self) -> int:
        """Count bookmarked conversations."""
        stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.is_bookmarked == True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def toggle_bookmark(self, conversation_id: UUID) -> bool | None:
        """Toggle bookmark. Returns new bookmark state or None if not found."""
        conv = await self.get_by_id(conversation_id)
        if conv is None:
            return None
        conv.is_bookmarked = not conv.is_bookmarked
        await self.session.flush()
        return conv.is_bookmarked

    async def delete_all(self) -> int:
        """Delete all conversations. Returns count deleted."""
        count_stmt = select(func.count()).select_from(Conversation)
        result = await self.session.execute(count_stmt)
        total = result.scalar_one()

        stmt = delete(Conversation)
        await self.session.execute(stmt)
        await self.session.flush()
        return total


class ConversationMessageRepository(BaseRepository[ConversationMessage]):
    model = ConversationMessage

    async def get_messages(
        self,
        conversation_id: UUID,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> Sequence[ConversationMessage]:
        """Get messages for a conversation, ordered by creation time."""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_last_message(
        self, conversation_id: UUID
    ) -> ConversationMessage | None:
        """Get the most recent message in a conversation."""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_for_conversation(self, conversation_id: UUID) -> int:
        """Count messages in a conversation."""
        stmt = (
            select(func.count())
            .select_from(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
