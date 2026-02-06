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
    PROMPT_KEY_HYBRID_WEB_PRIORITY,
    PROMPT_KEY_HYBRID_BALANCED,
    PROMPT_KEY_HYBRID_WEB_ONLY,
    PROMPT_KEY_HYBRID_LOCAL_ONLY,
    PROMPT_KEY_HYBRID_LOCAL_PRIORITY,
    DEFAULT_BASIC_PROMPT,
    DEFAULT_HYBRID_PROMPT,
    DEFAULT_TOOLS_ONLY_PROMPT,
    DEFAULT_HYBRID_WEB_PRIORITY_PROMPT,
    DEFAULT_HYBRID_BALANCED_PROMPT,
    DEFAULT_HYBRID_WEB_ONLY_PROMPT,
    DEFAULT_HYBRID_LOCAL_ONLY_PROMPT,
    DEFAULT_HYBRID_LOCAL_PRIORITY_PROMPT
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
    hybrid_web_priority: Optional[str] = None
    hybrid_balanced: Optional[str] = None
    hybrid_web_only: Optional[str] = None
    hybrid_local_only: Optional[str] = None
    hybrid_local_priority: Optional[str] = None


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
                'tools_only': str,  # 외부 도구 전용 프롬프트 (웹 + 공식문서만)
                'hybrid_web_priority': str,  # 웹 정보 우선 프롬프트
                'hybrid_balanced': str,  # 웹/로컬 균등 참조 프롬프트
                'hybrid_web_only': str,  # 웹 정보 전용 프롬프트
                'hybrid_local_only': str,  # 로컬 문서 전용 프롬프트
                'hybrid_local_priority': str  # 로컬 문서 우선 프롬프트
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
        hybrid_web_priority = redis_client.get(PROMPT_KEY_HYBRID_WEB_PRIORITY)
        hybrid_balanced = redis_client.get(PROMPT_KEY_HYBRID_BALANCED)
        hybrid_web_only = redis_client.get(PROMPT_KEY_HYBRID_WEB_ONLY)
        hybrid_local_only = redis_client.get(PROMPT_KEY_HYBRID_LOCAL_ONLY)
        hybrid_local_priority = redis_client.get(PROMPT_KEY_HYBRID_LOCAL_PRIORITY)

        # bytes to str 변환 및 기본값 적용 헬퍼 함수
        def decode_and_default(value, default):
            if isinstance(value, bytes):
                return value.decode('utf-8')
            return value if value else default

        return {
            'success': True,
            'prompts': {
                'basic': decode_and_default(basic_prompt, DEFAULT_BASIC_PROMPT),
                'hybrid': decode_and_default(hybrid_prompt, DEFAULT_HYBRID_PROMPT),
                'tools_only': decode_and_default(tools_only_prompt, DEFAULT_TOOLS_ONLY_PROMPT),
                'hybrid_web_priority': decode_and_default(hybrid_web_priority, DEFAULT_HYBRID_WEB_PRIORITY_PROMPT),
                'hybrid_balanced': decode_and_default(hybrid_balanced, DEFAULT_HYBRID_BALANCED_PROMPT),
                'hybrid_web_only': decode_and_default(hybrid_web_only, DEFAULT_HYBRID_WEB_ONLY_PROMPT),
                'hybrid_local_only': decode_and_default(hybrid_local_only, DEFAULT_HYBRID_LOCAL_ONLY_PROMPT),
                'hybrid_local_priority': decode_and_default(hybrid_local_priority, DEFAULT_HYBRID_LOCAL_PRIORITY_PROMPT)
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
            "tools_only": "외부 도구 전용 프롬프트 (optional)",
            "hybrid_web_priority": "웹 정보 우선 프롬프트 (optional)",
            "hybrid_balanced": "웹/로컬 균등 참조 프롬프트 (optional)",
            "hybrid_web_only": "웹 정보 전용 프롬프트 (optional)",
            "hybrid_local_only": "로컬 문서 전용 프롬프트 (optional)",
            "hybrid_local_priority": "로컬 문서 우선 프롬프트 (optional)"
        }

    Returns:
        {
            'success': True,
            'message': '프롬프트 업데이트 완료: basic, hybrid, ...'
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

        # 프롬프트 유효성 검증 및 저장 헬퍼 함수
        def validate_and_save(prompt_value, prompt_key, prompt_name, max_length=10000, legacy_key=None):
            if prompt_value is not None:
                if len(prompt_value) > max_length:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{prompt_name} 프롬프트가 너무 깁니다 (최대 {max_length:,}자)"
                    )
                redis_client.set(prompt_key, prompt_value)
                if legacy_key:
                    redis_client.set(legacy_key, prompt_value)
                updated.append(prompt_name)

        # 기존 프롬프트 업데이트
        validate_and_save(data.basic, PROMPT_KEY_BASIC, 'basic', legacy_key=PROMPT_KEY_LEGACY)
        validate_and_save(data.hybrid, PROMPT_KEY_HYBRID, 'hybrid')
        validate_and_save(data.tools_only, PROMPT_KEY_TOOLS_ONLY, 'tools_only')

        # 새로운 하이브리드 RAG 우선순위 프롬프트 업데이트
        validate_and_save(data.hybrid_web_priority, PROMPT_KEY_HYBRID_WEB_PRIORITY, 'hybrid_web_priority', max_length=2000)
        validate_and_save(data.hybrid_balanced, PROMPT_KEY_HYBRID_BALANCED, 'hybrid_balanced', max_length=2000)
        validate_and_save(data.hybrid_web_only, PROMPT_KEY_HYBRID_WEB_ONLY, 'hybrid_web_only', max_length=2000)
        validate_and_save(data.hybrid_local_only, PROMPT_KEY_HYBRID_LOCAL_ONLY, 'hybrid_local_only', max_length=2000)
        validate_and_save(data.hybrid_local_priority, PROMPT_KEY_HYBRID_LOCAL_PRIORITY, 'hybrid_local_priority', max_length=2000)

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
