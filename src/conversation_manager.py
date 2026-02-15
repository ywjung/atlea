"""
Conversation History Manager
Manages chat conversation sessions and message history using PostgreSQL
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional
from contextlib import contextmanager
from loguru import logger

from sqlalchemy import select, func, update, delete
from sqlalchemy.orm import Session as SaSession

from .database.connection import SyncSessionFactory
from .database.models.conversation import Conversation
from .database.models.conversation_message import ConversationMessage


class ConversationManager:
    """Manage conversation sessions and message history"""

    # 대화 세션 기본 TTL: 30일 (초)
    SESSION_TTL = 30 * 24 * 60 * 60

    def __init__(self):
        """
        Initialize conversation manager

        Args:
        """
        pass

    @contextmanager
    def _acquire_lock(self, lock_key: str, timeout: int = 10, retry_delay: float = 0.1):
        """
        Context manager kept for backward compatibility.
        PG transactions provide the needed atomicity, so this is a no-op wrapper.
        """
        yield True

    def create_session(self, title: str = None) -> str:
        """
        Create a new conversation session

        Args:
            title: Optional session title (auto-generated from first message if not provided)

        Returns:
            Session ID
        """
        session_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        conv = Conversation(
            id=session_id,
            title=title or "새 대화",
            created_at=now,
            updated_at=now,
            message_count=0,
            is_bookmarked=False,
        )

        with SyncSessionFactory() as db:
            db.add(conv)
            db.commit()

        logger.info(f"Created conversation session: {session_id}")
        return str(session_id)

    def add_message(self, session_id: str, role: str, content: str, metadata: Dict = None) -> bool:
        """
        Add a message to conversation history

        Args:
            session_id: Conversation session ID
            role: Message role ('user' or 'assistant')
            content: Message content
            metadata: Optional metadata (sources, chunk_count, etc.)

        Returns:
            True if successful
        """
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            logger.warning(f"Invalid session ID: {session_id}")
            return False

        with SyncSessionFactory() as db:
            conv = db.get(Conversation, sid)
            if conv is None:
                logger.warning(f"Session {session_id} does not exist")
                return False

            now = datetime.now(timezone.utc)

            msg = ConversationMessage(
                conversation_id=sid,
                role=role,
                content=content,
                metadata_json=metadata,
                created_at=now,
            )
            db.add(msg)

            # Update session metadata
            conv.updated_at = now
            conv.message_count = conv.message_count + 1

            # Update title with first user message if still default
            if conv.title == "새 대화" and role == "user":
                conv.title = content[:30] + "..." if len(content) > 30 else content

            db.commit()

        return True

    def get_messages(self, session_id: str, limit: int = None, offset: int = 0) -> List[Dict]:
        """
        Get conversation messages

        Args:
            session_id: Conversation session ID
            limit: Maximum number of messages to return (None = all)
            offset: Number of messages to skip

        Returns:
            List of message dictionaries
        """
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return []

        with SyncSessionFactory() as db:
            conv = db.get(Conversation, sid)
            if conv is None:
                logger.warning(f"Session {session_id} does not exist")
                return []

            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == sid)
                .order_by(ConversationMessage.created_at)
                .offset(offset)
            )
            if limit is not None:
                stmt = stmt.limit(limit)

            result = db.execute(stmt)
            rows = result.scalars().all()

        messages = []
        for row in rows:
            msg = {
                "role": row.role,
                "content": row.content,
                "timestamp": row.created_at.isoformat() if row.created_at else None,
            }
            if row.metadata_json:
                msg["metadata"] = row.metadata_json
            messages.append(msg)

        return messages

    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Get session metadata

        Args:
            session_id: Conversation session ID

        Returns:
            Session data dictionary or None
        """
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return None

        with SyncSessionFactory() as db:
            conv = db.get(Conversation, sid)
            if conv is None:
                return None

            return {
                "id": str(conv.id),
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "message_count": str(conv.message_count),
                "is_bookmarked": "1" if conv.is_bookmarked else "0",
            }

    def session_exists(self, session_id: str) -> bool:
        """
        Check if a conversation session exists

        Args:
            session_id: Conversation session ID

        Returns:
            True if session exists, False otherwise
        """
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            conv = db.get(Conversation, sid)
            return conv is not None

    def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        List conversation sessions (sorted by most recent)

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of session dictionaries
        """
        with SyncSessionFactory() as db:
            stmt = (
                select(Conversation)
                .order_by(Conversation.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = db.execute(stmt)
            rows = result.scalars().all()

        sessions = []
        for conv in rows:
            sessions.append({
                "id": str(conv.id),
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "message_count": str(conv.message_count),
                "is_bookmarked": "1" if conv.is_bookmarked else "0",
            })

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a conversation session and all its messages

        Args:
            session_id: Conversation session ID

        Returns:
            True if successful
        """
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            conv = db.get(Conversation, sid)
            if conv is None:
                logger.warning(f"Session {session_id} does not exist")
                return False

            db.delete(conv)  # CASCADE deletes messages
            db.commit()

        logger.info(f"Deleted conversation session: {session_id}")
        return True

    def clear_all_sessions(self) -> int:
        """
        Delete all conversation sessions (use with caution)

        Returns:
            Number of sessions deleted
        """
        with SyncSessionFactory() as db:
            count_stmt = select(func.count()).select_from(Conversation)
            count = db.execute(count_stmt).scalar_one()

            if count == 0:
                logger.info("No conversation sessions to delete")
                return 0

            db.execute(delete(Conversation))
            db.commit()

        logger.info(f"Deleted {count} conversation sessions (batch)")
        return count

    def get_session_count(self) -> int:
        """
        Get total number of conversation sessions

        Returns:
            Number of sessions
        """
        with SyncSessionFactory() as db:
            stmt = select(func.count()).select_from(Conversation)
            return db.execute(stmt).scalar_one()

    def toggle_bookmark(self, session_id: str) -> bool:
        """
        Toggle bookmark status for a conversation session

        Args:
            session_id: Conversation session ID

        Returns:
            New bookmark status (True if bookmarked, False if unbookmarked)
        """
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            conv = db.get(Conversation, sid)
            if conv is None:
                logger.warning(f"Session {session_id} does not exist")
                return False

            conv.is_bookmarked = not conv.is_bookmarked
            new_status = conv.is_bookmarked
            db.commit()

        action = "Bookmarked" if new_status else "Unbookmarked"
        logger.info(f"{action} conversation: {session_id}")
        return new_status

    def list_bookmarked_sessions(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        List bookmarked conversation sessions (sorted by most recent)

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of bookmarked session dictionaries
        """
        with SyncSessionFactory() as db:
            stmt = (
                select(Conversation)
                .where(Conversation.is_bookmarked == True)
                .order_by(Conversation.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = db.execute(stmt)
            rows = result.scalars().all()

        sessions = []
        for conv in rows:
            sessions.append({
                "id": str(conv.id),
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "message_count": str(conv.message_count),
                "is_bookmarked": "1",
            })

        return sessions

    def get_bookmarked_count(self) -> int:
        """
        Get total number of bookmarked conversations

        Returns:
            Number of bookmarked sessions
        """
        with SyncSessionFactory() as db:
            stmt = (
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.is_bookmarked == True)
            )
            return db.execute(stmt).scalar_one()

    def get_last_message(self, session_id: str) -> Optional[Dict]:
        """
        Get the last message in a session

        Args:
            session_id: Conversation session ID

        Returns:
            Last message as dict, or None if not found
        """
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return None

        with SyncSessionFactory() as db:
            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == sid)
                .order_by(ConversationMessage.created_at.desc())
                .limit(1)
            )
            result = db.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return None

            msg = {
                "role": row.role,
                "content": row.content,
                "timestamp": row.created_at.isoformat() if row.created_at else None,
            }
            if row.metadata_json:
                msg["metadata"] = row.metadata_json
            return msg

    def update_last_message_metadata(self, session_id: str, metadata_update: Dict) -> bool:
        """
        Update the metadata of the last message in a session

        Args:
            session_id: Conversation session ID
            metadata_update: Dictionary of metadata fields to add/update

        Returns:
            True if successful, False otherwise
        """
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            conv = db.get(Conversation, sid)
            if conv is None:
                logger.warning(f"Session {session_id} does not exist")
                return False

            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == sid)
                .order_by(ConversationMessage.created_at.desc())
                .limit(1)
            )
            result = db.execute(stmt)
            last_msg = result.scalar_one_or_none()

            if last_msg is None:
                logger.warning(f"No messages in session {session_id}")
                return False

            # Merge metadata
            existing = last_msg.metadata_json or {}
            existing.update(metadata_update)
            last_msg.metadata_json = existing
            db.commit()

        logger.debug(f"Updated last message metadata in session {session_id}")
        return True

    # --- Async wrappers (이벤트 루프 블로킹 방지) ---

    async def async_add_message(self, session_id: str, role: str, content: str, metadata: Dict = None) -> bool:
        """add_message의 비동기 래퍼"""
        import asyncio
        return await asyncio.to_thread(self.add_message, session_id, role, content, metadata)

    async def async_get_messages(self, session_id: str, limit: int = None, offset: int = 0) -> List[Dict]:
        """get_messages의 비동기 래퍼"""
        import asyncio
        return await asyncio.to_thread(self.get_messages, session_id, limit, offset)

    async def async_create_session(self, title: str = None) -> str:
        """create_session의 비동기 래퍼"""
        import asyncio
        return await asyncio.to_thread(self.create_session, title)

    async def async_list_sessions(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """list_sessions의 비동기 래퍼"""
        import asyncio
        return await asyncio.to_thread(self.list_sessions, limit, offset)
