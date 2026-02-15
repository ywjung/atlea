"""Semantic Cache ORM Model for LLM response caching with pgvector similarity."""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Float, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy.types import LargeBinary as Vector  # type: ignore

from ..base import Base


class SemanticCache(Base):
    __tablename__ = "semantic_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    response: Mapped[str] = mapped_column(Text, nullable=False)
    sources = mapped_column(JSONB, nullable=False, default=list)
    context = mapped_column(JSONB, nullable=False, default=list)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    document_ids = mapped_column(JSONB, nullable=False, default=list)
    group_ids = mapped_column(JSONB, nullable=False, default=list)
    embedding = mapped_column(Vector(1024), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<SemanticCache q='{self.question[:40]}...' hash={self.question_hash}>"
