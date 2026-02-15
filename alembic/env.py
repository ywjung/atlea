"""
Alembic Environment Configuration

Supports both sync and async migration execution.
Reads DATABASE_URL from environment variable.
"""

import os
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import Base and all models so Alembic can detect them
from src.database.base import Base
from src.database.models import (  # noqa: F401 — force model registration
    User, Organization, OrganizationMember,
    DocumentGroup, GroupDocument, GroupOrganization,
    DocumentVersion, DocumentLatestVersion,
    AuditLog, SecurityLog, SystemConfig,
    LoginHistory, Webhook, FeedbackEntry,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Read DATABASE_URL from environment, convert to sync driver for offline mode
_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://chatbot_user:chatbot_secret@localhost:5432/chatbot",
)


def _get_sync_url() -> str:
    """Convert async URL to sync for offline migrations."""
    return _DB_URL.replace("+asyncpg", "+psycopg2").replace("+aiopg", "+psycopg2")


def _get_async_url() -> str:
    """Ensure URL uses asyncpg driver."""
    url = _DB_URL
    if "+psycopg2" in url:
        url = url.replace("+psycopg2", "+asyncpg")
    if "postgresql://" == url[:14]:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL script without DB connection."""
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_async_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — delegates to async runner."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
