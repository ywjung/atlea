"""
TTS (Text-to-Speech) Router

Provides endpoints for:
- TTS configuration (admin)
- TTS model management (admin)
- Speech synthesis (user)
- Audio file serving
"""

import os
import json
import asyncio
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from loguru import logger

from ..auth.middleware import get_current_active_user
from ..auth.utils import require_admin, verify_token
from ..redis_helpers import decode_bytes

# Optional bearer scheme for audio endpoints (allows query param fallback)
optional_bearer = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/api", tags=["TTS"])

# Global dependencies (injected from web_server.py)
cache_manager = None
tts_service = None


def inject_dependencies(cache_mgr, tts_svc=None):
    """Inject dependencies from main application"""
    global cache_manager, tts_service
    cache_manager = cache_mgr
    tts_service = tts_svc


def initialize_tts_service(eager_load: bool = True):
    """Initialize TTS service at startup (eager loading)

    Args:
        eager_load: If True, load the model immediately. If False, defer to lazy loading.

    Returns:
        TTSService instance or None if disabled/failed
    """
    global tts_service

    # Get config to determine if TTS is enabled
    config = get_tts_config()

    if not config.get("enabled", False):
        logger.info("TTS is disabled, skipping initialization")
        return None

    try:
        from ..services.tts_service import TTSService
        model_id = config.get("model_id", "edge-tts")

        # Create TTS service
        tts_service = TTSService(model_id=model_id)
        logger.info(f"TTS service created with model: {model_id}")

        # Eagerly load the model if requested
        if eager_load:
            logger.info(f"Eagerly loading TTS model: {model_id}")
            tts_service.load_model()
            logger.success(f"TTS model loaded successfully: {model_id}")

        return tts_service
    except Exception as e:
        logger.error(f"Failed to initialize TTS service: {e}")
        return None


def get_or_create_tts_service():
    """Get or create TTS service instance (lazy loading)"""
    global tts_service

    if tts_service is not None:
        return tts_service

    # Get config to determine which model to use
    config = get_tts_config()

    if not config.get("enabled", False):
        return None

    try:
        from ..services.tts_service import TTSService
        model_id = config.get("model_id", "edge-tts")
        tts_service = TTSService(model_id=model_id)
        logger.info(f"TTS service initialized with model: {model_id}")
        return tts_service
    except Exception as e:
        logger.error(f"Failed to initialize TTS service: {e}")
        return None


# Request/Response Models
class TTSConfigRequest(BaseModel):
    """TTS configuration request"""
    enabled: bool = Field(default=False, description="Enable/disable TTS feature")
    model_id: str = Field(
        default="edge-tts",
        description="TTS model identifier"
    )
    default_voice: str = Field(default="default", description="Default voice ID")
    default_speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Default speed")
    default_language: str = Field(default="ko", description="Default language")
    auto_play: bool = Field(default=False, description="Auto-play on response")
    max_text_length: int = Field(default=5000, description="Max text length for TTS")


class TTSConfigResponse(BaseModel):
    """TTS configuration response"""
    enabled: bool
    model_id: str
    default_voice: str
    default_speed: float
    default_language: str
    auto_play: bool
    max_text_length: int
    model_loaded: bool = False


class TTSSynthesizeRequest(BaseModel):
    """TTS synthesis request"""
    text: str = Field(..., min_length=1, max_length=5000, description="Text to synthesize")
    voice_id: Optional[str] = Field(default="default", description="Voice identifier")
    speed: Optional[float] = Field(default=1.0, ge=0.5, le=2.0, description="Playback speed")
    language: Optional[str] = Field(default="ko", description="Language code")


class TTSModelInfo(BaseModel):
    """TTS model information"""
    id: str
    name: str
    description: str
    sample_rate: int
    languages: List[str]


# TTS 설정 인메모리 캐시
import time as _time
_tts_config_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 10  # 10초 캐시
}

_TTS_DEFAULT_CONFIG = {
    "enabled": False,
    "model_id": "edge-tts",
    "default_voice": "default",
    "default_speed": 1.0,
    "default_language": "ko",
    "auto_play": False,
    "max_text_length": 5000,
}


