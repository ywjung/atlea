"""
Settings and Preferences Management Router

Handles user preferences and system settings including:
- User preferences (search scope, document/group filters)
- System settings (auto-logout timeout, warning time)
- Admin settings management

Authentication required for all endpoints.
Admin privileges required for admin-specific endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from typing import Optional, List
import json
import logging

from ..auth.middleware import get_current_active_user

# Configure logger
logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(prefix="/api", tags=["Settings"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

cache_manager = None


def inject_dependencies(cache_mgr):
    """
    Inject dependencies from main application

    Args:
        cache_mgr: CacheManager instance for Redis access
    """
    global cache_manager
    cache_manager = cache_mgr


# ============================================================================
# Pydantic Models
# ============================================================================

class UserPreferences(BaseModel):
    """사용자 설정"""
    search_scope: Optional[str] = "all"  # "all", "selected_documents", "selected_groups"
    selected_document_ids: Optional[List[str]] = []
    selected_group_ids: Optional[List[str]] = []
    active_filter_tab: Optional[str] = "documents"  # "documents" or "groups"
    group_filter_mode: Optional[str] = "all"  # "all" or "selected"


class HybridRAGStatusResponse(BaseModel):
    """하이브리드 RAG 상태 응답"""
    success: bool = True
    enabled: bool
    web_search_enabled: bool = False
    doc_search_enabled: bool = False


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
        context: Context string for logging (e.g., "settings endpoint")

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
# User Preferences API Endpoints
# ============================================================================

@router.get("/user/preferences", tags=["User", "Preferences"])
async def get_user_preferences(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """
    사용자 설정 조회 (로그인 필요)

    사용자의 검색 범위 설정, 선택된 문서/그룹 등을 조회합니다.

    Args:
        request: FastAPI request object (for Redis access)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: User preferences
            - success: True if successful
            - data: User preferences object
                - search_scope: Search scope setting
                - selected_document_ids: List of selected document IDs
                - selected_group_ids: List of selected group IDs
                - active_filter_tab: Active filter tab
                - group_filter_mode: Group filter mode

    Raises:
        HTTPException: 500 if cache manager not initialized or error occurs
    """
    try:
        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis = cache_manager.redis
        username = current_user.get("username")

        # Redis에서 사용자 설정 조회
        preferences_key = f"user:preferences:{username}"
        preferences_data = redis.get(preferences_key)

        if preferences_data:
            preferences = json.loads(preferences_data)
        else:
            # 기본값 반환
            preferences = {
                "search_scope": "all",
                "selected_document_ids": [],
                "selected_group_ids": [],
                "active_filter_tab": "documents",
                "group_filter_mode": "all"
            }

        logger.info(f"📋 사용자 설정 조회: {username}")
        return {
            "success": True,
            "data": preferences
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "get user preferences endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.put("/user/preferences", tags=["User", "Preferences"])
async def update_user_preferences(
    request: Request,
    preferences: UserPreferences,
    current_user: dict = Depends(get_current_active_user)
):
    """
    사용자 설정 저장 (로그인 필요)

    사용자의 검색 범위 설정, 선택된 문서/그룹 등을 저장합니다.
    Redis에 저장되며 TTL은 1년입니다.

    Args:
        request: FastAPI request object (for Redis access)
        preferences: UserPreferences object to save
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Success message
            - success: True if saved successfully
            - message: Confirmation message

    Raises:
        HTTPException: 500 if cache manager not initialized or error occurs
    """
    try:
        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis = cache_manager.redis
        username = current_user.get("username")

        # Redis에 사용자 설정 저장 (TTL: 1년)
        preferences_key = f"user:preferences:{username}"
        preferences_data = preferences.dict()

        redis.setex(
            preferences_key,
            365 * 24 * 60 * 60,  # 1 year
            json.dumps(preferences_data)
        )

        logger.success(f"✅ 사용자 설정 저장 완료: {username}")
        logger.debug(f"   - 검색 범위: {preferences.search_scope}")
        logger.debug(f"   - 선택된 문서: {len(preferences.selected_document_ids or [])}개")
        logger.debug(f"   - 선택된 그룹: {len(preferences.selected_group_ids or [])}개")

        return {
            "success": True,
            "message": "설정이 저장되었습니다."
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "update user preferences endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


# ============================================================================
# System Settings API Endpoints
# ============================================================================

@router.get("/settings", tags=["Settings"])
async def get_settings(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """
    시스템 설정 조회 (로그인 필요)

    모든 인증된 사용자가 시스템 설정을 조회할 수 있습니다.
    자동 로그아웃 타임아웃 등의 설정이 포함됩니다.

    Args:
        request: FastAPI request object (for Redis and SettingsService access)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: System settings
            - settings: System settings object

    Raises:
        HTTPException: 500 if settings retrieval fails
    """
    try:
        # 사용자 인증 확인
        from ..auth.utils import get_current_user_from_request
        from ..services import SettingsService

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        get_current_user_from_request(request, redis_client)

        # 설정 조회
        settings_service = SettingsService(redis_client)
        settings = settings_service.get_settings_dict()

        return {"settings": settings}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve settings")


@router.get("/admin/settings", tags=["Admin", "Settings"])
async def get_admin_settings(request: Request):
    """
    시스템 설정 조회 (관리자 전용)

    관리자만 시스템 설정을 조회할 수 있습니다.
    자동 로그아웃 타임아웃 등의 설정이 포함됩니다.

    Args:
        request: FastAPI request object (for Redis and SettingsService access)

    Returns:
        dict: System settings
            - settings: System settings object

    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 500 if settings retrieval fails
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin
        from ..services import SettingsService

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # 설정 조회
        settings_service = SettingsService(redis_client)
        settings = settings_service.get_settings_dict()

        return {"settings": settings}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve settings")


