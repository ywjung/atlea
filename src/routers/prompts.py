"""
Prompts Management Router

Handles system prompt configuration including:
- System prompt save/retrieve (legacy)
- Multi-mode prompts (basic, hybrid, tools_only)
- Prompt updates with validation

Admin privileges required for all endpoints.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from loguru import logger

# Import prompt configuration
from ..config.prompts import (
    PROMPT_KEY_BASIC,
    PROMPT_KEY_HYBRID,
    PROMPT_KEY_TOOLS_ONLY,
    PROMPT_KEY_LEGACY,
    DEFAULT_BASIC_PROMPT,
    DEFAULT_HYBRID_PROMPT,
    DEFAULT_TOOLS_ONLY_PROMPT
)
from ..utils.error_handling import get_safe_error_message

# Create router with prefix and tags
router = APIRouter(prefix="/api/admin", tags=["Admin", "Settings"])

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
# Request Models
# ============================================================================

class PromptsUpdateRequest(BaseModel):
    """시스템 프롬프트 업데이트 요청"""
    basic: Optional[str] = None
    hybrid: Optional[str] = None
    tools_only: Optional[str] = None


# ============================================================================
# Prompts API Endpoints
# ============================================================================

@router.post("/system-prompt", tags=["Admin"])
async def save_system_prompt(request: Request):
    """시스템 프롬프트 저장 (관리자 전용)

    Request body:
        {
            "system_prompt": "당신은 AI 어시스턴트입니다..."
        }

    Returns:
        저장 성공 메시지
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin, extract_token_from_request, verify_token

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # Request body 파싱
        body = await request.json()
        system_prompt = body.get("system_prompt", "")

        # 유효성 검증
        if not system_prompt or not system_prompt.strip():
            raise HTTPException(status_code=400, detail="시스템 프롬프트는 비어있을 수 없습니다")

        if len(system_prompt) > 10000:
            raise HTTPException(status_code=400, detail="시스템 프롬프트가 너무 깁니다 (최대 10,000자)")

        # Redis에 저장
        redis_client.set("system:default_prompt", system_prompt)

        # 로깅
        token = extract_token_from_request(request)
        user_data = verify_token(token)
        logger.info(f"System prompt updated by user {user_data.get('user_id', 'unknown')} (length: {len(system_prompt)})")

        return {
            "message": "시스템 프롬프트가 저장되었습니다",
            "length": len(system_prompt)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save system prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to save system prompt")


@router.get("/system-prompt", tags=["Admin"])
async def get_system_prompt(request: Request):
    """시스템 프롬프트 조회 (관리자 전용)

    Returns:
        저장된 시스템 프롬프트
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # Redis에서 조회
        system_prompt = redis_client.get("system:default_prompt")

        if system_prompt:
            # bytes를 str로 변환
            if isinstance(system_prompt, bytes):
                system_prompt = system_prompt.decode('utf-8')
        else:
            # 기본값 사용
            system_prompt = DEFAULT_BASIC_PROMPT

        return {
            "system_prompt": system_prompt
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get system prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system prompt")


@router.get("/prompts", tags=["Admin", "Settings"])
async def get_all_prompts(request: Request):
    """모든 시스템 프롬프트 조회 (관리자 전용)

    Returns:
        {
            'success': True,
            'prompts': {
                'basic': str,  # 일반 검색용 프롬프트 (로컬 문서만)
                'hybrid': str,  # 하이브리드 검색용 프롬프트 (로컬 + 외부 도구)
                'tools_only': str  # 외부 도구 전용 프롬프트 (웹 + 공식문서만)
            }
        }
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        # 각 프롬프트 가져오기
        basic_prompt = redis_client.get(PROMPT_KEY_BASIC)
        hybrid_prompt = redis_client.get(PROMPT_KEY_HYBRID)
        tools_only_prompt = redis_client.get(PROMPT_KEY_TOOLS_ONLY)

        # bytes to str 변환
        if isinstance(basic_prompt, bytes):
            basic_prompt = basic_prompt.decode('utf-8')
        if isinstance(hybrid_prompt, bytes):
            hybrid_prompt = hybrid_prompt.decode('utf-8')
        if isinstance(tools_only_prompt, bytes):
            tools_only_prompt = tools_only_prompt.decode('utf-8')

        # 기본값 적용
        if not basic_prompt:
            basic_prompt = DEFAULT_BASIC_PROMPT
        if not hybrid_prompt:
            hybrid_prompt = DEFAULT_HYBRID_PROMPT
        if not tools_only_prompt:
            tools_only_prompt = DEFAULT_TOOLS_ONLY_PROMPT

        return {
            'success': True,
            'prompts': {
                'basic': basic_prompt,
                'hybrid': hybrid_prompt,
                'tools_only': tools_only_prompt
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get prompts: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve prompts")


@router.put("/prompts", tags=["Admin", "Settings"])
async def update_prompts(data: PromptsUpdateRequest, request: Request):
    """시스템 프롬프트 업데이트 (관리자 전용)

    Request body:
        {
            "basic": "일반 검색용 프롬프트 (optional)",
            "hybrid": "하이브리드 검색용 프롬프트 (optional)",
            "tools_only": "외부 도구 전용 프롬프트 (optional)"
        }

    Returns:
        {
            'success': True,
            'message': '프롬프트 업데이트 완료: basic, hybrid, tools_only'
        }
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin, extract_token_from_request, verify_token

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        updated = []

        if data.basic is not None:
            # 유효성 검증
            if len(data.basic) > 10000:
                raise HTTPException(status_code=400, detail="일반 프롬프트가 너무 깁니다 (최대 10,000자)")

            redis_client.set(PROMPT_KEY_BASIC, data.basic)
            redis_client.set(PROMPT_KEY_LEGACY, data.basic)  # 레거시 호환
            updated.append('basic')

        if data.hybrid is not None:
            # 유효성 검증
            if len(data.hybrid) > 10000:
                raise HTTPException(status_code=400, detail="하이브리드 프롬프트가 너무 깁니다 (최대 10,000자)")

            redis_client.set(PROMPT_KEY_HYBRID, data.hybrid)
            updated.append('hybrid')

        if data.tools_only is not None:
            # 유효성 검증
            if len(data.tools_only) > 10000:
                raise HTTPException(status_code=400, detail="외부 도구 전용 프롬프트가 너무 깁니다 (최대 10,000자)")

            redis_client.set(PROMPT_KEY_TOOLS_ONLY, data.tools_only)
            updated.append('tools_only')

        if not updated:
            raise HTTPException(status_code=400, detail="업데이트할 프롬프트를 제공해주세요")

        # 로깅
        token = extract_token_from_request(request)
        user_data = verify_token(token)
        logger.info(f"Prompts updated by user {user_data.get('user_id', 'unknown')}: {', '.join(updated)}")

        return {
            'success': True,
            'message': f'프롬프트 업데이트 완료: {", ".join(updated)}'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update prompts: {e}")
        raise HTTPException(status_code=500, detail="Failed to update prompts")
