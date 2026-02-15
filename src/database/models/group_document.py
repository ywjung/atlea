"""Group-Document Link ORM Model"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class GroupDocument(Base):
    __tablename__ = "group_documents"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    filename: Mapped[str] = mapped_column(String(500), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    group = relationship("DocumentGroup", back_populates="documents")

    def __repr__(self) -> str:
        return f"<GroupDocument group={self.group_id} file={self.filename}>"
