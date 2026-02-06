"""
System Status and Monitoring Router

Provides system status, health checks, metrics, and monitoring endpoints.
"""

import os
import time
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from loguru import logger

from ..auth.middleware import get_current_active_user
from ..document_tracker import DocumentTracker
from ..utils.error_handling import get_safe_error_message

router = APIRouter(tags=["System"])

# Global dependencies (injected at startup)
_vector_db = None
_cache_manager = None
_embedding_model = None
_llm = None
_rag_system = None
_reindex_service = None
_data_dir = None
_llm_model = None
_embedding_model_name = None

# Status endpoint cache (to avoid rescanning on every request)
status_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 5  # Cache for 5 seconds
}


def inject_dependencies(
    vector_db_instance,
    cache_mgr,
    emb_model,
    llm_instance,
    rag_system_instance,
    reindex_svc,
    data_dir: str,
    llm_model: str,
    embedding_model: str
):
    """Inject dependencies for system router"""
    global _vector_db, _cache_manager, _embedding_model, _llm, _rag_system
    global _reindex_service, _data_dir, _llm_model, _embedding_model_name

    _vector_db = vector_db_instance
    _cache_manager = cache_mgr
    _embedding_model = emb_model
    _llm = llm_instance
    _rag_system = rag_system_instance
    _reindex_service = reindex_svc
    _data_dir = data_dir
    _llm_model = llm_model
    _embedding_model_name = embedding_model


