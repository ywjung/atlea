"""Document Version ORM Models"""

from datetime import datetime

from sqlalchemy import String, Integer, BigInteger, DateTime, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("filename", "version_number", name="uq_doc_version"),
    )

    def __repr__(self) -> str:
        return f"<DocumentVersion {self.filename} v{self.version_number}>"


class DocumentLatestVersion(Base):
    __tablename__ = "document_latest_versions"

    filename: Mapped[str] = mapped_column(String(500), primary_key=True)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<DocumentLatestVersion {self.filename} v{self.latest_version}>"
