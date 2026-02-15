"""Config Service - PostgreSQL configuration management

시스템 설정(config:* 키)의 PostgreSQL 전용 서비스.
- Read/Write: PostgreSQL only (system_config 테이블)
- Sync + Async API 제공
"""

from typing import Optional

from loguru import logger
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.connection import AsyncSessionFactory, SyncSessionFactory
from ..database.models.system_config import SystemConfig
from ..repositories.config_repository import ConfigRepository


# ──────────────────────────────────────────────────────────────
# Internal helpers (async)
# ──────────────────────────────────────────────────────────────

async def _get_pg_value(key: str) -> Optional[str]:
    """PostgreSQL system_config 테이블에서 값 조회 (내부 세션 생성)."""
    try:
        async with AsyncSessionFactory() as session:
            repo = ConfigRepository(session)
            return await repo.get_value(key)
    except Exception as e:
        logger.debug(f"PG config read failed for '{key}': {e}")
        return None


async def _set_pg_value(
    key: str, value: str, value_type: str = "string", description: str | None = None
) -> bool:
    """PostgreSQL system_config 테이블에 값 저장."""
    try:
        async with AsyncSessionFactory() as session:
            repo = ConfigRepository(session)
            await repo.set_value(key, value, value_type, description)
            await session.commit()
        return True
    except Exception as e:
        logger.warning(f"PG config write failed for '{key}': {e}")
        return False


async def _delete_pg_value(key: str) -> bool:
    """PostgreSQL system_config 테이블에서 값 삭제."""
    try:
        async with AsyncSessionFactory() as session:
            repo = ConfigRepository(session)
            await repo.delete_key(key)
            await session.commit()
        return True
    except Exception as e:
        logger.warning(f"PG config delete failed for '{key}': {e}")
        return False


# ──────────────────────────────────────────────────────────────
# Public Async API
# ──────────────────────────────────────────────────────────────


async def config_get(key: str) -> Optional[str]:
    """설정 값 조회 (PostgreSQL).

    Args:
        key: 설정 키 (예: "config:tavily_api_key")

    Returns:
        설정 값 문자열, 없으면 None
    """
    return await _get_pg_value(key)


async def config_set(
    key: str,
    value: str,
    value_type: str = "string",
    description: str | None = None,
) -> bool:
    """설정 값 저장 (PostgreSQL).

    Args:
        key: 설정 키 (예: "config:tavily_api_key")
        value: 설정 값
        value_type: 값 타입 ("string", "boolean", "secret")
        description: 설정 설명

    Returns:
        성공 여부
    """
    return await _set_pg_value(key, value, value_type, description)


async def config_delete(key: str) -> bool:
    """설정 값 삭제 (PostgreSQL).

    Args:
        key: 설정 키

    Returns:
        성공 여부
    """
    return await _delete_pg_value(key)


async def config_get_multi(keys: list[str]) -> dict[str, Optional[str]]:
    """여러 설정 값 일괄 조회 (PostgreSQL).

    Args:
        keys: 설정 키 목록

    Returns:
        {key: value} 딕셔너리
    """
    result = {}
    for key in keys:
        result[key] = await config_get(key)
    return result


# ──────────────────────────────────────────────────────────────
# Public Sync API (for sync code: auth modules, middleware, etc.)
# ──────────────────────────────────────────────────────────────


def config_get_sync(key: str) -> Optional[str]:
    """설정 값 조회 — 동기 (PostgreSQL).

    Args:
        key: 설정 키

    Returns:
        설정 값 문자열, 없으면 None
    """
    try:
        with SyncSessionFactory() as session:
            config = session.get(SystemConfig, key)
            return config.value if config else None
    except Exception as e:
        logger.debug(f"PG sync config read failed for '{key}': {e}")
        return None


def config_set_sync(
    key: str,
    value: str,
    value_type: str = "string",
    description: str | None = None,
) -> bool:
    """설정 값 저장 — 동기 (PostgreSQL).

    Args:
        key: 설정 키
        value: 설정 값
        value_type: 값 타입
        description: 설정 설명

    Returns:
        성공 여부
    """
    try:
        with SyncSessionFactory() as session:
            existing = session.get(SystemConfig, key)
            if existing:
                existing.value = value
                existing.value_type = value_type
                if description is not None:
                    existing.description = description
            else:
                config = SystemConfig(
                    key=key, value=value, value_type=value_type, description=description
                )
                session.add(config)
            session.commit()
        return True
    except Exception as e:
        logger.warning(f"PG sync config write failed for '{key}': {e}")
        return False


def config_delete_sync(key: str) -> bool:
    """설정 값 삭제 — 동기 (PostgreSQL).

    Args:
        key: 설정 키

    Returns:
        성공 여부
    """
    try:
        with SyncSessionFactory() as session:
            existing = session.get(SystemConfig, key)
            if existing:
                session.delete(existing)
                session.commit()
                return True
            return False
    except Exception as e:
        logger.warning(f"PG sync config delete failed for '{key}': {e}")
        return False
