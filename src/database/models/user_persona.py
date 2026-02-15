"""UserPersona ORM Model"""

import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class UserPersona(Base):
    __tablename__ = "user_personas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expertise_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expertise_domains: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language_style: Mapped[str | None] = mapped_column(String(20), nullable=True)
    response_format_preference: Mapped[str | None] = mapped_column(String(30), nullable=True)
    additional_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<UserPersona {self.id} user={self.user_id}>"
