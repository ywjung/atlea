"""Persona Service

사용자별 페르소나 관리 서비스 (PostgreSQL 기반)
"""

from typing import Optional
from loguru import logger

from src.models.persona import PersonaCreate, PersonaUpdate, PersonaResponse
from src.database.connection import AsyncSessionFactory
from src.database.models.user_persona import UserPersona
from src.repositories.persona_repository import PersonaRepository


class PersonaService:
    """페르소나 관리 서비스"""

    def __init__(self):
        """
        초기화

        Args:
        """
        pass

    def _to_response(self, persona: UserPersona) -> PersonaResponse:
        """Convert ORM model to Pydantic response."""
        return PersonaResponse(
            user_id=persona.user_id,
            role=persona.role,
            expertise_level=persona.expertise_level,
            expertise_domains=persona.expertise_domains,
            tone=persona.tone,
            language_style=persona.language_style,
            response_format_preference=persona.response_format_preference,
            additional_context=persona.additional_context,
            enabled=persona.enabled,
        )

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
        async with AsyncSessionFactory() as session:
            repo = PersonaRepository(session)

            persona = UserPersona(
                user_id=user_id,
                role=persona_data.role,
                expertise_level=persona_data.expertise_level,
                expertise_domains=persona_data.expertise_domains,
                tone=persona_data.tone,
                language_style=persona_data.language_style,
                response_format_preference=persona_data.response_format_preference,
                additional_context=persona_data.additional_context,
                enabled=True,
            )
            await repo.create(persona)
            await session.commit()

            logger.info(f"Persona saved for user {user_id}")
            return self._to_response(persona)

    async def get_persona(self, user_id: str) -> Optional[PersonaResponse]:
        """
        페르소나 조회

        Args:
            user_id: 사용자 ID

        Returns:
            페르소나 (없으면 None)
        """
        async with AsyncSessionFactory() as session:
            repo = PersonaRepository(session)
            persona = await repo.get_by_user_id(user_id)

            if persona is None:
                return None

            return self._to_response(persona)

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
        async with AsyncSessionFactory() as session:
            repo = PersonaRepository(session)
            persona = await repo.get_by_user_id(user_id)

            if persona is None:
                return None

            # Update only non-None fields
            update_dict = persona_update.model_dump(exclude_none=True)
            for key, value in update_dict.items():
                setattr(persona, key, value)

            await session.flush()
            await session.commit()

            logger.info(f"Persona updated for user {user_id}")
            return self._to_response(persona)

    async def delete_persona(self, user_id: str) -> bool:
        """
        페르소나 삭제

        Args:
            user_id: 사용자 ID

        Returns:
            삭제 성공 여부
        """
        async with AsyncSessionFactory() as session:
            repo = PersonaRepository(session)
            deleted = await repo.delete_by_user_id(user_id)
            await session.commit()

            if deleted:
                logger.info(f"Persona deleted for user {user_id}")
            else:
                logger.warning(f"No persona found to delete for user {user_id}")

            return deleted

    async def toggle_persona(self, user_id: str, enabled: bool) -> Optional[PersonaResponse]:
        """
        페르소나 활성화/비활성화

        Args:
            user_id: 사용자 ID
            enabled: 활성화 여부

        Returns:
            업데이트된 페르소나 (없으면 None)
        """
        async with AsyncSessionFactory() as session:
            repo = PersonaRepository(session)
            persona = await repo.get_by_user_id(user_id)

            if persona is None:
                return None

            persona.enabled = enabled
            await session.flush()
            await session.commit()

            logger.info(f"Persona {'enabled' if enabled else 'disabled'} for user {user_id}")
            return self._to_response(persona)
