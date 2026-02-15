"""Document Version Repository"""

from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.document_version import DocumentVersion, DocumentLatestVersion
from .base import BaseRepository


class DocumentVersionRepository(BaseRepository[DocumentVersion]):
    model = DocumentVersion

    async def get_versions(self, filename: str) -> Sequence[DocumentVersion]:
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.filename == filename)
            .order_by(DocumentVersion.version_number.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_version(self, filename: str, version_number: int) -> DocumentVersion | None:
        stmt = select(DocumentVersion).where(
            DocumentVersion.filename == filename,
            DocumentVersion.version_number == version_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_version_number(self, filename: str) -> int | None:
        stmt = select(DocumentLatestVersion).where(
            DocumentLatestVersion.filename == filename
        )
        result = await self.session.execute(stmt)
        latest = result.scalar_one_or_none()
        return latest.latest_version if latest else None

    async def set_latest_version(self, filename: str, version_number: int) -> None:
        existing = await self.session.get(DocumentLatestVersion, filename)
        if existing:
            existing.latest_version = version_number
        else:
            self.session.add(
                DocumentLatestVersion(filename=filename, latest_version=version_number)
            )
        await self.session.flush()

    async def count_versions(self, filename: str) -> int:
        stmt = (
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.filename == filename)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
