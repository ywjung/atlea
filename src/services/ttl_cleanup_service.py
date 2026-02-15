"""
TTL Cleanup Service

Periodically deletes expired rows from PostgreSQL tables that use TTL semantics
(token_blacklist, captcha_challenges, password_reset_tokens, ip_rate_limits, sessions,
semantic_cache, embedding_cache, query_result_cache, followup_cache).
Handles TTL-based row cleanup.
"""

import asyncio
from datetime import datetime, timezone
from loguru import logger

from ..database.connection import AsyncSessionFactory
from ..repositories.token_blacklist_repository import TokenBlacklistRepository
from ..repositories.captcha_repository import CaptchaRepository
from ..repositories.password_reset_repository import PasswordResetRepository
from ..repositories.ip_rate_limit_repository import IpRateLimitRepository
from ..repositories.session_repository import SessionRepository


async def cleanup_expired_rows() -> dict:
    """Delete expired rows from all TTL-based tables.

    Returns:
        Dict with count of deleted rows per table.
    """
    results = {}

    async with AsyncSessionFactory() as session:
        try:
            # Token blacklist
            repo = TokenBlacklistRepository(session)
            results["token_blacklist"] = await repo.delete_expired()
        except Exception as e:
            logger.error(f"token_blacklist cleanup failed: {e}")
            results["token_blacklist"] = -1

        try:
            # Captcha challenges
            repo = CaptchaRepository(session)
            results["captcha_challenges"] = await repo.delete_expired()
        except Exception as e:
            logger.error(f"captcha_challenges cleanup failed: {e}")
            results["captcha_challenges"] = -1

        try:
            # Password reset tokens
            repo = PasswordResetRepository(session)
            results["password_reset_tokens"] = await repo.delete_expired()
        except Exception as e:
            logger.error(f"password_reset_tokens cleanup failed: {e}")
            results["password_reset_tokens"] = -1

        try:
            # IP rate limits
            repo = IpRateLimitRepository(session)
            results["ip_rate_limits"] = await repo.delete_expired()
        except Exception as e:
            logger.error(f"ip_rate_limits cleanup failed: {e}")
            results["ip_rate_limits"] = -1

        try:
            # Expired sessions
            repo = SessionRepository(session)
            results["sessions"] = await repo.delete_expired()
        except Exception as e:
            logger.error(f"sessions cleanup failed: {e}")
            results["sessions"] = -1

        # Cache tables
        try:
            from sqlalchemy import delete
            from ..database.models.semantic_cache import SemanticCache
            from ..database.models.generic_cache import (
                EmbeddingCache, QueryResultCache, FollowupCache,
            )

            now = datetime.now(timezone.utc)

            r = await session.execute(
                delete(SemanticCache).where(SemanticCache.expires_at <= now)
            )
            results["semantic_cache"] = r.rowcount

            r = await session.execute(
                delete(EmbeddingCache).where(EmbeddingCache.expires_at <= now)
            )
            results["embedding_cache"] = r.rowcount

            r = await session.execute(
                delete(QueryResultCache).where(QueryResultCache.expires_at <= now)
            )
            results["query_result_cache"] = r.rowcount

            r = await session.execute(
                delete(FollowupCache).where(FollowupCache.expires_at <= now)
            )
            results["followup_cache"] = r.rowcount
        except Exception as e:
            logger.error(f"cache tables cleanup failed: {e}")
            results["cache_tables"] = -1

        await session.commit()

    return results


async def ttl_cleanup_scheduler(interval_seconds: int = 300):
    """Background scheduler that runs cleanup every `interval_seconds` (default 5 min).

    Args:
        interval_seconds: Seconds between cleanup runs.
    """
    logger.info(f"TTL cleanup scheduler started (interval={interval_seconds}s)")

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            results = await cleanup_expired_rows()

            total = sum(v for v in results.values() if v > 0)
            if total > 0:
                logger.info(f"TTL cleanup: {results}")
            else:
                logger.debug("TTL cleanup: no expired rows")

        except asyncio.CancelledError:
            logger.info("TTL cleanup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"TTL cleanup scheduler error: {e}")
            await asyncio.sleep(60)
