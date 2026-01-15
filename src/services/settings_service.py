"""Settings service

시스템 설정을 관리하는 서비스 계층입니다.
Redis에서 설정을 읽고 쓰는 비즈니스 로직을 처리합니다.
"""

import json
from typing import Dict
from ..auth.models import SystemSettings
from ..config.settings import (
    REDIS_SETTINGS_KEY,
    DEFAULT_INACTIVITY_TIMEOUT,
    DEFAULT_WARNING_TIME,
    DEFAULT_CHECK_INTERVAL
)


class SettingsService:
    """시스템 설정 관리 서비스"""

    def __init__(self, redis_client):
        """
        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client

    def get_settings(self) -> SystemSettings:
        """시스템 설정 조회

        Redis에서 설정을 읽고, 없으면 기본값을 반환합니다.

        Returns:
            SystemSettings 객체
        """
        settings_json = self.redis.get(REDIS_SETTINGS_KEY)

        if settings_json:
            # Redis에 저장된 설정 사용
            settings_dict = json.loads(settings_json)
            return SystemSettings(**settings_dict)

        # 기본 설정 반환
        return SystemSettings(
            inactivity_timeout=DEFAULT_INACTIVITY_TIMEOUT,
            warning_time=DEFAULT_WARNING_TIME,
            check_interval=DEFAULT_CHECK_INTERVAL
        )

    def update_settings(self, settings: SystemSettings) -> SystemSettings:
        """시스템 설정 업데이트

        Args:
            settings: 업데이트할 SystemSettings 객체

        Returns:
            업데이트된 SystemSettings 객체

        Raises:
            ValueError: 유효성 검증 실패 시
        """
        # Pydantic 모델 검증 (Field constraints)
        # settings 객체가 이미 검증되었음

        # 추가 비즈니스 로직 검증
        if settings.warning_time >= settings.inactivity_timeout:
            raise ValueError(
                "Warning time must be less than inactivity timeout"
            )

        # Redis에 저장
        settings_dict = settings.model_dump()
        self.redis.set(REDIS_SETTINGS_KEY, json.dumps(settings_dict))

        return settings

    def reset_to_defaults(self) -> SystemSettings:
        """설정을 기본값으로 초기화

        Returns:
            기본 SystemSettings 객체
        """
        default_settings = SystemSettings(
            inactivity_timeout=DEFAULT_INACTIVITY_TIMEOUT,
            warning_time=DEFAULT_WARNING_TIME,
            check_interval=DEFAULT_CHECK_INTERVAL
        )

        # Redis에 저장
        settings_dict = default_settings.model_dump()
        self.redis.set(REDIS_SETTINGS_KEY, json.dumps(settings_dict))

        return default_settings

    def get_settings_dict(self) -> Dict:
        """설정을 딕셔너리로 반환

        API 응답용 딕셔너리 형식으로 반환합니다.

        Returns:
            설정 딕셔너리
        """
        settings = self.get_settings()
        return settings.model_dump()
