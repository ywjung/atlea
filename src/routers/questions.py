"""
Question Suggestions Router

Provides suggested questions for autocomplete based on indexed documents.
Questions are generated from document content using LLM.
"""

from fastapi import APIRouter, Depends
import random
from loguru import logger

from ..auth.middleware import get_current_active_user

router = APIRouter(prefix="/api", tags=["Query"])

# Global dependency (injected from web_server.py)
question_service = None


def inject_dependencies(question_gen_service):
    """
    Inject question generation service dependency

    Args:
        question_gen_service: Question generation service module
    """
    global question_service
    question_service = question_gen_service


@router.get("/suggested-questions")
async def get_suggested_questions(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get suggested questions (로그인 필요)

    Returns 50 random questions from the pre-generated pool for autocomplete.
    Falls back to diverse question set if pool is empty.
    """
    try:
        # Get current question pool
        question_pool = question_service.get_question_pool()

        # Use pre-generated question pool for fast response
        if not question_pool:
            # Fallback if pool is empty - use diverse question pool
            logger.warning("Question pool is empty, using fallback questions")

            fallback_pool = question_service.get_fallback_questions()

            # Randomly select 5 questions from the pool
            selected_questions = random.sample(fallback_pool, 5)
            return {"questions": selected_questions}

        # Sample 50 random questions from the pool for better autocomplete coverage
        num_questions = min(50, len(question_pool))
        selected_questions = random.sample(question_pool, num_questions)

        logger.info(f"Returning {num_questions} questions from pool of {len(question_pool)}")
        return {"questions": selected_questions}

    except Exception as e:
        logger.error(f"Failed to get suggested questions: {e}")
        return {
            "questions": [
                "이 문서의 주요 내용은 무엇인가요?",
                "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
                "이 문서를 간단히 요약해주세요."
            ]
        }
