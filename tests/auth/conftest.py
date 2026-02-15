"""Shared test fixtures for auth tests.

Provides an in-memory SQLite database that replaces PostgreSQL for testing.
All auth tests run against real SQLAlchemy code paths without needing a PG server.
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID, ARRAY as PG_ARRAY

try:
    from pgvector.sqlalchemy import Vector as PG_VECTOR
except ImportError:
    PG_VECTOR = None

from src.database.base import Base


# ── SQLite type compilation hooks ─────────────────────────────
# Map PostgreSQL-specific types to SQLite equivalents so that
# Base.metadata.create_all() works on SQLite engines.

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(32)"

@compiles(PG_ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"

if PG_VECTOR is not None:
    @compiles(PG_VECTOR, "sqlite")
    def _compile_vector_sqlite(type_, compiler, **kw):
        return "BLOB"


# ── SQLite UUID workaround ──────────────────────────────────────
# PostgreSQL UUID columns store native UUIDs; SQLite stores them as
# 32-char hex strings. We register adapters so uuid.UUID round-trips.
import sqlite3

sqlite3.register_adapter(uuid.UUID, lambda u: u.hex)
sqlite3.register_converter("UUID", lambda b: uuid.UUID(b.decode()))
sqlite3.register_converter("uuid", lambda b: uuid.UUID(b.decode()))


# ── Engine & session factories for tests ────────────────────────

# Use named shared-cache in-memory DB so sync and async engines share data.
_SQLITE_URL_SYNC = "sqlite:///file:testdb?mode=memory&cache=shared&uri=true"
_SQLITE_URL_ASYNC = "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"


def _create_test_engines():
    """Create async and sync engines backed by the same in-memory database."""
    # Sync engine — keep one connection alive to prevent DB from vanishing
    sync_engine = create_engine(
        _SQLITE_URL_SYNC,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable FK constraints on every connection
    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Async engine sharing the same named in-memory DB
    async_engine = create_async_engine(
        _SQLITE_URL_ASYNC,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    return async_engine, sync_engine


def _build_factories(async_engine, sync_engine):
    """Build session factories from engines."""
    async_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    sync_factory = sessionmaker(
        bind=sync_engine,
        class_=Session,
        expire_on_commit=False,
    )
    return async_factory, sync_factory


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _setup_test_db(monkeypatch):
    """Create in-memory SQLite tables and patch connection module.

    This fixture runs automatically for every test in tests/auth/.
    It replaces AsyncSessionFactory and SyncSessionFactory so that
    AuthService (and everything it imports) hits SQLite instead of PG.
    """
    import importlib
    from src.database import connection as conn_mod
    from src.database.base import Base

    # Import all models so Base.metadata is populated
    import src.database.models  # noqa: F401

    async_engine, sync_engine = _create_test_engines()
    async_factory, sync_factory = _build_factories(async_engine, sync_engine)

    # Create tables in both databases
    Base.metadata.create_all(sync_engine)

    # We also need tables in the async engine's database
    import asyncio

    async def _create_async_tables():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Run in event loop (pytest-asyncio provides one)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(asyncio.run, _create_async_tables()).result()
        else:
            loop.run_until_complete(_create_async_tables())
    except RuntimeError:
        asyncio.run(_create_async_tables())

    # Patch the connection module
    monkeypatch.setattr(conn_mod, "AsyncSessionFactory", async_factory)
    monkeypatch.setattr(conn_mod, "SyncSessionFactory", sync_factory)
    monkeypatch.setattr(conn_mod, "async_engine", async_engine)

    # Also patch the modules that import these directly
    # (services/config_service.py imports from connection)
    try:
        from src.services import config_service as cfg_mod
        monkeypatch.setattr(cfg_mod, "AsyncSessionFactory", async_factory)
        monkeypatch.setattr(cfg_mod, "SyncSessionFactory", sync_factory)
    except Exception:
        pass

    # Clear in-memory rate limiter caches between tests
    try:
        from src.auth import rate_limiter as rl_mod
        rl_mod._rate_cache.clear()
        rl_mod._last_cleanup = 0
    except Exception:
        pass

    try:
        from src.middleware import rate_limiter_middleware as rlr_mod
        rlr_mod._buckets.clear()
        rlr_mod._last_bucket_cleanup = 0
    except Exception:
        pass

    # Clear brute force in-memory caches
    try:
        from src.auth import brute_force_protection as bf_mod
        bf_mod._ip_failure_cache.clear()
        bf_mod._ip_block_cache.clear()
    except Exception:
        pass

    # Disable background webhook triggers in tests.
    # With StaticPool (single connection), asyncio.create_task() for webhook
    # delivery opens a concurrent DB session that interferes with the main
    # test flow's transaction on the shared connection.
    try:
        from src.auth import security_logger as sl_mod

        async def _noop_webhooks(*args, **kwargs):
            pass

        monkeypatch.setattr(sl_mod.SecurityLogger, "_trigger_webhooks", _noop_webhooks)
    except Exception:
        pass

    yield

    # Cleanup
    Base.metadata.drop_all(sync_engine)
    sync_engine.dispose()

    async def _dispose_async():
        await async_engine.dispose()

    try:
        asyncio.run(_dispose_async())
    except Exception:
        pass
