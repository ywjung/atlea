"""
Database Connection Management

Provides async engine, session factory, and dependency injection helper
for FastAPI endpoints.
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from loguru import logger


# Default DATABASE_URL (async driver for app, sync driver for Alembic)
_DEFAULT_URL = "postgresql+asyncpg://chatbot_user:chatbot_secret@localhost:5432/chatbot"

DATABASE_URL: str = os.getenv("DATABASE_URL", _DEFAULT_URL)

# Async engine (used by the application)
async_engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
    pool_pre_ping=True,
    pool_recycle=300,
)

# Async session factory
AsyncSessionFactory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_sync_engine():
    """Create a sync engine (for Alembic migrations)."""
    sync_url = DATABASE_URL.replace("+asyncpg", "+psycopg2").replace("+aiopg", "+psycopg2")
    return create_engine(sync_url, echo=False)


# Sync engine & session factory (for sync code accessing PG config)
_sync_engine = get_sync_engine()

SyncSessionFactory = sessionmaker(
    bind=_sync_engine,
    class_=Session,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Usage in routers:
        @router.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Health check: verify PostgreSQL is reachable."""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        return True
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        return False


async def close_db() -> None:
    """Dispose engine connections on shutdown."""
    await async_engine.dispose()
    logger.info("PostgreSQL connection pool closed")
