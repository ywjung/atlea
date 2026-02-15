"""
Settings and Preferences Management Router

Handles user preferences and system settings including:
- User preferences (search scope, document/group filters)
- System settings (auto-logout timeout, warning time)
- Admin settings management

Authentication required for all endpoints.
Admin privileges required for admin-specific endpoints.
PostgreSQL-based storage via SystemConfig table.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from typing import Optional, List
import json
from loguru import logger

from ..auth.middleware import get_current_active_user
from ..utils.error_handling import get_safe_error_message
from ..services.config_service import config_get_sync, config_set_sync, config_get_multi

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
        cache_mgr: CacheManager instance (kept for backward compatibility)
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


class RAGQualityFeatures(BaseModel):
    """RAG 품질 기능 상태"""
    reranking_enabled: bool = False
    query_rewrite_enabled: bool = False
    reranker_model: str = "dengcao/Qwen3-Reranker-8B:Q4_K_M"


class HybridRAGStatusResponse(BaseModel):
    """하이브리드 RAG 상태 응답"""
    success: bool = True
    enabled: bool
    web_search_enabled: bool = False
    doc_search_enabled: bool = False
    quality_features: Optional[RAGQualityFeatures] = None


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
    """
    try:
        username = current_user.get("username")

        # PostgreSQL에서 사용자 설정 조회
        preferences_key = f"user:preferences:{username}"
        preferences_data = config_get_sync(preferences_key)

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

        logger.info(f"사용자 설정 조회: {username}")
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
    """
    try:
        username = current_user.get("username")

        # PostgreSQL에 사용자 설정 저장
        preferences_key = f"user:preferences:{username}"
        preferences_data = preferences.dict()

        config_set_sync(preferences_key, json.dumps(preferences_data))

        logger.success(f"사용자 설정 저장 완료: {username}")
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
    """
    try:
        from ..auth.utils import get_current_user_from_request
        from ..services import SettingsService

        get_current_user_from_request(request)

        # 설정 조회
        settings_service = SettingsService()
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
    """
    try:
        from ..auth.utils import require_admin
        from ..services import SettingsService

        require_admin(request)

        # 설정 조회
        settings_service = SettingsService()
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
    """
    try:
        from ..auth.utils import require_admin, extract_token_from_request, verify_token
        from ..services import SettingsService
        from ..auth.models import SystemSettings

        require_admin(request)

        # Request body 파싱 및 검증
        body = await request.json()

        try:
            new_settings = SystemSettings(**body)
        except ValidationError as e:
            # Pydantic 검증 에러를 HTTP 400으로 변환
            error_messages = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            raise HTTPException(status_code=400, detail=error_messages)

        # 설정 업데이트
        settings_service = SettingsService()
        try:
            updated_settings = settings_service.update_settings(new_settings)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 로깅
        token = extract_token_from_request(request)
        user_data = verify_token(token)
        logger.info(f"System settings updated by user {user_data.get('user_id', 'unknown')}: {updated_settings.model_dump()}")

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
        # PostgreSQL에서 설정 가져오기
        cfg = await config_get_multi([
            "config:hybrid_rag_enabled",
            "config:hybrid_rag_web_search",
            "config:hybrid_rag_doc_search",
            "config:reranking_enabled",
            "config:query_rewrite_enabled",
            "config:reranker_model",
        ])

        # 기본값 설정
        enabled = cfg.get("config:hybrid_rag_enabled") == "true"
        web_search_enabled = cfg.get("config:hybrid_rag_web_search") == "true"
        doc_search_enabled = cfg.get("config:hybrid_rag_doc_search") == "true"

        # RAG 품질 기능 기본값
        reranking_enabled = cfg.get("config:reranking_enabled") == "true"
        query_rewrite_enabled = cfg.get("config:query_rewrite_enabled") == "true"
        reranker_model = cfg.get("config:reranker_model") or "dengcao/Qwen3-Reranker-8B:Q4_K_M"

        return HybridRAGStatusResponse(
            success=True,
            enabled=enabled,
            web_search_enabled=web_search_enabled,
            doc_search_enabled=doc_search_enabled,
            quality_features=RAGQualityFeatures(
                reranking_enabled=reranking_enabled,
                query_rewrite_enabled=query_rewrite_enabled,
                reranker_model=reranker_model
            )
        )

    except Exception as e:
        logger.error(f"하이브리드 RAG 상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="Failed to get hybrid RAG status")
