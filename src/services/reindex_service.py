"""
Reindex Service

Manages document reindexing state and coordination:
- Reindex event for progress tracking
- Stale state cleanup on startup
- Status checking for UI
"""

import asyncio
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Global reindex event (shared with documents router)
reindex_event: Optional[asyncio.Event] = None

# Global dependencies (injected from web_server.py)
vector_db = None


def inject_dependencies(vector_db_instance):
    """
    Inject dependencies from web_server.py

    Args:
        vector_db_instance: Vector database instance with Redis client
    """
    global vector_db
    vector_db = vector_db_instance


def initialize_reindex_event():
    """
    Initialize reindex event for coordination with documents router

    Returns:
        asyncio.Event: Event that signals reindex completion
    """
    global reindex_event
    reindex_event = asyncio.Event()
    reindex_event.set()  # Initially set (not reindexing)
    return reindex_event


def cleanup_stale_reindex_state():
    """
    Clean up stale reindexing state from previous abnormal shutdown

    Clears Redis reindex progress if:
    - Error state detected
    - Stuck for more than 1 hour
    """
    try:
        progress_data = vector_db.client.hgetall("reindex:progress")
        if progress_data:
            in_progress = progress_data.get(b'in_progress', b'false').decode() == 'true'
            step = progress_data.get(b'step', b'').decode()
            elapsed_seconds = int(progress_data.get(b'elapsed_seconds', 0))

            # Clear if: (1) error state, or (2) stuck for >1 hour
            should_clear = (
                in_progress and (
                    '오류' in step or
                    'error' in step.lower() or
                    elapsed_seconds > 3600  # 1 hour
                )
            )

            if should_clear:
                vector_db.client.delete("reindex:progress")
                logger.warning(f"🧹 Cleared stale reindex state (step: {step}, elapsed: {elapsed_seconds}s)")
            elif in_progress:
                logger.info(f"ℹ️  Found active reindex state (step: {step}, elapsed: {elapsed_seconds}s)")
    except Exception as e:
        logger.debug(f"Failed to check reindex state (non-critical): {e}")


def is_reindexing() -> bool:
    """
    Check if reindexing is currently in progress

    Returns:
        bool: True if reindexing is in progress, False otherwise
    """
    return reindex_event and not reindex_event.is_set()


def get_reindex_event() -> Optional[asyncio.Event]:
    """
    Get the reindex event for coordination

    Returns:
        Optional[asyncio.Event]: The reindex event or None if not initialized
    """
    return reindex_event
