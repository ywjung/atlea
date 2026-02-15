"""System Config Repository"""

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.system_config import SystemConfig
from .base import BaseRepository


class ConfigRepository(BaseRepository[SystemConfig]):
    model = SystemConfig

    async def get_value(self, key: str) -> str | None:
        """Get a single config value by key."""
        config = await self.get_by_id(key)
        return config.value if config else None

    async def set_value(
        self, key: str, value: str, value_type: str = "string", description: str | None = None
    ) -> SystemConfig:
        """Upsert a config entry."""
        existing = await self.get_by_id(key)
        if existing:
            existing.value = value
            existing.value_type = value_type
            if description is not None:
                existing.description = description
            await self.session.flush()
            return existing
        else:
            config = SystemConfig(
                key=key, value=value, value_type=value_type, description=description
            )
            self.session.add(config)
            await self.session.flush()
            return config

    async def get_by_prefix(self, prefix: str) -> Sequence[SystemConfig]:
        """Get all config entries whose key starts with prefix."""
        stmt = (
            select(SystemConfig)
            .where(SystemConfig.key.startswith(prefix))
            .order_by(SystemConfig.key)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_key(self, key: str) -> bool:
        return await self.delete_by_id(key)