# Helper functions
def get_tts_config() -> dict:
    """Get TTS configuration from Redis (인메모리 캐시 사용)"""
    if not cache_manager:
        raise HTTPException(status_code=500, detail="Service not initialized")

    # 인메모리 캐시 확인
    now = _time.time()
    if (_tts_config_cache["data"] is not None and
            now - _tts_config_cache["timestamp"] < _tts_config_cache["ttl"]):
        return _tts_config_cache["data"]

    redis = cache_manager.redis
    config_str = redis.get("config:tts")

    if config_str:
        # Decode bytes from Redis if needed
        config_str = decode_bytes(config_str)
        config = json.loads(config_str)
    else:
        config = _TTS_DEFAULT_CONFIG.copy()

    # 캐시 업데이트
    _tts_config_cache["data"] = config
    _tts_config_cache["timestamp"] = now
    return config


def save_tts_config(config: dict):
    """Save TTS configuration to Redis"""
    if not cache_manager:
        raise HTTPException(status_code=500, detail="Service not initialized")

    redis = cache_manager.redis
    redis.set("config:tts", json.dumps(config))

    # 인메모리 캐시 무효화
    _tts_config_cache["data"] = None
    _tts_config_cache["timestamp"] = 0


# Admin Endpoints
@router.get("/admin/tts/config", response_model=TTSConfigResponse)
async def get_tts_configuration(request: Request):
    """
    Get TTS configuration (Admin only)
    """
    require_admin(request, cache_manager.redis)

    config = get_tts_config()

    # Add model loaded status
    model_loaded = False
    if tts_service:
        model_loaded = tts_service._initialized

    return TTSConfigResponse(
        enabled=config.get("enabled", False),
        model_id=config.get("model_id", "edge-tts"),
        default_voice=config.get("default_voice", "default"),
        default_speed=config.get("default_speed", 1.0),
        default_language=config.get("default_language", "ko"),
        auto_play=config.get("auto_play", False),
        max_text_length=config.get("max_text_length", 5000),
        model_loaded=model_loaded,
    )


@router.put("/admin/tts/config", response_model=TTSConfigResponse)
async def update_tts_configuration(request: Request, config: TTSConfigRequest):
    """
    Update TTS configuration (Admin only)
    """
    global tts_service

    require_admin(request, cache_manager.redis)

    logger.info(f"Updating TTS config: enabled={config.enabled}, model={config.model_id}")

    # Get current config
    current_config = get_tts_config()

    # Check if model changed or TTS is being enabled
    model_changed = current_config.get("model_id") != config.model_id
    enabling_tts = config.enabled and not current_config.get("enabled", False)

    # Update config
    new_config = {
        "enabled": config.enabled,
        "model_id": config.model_id,
        "default_voice": config.default_voice,
        "default_speed": config.default_speed,
        "default_language": config.default_language,
        "auto_play": config.auto_play,
        "max_text_length": config.max_text_length,
    }
    save_tts_config(new_config)

    # Handle TTS service initialization/reload
    if config.enabled:
        try:
            if tts_service is None:
                # Create new TTS service and eagerly load model
                logger.info(f"Creating TTS service with model: {config.model_id}")
                from ..services.tts_service import TTSService
                tts_service = TTSService(model_id=config.model_id)
                tts_service.load_model()
                logger.success(f"TTS model loaded: {config.model_id}")
            elif model_changed:
                # Reload model with eager loading
                logger.info(f"Reloading TTS model: {config.model_id}")
                tts_service.reload_model(config.model_id, eager_load=True)
                logger.success(f"TTS model reloaded: {config.model_id}")
        except Exception as e:
            logger.error(f"Failed to load TTS model: {e}")
            # Don't fail the config update, but warn user

    model_loaded = False
    if tts_service:
        model_loaded = tts_service._initialized

    logger.success(f"TTS configuration updated successfully")

    return TTSConfigResponse(
        **new_config,
        model_loaded=model_loaded,
    )


