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
from datetime import datetime, timezone
import json
import logging

from ..auth.middleware import get_current_active_user
from ..routers.admin import require_admin

# Configure logger
logger = logging.getLogger(__name__)

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
        cache_mgr: CacheManager instance for Redis access
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
# Helper Functions
# ============================================================================

def get_safe_error_message(error: Exception, context: str = "") -> str:
    """
    Get sanitized error message for user display

    Prevents information disclosure by mapping exception types to
    generic user-friendly messages while logging the full error.

    Args:
        error: The exception that occurred
        context: Context string for logging (e.g., "feedback endpoint")

    Returns:
        Safe error message suitable for user display
    """
    error_type = type(error).__name__

    # Log full error for debugging
    logger.error(f"Error in {context}: {error_type}: {str(error)}")

    # Map exception types to safe messages
    error_messages = {
        "FileNotFoundError": "요청한 리소스를 찾을 수 없습니다.",
        "PermissionError": "접근 권한이 없습니다.",
        "ValueError": "잘못된 입력값입니다.",
        "ConnectionError": "서비스 연결에 실패했습니다.",
        "TimeoutError": "요청 시간이 초과되었습니다.",
    }

    # Return mapped message or generic message
    return error_messages.get(
        error_type,
        "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    )


# ============================================================================
# Feedback API Endpoints
# ============================================================================

@router.post("/feedback", tags=["Feedback"])
async def submit_feedback(
    request: Request,
    feedback: FeedbackRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    답변 평가 피드백 제출 (로그인 필요)

    사용자가 챗봇 답변에 대해 👍/👎 피드백을 제공합니다.
    Redis에 피드백을 저장하고 통계 데이터를 업데이트합니다.

    Args:
        request: FastAPI request object (for Redis access)
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
        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis = cache_manager.redis

        # 피드백 데이터 구성
        feedback_key = f"feedback:{feedback.conversation_id}:{feedback.message_id}"
        feedback_data = {
            "type": feedback.feedback_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "conversation_id": feedback.conversation_id,
            "message_id": feedback.message_id
        }

        # Redis에 피드백 저장 (TTL: 90일)
        redis.setex(
            feedback_key,
            90 * 24 * 60 * 60,  # 90 days
            json.dumps(feedback_data)
        )

        # 통계용 ZSET에 추가 (타임스탬프를 스코어로 사용)
        timestamp_score = datetime.now(timezone.utc).timestamp()
        stats_key = f"feedback:stats:{feedback.feedback_type}"
        redis.zadd(stats_key, {feedback_key: timestamp_score})

        # 전체 피드백 카운트 증가
        redis.incr(f"feedback:count:{feedback.feedback_type}")

        # 📊 FeedbackAnalyzer에 피드백 기록
        # 대화 기록에서 메시지 가져오기
        if conversation_manager and feedback_analyzer:
            try:
                # Get all messages and find the specific message by ID
                messages = conversation_manager.get_messages(feedback.conversation_id)
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
        request: FastAPI request object (for Redis access)
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
        if not cache_manager:
            raise HTTPException(status_code=500, detail="Cache manager not initialized")

        redis = cache_manager.redis

        # 전체 피드백 카운트 조회
        positive_count = int(redis.get("feedback:count:positive") or 0)
        negative_count = int(redis.get("feedback:count:negative") or 0)
        total_count = positive_count + negative_count

        # 긍정 비율 계산
        positive_ratio = (positive_count / total_count * 100) if total_count > 0 else 0

        # 최근 7일 피드백 조회
        week_ago = (datetime.now(timezone.utc).timestamp() - 7 * 24 * 60 * 60)
        recent_positive = redis.zcount("feedback:stats:positive", week_ago, "+inf")
        recent_negative = redis.zcount("feedback:stats:negative", week_ago, "+inf")

        # 최근 피드백 목록 (최대 10개) - Pipeline으로 배치 조회 (N+1 방지)
        recent_feedback_keys = []
        recent_positive_keys = redis.zrevrange("feedback:stats:positive", 0, 4) or []
        recent_negative_keys = redis.zrevrange("feedback:stats:negative", 0, 4) or []
        recent_feedback_keys.extend(recent_positive_keys)
        recent_feedback_keys.extend(recent_negative_keys)

        recent_feedbacks = []
        if recent_feedback_keys:
            # Pipeline으로 모든 키를 한 번에 조회
            pipe = redis.pipeline()
            for key in recent_feedback_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                pipe.get(key_str)
            results = pipe.execute()

            for feedback_data in results:
                if feedback_data:
                    recent_feedbacks.append(json.loads(feedback_data))

        # 타임스탬프 기준으로 정렬
        recent_feedbacks.sort(key=lambda x: x['timestamp'], reverse=True)
        recent_feedbacks = recent_feedbacks[:10]

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
    current_user: dict = Depends(get_current_active_user)
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
