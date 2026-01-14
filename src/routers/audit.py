"""
Audit Log Management Router

Handles audit logging and compliance including:
- Audit log retrieval with filtering
- Audit statistics and analytics
- User activity tracking
- Available audit action types

Admin privileges required for all endpoints.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional
import logging

from ..audit import AuditAction

# Configure logger
logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(prefix="/api/admin", tags=["Admin", "Audit"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

audit_logger = None
cache_manager = None


def inject_dependencies(audit_log, cache_mgr):
    """
    Inject dependencies from main application

    Args:
        audit_log: AuditLogger instance for logging operations
        cache_mgr: CacheManager instance for Redis access
    """
    global audit_logger, cache_manager
    audit_logger = audit_log
    cache_manager = cache_mgr


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
        context: Context string for logging (e.g., "audit endpoint")

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
# Audit Log API Endpoints
# ============================================================================

@router.get("/audit/logs", tags=["Audit"])
async def get_audit_logs(
    request: Request,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    감사 로그 조회 (관리자 전용)

    Query params:
        user_id: 사용자 ID 필터
        username: 사용자명 필터 (부분 매칭 지원)
        action: 작업 유형 필터 (login, document_upload, chat_query 등)
        start_date: 시작 날짜 (YYYY-MM-DD)
        end_date: 종료 날짜 (YYYY-MM-DD)
        limit: 최대 반환 개수 (기본: 100)
        offset: 오프셋 (페이지네이션)

    Returns:
        감사 로그 목록
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # Audit logger 가져오기
        if not audit_logger:
            raise HTTPException(status_code=503, detail="Audit logger not initialized")

        # 작업 유형 검증
        action_enum = None
        if action:
            try:
                action_enum = AuditAction(action)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

        # 로그 조회 (더 많이 가져와서 필터링 후 페이지네이션 적용)
        fetch_limit = limit * 10 if username else limit
        logs = audit_logger.get_logs(
            user_id=user_id,
            action=action_enum,
            start_date=start_date,
            end_date=end_date,
            limit=fetch_limit,
            offset=0 if username else offset
        )

        # username 필터링 (부분 매칭)
        if username:
            username_lower = username.lower()
            logs = [
                log for log in logs
                if log.get("username") and username_lower in log["username"].lower()
            ]
            # 필터링 후 페이지네이션 적용
            logs = logs[offset:offset + limit]

        return {
            "logs": logs,
            "count": len(logs),
            "limit": limit,
            "offset": offset,
            "filters": {
                "user_id": user_id,
                "username": username,
                "action": action,
                "start_date": start_date,
                "end_date": end_date
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit logs")


@router.get("/audit/stats", tags=["Audit"])
async def get_audit_stats(
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    감사 로그 통계 조회 (관리자 전용)

    Query params:
        start_date: 시작 날짜 (YYYY-MM-DD, 기본: 7일 전)
        end_date: 종료 날짜 (YYYY-MM-DD, 기본: 오늘)

    Returns:
        감사 로그 통계
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # Audit logger 가져오기
        if not audit_logger:
            raise HTTPException(status_code=503, detail="Audit logger not initialized")

        # 통계 조회
        stats = audit_logger.get_stats(
            start_date=start_date,
            end_date=end_date
        )

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit statistics")


@router.get("/audit/user/{user_id}", tags=["Audit"])
async def get_user_audit_logs(
    request: Request,
    user_id: str,
    limit: int = 50
):
    """
    특정 사용자의 감사 로그 조회 (관리자 전용)

    Path params:
        user_id: 사용자 ID

    Query params:
        limit: 최대 반환 개수 (기본: 50)

    Returns:
        사용자 활동 로그
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # Audit logger 가져오기
        if not audit_logger:
            raise HTTPException(status_code=503, detail="Audit logger not initialized")

        # 사용자 활동 조회
        logs = audit_logger.get_user_activity(
            user_id=user_id,
            limit=limit
        )

        return {
            "user_id": user_id,
            "logs": logs,
            "count": len(logs)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user audit logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user audit logs")


@router.get("/audit/actions", tags=["Audit"])
async def get_audit_actions(request: Request):
    """
    사용 가능한 감사 로그 작업 유형 목록 (관리자 전용)

    Returns:
        작업 유형 목록
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # 작업 유형 목록
        actions = [
            {"value": action.value, "description": action.value.replace("_", " ").title()}
            for action in AuditAction
        ]

        return {"actions": actions}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit actions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit actions")
