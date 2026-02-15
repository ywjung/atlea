"""Organization Repository"""

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models.organization import Organization
from src.database.models.organization_member import OrganizationMember
from .base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    async def get_by_name(self, name: str) -> Organization | None:
        stmt = select(Organization).where(Organization.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_members(self, org_id: uuid.UUID) -> Organization | None:
        stmt = (
            select(Organization)
            .options(selectinload(Organization.members))
            .where(Organization.id == org_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active(self) -> Sequence[Organization]:
        stmt = select(Organization).where(Organization.is_active == True).order_by(Organization.name)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add_member(
        self, org_id: uuid.UUID, user_id: uuid.UUID, role: str = "member"
    ) -> OrganizationMember:
        member = OrganizationMember(org_id=org_id, user_id=user_id, role=role)
        self.session.add(member)
        await self.session.flush()
        return member

    async def remove_member(self, org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        stmt = select(OrganizationMember).where(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        member = result.scalar_one_or_none()
        if member:
            await self.session.delete(member)
            await self.session.flush()
            return True
        return False
