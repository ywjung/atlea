"""
Conversation Management Router

Handles conversation session management including:
- Creating and listing conversation sessions
- Retrieving conversation messages
- Deleting conversations (single or all)
- Bookmarking conversations
- Listing bookmarked conversations

All endpoints require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from loguru import logger
import html

from ..auth.middleware import get_current_active_user
from ..utils.error_handling import get_safe_error_message


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

    Args:
        title: Optional conversation title (max 200 characters, sanitized for XSS)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Session ID and metadata
            - session_id: Unique session identifier
            - session: Session metadata (title, created_at, etc.)

    Raises:
        HTTPException: 500 if conversation manager not initialized or error occurs
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        # Sanitize title to prevent XSS
        safe_title = sanitize_title(title)
        session_id = conversation_manager.create_session(title=safe_title)
        session = conversation_manager.get_session(session_id)

        logger.info(f"Created conversation {session_id} for user {current_user.get('user_id')}")

        return {
            "session_id": session_id,
            "session": session
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "create conversation endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.get("/conversations", tags=["Conversations"])
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum sessions to return (1-200)"),
    offset: int = Query(default=0, ge=0, le=10000, description="Sessions to skip (0-10000)"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    List conversation sessions (로그인 필요)

    Returns a paginated list of conversation sessions sorted by most recent.
    Useful for displaying conversation history in UI.

    Args:
        limit: Maximum number of sessions to return (1-200, default: 50)
        offset: Number of sessions to skip for pagination (0-10000, default: 0)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Paginated conversation list
            - sessions: List of conversation session objects
            - total_count: Total number of sessions
            - limit: Requested limit
            - offset: Requested offset

    Raises:
        HTTPException: 500 if conversation manager not initialized or error occurs
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        sessions = conversation_manager.list_sessions(limit=limit, offset=offset)
        total_count = conversation_manager.get_session_count()

        return {
            "sessions": sessions,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "list conversations endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


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
    Supports pagination for large conversations.

    Args:
        session_id: Conversation session ID
        limit: Maximum number of messages to return (None = all messages)
        offset: Number of messages to skip for pagination (default: 0)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Conversation session and messages
            - session: Session metadata
            - messages: List of messages (user/assistant)
            - message_count: Number of messages returned

    Raises:
        HTTPException: 404 if conversation not found
        HTTPException: 500 if conversation manager not initialized or error occurs
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        session = conversation_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Conversation {session_id} not found")

        messages = conversation_manager.get_messages(session_id, limit=limit, offset=offset)

        return {
            "session": session,
            "messages": messages,
            "message_count": len(messages)
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "get conversation endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.delete("/conversations/{session_id}", tags=["Conversations"])
async def delete_conversation(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete a conversation session and all its messages (로그인 필요)

    Permanently deletes a conversation session and all associated messages.
    This operation cannot be undone.

    Args:
        session_id: Conversation session ID to delete
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Success message
            - status: "success"
            - message: Confirmation message

    Raises:
        HTTPException: 404 if conversation not found
        HTTPException: 500 if conversation manager not initialized or error occurs
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        success = conversation_manager.delete_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Conversation {session_id} not found")

        logger.info(f"Deleted conversation {session_id} by user {current_user.get('user_id')}")

        return {
            "status": "success",
            "message": f"Conversation {session_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "delete conversation endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.delete("/conversations", tags=["Conversations"])
async def delete_all_conversations(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete all conversation sessions (로그인 필요)

    ⚠️ WARNING: This deletes ALL conversations for the user.
    Use with caution - this operation cannot be undone.

    Useful for:
    - Clearing all conversation history
    - Testing and development
    - Privacy/data cleanup

    Args:
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Success message with count
            - status: "success"
            - message: Confirmation message
            - deleted_count: Number of conversations deleted

    Raises:
        HTTPException: 500 if conversation manager not initialized or error occurs
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        deleted_count = conversation_manager.clear_all_sessions()

        logger.warning(f"Deleted ALL {deleted_count} conversations by user {current_user.get('user_id')}")

        return {
            "status": "success",
            "message": f"Successfully deleted {deleted_count} conversations",
            "deleted_count": deleted_count
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "delete all conversations endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/conversations/{session_id}/bookmark", tags=["Conversations"])
async def toggle_bookmark(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Toggle bookmark status for a conversation (로그인 필요)

    Bookmarks help users mark important conversations for quick access.
    Calling this endpoint toggles the bookmark status:
    - If not bookmarked → becomes bookmarked
    - If bookmarked → becomes unbookmarked

    Args:
        session_id: Conversation session ID
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: New bookmark status
            - status: "success"
            - session_id: Conversation ID
            - is_bookmarked: New bookmark status (true/false)

    Raises:
        HTTPException: 500 if conversation manager not initialized or error occurs
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        is_bookmarked = conversation_manager.toggle_bookmark(session_id)

        action = "bookmarked" if is_bookmarked else "unbookmarked"
        logger.info(f"User {current_user.get('user_id')} {action} conversation {session_id}")

        return {
            "status": "success",
            "session_id": session_id,
            "is_bookmarked": is_bookmarked
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "toggle bookmark endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.get("/conversations/bookmarked/list", tags=["Conversations"])
async def get_bookmarked_conversations(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum conversations to return (1-200)"),
    offset: int = Query(default=0, ge=0, le=10000, description="Conversations to skip (0-10000)"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get list of bookmarked conversations (로그인 필요)

    Returns a paginated list of conversations that have been bookmarked.
    Useful for "Favorites" or "Starred" conversations view.

    Args:
        limit: Maximum number of conversations to return (1-200, default: 50)
        offset: Number of conversations to skip for pagination (0-10000, default: 0)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Paginated bookmarked conversation list
            - status: "success"
            - sessions: List of bookmarked conversation sessions
            - total: Total number of bookmarked conversations
            - limit: Requested limit
            - offset: Requested offset

    Raises:
        HTTPException: 500 if conversation manager not initialized or error occurs
    """
    try:
        if not conversation_manager:
            raise HTTPException(status_code=500, detail="Conversation manager not initialized")

        sessions = conversation_manager.list_bookmarked_sessions(limit, offset)
        total = conversation_manager.get_bookmarked_count()

        return {
            "status": "success",
            "sessions": sessions,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "get bookmarked conversations endpoint")
        raise HTTPException(status_code=500, detail=safe_message)
