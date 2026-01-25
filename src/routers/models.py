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
from loguru import logger

from ..utils.error_handling import get_safe_error_message

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

        # Redis에서 모델 설정 읽기 (멀티 워커 환경에서 일관성 보장)
        redis_config = redis_client.hgetall("config:model")

        if redis_config:
            # Redis에 설정이 있으면 사용
            def get_redis_value(key, default=""):
                val = redis_config.get(key.encode()) or redis_config.get(key)
                if val is None:
                    return default
                return val.decode() if isinstance(val, bytes) else val

            use_ollama = get_redis_value("use_ollama", "false").lower() == "true"
            backend = "ollama" if use_ollama else "local"

            config = {
                "backend": backend,
                "ollama": {
                    "base_url": get_redis_value("ollama_base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
                    "llm_model": get_redis_value("ollama_llm_model", os.getenv("OLLAMA_LLM_MODEL", "")),
                    "embedding_model": get_redis_value("ollama_embedding_model", os.getenv("OLLAMA_EMBEDDING_MODEL", ""))
                },
                "local": {
                    "llm_model": get_redis_value("local_llm_model", os.getenv("LLM_MODEL", "mlx-community/Qwen3-30B-A3B-4bit")),
                    "embedding_model": get_redis_value("local_embedding_model", os.getenv("EMBEDDING_MODEL", "nlpai-lab/KURE-v1"))
                }
            }
        else:
            # Redis에 설정이 없으면 환경변수에서 읽기 (기존 동작)
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

                # LLM, 임베딩, Reranker 모델 분류
                llm_models = []
                embedding_models = []
                reranker_models = []

                for model in models:
                    model_name = model.get("name", "")
                    size = model.get("size", 0)
                    size_gb = size / (1024**3) if size else 0

                    model_info = {
                        "name": model_name,
                        "size": f"{size_gb:.2f} GB",
                        "modified_at": model.get("modified_at", "")
                    }

                    model_name_lower = model_name.lower()

                    # Reranker 모델 판별 (이름에 rerank가 포함된 경우)
                    if "rerank" in model_name_lower:
                        reranker_models.append(model_info)
                    # 임베딩 모델 판별 (이름에 embed, kure, bge 등이 포함된 경우)
                    elif any(keyword in model_name_lower for keyword in ["embed", "kure", "bge", "e5", "gte"]):
                        embedding_models.append(model_info)
                    else:
                        llm_models.append(model_info)

                return {
                    "llm_models": llm_models,
                    "embedding_models": embedding_models,
                    "reranker_models": reranker_models
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
                ],
                "reranker_models": [
                    {"name": "cross-encoder/ms-marco-MiniLM-L-12-v2", "size": "0.5 GB", "description": "MS MARCO Cross-encoder"}
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

        # 현재 LLM 모델 저장 (캐시 삭제 여부 판단용)
        current_use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if current_use_ollama:
            current_llm_model = os.getenv("OLLAMA_LLM_MODEL", "")
        else:
            current_llm_model = os.getenv("LLM_MODEL", "")

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

        # Redis에 모델 설정 저장 (멀티 워커 환경에서 일관성 보장)
        redis_config = {
            "use_ollama": "true" if backend == "ollama" else "false",
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        }
        if backend == "ollama":
            if llm_model:
                redis_config["ollama_llm_model"] = llm_model
            if embedding_model_name:
                redis_config["ollama_embedding_model"] = embedding_model_name
        else:
            if llm_model:
                redis_config["local_llm_model"] = llm_model
            if embedding_model_name:
                redis_config["local_embedding_model"] = embedding_model_name

        redis_client.hset("config:model", mapping=redis_config)
        logger.info(f"Model configuration saved to Redis: {redis_config}")

        logger.info(f"Model configuration updated: backend={backend}, llm={llm_model}, embedding={embedding_model_name}")

        # LLM 모델이 변경되었는지 확인하고 캐시 삭제
        cache_cleared = 0
        if llm_model and llm_model != current_llm_model:
            try:
                cache_cleared = cache_manager.clear_cache()
                logger.info(f"🗑️ LLM model changed ({current_llm_model} → {llm_model}), cache cleared: {cache_cleared} entries")
            except Exception as e:
                logger.warning(f"Failed to clear cache after LLM model change: {e}")

        # 모델 즉시 적용 (callback을 통해)
        if model_reload_callback:
            try:
                result = model_reload_callback(backend, llm_model, embedding_model_name)
                # 캐시 삭제 정보 추가
                if cache_cleared > 0:
                    result["cache_cleared"] = cache_cleared
                return result
            except Exception as e:
                logger.error(f"Failed to reload models: {e}")
                # 설정은 저장되었지만 모델 로드 실패
                return {
                    "llm_changed": False,
                    "embedding_changed": False,
                    "restart_required": True,
                    "message": "설정이 저장되었습니다. 서버를 재시작하여 적용하세요.",
                    "error": str(e),
                    "cache_cleared": cache_cleared
                }
        else:
            # Callback이 없는 경우 (재시작 필요)
            return {
                "llm_changed": False,
                "embedding_changed": False,
                "restart_required": True,
                "message": "설정이 저장되었습니다. 서버를 재시작하여 적용하세요.",
                "cache_cleared": cache_cleared
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model configuration")
