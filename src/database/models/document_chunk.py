"""Document Chunk ORM Model for vector search (pgvector)"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Fallback for environments without pgvector (e.g., testing with SQLite)
    from sqlalchemy.types import LargeBinary as Vector  # type: ignore

from ..base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    index_version: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Vector embedding — dimension set at migration level
    embedding = mapped_column(Vector(1024), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk file={self.filename} idx={self.chunk_index}>"
