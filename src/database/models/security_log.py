"""Security Log ORM Model (partitioned by created_at)"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class SecurityLog(Base):
    __tablename__ = "security_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<SecurityLog {self.event_type} [{self.level}]>"
