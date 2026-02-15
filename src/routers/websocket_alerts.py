"""
WebSocket Alerts Router

Real-time security alerts via WebSocket for admin users.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter()

# Global dependencies (injected at startup)
_cache_manager = None


def inject_dependencies(cache_mgr):
    """Inject dependencies for websocket_alerts router"""
    global _cache_manager
    _cache_manager = cache_mgr


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    실시간 보안 알림을 위한 WebSocket 엔드포인트
    관리자만 접근 가능 (토큰 기반 인증)
    """
    from ..auth.alert_system import alert_manager
    from ..auth.utils import verify_token

    # WebSocket 인증: query parameter에서 토큰 추출
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="인증 토큰이 필요합니다")
        return

    # JWT 토큰 검증
    payload = verify_token(token, expected_type="access")
    if not payload:
        await websocket.close(code=4001, reason="유효하지 않은 토큰입니다")
        return

    # 관리자 권한 확인
    user_id = payload.get("user_id")
    if user_id:
        from ..auth.utils import get_user
        user_data = get_user(user_id)
        user_role = user_data.get("role", "") if user_data else ""
        if user_role != "admin":
            await websocket.close(code=4003, reason="관리자 권한이 필요합니다")
            return
    else:
        await websocket.close(code=4001, reason="유효하지 않은 토큰입니다")
        return

    try:
        # WebSocket 연결 수락 (인증 통과 후)
        await alert_manager.connect(websocket)

        # 연결 유지 및 메시지 수신
        while True:
            try:
                # 클라이언트로부터 메시지 수신 (ping/pong)
                data = await websocket.receive_text()

                # ping 메시지에 대한 pong 응답
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                # 통계 요청
                elif data == "get_stats":
                    await alert_manager.send_stats()

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        # 연결 해제
        await alert_manager.disconnect(websocket)
