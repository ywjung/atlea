"""Sentence Embedding ORM Model for sentence-level vector search (pgvector)

Each document chunk is split into sentences. Each sentence gets its own
embedding for finer-grained retrieval, then maps back to the parent chunk.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy.types import LargeBinary as Vector  # type: ignore

from ..base import Base


class SentenceEmbedding(Base):
    __tablename__ = "sentence_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    index_version: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentence_text: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Vector embedding — same dimension as chunk embeddings
    embedding = mapped_column(Vector(1024), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<SentenceEmbedding file={self.filename} "
            f"chunk={self.chunk_index} sent={self.sentence_index}>"
        )
