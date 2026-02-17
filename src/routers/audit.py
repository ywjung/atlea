"""
Audit Log Management Router

Handles audit logging and compliance including:
- Audit log retrieval with filtering
- Audit statistics and analytics
- User activity tracking
- Available audit action types

Admin privileges required for all endpoints.
"""

from fastapi import APIRouter, Depends, Request
from typing import Optional
from loguru import logger

from ..audit import AuditAction
from ..auth.middleware import require_admin
from ..utils.error_handling import (
    raise_server_error,
    raise_bad_request,
    raise_service_unavailable,
)

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
        cache_mgr: CacheManager instance
    """
    global audit_logger, cache_manager
    audit_logger = audit_log
    cache_manager = cache_mgr


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
    offset: int = 0,
    _=Depends(require_admin)
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
        if not cache_manager:
            raise_service_unavailable("캐시 관리자", "get audit logs")

        # Audit logger 가져오기
        if not audit_logger:
            raise_service_unavailable("감사 로거", "get audit logs")

        # 작업 유형 검증
        action_enum = None
        if action:
            try:
                action_enum = AuditAction(action)
            except ValueError:
                raise_bad_request(f"유효하지 않은 작업 유형: {action}", "get audit logs")

        # 로그 조회 (username 인덱스 사용으로 효율적 필터링)
        logs = audit_logger.get_logs(
            user_id=user_id,
            username=username,  # username 인덱스 사용
            action=action_enum,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )

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

    except Exception as e:
        raise_server_error(e, "get audit logs", "감사 로그 조회에 실패했습니다")


@router.get("/audit/stats", tags=["Audit"])
async def get_audit_stats(
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    _=Depends(require_admin)
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
        if not cache_manager:
            raise_service_unavailable("캐시 관리자", "get audit stats")

        # Audit logger 가져오기
        if not audit_logger:
            raise_service_unavailable("감사 로거", "get audit stats")

        # 통계 조회
        stats = audit_logger.get_stats(
            start_date=start_date,
            end_date=end_date
        )

        return stats

    except Exception as e:
        raise_server_error(e, "get audit stats", "감사 로그 통계 조회에 실패했습니다")


@router.get("/audit/user/{user_id}", tags=["Audit"])
async def get_user_audit_logs(
    request: Request,
    user_id: str,
    limit: int = 50,
    _=Depends(require_admin)
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
        if not cache_manager:
            raise_service_unavailable("캐시 관리자", "get user audit logs")

        # Audit logger 가져오기
        if not audit_logger:
            raise_service_unavailable("감사 로거", "get user audit logs")

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

    except Exception as e:
        raise_server_error(e, "get user audit logs", "사용자 감사 로그 조회에 실패했습니다")


@router.get("/audit/actions", tags=["Audit"])
async def get_audit_actions(request: Request, _=Depends(require_admin)):
    """
    사용 가능한 감사 로그 작업 유형 목록 (관리자 전용)

    Returns:
        작업 유형 목록
    """
    try:
        if not cache_manager:
            raise_service_unavailable("캐시 관리자", "get audit actions")

        # 작업 유형 목록
        actions = [
            {"value": action.value, "description": action.value.replace("_", " ").title()}
            for action in AuditAction
        ]

        return {"actions": actions}

    except Exception as e:
        raise_server_error(e, "get audit actions", "작업 유형 조회에 실패했습니다")
