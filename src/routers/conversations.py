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

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
import logging

from ..auth.middleware import get_current_active_user

# Configure logger
logger = logging.getLogger(__name__)

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
# Helper Functions
# ============================================================================

def get_safe_error_message(error: Exception, context: str = "") -> str:
    """
    Get sanitized error message for user display

    Prevents information disclosure by mapping exception types to
    generic user-friendly messages while logging the full error.

    Args:
        error: The exception that occurred
        context: Context string for logging (e.g., "create conversation endpoint")

    Returns:
        Safe error message suitable for user display
    """
    error_type = type(error).__name__

    # Log full error for debugging
    logger.error(f"Error in {context}: {error_type}: {str(error)}")

    # Map exception types to safe messages
    error_messages = {
        "FileNotFoundError": "요청한 리소스를 찾을 수 없습니다.",
        "PermissionError": "접근 권한이 없습니다.",
        "ValueError": "잘못된 입력값입니다.",
        "ConnectionError": "서비스 연결에 실패했습니다.",
        "TimeoutError": "요청 시간이 초과되었습니다.",
    }

    # Return mapped message or generic message
    return error_messages.get(
        error_type,
        "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    )


# ============================================================================
# Conversation API Endpoints
# ============================================================================

@router.post("/conversations", tags=["Conversations"])
async def create_conversation(
    title: str = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Create a new conversation session (로그인 필요)

    Creates a new conversation session with optional title.
    Each session maintains its own message history.

    Args:
        title: Optional conversation title
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

        session_id = conversation_manager.create_session(title=title)
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
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_active_user)
):
    """
    List conversation sessions (로그인 필요)

    Returns a paginated list of conversation sessions sorted by most recent.
    Useful for displaying conversation history in UI.

    Args:
        limit: Maximum number of sessions to return (default: 50)
        offset: Number of sessions to skip for pagination (default: 0)
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
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get list of bookmarked conversations (로그인 필요)

    Returns a paginated list of conversations that have been bookmarked.
    Useful for "Favorites" or "Starred" conversations view.

    Args:
        limit: Maximum number of conversations to return (default: 50)
        offset: Number of conversations to skip for pagination (default: 0)
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
