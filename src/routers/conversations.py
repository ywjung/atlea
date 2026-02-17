"""
Conversation Management Router

Handles conversation session management including:
- Creating and listing conversation sessions
- Retrieving conversation messages
- Deleting conversations (single or all)
- Bookmarking conversations
- Listing bookmarked conversations

All endpoints require authentication.
Conversations are scoped to the authenticated user (IDOR protection).
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from loguru import logger
import html

from ..auth.middleware import get_current_active_user
from ..utils.error_handling import (
    raise_server_error,
    raise_not_found,
    raise_service_unavailable,
)


def sanitize_title(title: Optional[str]) -> Optional[str]:
    """Sanitize title to prevent XSS and enforce length limits"""
    if title is None:
        return None
    # Strip whitespace and limit length
    title = title.strip()[:200]
    # Escape HTML to prevent XSS
    title = html.escape(title)
    return title if title else None

# Create router with prefix and tags
router = APIRouter(prefix="/api", tags=["Conversations"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

conversation_manager = None


def inject_dependencies(conv_manager):
    """
    Inject dependencies from main application

    Args:
        conv_manager: ConversationManager instance for conversation operations
    """
    global conversation_manager
    conversation_manager = conv_manager




# ============================================================================
# Conversation API Endpoints
# ============================================================================

@router.post("/conversations", tags=["Conversations"])
async def create_conversation(
    title: Optional[str] = Query(
        default=None,
        max_length=200,
        description="Optional conversation title (max 200 characters)"
    ),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Create a new conversation session (로그인 필요)

    Creates a new conversation session with optional title.
    Each session maintains its own message history.
    """
    try:
        if not conversation_manager:
            raise_service_unavailable("대화 관리자", "create conversation")

        user_id = current_user.get("user_id")
        safe_title = sanitize_title(title)
        session_id = conversation_manager.create_session(title=safe_title, user_id=user_id)
        session = conversation_manager.get_session(session_id, user_id=user_id)

        logger.info(f"Created conversation {session_id} for user {user_id}")

        return {
            "session_id": session_id,
            "session": session
        }
    except Exception as e:
        raise_server_error(e, "create conversation")


@router.get("/conversations", tags=["Conversations"])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum sessions to return (1-200)"),
    offset: int = Query(default=0, ge=0, le=10000, description="Sessions to skip (0-10000)"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    List conversation sessions (로그인 필요)

    Returns a paginated list of conversation sessions sorted by most recent.
    Only returns conversations owned by the authenticated user.
    """
    try:
        if not conversation_manager:
            raise_service_unavailable("대화 관리자", "list conversations")

        user_id = current_user.get("user_id")
        sessions = conversation_manager.list_sessions(limit=limit, offset=offset, user_id=user_id)
        total_count = conversation_manager.get_session_count(user_id=user_id)

        return {
            "sessions": sessions,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise_server_error(e, "list conversations")


@router.get("/conversations/{session_id}", tags=["Conversations"])
async def get_conversation(
    session_id: str,
    limit: int = None,
    offset: int = 0,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get conversation session with messages (로그인 필요)

    Retrieves a specific conversation session including its metadata and messages.
    Returns 404 if the conversation doesn't exist or is not owned by the user.
    """
    try:
        if not conversation_manager:
            raise_service_unavailable("대화 관리자", "get conversation")

        user_id = current_user.get("user_id")
        session = conversation_manager.get_session(session_id, user_id=user_id)
        if not session:
            raise_not_found("대화", "get conversation")

        messages = conversation_manager.get_messages(session_id, limit=limit, offset=offset, user_id=user_id)

        return {
            "session": session,
            "messages": messages,
            "message_count": len(messages)
        }
    except Exception as e:
        raise_server_error(e, "get conversation")


@router.delete("/conversations/{session_id}", tags=["Conversations"])
async def delete_conversation(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete a conversation session and all its messages (로그인 필요)

    Returns 404 if the conversation doesn't exist or is not owned by the user.
    """
    try:
        if not conversation_manager:
            raise_service_unavailable("대화 관리자", "delete conversation")

        user_id = current_user.get("user_id")
        success = conversation_manager.delete_session(session_id, user_id=user_id)

        if not success:
            raise_not_found("대화", "delete conversation")

        logger.info(f"Deleted conversation {session_id} by user {user_id}")

        return {
            "status": "success",
            "message": f"Conversation {session_id} deleted successfully"
        }
    except Exception as e:
        raise_server_error(e, "delete conversation")


@router.delete("/conversations", tags=["Conversations"])
async def delete_all_conversations(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete all conversation sessions for the current user (로그인 필요)

    Only deletes conversations owned by the authenticated user.
    """
    try:
        if not conversation_manager:
            raise_service_unavailable("대화 관리자", "delete all conversations")

        user_id = current_user.get("user_id")
        deleted_count = conversation_manager.clear_all_sessions(user_id=user_id)

        logger.warning(f"Deleted ALL {deleted_count} conversations by user {user_id}")

        return {
            "status": "success",
            "message": f"Successfully deleted {deleted_count} conversations",
            "deleted_count": deleted_count
        }
    except Exception as e:
        raise_server_error(e, "delete all conversations")


@router.post("/conversations/{session_id}/bookmark", tags=["Conversations"])
async def toggle_bookmark(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Toggle bookmark status for a conversation (로그인 필요)

    Returns 404 if the conversation doesn't exist or is not owned by the user.
    """
    try:
        if not conversation_manager:
            raise_service_unavailable("대화 관리자", "toggle bookmark")

        user_id = current_user.get("user_id")
        is_bookmarked = conversation_manager.toggle_bookmark(session_id, user_id=user_id)

        action = "bookmarked" if is_bookmarked else "unbookmarked"
        logger.info(f"User {user_id} {action} conversation {session_id}")

        return {
            "status": "success",
            "session_id": session_id,
            "is_bookmarked": is_bookmarked
        }
    except Exception as e:
        raise_server_error(e, "toggle bookmark")


@router.get("/conversations/bookmarked/list", tags=["Conversations"])
async def get_bookmarked_conversations(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum conversations to return (1-200)"),
    offset: int = Query(default=0, ge=0, le=10000, description="Conversations to skip (0-10000)"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get list of bookmarked conversations (로그인 필요)

    Only returns bookmarked conversations owned by the authenticated user.
    """
    try:
        if not conversation_manager:
            raise_service_unavailable("대화 관리자", "get bookmarked conversations")

        user_id = current_user.get("user_id")
        sessions = conversation_manager.list_bookmarked_sessions(limit, offset, user_id=user_id)
        total = conversation_manager.get_bookmarked_count(user_id=user_id)

        return {
            "status": "success",
            "sessions": sessions,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise_server_error(e, "get bookmarked conversations")
