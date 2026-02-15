"""Persona API Router

사용자 페르소나 설정 API
"""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from src.models.persona import PersonaCreate, PersonaUpdate, PersonaResponse
from src.services.persona_service import PersonaService
from src.auth.middleware import get_current_active_user


router = APIRouter(prefix="/api/persona", tags=["Persona"])


def get_persona_service() -> PersonaService:
    """
    페르소나 서비스 의존성

    Returns:
        PersonaService 인스턴스
    """
    return PersonaService()


@router.get("", response_model=PersonaResponse)
async def get_persona(
    current_user: dict = Depends(get_current_active_user),
    persona_service: PersonaService = Depends(get_persona_service)
):
    """
    현재 사용자의 페르소나 조회

    Returns:
        사용자 페르소나 (없으면 404)
    """
    user_id = current_user.get("user_id")

    persona = await persona_service.get_persona(user_id)

    if not persona:
        raise HTTPException(
            status_code=404,
            detail="페르소나가 설정되지 않았습니다"
        )

    return persona


@router.post("", response_model=PersonaResponse)
async def create_persona(
    persona_data: PersonaCreate,
    current_user: dict = Depends(get_current_active_user),
    persona_service: PersonaService = Depends(get_persona_service)
):
    """
    페르소나 생성

    Args:
        persona_data: 페르소나 데이터

    Returns:
        생성된 페르소나
    """
    user_id = current_user.get("user_id")

    # 기존 페르소나 확인
    existing_persona = await persona_service.get_persona(user_id)
    if existing_persona:
        raise HTTPException(
            status_code=400,
            detail="이미 페르소나가 존재합니다. PUT 요청으로 수정해주세요"
        )

    persona = await persona_service.save_persona(user_id, persona_data)

    logger.info(f"✅ Persona created for user {user_id}")

    return persona


@router.put("", response_model=PersonaResponse)
async def update_persona(
    persona_update: PersonaUpdate,
    current_user: dict = Depends(get_current_active_user),
    persona_service: PersonaService = Depends(get_persona_service)
):
    """
    페르소나 업데이트

    Args:
        persona_update: 업데이트할 데이터

    Returns:
        업데이트된 페르소나
    """
    user_id = current_user.get("user_id")

    # 기존 페르소나가 없으면 생성
    existing_persona = await persona_service.get_persona(user_id)
    if not existing_persona:
        # PersonaUpdate를 PersonaCreate로 변환
        create_data = PersonaCreate(**persona_update.model_dump(exclude_none=True))
        persona = await persona_service.save_persona(user_id, create_data)
        logger.info(f"✅ Persona created (via PUT) for user {user_id}")
    else:
        persona = await persona_service.update_persona(user_id, persona_update)
        logger.info(f"✅ Persona updated for user {user_id}")

    return persona


@router.delete("")
async def delete_persona(
    current_user: dict = Depends(get_current_active_user),
    persona_service: PersonaService = Depends(get_persona_service)
):
    """
    페르소나 삭제

    Returns:
        삭제 성공 메시지
    """
    user_id = current_user.get("user_id")

    success = await persona_service.delete_persona(user_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="삭제할 페르소나가 없습니다"
        )

    return {"message": "페르소나가 삭제되었습니다"}


@router.post("/toggle")
async def toggle_persona(
    enabled: bool,
    current_user: dict = Depends(get_current_active_user),
    persona_service: PersonaService = Depends(get_persona_service)
):
    """
    페르소나 활성화/비활성화

    Args:
        enabled: 활성화 여부

    Returns:
        업데이트된 페르소나
    """
    user_id = current_user.get("user_id")

    persona = await persona_service.toggle_persona(user_id, enabled)

    if not persona:
        raise HTTPException(
            status_code=404,
            detail="페르소나가 설정되지 않았습니다"
        )

    return persona
