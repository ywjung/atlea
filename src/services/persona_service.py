"""Persona Service

사용자별 페르소나 관리 서비스
"""

from typing import Optional
from redis import Redis
from loguru import logger
import json

from src.models.persona import PersonaCreate, PersonaUpdate, PersonaResponse


class PersonaService:
    """페르소나 관리 서비스"""

    def __init__(self, redis_client: Redis):
        """
        초기화

        Args:
            redis_client: Redis 클라이언트
        """
        self.redis = redis_client

    def _get_persona_key(self, user_id: str) -> str:
        """
        페르소나 Redis 키 생성

        Args:
            user_id: 사용자 ID

        Returns:
            Redis 키
        """
        return f"user:persona:{user_id}"

    async def save_persona(
        self,
        user_id: str,
        persona_data: PersonaCreate
    ) -> PersonaResponse:
        """
        페르소나 저장

        Args:
            user_id: 사용자 ID
            persona_data: 페르소나 데이터

        Returns:
            저장된 페르소나
        """
        persona_key = self._get_persona_key(user_id)

        # 페르소나 데이터 준비
        persona_dict = persona_data.model_dump(exclude_none=True)
        persona_dict['user_id'] = user_id
        persona_dict['enabled'] = True

        # Redis에 JSON으로 저장
        self.redis.set(persona_key, json.dumps(persona_dict, ensure_ascii=False))

        logger.info(f"✅ Persona saved for user {user_id}")

        return PersonaResponse(**persona_dict)

    async def get_persona(self, user_id: str) -> Optional[PersonaResponse]:
        """
        페르소나 조회

        Args:
            user_id: 사용자 ID

        Returns:
            페르소나 (없으면 None)
        """
        persona_key = self._get_persona_key(user_id)

        persona_json = self.redis.get(persona_key)
        if not persona_json:
            return None

        try:
            persona_dict = json.loads(persona_json)
            return PersonaResponse(**persona_dict)
        except Exception as e:
            logger.error(f"❌ Failed to parse persona for user {user_id}: {e}")
            return None

    async def update_persona(
        self,
        user_id: str,
        persona_update: PersonaUpdate
    ) -> Optional[PersonaResponse]:
        """
        페르소나 업데이트

        Args:
            user_id: 사용자 ID
            persona_update: 업데이트할 데이터

        Returns:
            업데이트된 페르소나 (없으면 None)
        """
        # 기존 페르소나 조회
        existing_persona = await self.get_persona(user_id)
        if not existing_persona:
            return None

        # 업데이트할 필드만 병합
        update_dict = persona_update.model_dump(exclude_none=True)
        existing_dict = existing_persona.model_dump()

        for key, value in update_dict.items():
            existing_dict[key] = value

        # 저장
        persona_key = self._get_persona_key(user_id)
        self.redis.set(persona_key, json.dumps(existing_dict, ensure_ascii=False))

        logger.info(f"✅ Persona updated for user {user_id}")

        return PersonaResponse(**existing_dict)

    async def delete_persona(self, user_id: str) -> bool:
        """
        페르소나 삭제

        Args:
            user_id: 사용자 ID

        Returns:
            삭제 성공 여부
        """
        persona_key = self._get_persona_key(user_id)

        result = self.redis.delete(persona_key)

        if result > 0:
            logger.info(f"✅ Persona deleted for user {user_id}")
            return True
        else:
            logger.warning(f"⚠️ No persona found to delete for user {user_id}")
            return False

    async def toggle_persona(self, user_id: str, enabled: bool) -> Optional[PersonaResponse]:
        """
        페르소나 활성화/비활성화

        Args:
            user_id: 사용자 ID
            enabled: 활성화 여부

        Returns:
            업데이트된 페르소나 (없으면 None)
        """
        existing_persona = await self.get_persona(user_id)
        if not existing_persona:
            return None

        persona_dict = existing_persona.model_dump()
        persona_dict['enabled'] = enabled

        persona_key = self._get_persona_key(user_id)
        self.redis.set(persona_key, json.dumps(persona_dict, ensure_ascii=False))

        logger.info(f"✅ Persona {'enabled' if enabled else 'disabled'} for user {user_id}")

        return PersonaResponse(**persona_dict)
