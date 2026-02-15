"""Document Group Repository"""

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models.document_group import DocumentGroup
from src.database.models.group_document import GroupDocument
from src.database.models.group_organization import GroupOrganization
from .base import BaseRepository


class GroupRepository(BaseRepository[DocumentGroup]):
    model = DocumentGroup

    async def get_with_children(self, group_id: uuid.UUID) -> DocumentGroup | None:
        stmt = (
            select(DocumentGroup)
            .options(selectinload(DocumentGroup.children))
            .where(DocumentGroup.id == group_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_root_groups(self) -> Sequence[DocumentGroup]:
        """Get top-level groups (no parent)."""
        stmt = (
            select(DocumentGroup)
            .where(DocumentGroup.parent_id.is_(None))
            .order_by(DocumentGroup.name)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_org(self, org_id: uuid.UUID) -> Sequence[DocumentGroup]:
        stmt = (
            select(DocumentGroup)
            .join(GroupOrganization)
            .where(GroupOrganization.org_id == org_id)
            .order_by(DocumentGroup.name)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add_document(self, group_id: uuid.UUID, filename: str) -> GroupDocument:
        link = GroupDocument(group_id=group_id, filename=filename)
        self.session.add(link)
        await self.session.flush()
        return link

    async def remove_document(self, group_id: uuid.UUID, filename: str) -> bool:
        stmt = select(GroupDocument).where(
            GroupDocument.group_id == group_id,
            GroupDocument.filename == filename,
        )
        result = await self.session.execute(stmt)
        link = result.scalar_one_or_none()
        if link:
            await self.session.delete(link)
            await self.session.flush()
            return True
        return False

    async def get_documents(self, group_id: uuid.UUID) -> Sequence[GroupDocument]:
        stmt = (
            select(GroupDocument)
            .where(GroupDocument.group_id == group_id)
            .order_by(GroupDocument.filename)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def link_organization(
        self, group_id: uuid.UUID, org_id: uuid.UUID, is_root: bool = False
    ) -> GroupOrganization:
        link = GroupOrganization(group_id=group_id, org_id=org_id, is_root=is_root)
        self.session.add(link)
        await self.session.flush()
        return link