@router.get("/admin/tts/models", response_model=List[TTSModelInfo])
async def get_available_tts_models(request: Request):
    """
    Get available TTS models (Admin only)
    """
    require_admin(request, cache_manager.redis)

    if tts_service:
        return tts_service.get_available_models()

    # Return default models if service not initialized
    from ..services.tts_service import TTSService
    return [
        {
            "id": model_id,
            "name": info["name"],
            "description": info["description"],
            "sample_rate": info["sample_rate"],
            "languages": info["language"],
        }
        for model_id, info in TTSService.AVAILABLE_MODELS.items()
    ]


@router.post("/admin/tts/clear-cache")
async def clear_tts_cache(request: Request):
    """
    Clear TTS audio cache (Admin only)
    """
    require_admin(request, cache_manager.redis)

    service = get_or_create_tts_service()
    if not service:
        # Even if service isn't created, try to clear cache directory
        import shutil
        from pathlib import Path
        cache_dir = Path(__file__).parent.parent.parent / "cache" / "tts" / "audio"
        count = 0
        if cache_dir.exists():
            for ext in ("*.wav", "*.mp3"):
                for f in cache_dir.glob(ext):
                    try:
                        f.unlink()
                        count += 1
                    except Exception:
                        pass
        return {"message": f"Cleared {count} cached audio files", "count": count}

    count = service.clear_cache()

    return {"message": f"Cleared {count} cached audio files", "count": count}


@router.get("/admin/tts/status")
async def get_tts_status(request: Request):
    """
    Get TTS service status (Admin only)
    """
    require_admin(request, cache_manager.redis)

    config = get_tts_config()

    # Check if service is available (don't create it just for status check)
    service = tts_service  # Use global directly, don't create

    status = {
        "enabled": config.get("enabled", False),
        "service_available": service is not None or config.get("enabled", False),
        "model_loaded": False,
        "model_id": config.get("model_id"),
        "device": None,
    }

    if service:
        info = service.get_model_info()
        status["model_loaded"] = info["initialized"]
        status["device"] = info["device"]
        status["cache_dir"] = info["cache_dir"]

    return status


