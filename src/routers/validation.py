"""
Validation Statistics Router

Provides endpoints for response quality validation statistics.
Admin and authenticated users can view validation metrics.
"""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from ..auth.middleware import get_current_active_user, require_admin
from ..response_validator import response_validator
from ..utils.error_handling import get_safe_error_message

router = APIRouter(prefix="/api/validation", tags=["Quality", "Admin"])


@router.get("/stats")
async def get_validation_stats(
    current_user: dict = Depends(get_current_active_user)
):
    """
    응답 품질 검증 통계 조회

    Returns:
        - total_checks: 총 검증 횟수
        - total_violations: 총 위반 횟수
        - pass_rate: 검증 통과율
        - violation_by_pattern: 패턴별 위반 횟수
    """
    try:
        stats = response_validator.get_statistics()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        safe_message = get_safe_error_message(e, "validation stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/stats/reset")
async def reset_validation_stats(
    current_user: dict = Depends(require_admin)
):
    """
    응답 품질 검증 통계 초기화
    """
    try:
        response_validator.reset_statistics()
        return {
            "success": True,
            "message": "검증 통계가 초기화되었습니다"
        }
    except Exception as e:
        safe_message = get_safe_error_message(e, "reset validation stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)
