"""
Conversation History Manager
Manages chat conversation sessions and message history using Redis
"""

import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from redis import Redis
from loguru import logger


class ConversationManager:
    """Manage conversation sessions and message history"""

    def __init__(self, redis_client: Redis):
        """
        Initialize conversation manager

        Args:
            redis_client: Redis client instance
        """
        self.client = redis_client

    def create_session(self, title: str = None) -> str:
        """
        Create a new conversation session

        Args:
            title: Optional session title (auto-generated from first message if not provided)

        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        session_data = {
            'id': session_id,
            'title': title or '새 대화',
            'created_at': now,
            'updated_at': now,
            'message_count': '0'
        }

        # Store session metadata
        self.client.hset(f'conversation:{session_id}', mapping=session_data)

        # Add to sessions list (sorted set by updated_at timestamp)
        self.client.zadd('conversations:list', {session_id: datetime.now().timestamp()})

        logger.info(f"Created conversation session: {session_id}")
        return session_id

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
        if not self.client.exists(f'conversation:{session_id}'):
            logger.warning(f"Session {session_id} does not exist")
            return False

        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }

        if metadata:
            message['metadata'] = metadata

        # Append message to session's message list
        self.client.rpush(
            f'conversation:{session_id}:messages',
            json.dumps(message, ensure_ascii=False)
        )

        # Update session metadata
        now = datetime.now()
        pipe = self.client.pipeline()
        pipe.hset(f'conversation:{session_id}', 'updated_at', now.isoformat())
        pipe.hincrby(f'conversation:{session_id}', 'message_count', 1)

        # Update title with first user message if still "새 대화"
        current_title = self.client.hget(f'conversation:{session_id}', 'title')
        if current_title and current_title.decode('utf-8') == '새 대화' and role == 'user':
            # Use first 30 characters of user message as title
            title = content[:30] + '...' if len(content) > 30 else content
            pipe.hset(f'conversation:{session_id}', 'title', title)

        # Update sorted set timestamp
        pipe.zadd('conversations:list', {session_id: now.timestamp()})

        pipe.execute()

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
        if not self.client.exists(f'conversation:{session_id}'):
            logger.warning(f"Session {session_id} does not exist")
            return []

        messages_key = f'conversation:{session_id}:messages'

        if limit:
            end = offset + limit - 1
            raw_messages = self.client.lrange(messages_key, offset, end)
        else:
            raw_messages = self.client.lrange(messages_key, offset, -1)

        messages = []
        for raw in raw_messages:
            try:
                msg = json.loads(raw.decode('utf-8'))
                messages.append(msg)
            except Exception as e:
                logger.error(f"Failed to parse message: {e}")

        return messages

    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        Get session metadata

        Args:
            session_id: Conversation session ID

        Returns:
            Session data dictionary or None
        """
        session_data = self.client.hgetall(f'conversation:{session_id}')

        if not session_data:
            return None

        return {
            k.decode('utf-8'): v.decode('utf-8')
            for k, v in session_data.items()
        }

    def session_exists(self, session_id: str) -> bool:
        """
        Check if a conversation session exists

        Args:
            session_id: Conversation session ID

        Returns:
            True if session exists, False otherwise
        """
        return self.client.exists(f'conversation:{session_id}') > 0

    def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        List conversation sessions (sorted by most recent)

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of session dictionaries
        """
        # Get session IDs from sorted set (most recent first)
        session_ids = self.client.zrevrange(
            'conversations:list',
            offset,
            offset + limit - 1
        )

        sessions = []
        for session_id in session_ids:
            session_id = session_id.decode('utf-8')
            session = self.get_session(session_id)
            if session:
                sessions.append(session)

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a conversation session and all its messages

        Args:
            session_id: Conversation session ID

        Returns:
            True if successful
        """
        if not self.client.exists(f'conversation:{session_id}'):
            logger.warning(f"Session {session_id} does not exist")
            return False

        pipe = self.client.pipeline()

        # Delete session metadata
        pipe.delete(f'conversation:{session_id}')

        # Delete session messages
        pipe.delete(f'conversation:{session_id}:messages')

        # Remove from sessions list
        pipe.zrem('conversations:list', session_id)

        pipe.execute()

        logger.info(f"Deleted conversation session: {session_id}")
        return True

    def clear_all_sessions(self) -> int:
        """
        Delete all conversation sessions (use with caution)
        Pipeline 최적화로 모든 세션을 한 번에 삭제

        Returns:
            Number of sessions deleted
        """
        session_ids_bytes = self.client.zrange('conversations:list', 0, -1)

        if not session_ids_bytes:
            logger.info("No conversation sessions to delete")
            return 0

        session_ids = [sid.decode('utf-8') for sid in session_ids_bytes]

        # 단일 Pipeline으로 모든 세션 삭제 (N+1 쿼리 제거)
        pipe = self.client.pipeline()
        for session_id in session_ids:
            pipe.delete(f'conversation:{session_id}')
            pipe.delete(f'conversation:{session_id}:messages')
            pipe.zrem('conversations:list', session_id)
        pipe.execute()

        count = len(session_ids)
        logger.info(f"Deleted {count} conversation sessions (batch)")
        return count

    def get_session_count(self) -> int:
        """
        Get total number of conversation sessions

        Returns:
            Number of sessions
        """
        return self.client.zcard('conversations:list')

    def toggle_bookmark(self, session_id: str) -> bool:
        """
        Toggle bookmark status for a conversation session

        Args:
            session_id: Conversation session ID

        Returns:
            New bookmark status (True if bookmarked, False if unbookmarked)
        """
        if not self.client.exists(f'conversation:{session_id}'):
            logger.warning(f"Session {session_id} does not exist")
            return False

        # Get current bookmark status
        current_status = self.client.hget(f'conversation:{session_id}', 'is_bookmarked')
        is_bookmarked = current_status and current_status.decode('utf-8') == '1'

        # Toggle bookmark status
        new_status = '0' if is_bookmarked else '1'
        self.client.hset(f'conversation:{session_id}', 'is_bookmarked', new_status)

        # Update bookmarks sorted set
        if new_status == '1':
            # Add to bookmarks set
            self.client.zadd('conversations:bookmarked', {session_id: datetime.now().timestamp()})
            logger.info(f"Bookmarked conversation: {session_id}")
        else:
            # Remove from bookmarks set
            self.client.zrem('conversations:bookmarked', session_id)
            logger.info(f"Unbookmarked conversation: {session_id}")

        return new_status == '1'

    def list_bookmarked_sessions(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        List bookmarked conversation sessions (sorted by most recent)

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of bookmarked session dictionaries
        """
        # Get bookmarked session IDs from sorted set (most recent first)
        session_ids = self.client.zrevrange(
            'conversations:bookmarked',
            offset,
            offset + limit - 1
        )

        sessions = []
        for session_id in session_ids:
            session_id = session_id.decode('utf-8')
            session = self.get_session(session_id)
            if session:
                sessions.append(session)

        return sessions

    def get_bookmarked_count(self) -> int:
        """
        Get total number of bookmarked conversations

        Returns:
            Number of bookmarked sessions
        """
        return self.client.zcard('conversations:bookmarked')