# User Endpoints
@router.post("/tts/synthesize")
async def synthesize_speech(
    tts_req: TTSSynthesizeRequest,
    current_user: dict = Depends(get_current_active_user),
):
    """
    Synthesize speech from text (requires authentication)

    Returns audio file path for download
    """
    # Check if TTS is enabled
    config = get_tts_config()
    if not config.get("enabled", False):
        raise HTTPException(status_code=503, detail="TTS feature is disabled")

    # Get or create TTS service (lazy loading)
    service = get_or_create_tts_service()
    if not service:
        raise HTTPException(status_code=503, detail="TTS service not available")

    # Check text length
    max_length = config.get("max_text_length", 5000)
    if len(tts_req.text) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"텍스트가 너무 깁니다. 최대 {max_length}자까지 허용됩니다."
        )

    try:
        # Use config defaults if not specified
        voice_id = tts_req.voice_id or config.get("default_voice", "default")
        speed = tts_req.speed or config.get("default_speed", 1.0)
        language = tts_req.language or config.get("default_language", "ko")

        logger.info(f"TTS synthesis request: {len(tts_req.text)} chars, voice={voice_id}, speed={speed}")

        # Determine timeout based on model (Edge TTS is fast, Qwen is slow)
        model_id = config.get("model_id", "edge-tts")
        if model_id == "edge-tts":
            timeout_seconds = 60  # 1 minute for Edge TTS
        else:
            timeout_seconds = 180  # 3 minutes for local models

        # Synthesize with timeout
        try:
            audio_path = await asyncio.wait_for(
                service.synthesize(
                    text=tts_req.text,
                    voice_id=voice_id,
                    speed=speed,
                    language=language,
                ),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error(f"TTS synthesis timed out after {timeout_seconds}s for {len(tts_req.text)} chars")
            raise HTTPException(
                status_code=504,
                detail=f"TTS 생성 시간이 초과되었습니다 ({timeout_seconds}초). 텍스트가 너무 길거나 모델이 느릴 수 있습니다. Edge TTS 사용을 권장합니다."
            )

        # Return file ID for download
        file_id = Path(audio_path).stem

        logger.info(f"TTS synthesis completed: {file_id}")

        return {
            "success": True,
            "audio_url": f"/api/tts/audio/{file_id}",
            "file_id": file_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(e)}")


@router.get("/tts/audio/{file_id}")
async def get_audio_file(
    file_id: str,
    token: Optional[str] = Query(None, description="JWT token for authentication"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
):
    """
    Get synthesized audio file

    Accepts authentication via:
    - Authorization header (Bearer token)
    - Query parameter (?token=...)

    Returns WAV audio file
    """
    # Get token from header or query param
    jwt_token = None
    if credentials and credentials.credentials:
        jwt_token = credentials.credentials
    elif token:
        jwt_token = token

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Verify token
    try:
        payload = verify_token(jwt_token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Check if TTS is enabled
    config = get_tts_config()
    if not config.get("enabled", False):
        raise HTTPException(status_code=503, detail="TTS feature is disabled")

    # Get or create TTS service for cache directory
    service = get_or_create_tts_service()
    if not service:
        raise HTTPException(status_code=503, detail="TTS service not available")

    # Validate file_id (prevent directory traversal)
    if ".." in file_id or "/" in file_id or "\\" in file_id:
        raise HTTPException(status_code=400, detail="Invalid file ID")

    # Get audio file path (try MP3 first, then WAV)
    audio_dir = os.path.join(service.cache_dir, "audio")

    # Check for MP3 (Edge TTS) or WAV (Qwen TTS)
    audio_path_mp3 = os.path.join(audio_dir, f"{file_id}.mp3")
    audio_path_wav = os.path.join(audio_dir, f"{file_id}.wav")

    if os.path.exists(audio_path_mp3):
        return FileResponse(
            audio_path_mp3,
            media_type="audio/mpeg",
            filename=f"{file_id}.mp3",
        )
    elif os.path.exists(audio_path_wav):
        return FileResponse(
            audio_path_wav,
            media_type="audio/wav",
            filename=f"{file_id}.wav",
        )
    else:
        raise HTTPException(status_code=404, detail="Audio file not found")


@router.get("/tts/stream/{file_id}")
async def stream_audio_file(
    file_id: str,
    token: Optional[str] = Query(None, description="JWT token for authentication"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
):
    """
    Stream synthesized audio file

    Accepts authentication via:
    - Authorization header (Bearer token)
    - Query parameter (?token=...)

    Returns streaming audio response
    """
    # Get token from header or query param
    jwt_token = None
    if credentials and credentials.credentials:
        jwt_token = credentials.credentials
    elif token:
        jwt_token = token

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Verify token
    try:
        payload = verify_token(jwt_token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Check if TTS is enabled
    config = get_tts_config()
    if not config.get("enabled", False):
        raise HTTPException(status_code=503, detail="TTS feature is disabled")

    # Get or create TTS service for cache directory
    service = get_or_create_tts_service()
    if not service:
        raise HTTPException(status_code=503, detail="TTS service not available")

    # Validate file_id
    if ".." in file_id or "/" in file_id or "\\" in file_id:
        raise HTTPException(status_code=400, detail="Invalid file ID")

    # Get audio file path (try MP3 first, then WAV)
    audio_dir = os.path.join(service.cache_dir, "audio")
    audio_path_mp3 = os.path.join(audio_dir, f"{file_id}.mp3")
    audio_path_wav = os.path.join(audio_dir, f"{file_id}.wav")

    if os.path.exists(audio_path_mp3):
        audio_path = audio_path_mp3
        media_type = "audio/mpeg"
        ext = "mp3"
    elif os.path.exists(audio_path_wav):
        audio_path = audio_path_wav
        media_type = "audio/wav"
        ext = "wav"
    else:
        raise HTTPException(status_code=404, detail="Audio file not found")

    def iterfile():
        with open(audio_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    return StreamingResponse(
        iterfile(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{file_id}.{ext}"',
        }
    )


# Public endpoint to check TTS availability
@router.get("/tts/available")
async def check_tts_available():
    """
    Check if TTS is available (public endpoint)

    Returns whether TTS is enabled, available, and current model
    """
    config = get_tts_config()

    return {
        "enabled": config.get("enabled", False),
        "available": tts_service is not None,
        "auto_play": config.get("auto_play", False),
        "model_id": config.get("model_id", "edge-tts"),
    }
