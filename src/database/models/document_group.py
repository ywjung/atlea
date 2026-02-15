"""Document Group ORM Model (hierarchical via parent_id)"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


class DocumentGroup(Base):
    __tablename__ = "document_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Self-referential hierarchy
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_groups.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    children = relationship(
        "DocumentGroup",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent = relationship("DocumentGroup", back_populates="children", remote_side=[id])
    documents = relationship("GroupDocument", back_populates="group", cascade="all, delete-orphan")
    organization_links = relationship("GroupOrganization", back_populates="group", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DocumentGroup {self.name}>"
