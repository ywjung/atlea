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
        vector_db_instance: Vector database instance
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
    Clean up stale reindexing state from previous abnormal shutdown.

    Reindex progress is now stored in-memory (documents router _reindex_progress dict),
    so on startup we just reset the reindex event to ensure clean state.
    """
    try:
        if reindex_event and not reindex_event.is_set():
            reindex_event.set()
            logger.warning("🧹 Cleared stale reindex state from previous shutdown")
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
