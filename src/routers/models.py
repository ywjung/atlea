"""
Model Management Router

Handles AI model configuration and management including:
- Model backend selection (Ollama/Local)
- Available model listing
- Model configuration updates
- Model reloading and switching

Admin privileges required for all endpoints.
"""

from fastapi import APIRouter, HTTPException, Request
from pathlib import Path
import os
import logging

# Configure logger
logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(prefix="/api/admin", tags=["Admin", "Models"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

cache_manager = None
model_reload_callback = None


def inject_dependencies(cache_mgr, reload_callback=None):
    """
    Inject dependencies from main application

    Args:
        cache_mgr: CacheManager instance for Redis access
        reload_callback: Callback function to reload models in main app
    """
    global cache_manager, model_reload_callback
    cache_manager = cache_mgr
    model_reload_callback = reload_callback


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
        context: Context string for logging (e.g., "models endpoint")

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
# Model Management API Endpoints
# ============================================================================

@router.get("/models/backend", tags=["Models"])
async def get_model_backend(request: Request):
    """
    현재 모델 백엔드 설정 조회 (관리자 전용)

    Returns:
        현재 사용 중인 백엔드 (ollama/local)와 모델 설정
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        backend = "ollama" if use_ollama else "local"

        config = {
            "backend": backend,
            "ollama": {
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                "llm_model": os.getenv("OLLAMA_LLM_MODEL", ""),
                "embedding_model": os.getenv("OLLAMA_EMBEDDING_MODEL", "")
            },
            "local": {
                "llm_model": os.getenv("LLM_MODEL", "mlx-community/Qwen3-30B-A3B-4bit"),
                "embedding_model": os.getenv("EMBEDDING_MODEL", "nlpai-lab/KURE-v1")
            }
        }

        return config

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model backend: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model backend")


@router.get("/models/list", tags=["Models"])
async def get_model_list(request: Request, backend: str = "ollama"):
    """
    모델 목록 조회 (관리자 전용)

    Args:
        backend: ollama 또는 local

    Returns:
        사용 가능한 모델 목록
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        if backend == "ollama":
            # Ollama 모델 목록 가져오기
            import httpx
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

            try:
                response = httpx.get(f"{base_url}/api/tags", timeout=10.0)
                response.raise_for_status()
                data = response.json()

                models = data.get("models", [])

                # LLM과 임베딩 모델 분류
                llm_models = []
                embedding_models = []

                for model in models:
                    model_name = model.get("name", "")
                    size = model.get("size", 0)
                    size_gb = size / (1024**3) if size else 0

                    model_info = {
                        "name": model_name,
                        "size": f"{size_gb:.2f} GB",
                        "modified_at": model.get("modified_at", "")
                    }

                    # 임베딩 모델 판별 (이름에 embed, kure, bge 등이 포함된 경우)
                    if any(keyword in model_name.lower() for keyword in ["embed", "kure", "bge", "e5", "gte"]):
                        embedding_models.append(model_info)
                    else:
                        llm_models.append(model_info)

                return {
                    "llm_models": llm_models,
                    "embedding_models": embedding_models
                }

            except httpx.HTTPError as e:
                logger.error(f"Failed to connect to Ollama: {e}")
                raise HTTPException(status_code=503, detail="Ollama 서버에 연결할 수 없습니다")

        elif backend == "local":
            # 로컬 모델은 하드코딩된 목록 반환 (실제로는 model 디렉토리에서 읽을 수 있음)
            return {
                "llm_models": [
                    {"name": "mlx-community/Qwen3-30B-A3B-4bit", "size": "7.5 GB", "description": "MLX 최적화 Qwen 모델"}
                ],
                "embedding_models": [
                    {"name": "nlpai-lab/KURE-v1", "size": "1.2 GB", "description": "한국어 임베딩 모델"}
                ]
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid backend type")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model list: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model list")


@router.post("/models/config", tags=["Models"])
async def update_model_config(request: Request):
    """
    모델 설정 업데이트 (관리자 전용)

    Request body:
        {
            "backend": "ollama" | "local",
            "llm_model": "model_name",
            "embedding_model": "model_name"
        }
    """
    try:
        # 관리자 권한 확인
        from ..auth.utils import require_admin

        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis_client = cache_manager.redis
        require_admin(request, redis_client)

        data = await request.json()
        backend = data.get("backend")
        llm_model = data.get("llm_model")
        embedding_model_name = data.get("embedding_model")

        if not backend or backend not in ["ollama", "local"]:
            raise HTTPException(status_code=400, detail="Invalid backend")

        # .env 파일 업데이트
        env_path = Path(".env")
        env_lines = []

        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()

        # 기존 설정 업데이트
        updated = {
            "USE_OLLAMA": None,
            "OLLAMA_LLM_MODEL": None,
            "OLLAMA_EMBEDDING_MODEL": None,
            "LLM_MODEL": None,
            "EMBEDDING_MODEL": None
        }

        for i, line in enumerate(env_lines):
            for key in updated.keys():
                if line.startswith(f"{key}="):
                    updated[key] = i
                    break

        # 새로운 설정 준비
        new_values = {
            "USE_OLLAMA": "true" if backend == "ollama" else "false"
        }

        if backend == "ollama":
            if llm_model:
                new_values["OLLAMA_LLM_MODEL"] = llm_model
            if embedding_model_name:
                new_values["OLLAMA_EMBEDDING_MODEL"] = embedding_model_name
        else:
            if llm_model:
                new_values["LLM_MODEL"] = llm_model
            if embedding_model_name:
                new_values["EMBEDDING_MODEL"] = embedding_model_name

        # 환경 변수 업데이트 (메모리에도 즉시 반영)
        for key, value in new_values.items():
            os.environ[key] = value
            line = f"{key}={value}\n"
            if updated[key] is not None:
                env_lines[updated[key]] = line
            else:
                env_lines.append(line)

        # .env 파일 저장
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)

        logger.info(f"Model configuration updated: backend={backend}, llm={llm_model}, embedding={embedding_model_name}")

        # 모델 즉시 적용 (callback을 통해)
        if model_reload_callback:
            try:
                result = model_reload_callback(backend, llm_model, embedding_model_name)
                return result
            except Exception as e:
                logger.error(f"Failed to reload models: {e}")
                # 설정은 저장되었지만 모델 로드 실패
                return {
                    "llm_changed": False,
                    "embedding_changed": False,
                    "restart_required": True,
                    "message": "설정이 저장되었습니다. 서버를 재시작하여 적용하세요.",
                    "error": str(e)
                }
        else:
            # Callback이 없는 경우 (재시작 필요)
            return {
                "llm_changed": False,
                "embedding_changed": False,
                "restart_required": True,
                "message": "설정이 저장되었습니다. 서버를 재시작하여 적용하세요."
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model configuration")
