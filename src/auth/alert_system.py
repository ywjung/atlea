"""Real-time Security Alert System

WebSocket 기반 실시간 보안 알림 시스템
중요한 보안 이벤트를 관리자에게 즉시 알림
"""
from typing import Set, Dict, Any, Optional
from datetime import datetime
from fastapi import WebSocket
from loguru import logger
import json
import asyncio


class AlertLevel:
    """알림 레벨"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertRule:
    """알림 규칙 정의"""

    # 즉시 알림 대상 이벤트 (CRITICAL)
    CRITICAL_EVENTS = {
        "BRUTE_FORCE_ATTEMPT",  # 브루트포스 공격 시도
        "ACCOUNT_LOCKED",  # 계정 잠금
        "SUSPICIOUS_ACTIVITY",  # 의심스러운 활동
        "UNAUTHORIZED_ACCESS",  # 무단 접근 시도
    }

    # 경고 알림 대상 이벤트 (WARNING)
    WARNING_EVENTS = {
        "LOGIN_FAILED",  # 로그인 실패
        "TOKEN_INVALID",  # 유효하지 않은 토큰
        "RATE_LIMIT_EXCEEDED",  # Rate limit 초과
        "PERMISSION_DENIED",  # 권한 부족
    }

    # 정보성 알림 대상 이벤트 (INFO)
    INFO_EVENTS = {
        "LOGIN_SUCCESS",  # 로그인 성공 (관리자만)
        "USER_REGISTERED",  # 신규 사용자 등록
        "ACCOUNT_UNLOCKED",  # 계정 잠금 해제
    }

    @classmethod
    def get_alert_level(cls, event_type: str) -> Optional[str]:
        """이벤트 타입에 따른 알림 레벨 반환"""
        if event_type in cls.CRITICAL_EVENTS:
            return AlertLevel.CRITICAL
        elif event_type in cls.WARNING_EVENTS:
            return AlertLevel.WARNING
        elif event_type in cls.INFO_EVENTS:
            return AlertLevel.INFO
        return None

    @classmethod
    def should_alert(cls, event_type: str) -> bool:
        """이벤트가 알림 대상인지 확인"""
        return event_type in (cls.CRITICAL_EVENTS | cls.WARNING_EVENTS | cls.INFO_EVENTS)


class AlertManager:
    """실시간 알림 관리자

    WebSocket 연결을 관리하고 보안 이벤트를 실시간으로 전송
    """

    def __init__(self):
        # 연결된 WebSocket 클라이언트 (관리자 세션들)
        self.active_connections: Set[WebSocket] = set()

        # 알림 통계
        self.stats = {
            "total_alerts": 0,
            "critical_alerts": 0,
            "warning_alerts": 0,
            "info_alerts": 0,
            "connected_admins": 0
        }

    async def connect(self, websocket: WebSocket):
        """WebSocket 연결 수락"""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.stats["connected_admins"] = len(self.active_connections)

        logger.info(f"✅ Admin WebSocket connected. Total: {len(self.active_connections)}")

        # 연결 확인 메시지 전송
        await self.send_to_client(websocket, {
            "type": "connection",
            "message": "실시간 알림 연결됨",
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "stats": self.stats
        })

    async def disconnect(self, websocket: WebSocket):
        """WebSocket 연결 해제"""
        self.active_connections.discard(websocket)
        self.stats["connected_admins"] = len(self.active_connections)
        logger.info(f"❌ Admin WebSocket disconnected. Remaining: {len(self.active_connections)}")

    async def send_to_client(self, websocket: WebSocket, data: Dict[str, Any]):
        """특정 클라이언트에게 메시지 전송"""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"Failed to send to client: {e}")
            await self.disconnect(websocket)

    async def broadcast(self, data: Dict[str, Any]):
        """모든 연결된 클라이언트에게 브로드캐스트"""
        if not self.active_connections:
            return

        disconnected = set()

        for websocket in self.active_connections:
            try:
                await websocket.send_json(data)
            except Exception as e:
                logger.error(f"Failed to broadcast to client: {e}")
                disconnected.add(websocket)

        # 실패한 연결 정리
        for websocket in disconnected:
            await self.disconnect(websocket)

    async def send_alert(self, event_data: Dict[str, Any]):
        """보안 이벤트를 알림으로 전송

        Args:
            event_data: 보안 이벤트 데이터
        """
        event_type = event_data.get("event_type", "")

        # 알림 대상 이벤트인지 확인
        if not AlertRule.should_alert(event_type):
            return

        # 알림 레벨 결정
        alert_level = AlertRule.get_alert_level(event_type)

        # 알림 데이터 구성
        alert_data = {
            "type": "security_alert",
            "level": alert_level,
            "event_type": event_type,
            "timestamp": event_data.get("timestamp", datetime.utcnow().isoformat() + 'Z'),
            "user_id": event_data.get("user_id", "unknown"),
            "ip_address": event_data.get("ip_address", "unknown"),
            "message": event_data.get("message", ""),
            "details": {
                "reason": event_data.get("reason"),
                "attempts": event_data.get("attempts"),
                "resource": event_data.get("resource"),
                "email": event_data.get("email")
            }
        }

        # 통계 업데이트
        self.stats["total_alerts"] += 1
        if alert_level == AlertLevel.CRITICAL:
            self.stats["critical_alerts"] += 1
        elif alert_level == AlertLevel.WARNING:
            self.stats["warning_alerts"] += 1
        elif alert_level == AlertLevel.INFO:
            self.stats["info_alerts"] += 1

        # 브로드캐스트
        await self.broadcast(alert_data)

        logger.info(f"🚨 Alert broadcasted: {alert_level.upper()} - {event_type}")

    async def send_stats(self):
        """현재 알림 통계 전송"""
        stats_data = {
            "type": "stats_update",
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "stats": self.stats
        }
        await self.broadcast(stats_data)

    def get_stats(self) -> Dict[str, int]:
        """알림 통계 반환"""
        return self.stats.copy()


# 전역 AlertManager 인스턴스
alert_manager = AlertManager()
