"""User Repository"""

import uuid
from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.user import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_org(
        self, org_id: uuid.UUID, *, offset: int = 0, limit: int = 100
    ) -> Sequence[User]:
        stmt = (
            select(User)
            .where(User.org_id == org_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search(
        self,
        *,
        query: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[User], int]:
        """Search users with filters. Returns (users, total_count)."""
        stmt = select(User)
        count_stmt = select(func.count()).select_from(User)

        if query:
            pattern = f"%{query}%"
            filter_ = User.email.ilike(pattern) | User.username.ilike(pattern)
            stmt = stmt.where(filter_)
            count_stmt = count_stmt.where(filter_)

        if role is not None:
            stmt = stmt.where(User.role == role)
            count_stmt = count_stmt.where(User.role == role)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)

        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def increment_failed_attempts(self, user_id: uuid.UUID) -> int:
        """Increment failed login attempts. Returns new count."""
        user = await self.get_by_id(user_id)
        if user:
            user.failed_login_attempts += 1
            await self.session.flush()
            return user.failed_login_attempts
        return 0

    async def reset_failed_attempts(self, user_id: uuid.UUID) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.failed_login_attempts = 0
            user.locked_until = None
            await self.session.flush()
