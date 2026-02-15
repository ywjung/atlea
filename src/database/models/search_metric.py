"""Search Metric ORM Model"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class SearchMetric(Base):
    __tablename__ = "search_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    search_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    sources_used: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
    local_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    web_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_time: Mapped[float] = mapped_column(Float, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<SearchMetric mode={self.search_mode} time={self.response_time}s>"
