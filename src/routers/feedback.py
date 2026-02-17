"""
Feedback Management Router

Handles user feedback submission and analytics including:
- Feedback submission (positive/negative ratings)
- Admin feedback statistics
- Feedback analytics and reporting
- FeedbackAnalyzer statistics and management

Authentication required for all endpoints.
Admin privileges required for admin-specific endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import json
from loguru import logger

from sqlalchemy import select, func, case

from ..auth.middleware import get_current_active_user
from ..auth.rate_limiter import create_rate_limit_dependency
from ..routers.admin import require_admin
from ..utils.error_handling import get_safe_error_message
from ..database.connection import SyncSessionFactory
from ..database.models.feedback import FeedbackEntry

# Create router with prefix and tags
router = APIRouter(prefix="/api", tags=["Feedback"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

feedback_analyzer = None
conversation_manager = None
cache_manager = None


def inject_dependencies(fb_analyzer, conv_manager, cache_mgr):
    """
    Inject dependencies from main application

    Args:
        fb_analyzer: FeedbackAnalyzer instance for feedback analytics
        conv_manager: ConversationManager instance for conversation lookup
        cache_mgr: CacheManager instance
    """
    global feedback_analyzer, conversation_manager, cache_manager
    feedback_analyzer = fb_analyzer
    conversation_manager = conv_manager
    cache_manager = cache_mgr


# ============================================================================
# Pydantic Models
# ============================================================================

class FeedbackRequest(BaseModel):
    """답변 평가 피드백 요청"""
    conversation_id: str
    message_id: str
    feedback_type: str  # 'positive' or 'negative'


# ============================================================================
# Feedback API Endpoints
# ============================================================================

@router.post("/feedback", tags=["Feedback"])
async def submit_feedback(
    request: Request,
    feedback: FeedbackRequest,
    current_user: dict = Depends(get_current_active_user),
    _rate_limit: bool = Depends(
        create_rate_limit_dependency(max_requests=10, window_seconds=60, identifier="feedback")
    )
):
    """
    답변 평가 피드백 제출 (로그인 필요)

    사용자가 챗봇 답변에 대해 👍/👎 피드백을 제공합니다.
    피드백을 저장하고 통계 데이터를 업데이트합니다.

    Args:
        request: FastAPI request object
        feedback: FeedbackRequest with conversation_id, message_id, feedback_type
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Success message and feedback type
            - success: True if saved successfully
            - message: Confirmation message
            - feedback_type: Type of feedback submitted

    Raises:
        HTTPException: 500 if cache manager not initialized or save fails
    """
    try:
        # 피드백을 PG에 저장
        rating = 1 if feedback.feedback_type == "positive" else -1

        with SyncSessionFactory() as db:
            entry = FeedbackEntry(
                query="",  # Will be filled from conversation if available
                response="",
                rating=rating,
                user_id=current_user.get("user_id") or current_user.get("username"),
                metadata_={
                    "type": feedback.feedback_type,
                    "conversation_id": feedback.conversation_id,
                    "message_id": feedback.message_id,
                },
            )
            db.add(entry)
            db.commit()

        # 📊 FeedbackAnalyzer에 피드백 기록
        # 대화 기록에서 메시지 가져오기
        if conversation_manager and feedback_analyzer:
            try:
                # Get all messages and find the specific message by ID
                messages = conversation_manager.get_messages(feedback.conversation_id, user_id=current_user.get("user_id"))
                message = None
                question = None

                for idx, msg in enumerate(messages):
                    if msg.get("id") == feedback.message_id:
                        message = msg
                        # 이전 사용자 질문 가져오기
                        if idx > 0:
                            prev_msg = messages[idx - 1]
                            if prev_msg.get("role") == "user":
                                question = prev_msg.get("content")
                        break

                if message and message.get("role") == "assistant":
                    # 메타데이터에서 컨텍스트와 신뢰도 정보 추출
                    metadata = message.get("metadata", {})
                    context = metadata.get("context", [])

                    # FeedbackAnalyzer에 기록
                    feedback_analyzer.record_feedback(
                        feedback_type=feedback.feedback_type,
                        answer=message.get("content", ""),
                        context=context,
                        confidence=metadata.get("confidence"),
                        question=question,
                        metadata={
                            "conversation_id": feedback.conversation_id,
                            "message_id": feedback.message_id,
                            "sources": metadata.get("sources", [])
                        }
                    )
                    logger.success(f"✅ FeedbackAnalyzer 기록 완료")
            except Exception as analyzer_error:
                logger.warning(f"⚠️ FeedbackAnalyzer 기록 실패 (무시됨): {analyzer_error}")

        logger.info(f"👍👎 Feedback saved: {feedback.feedback_type} for message {feedback.message_id}")

        return {
            "success": True,
            "message": "피드백이 성공적으로 저장되었습니다.",
            "feedback_type": feedback.feedback_type
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Feedback submission failed: {str(e)}")
        raise HTTPException(status_code=500, detail="피드백 저장에 실패했습니다.")


@router.get("/admin/feedback/stats", tags=["Feedback", "Admin"])
async def get_feedback_stats(
    request: Request,
    user=Depends(require_admin)
):
    """
    피드백 통계 조회 (관리자 전용)

    전체 피드백 수, 긍정/부정 비율, 최근 피드백 등을 제공합니다.

    Args:
        request: FastAPI request object
        user: Admin user (injected by require_admin dependency)

    Returns:
        dict: Comprehensive feedback statistics
            - total_count: Total number of feedbacks
            - positive_count: Number of positive feedbacks
            - negative_count: Number of negative feedbacks
            - positive_ratio: Percentage of positive feedbacks
            - recent_week: Statistics for last 7 days
            - recent_feedbacks: List of recent feedback entries (max 10)

    Raises:
        HTTPException: 403 if user is not admin
        HTTPException: 500 if cache manager not initialized or retrieval fails
    """
    try:
        with SyncSessionFactory() as db:
            # 전체 카운트 조회
            count_stmt = select(
                func.count().label("total"),
                func.sum(case((FeedbackEntry.rating > 0, 1), else_=0)).label("positive"),
                func.sum(case((FeedbackEntry.rating <= 0, 1), else_=0)).label("negative"),
            )
            row = db.execute(count_stmt).one()
            total_count = row.total or 0
            positive_count = int(row.positive or 0)
            negative_count = int(row.negative or 0)

            # 긍정 비율 계산
            positive_ratio = (positive_count / total_count * 100) if total_count > 0 else 0

            # 최근 7일 피드백 조회
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            recent_stmt = select(
                func.sum(case((FeedbackEntry.rating > 0, 1), else_=0)).label("positive"),
                func.sum(case((FeedbackEntry.rating <= 0, 1), else_=0)).label("negative"),
            ).where(FeedbackEntry.created_at >= week_ago)
            recent_row = db.execute(recent_stmt).one()
            recent_positive = int(recent_row.positive or 0)
            recent_negative = int(recent_row.negative or 0)

            # 최근 피드백 목록 (최대 10개)
            recent_stmt = (
                select(FeedbackEntry)
                .order_by(FeedbackEntry.created_at.desc())
                .limit(10)
            )
            recent_rows = db.execute(recent_stmt).scalars().all()

        recent_feedbacks = []
        for fb in recent_rows:
            meta = fb.metadata_ or {}
            recent_feedbacks.append({
                "type": meta.get("type", "positive" if fb.rating > 0 else "negative"),
                "timestamp": fb.created_at.isoformat() if fb.created_at else "",
                "conversation_id": meta.get("conversation_id", ""),
                "message_id": meta.get("message_id", ""),
            })

        stats = {
            "total_count": total_count,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "positive_ratio": round(positive_ratio, 2),
            "recent_week": {
                "positive": recent_positive,
                "negative": recent_negative,
                "total": recent_positive + recent_negative
            },
            "recent_feedbacks": recent_feedbacks
        }

        logger.info(f"📊 Feedback stats retrieved: {total_count} total feedbacks")

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get feedback stats: {str(e)}")
        raise HTTPException(status_code=500, detail="피드백 통계 조회에 실패했습니다.")


@router.get("/feedback/analytics", tags=["Feedback", "Analytics"])
async def get_feedback_analytics(
    days: int = 7,
    current_user: dict = Depends(get_current_active_user)
):
    """
    피드백 분석 리포트 조회 (로그인 필요)

    FeedbackAnalyzer를 사용하여 피드백 데이터를 분석하고
    만족도, 학습된 패턴, 권장사항 등을 제공합니다.

    Args:
        days: 분석 기간 (일, 기본값: 7)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Analytics report
            - success: True if successful
            - data: Analytics data (satisfaction, patterns, recommendations, etc.)

    Raises:
        HTTPException: 500 if feedback analyzer not initialized or error occurs
    """
    try:
        if not feedback_analyzer:
            raise HTTPException(status_code=500, detail="Feedback analyzer not initialized")

        analytics = feedback_analyzer.get_analytics(days=days)
        logger.info(f"📊 피드백 분석 리포트 조회: {days}일 기간")
        return {
            "success": True,
            "data": analytics
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "feedback analytics endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.get("/feedback/analyzer/stats", tags=["Feedback", "Analytics"])
async def get_feedback_analyzer_stats(
    current_user: dict = Depends(get_current_active_user)
):
    """
    FeedbackAnalyzer 통계 조회 (로그인 필요)

    FeedbackAnalyzer가 수집한 전체 피드백 통계 및
    학습된 패턴을 조회합니다.

    Args:
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: FeedbackAnalyzer statistics
            - success: True if successful
            - data: Statistics data (total feedbacks, patterns, trends, etc.)

    Raises:
        HTTPException: 500 if feedback analyzer not initialized or error occurs
    """
    try:
        if not feedback_analyzer:
            raise HTTPException(status_code=500, detail="Feedback analyzer not initialized")

        stats = feedback_analyzer.get_statistics()
        logger.info(f"📊 FeedbackAnalyzer 통계 조회")
        return {
            "success": True,
            "data": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "feedback analyzer stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/feedback/analyzer/stats/reset", tags=["Feedback", "Analytics", "Admin"])
async def reset_feedback_analyzer_stats(
    current_user: dict = Depends(require_admin)
):
    """
    FeedbackAnalyzer 통계 초기화 (로그인 필요)

    ⚠️ WARNING: This resets all FeedbackAnalyzer statistics.
    Use with caution - this operation cannot be undone.

    Note: This endpoint requires authentication but not admin privileges.
    Consider adding require_admin if you want to restrict to admins only.

    Args:
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Success message
            - success: True if reset successfully
            - message: Confirmation message

    Raises:
        HTTPException: 500 if feedback analyzer not initialized or error occurs
    """
    try:
        if not feedback_analyzer:
            raise HTTPException(status_code=500, detail="Feedback analyzer not initialized")

        feedback_analyzer.reset_statistics()
        logger.success("✅ FeedbackAnalyzer 통계 초기화 완료")
        return {
            "success": True,
            "message": "FeedbackAnalyzer 통계가 초기화되었습니다."
        }
    except HTTPException:
        raise
    except Exception as e:
        safe_message = get_safe_error_message(e, "reset feedback analyzer stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)