@router.get("/api/status")
async def status():
    """
    Get system status with detailed information (cached for performance)
    Public endpoint for health checks
    """
    global status_cache

    try:
        # Check if cache is valid
        current_time = time.time()
        if (status_cache["data"] is not None and
            current_time - status_cache["timestamp"] < status_cache["ttl"]):
            # Return cached response
            return status_cache["data"]

        # Cache miss or expired - recalculate status
        chunk_count = _vector_db.count_documents() if _vector_db else 0
        pdf_count = _vector_db.count_unique_files() if _vector_db else 0

        # Get index state
        index_state = _vector_db.get_index_state() if _vector_db else None

        # Check for PDF changes
        change_info = None
        if _vector_db and _vector_db.is_indexed():
            try:
                doc_tracker = DocumentTracker(data_dir=_data_dir)
                change_summary = doc_tracker.get_change_summary()
                change_info = {
                    "needs_reindex": change_summary["needs_reindex"],
                    "total_changes": change_summary["total_changes"]
                }
            except Exception:
                pass

        # System is ready if documents are indexed (LLM loads on first use)
        is_ready = (chunk_count > 0) or (_rag_system is not None)

        # Check if reindexing is in progress
        is_reindexing = _reindex_service.is_reindexing() if _reindex_service else False

        # Determine status: reindexing > ready > initializing
        if is_reindexing:
            status_value = "reindexing"
        elif is_ready:
            status_value = "ready"
        else:
            status_value = "initializing"

        # Get current models from environment variables
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            current_llm_model = os.getenv("OLLAMA_LLM_MODEL", "qwen3:latest")
            current_embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "daynice/kure-v1:latest")
        else:
            current_llm_model = os.getenv("LLM_MODEL", _llm_model)
            current_embedding_model = os.getenv("EMBEDDING_MODEL", _embedding_model_name)

        response = {
            "status": status_value,
            "document_count": chunk_count,  # 하위 호환성 유지
            "chunk_count": chunk_count,
            "pdf_count": pdf_count,
            "embedding_model": current_embedding_model,
            "llm_model": current_llm_model,
            "is_reindexing": is_reindexing
        }

        if index_state:
            response["index_state"] = index_state

        if change_info:
            response["changes"] = change_info

        # Update cache
        status_cache["data"] = response
        status_cache["timestamp"] = current_time

        return response
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/api/system-prompt")
async def get_public_system_prompt(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """시스템 프롬프트 조회 (로그인한 사용자만 접근 가능)

    관리자가 설정한 시스템 프롬프트를 로그인한 사용자가 조회할 수 있는 엔드포인트

    Args:
        current_user: 현재 로그인한 사용자 정보

    Returns:
        저장된 시스템 프롬프트 또는 기본값
    """
    try:
        redis_client = request.app.state.cache_manager.redis

        # Redis에서 조회
        system_prompt = redis_client.get("system:default_prompt")

        if system_prompt:
            # bytes를 str로 변환
            if isinstance(system_prompt, bytes):
                system_prompt = system_prompt.decode('utf-8')
        else:
            # 기본값
            system_prompt = """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다.

# 🎯 역할 정의
- 제공된 문서만을 기반으로 정확하고 신뢰할 수 있는 답변 제공
- 사용자의 질문 의도를 정확히 파악하여 맞춤형 답변 작성
- 전문적이면서도 이해하기 쉬운 설명 제공

# ⚠️ 필수 준수 규칙 (CRITICAL)

## 1. 환각(Hallucination) 방지 - 최우선 원칙
✅ 반드시 지킬 것:
- 제공된 문서에 있는 정보만 사용
- 불확실한 내용은 추측하지 않음
- 문서에 없는 정보는 절대 만들어내지 않음

❌ 절대 금지:
- 일반 지식이나 학습 데이터 기반 답변
- 문서에 없는 내용 추가
- 불확실한 정보를 확실한 것처럼 제시

## 2. 출처 명시
- 답변의 근거가 되는 문서와 위치를 명확히 밝힘
- 여러 문서의 정보를 종합할 때는 각각의 출처를 구분하여 표시

## 3. 불확실성 표현
문서에 정보가 불충분하거나 없을 때:
- "제공된 문서에는 해당 정보가 없습니다"
- "문서에서 명확한 답변을 찾을 수 없습니다"
- "추가 자료가 필요합니다"

# 📋 답변 작성 가이드

## 구조화된 답변
1. **핵심 답변**: 질문에 대한 직접적인 답
2. **상세 설명**: 필요시 맥락과 배경 정보
3. **출처 표시**: 정보의 근거가 된 문서 명시

## 스타일
- 명확하고 간결한 문장
- 전문 용어 사용 시 설명 추가
- 필요시 예시나 비유 활용
- 마크다운 형식으로 가독성 향상"""

        return {
            "system_prompt": system_prompt
        }

    except Exception as e:
        logger.error(f"Failed to get system prompt: {e}")
        # 에러 발생 시에도 기본값 반환
        return {
            "system_prompt": """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다. 제공된 문서 내용을 정확하게 분석하여 사용자에게 도움이 되는 답변을 제공합니다."""
        }


@router.get("/api/system/metrics")
async def get_system_metrics(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """시스템 메트릭 조회 (관리자 및 로그인한 사용자)

    시스템 전체의 성능 및 상태 메트릭을 조회합니다:
    - Redis 메모리 사용량 및 통계
    - 캐시 히트율 및 검색 통계
    - 슬로우 쿼리 성능 통계

    Args:
        current_user: 현재 로그인한 사용자 정보

    Returns:
        시스템 메트릭 정보
    """
    try:
        metrics_collector = request.app.state.metrics_collector

        if not metrics_collector:
            raise HTTPException(status_code=500, detail="Metrics collector not available")

        # 시스템 메트릭 조회
        metrics = metrics_collector.get_system_metrics()

        return {
            "success": True,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "system metrics"))


@router.get("/health")
async def health_check():
    """
    Health check endpoint for load balancers and monitoring systems.
    Returns detailed system status including Redis, models, and cache.
    Optimized for fast response (<10ms).
    """
    try:
        import psutil
        from datetime import datetime

        # Check Redis connectivity (fast PING only)
        redis_healthy = False
        redis_info = {}
        try:
            _vector_db.client.ping()
            redis_healthy = True
            # Minimal info for performance - avoid expensive INFO command
            redis_info = {
                "connected": True
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

        # Check cache stats (lightweight)
        cache_stats = {}
        if _cache_manager:
            cache_stats = _cache_manager.get_cache_stats()

        # System resources (instant read, no interval)
        cpu_percent = psutil.cpu_percent(interval=0)  # Instant, no blocking
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Model status (simple bool check)
        models_loaded = {
            "embedding": _embedding_model is not None,
            "llm": _llm is not None,
            "rag": _rag_system is not None
        }

        # Overall health status
        is_healthy = redis_healthy and all(models_loaded.values())

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "redis": {
                "healthy": redis_healthy,
                "info": redis_info
            },
            "cache": {
                "entries": cache_stats.get("total_entries", 0),
                "hit_rate": (cache_stats.get("cache_hits", 0) / max(cache_stats.get("total_queries", 1), 1)) * 100
            },
            "models": models_loaded,
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": disk.percent
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


@router.get("/metrics")
async def metrics():
    """
    Prometheus-compatible metrics endpoint for monitoring.
    Returns key performance metrics in plain text format.
    """
    try:
        import psutil

        # Get cache stats
        cache_stats = _cache_manager.get_cache_stats() if _cache_manager else {}

        # Get Redis stats
        redis_info = {}
        try:
            info = _vector_db.client.info()
            redis_info = {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "total_commands": info.get("total_commands_processed", 0)
            }
        except Exception:
            pass

        # System metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        # Format metrics in Prometheus format
        metrics_output = f"""# HELP cache_entries Total number of cache entries
# TYPE cache_entries gauge
cache_entries {cache_stats.get('total_entries', 0)}

# HELP cache_queries_total Total number of cache queries
# TYPE cache_queries_total counter
cache_queries_total {cache_stats.get('total_queries', 0)}

# HELP cache_hits_total Total number of cache hits
# TYPE cache_hits_total counter
cache_hits_total {cache_stats.get('cache_hits', 0)}

# HELP redis_connected_clients Number of Redis client connections
# TYPE redis_connected_clients gauge
redis_connected_clients {redis_info.get('connected_clients', 0)}

# HELP redis_memory_used_bytes Redis memory usage in bytes
# TYPE redis_memory_used_bytes gauge
redis_memory_used_bytes {redis_info.get('used_memory', 0)}

# HELP system_cpu_percent CPU usage percentage
# TYPE system_cpu_percent gauge
system_cpu_percent {cpu_percent}

# HELP system_memory_percent Memory usage percentage
# TYPE system_memory_percent gauge
system_memory_percent {memory.percent}
"""

        return Response(content=metrics_output, media_type="text/plain")
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return Response(content="", media_type="text/plain", status_code=500)