@router.put("/admin/settings", tags=["Admin", "Settings"])
async def update_admin_settings(request: Request):
    """
    시스템 설정 업데이트 (관리자 전용)

    관리자만 시스템 설정을 업데이트할 수 있습니다.

    Request body:
        {
            "inactivity_timeout": 30,  # 분 단위
            "warning_time": 5,         # 분 단위
            "check_interval": 1        # 분 단위
        }

    Args:
        request: FastAPI request object (for Redis and SettingsService access)

    Returns:
        dict: Updated settings and success message
            - settings: Updated system settings
            - message: Confirmation message

    Raises:
        HTTPException: 400 if validation fails
        HTTPException: 403 if user is not admin
        HTTPException: 500 if settings update fails
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin, extract_token_from_request, verify_token
        from ..services import SettingsService
        from ..auth.models import SystemSettings

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # Request body 파싱 및 검증
        body = await request.json()

        try:
            new_settings = SystemSettings(**body)
        except ValidationError as e:
            # Pydantic 검증 에러를 HTTP 400으로 변환
            error_messages = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            raise HTTPException(status_code=400, detail=error_messages)

        # 설정 업데이트
        settings_service = SettingsService(redis_client)
        try:
            updated_settings = settings_service.update_settings(new_settings)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 로깅
        token = extract_token_from_request(request)
        user_data = verify_token(token)
        logger.info(f"System settings updated by user {user_data['user_id']}: {updated_settings.model_dump()}")

        return {
            "settings": updated_settings.model_dump(),
            "message": "Settings updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings")


# ============================================================================
# Hybrid RAG Status API Endpoints
# ============================================================================

@router.get("/hybrid-rag/status", response_model=HybridRAGStatusResponse, tags=["Hybrid RAG"])
async def get_hybrid_rag_status(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """
    하이브리드 RAG 상태 조회 (인증된 사용자 전용)

    Returns:
        현재 하이브리드 RAG 활성화 상태
    """
    try:
        cache_manager = request.app.state.cache_manager

        # Redis에서 설정 가져오기
        enabled = cache_manager.redis.get("config:hybrid_rag_enabled")
        web_search_enabled = cache_manager.redis.get("config:hybrid_rag_web_search")
        doc_search_enabled = cache_manager.redis.get("config:hybrid_rag_doc_search")

        # 기본값 설정
        enabled = enabled.decode() == "true" if enabled else False
        web_search_enabled = web_search_enabled.decode() == "true" if web_search_enabled else False
        doc_search_enabled = doc_search_enabled.decode() == "true" if doc_search_enabled else False

        return HybridRAGStatusResponse(
            success=True,
            enabled=enabled,
            web_search_enabled=web_search_enabled,
            doc_search_enabled=doc_search_enabled
        )

    except Exception as e:
        logger.error(f"하이브리드 RAG 상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="Failed to get hybrid RAG status")
