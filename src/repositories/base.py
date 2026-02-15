"""
Base Repository with generic CRUD operations.
"""

import uuid
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async CRUD repository for SQLAlchemy models."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_value: Any) -> ModelT | None:
        """Get a single record by primary key."""
        return await self.session.get(self.model, id_value)

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelT]:
        """Get all records with pagination."""
        stmt = select(self.model).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Count total records."""
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, obj: ModelT) -> ModelT:
        """Insert a new record."""
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def create_many(self, objects: list[ModelT]) -> list[ModelT]:
        """Insert multiple records."""
        self.session.add_all(objects)
        await self.session.flush()
        return objects

    async def update(self, obj: ModelT) -> ModelT:
        """Merge changes into the session."""
        merged = await self.session.merge(obj)
        await self.session.flush()
        return merged

    async def delete(self, obj: ModelT) -> None:
        """Delete a single record."""
        await self.session.delete(obj)
        await self.session.flush()

    async def delete_by_id(self, id_value: Any) -> bool:
        """Delete a record by primary key. Returns True if deleted."""
        obj = await self.get_by_id(id_value)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True
