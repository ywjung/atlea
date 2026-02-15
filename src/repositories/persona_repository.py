"""Repository for UserPersona model."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..database.models.user_persona import UserPersona


class PersonaRepository(BaseRepository[UserPersona]):
    model = UserPersona

    async def get_by_user_id(self, user_id: str) -> UserPersona | None:
        """Get persona by user ID."""
        stmt = select(UserPersona).where(UserPersona.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_user_id(self, user_id: str) -> bool:
        """Delete persona by user ID. Returns True if deleted."""
        persona = await self.get_by_user_id(user_id)
        if persona is None:
            return False
        await self.session.delete(persona)
        await self.session.flush()
        return True
