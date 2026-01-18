"""
Production Configuration
프로덕션 환경을 위한 설정 및 검증
"""
import os
import sys
from typing import List, Optional
from loguru import logger


class ProductionConfig:
    """프로덕션 환경 설정"""

    # Environment
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    WORKERS: int = int(os.getenv("WORKERS", 4))

    # CORS Configuration
    CORS_ORIGINS: List[str] = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:8000"
    ).split(",")
    CORS_ALLOW_CREDENTIALS: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", 60))
    RATE_LIMIT_BURST: int = int(os.getenv("RATE_LIMIT_BURST", 10))

    # Request Timeouts (seconds)
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", 300))
    KEEPALIVE_TIMEOUT: int = int(os.getenv("KEEPALIVE_TIMEOUT", 5))

    # File Upload
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", 100))
    ALLOWED_FILE_TYPES: List[str] = [
        "pdf", "hwp", "hwpx", "doc", "docx",
        "xls", "xlsx", "ppt", "pptx"
    ]

    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", 50))

    # Security
    SECRET_KEY: Optional[str] = os.getenv("SECRET_KEY")
    REQUIRE_HTTPS: bool = os.getenv("REQUIRE_HTTPS", "false").lower() == "true"
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO" if ENV == "production" else "DEBUG")
    LOG_FORMAT: str = os.getenv(
        "LOG_FORMAT",
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    LOG_FILE: Optional[str] = os.getenv("LOG_FILE")
    LOG_ROTATION: str = os.getenv("LOG_ROTATION", "100 MB")
    LOG_RETENTION: str = os.getenv("LOG_RETENTION", "30 days")

    @classmethod
    def validate(cls) -> bool:
        """필수 환경 변수 검증"""
        errors = []

        # Production 환경에서 필수 체크
        if cls.ENV == "production":
            # SECRET_KEY 필수
            if not cls.SECRET_KEY:
                errors.append("SECRET_KEY must be set in production")

            # BASE_URL 검증 (production에서는 localhost가 아니어야 함)
            if not cls.BASE_URL or cls.BASE_URL == "http://localhost:8000":
                logger.warning("⚠️  BASE_URL is using default localhost (must be set for production)")
            elif not cls.BASE_URL.startswith("https://"):
                logger.warning("⚠️  BASE_URL should use HTTPS in production")

            # DEBUG 모드 비활성화 확인
            if cls.DEBUG:
                logger.warning("⚠️  DEBUG mode is enabled in production (not recommended)")

            # HTTPS 권장
            if not cls.REQUIRE_HTTPS:
                logger.warning("⚠️  HTTPS is not required (recommended for production)")

            # CORS origins 확인
            if "*" in cls.CORS_ORIGINS or "http://localhost" in str(cls.CORS_ORIGINS):
                logger.warning("⚠️  CORS origins include localhost or wildcard (not recommended for production)")

        # Redis 연결 정보 확인
        if not cls.REDIS_HOST:
            errors.append("REDIS_HOST must be set")

        # 오류가 있으면 출력하고 종료
        if errors:
            logger.error("❌ Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        return True

    @classmethod
    def setup_logging(cls):
        """로깅 설정 (환경별)"""
        # 기본 로거 제거
        logger.remove()

        # 환경변수에서 로그 레벨 읽기 (대문자로 변환하여 loguru 호환성 보장)
        log_level = os.getenv("LOG_LEVEL", "INFO" if cls.ENV == "production" else "DEBUG").upper()

        # 콘솔 로거 추가
        logger.add(
            sys.stderr,
            format=cls.LOG_FORMAT,
            level=log_level,
            colorize=True
        )

        # 파일 로거 추가 (프로덕션)
        if cls.LOG_FILE:
            logger.add(
                cls.LOG_FILE,
                format=cls.LOG_FORMAT,
                level=log_level,
                rotation=cls.LOG_ROTATION,
                retention=cls.LOG_RETENTION,
                compression="gz",
                enqueue=True  # 비동기 로깅
            )

        # 프로덕션 환경에서 민감 정보 필터링
        if cls.ENV == "production":
            logger.add(
                lambda msg: msg.replace(cls.SECRET_KEY or "", "***SECRET***")
            )

    @classmethod
    def get_uvicorn_config(cls) -> dict:
        """Uvicorn 서버 설정 반환"""
        config = {
            "host": cls.HOST,
            "port": cls.PORT,
            "workers": cls.WORKERS,
            "log_level": cls.LOG_LEVEL.lower(),
            "timeout_keep_alive": cls.KEEPALIVE_TIMEOUT,
            "limit_concurrency": 1000,
            "limit_max_requests": 10000,
        }

        # 프로덕션 최적화
        if cls.ENV == "production":
            config.update({
                "access_log": False,  # 성능 향상
                "use_colors": False,
                "server_header": False,  # 보안 향상
                "date_header": False,
            })

        return config

    @classmethod
    def print_config(cls):
        """현재 설정 출력 (민감 정보 제외)"""
        logger.info("=" * 60)
        logger.info("🔧 Server Configuration")
        logger.info("=" * 60)
        logger.info(f"Environment: {cls.ENV}")
        logger.info(f"Debug Mode: {cls.DEBUG}")
        logger.info(f"Host: {cls.HOST}")
        logger.info(f"Port: {cls.PORT}")
        logger.info(f"Workers: {cls.WORKERS}")
        logger.info(f"CORS Origins: {cls.CORS_ORIGINS}")
        logger.info(f"Rate Limit: {cls.RATE_LIMIT_PER_MINUTE}/min (enabled: {cls.RATE_LIMIT_ENABLED})")
        logger.info(f"Request Timeout: {cls.REQUEST_TIMEOUT}s")
        logger.info(f"Max File Size: {cls.MAX_FILE_SIZE_MB}MB")
        logger.info(f"Redis: {cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}")
        logger.info(f"Log Level: {cls.LOG_LEVEL}")
        logger.info("=" * 60)


# 설정 인스턴스
config = ProductionConfig()
