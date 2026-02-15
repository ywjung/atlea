"""Generic Cache ORM Models for embedding, query result, and follow-up caches."""

from datetime import datetime

from sqlalchemy import String, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    embedding_data: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<EmbeddingCache id={self.id}>"


class QueryResultCache(Base):
    __tablename__ = "query_result_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<QueryResultCache id={self.id}>"


class FollowupCache(Base):
    __tablename__ = "followup_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    questions: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<FollowupCache id={self.id}>"
