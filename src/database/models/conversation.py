"""Conversation ORM Model"""

import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="새 대화")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_bookmarked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Relationship to messages
    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} title={self.title!r}>"
