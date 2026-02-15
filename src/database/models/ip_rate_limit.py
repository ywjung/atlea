"""IP Rate Limit ORM Model"""

from datetime import datetime

from sqlalchemy import Integer, String, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class IpRateLimit(Base):
    __tablename__ = "ip_rate_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<IpRateLimit {self.ip_address}:{self.endpoint}>"
