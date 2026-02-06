"""User Persona Models

사용자별 페르소나 설정 모델
검색 및 응답 생성 시 사용자 맞춤형 스타일 적용
"""

from typing import Optional
from pydantic import BaseModel, Field, validator


class PersonaBase(BaseModel):
    """페르소나 기본 모델"""

    role: Optional[str] = Field(
        None,
        max_length=100,
        description="사용자 역할 (예: 개발자, 연구원, 마케터, 학생)"
    )

    expertise_level: Optional[str] = Field(
        None,
        description="전문성 수준 (beginner, intermediate, expert)"
    )

    expertise_domains: Optional[str] = Field(
        None,
        max_length=500,
        description="전문 분야 (쉼표로 구분, 예: Python, 머신러닝, 웹 개발)"
    )

    tone: Optional[str] = Field(
        None,
        description="응답 톤 (professional, casual, friendly, technical)"
    )

    language_style: Optional[str] = Field(
        None,
        description="언어 스타일 (formal, informal, concise, detailed)"
    )

    response_format_preference: Optional[str] = Field(
        None,
        description="응답 형식 선호 (code_focused, explanation_focused, balanced)"
    )

    additional_context: Optional[str] = Field(
        None,
        max_length=1000,
        description="추가 컨텍스트 (특별한 요구사항, 제약사항 등)"
    )

    @validator('expertise_level')
    def validate_expertise_level(cls, v):
        """전문성 수준 검증"""
        if v is not None:
            allowed = ['beginner', 'intermediate', 'expert']
            if v not in allowed:
                raise ValueError(f"expertise_level must be one of {allowed}")
        return v

    @validator('tone')
    def validate_tone(cls, v):
        """톤 검증"""
        if v is not None:
            allowed = ['professional', 'casual', 'friendly', 'technical']
            if v not in allowed:
                raise ValueError(f"tone must be one of {allowed}")
        return v

    @validator('language_style')
    def validate_language_style(cls, v):
        """언어 스타일 검증"""
        if v is not None:
            allowed = ['formal', 'informal', 'concise', 'detailed']
            if v not in allowed:
                raise ValueError(f"language_style must be one of {allowed}")
        return v

    @validator('response_format_preference')
    def validate_response_format(cls, v):
        """응답 형식 검증"""
        if v is not None:
            allowed = ['code_focused', 'explanation_focused', 'balanced']
            if v not in allowed:
                raise ValueError(f"response_format_preference must be one of {allowed}")
        return v


class PersonaCreate(PersonaBase):
    """페르소나 생성 모델"""
    pass


class PersonaUpdate(PersonaBase):
    """페르소나 업데이트 모델"""
    pass


class PersonaResponse(PersonaBase):
    """페르소나 응답 모델"""

    user_id: str = Field(..., description="사용자 ID")
    enabled: bool = Field(True, description="페르소나 활성화 여부")

    class Config:
        from_attributes = True


def build_persona_prompt(persona: PersonaResponse) -> str:
    """
    페르소나를 기반으로 시스템 프롬프트 텍스트 생성

    Args:
        persona: 사용자 페르소나 객체

    Returns:
        시스템 프롬프트에 추가할 페르소나 컨텍스트
    """
    if not persona or not persona.enabled:
        return ""

    persona_parts = []

    # 역할
    if persona.role:
        persona_parts.append(f"사용자 역할: {persona.role}")

    # 전문성 수준
    if persona.expertise_level:
        level_map = {
            'beginner': '초보자 - 기본 개념부터 자세히 설명',
            'intermediate': '중급자 - 핵심 내용 중심으로 설명',
            'expert': '전문가 - 고급 개념과 세부사항 중심'
        }
        persona_parts.append(f"전문성 수준: {level_map.get(persona.expertise_level, persona.expertise_level)}")

    # 전문 분야
    if persona.expertise_domains:
        persona_parts.append(f"전문 분야: {persona.expertise_domains}")

    # 톤
    if persona.tone:
        tone_map = {
            'professional': '전문적이고 공식적인 톤',
            'casual': '편안하고 캐주얼한 톤',
            'friendly': '친근하고 다정한 톤',
            'technical': '기술적이고 정확한 톤'
        }
        persona_parts.append(f"응답 톤: {tone_map.get(persona.tone, persona.tone)}")

    # 언어 스타일
    if persona.language_style:
        style_map = {
            'formal': '격식 있는 표현 사용',
            'informal': '일상적인 표현 사용',
            'concise': '간결하고 요약적으로 답변',
            'detailed': '상세하고 구체적으로 답변'
        }
        persona_parts.append(f"언어 스타일: {style_map.get(persona.language_style, persona.language_style)}")

    # 응답 형식 선호
    if persona.response_format_preference:
        format_map = {
            'code_focused': '코드 예제 중심으로 답변',
            'explanation_focused': '개념 설명 중심으로 답변',
            'balanced': '설명과 코드를 균형있게 제공'
        }
        persona_parts.append(f"응답 형식: {format_map.get(persona.response_format_preference, persona.response_format_preference)}")

    # 추가 컨텍스트
    if persona.additional_context:
        persona_parts.append(f"추가 요구사항: {persona.additional_context}")

    if not persona_parts:
        return ""

    # 페르소나 프롬프트 조합
    persona_prompt = "\n\n[사용자 페르소나 설정]\n" + "\n".join(f"- {part}" for part in persona_parts)
    persona_prompt += "\n\n위 사용자 페르소나를 고려하여 답변을 작성해주세요."

    return persona_prompt
