"""
Audit Logger - 사용자 활동 기록 및 추적
User activity tracking and audit logging system
"""
import json
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta, timezone
from enum import Enum
from loguru import logger


class AuditAction(str, Enum):
    """감사 로그 작업 유형"""
    # 인증
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    REGISTER = "register"
    PASSWORD_CHANGE = "password_change"

    # 문서 관리
    DOCUMENT_UPLOAD = "document_upload"
    DOCUMENT_DELETE = "document_delete"
    DOCUMENT_VIEW = "document_view"
    DOCUMENT_DOWNLOAD = "document_download"
    VIRUS_SCAN = "virus_scan"  # 수동 바이러스 검사
    VIRUS_SCAN_AUTO = "virus_scan_auto"  # 업로드 시 자동 바이러스 검사

    # 채팅/질의
    CHAT_QUERY = "chat_query"
    CHAT_RESPONSE = "chat_response"

    # 그룹 관리
    GROUP_CREATE = "group_create"
    GROUP_UPDATE = "group_update"
    GROUP_DELETE = "group_delete"
    GROUP_ADD_DOCUMENT = "group_add_document"
    GROUP_REMOVE_DOCUMENT = "group_remove_document"

    # 설정
    SETTINGS_VIEW = "settings_view"
    SETTINGS_UPDATE = "settings_update"

    # 캐시
    CACHE_CLEAR = "cache_clear"
    CACHE_VIEW = "cache_view"

    # 관리자
    ADMIN_USER_CREATE = "admin_user_create"
    ADMIN_USER_UPDATE = "admin_user_update"
    ADMIN_USER_DELETE = "admin_user_delete"
    ADMIN_ROLE_CHANGE = "admin_role_change"
    ADMIN_AUDIT_VIEW = "admin_audit_view"

    # 시스템
    SYSTEM_HEALTH_CHECK = "system_health_check"
    SYSTEM_REINDEX = "system_reindex"


class AuditLogger:
    """감사 로그 시스템"""

    def __init__(self, redis_client, retention_days: int = 90):
        """
        Args:
            redis_client: Redis client instance
            retention_days: 로그 보관 기간 (일)
        """
        self.redis = redis_client
        self.retention_days = retention_days

        # Redis keys
        self.audit_prefix = "audit:log"
        self.user_activity_prefix = "audit:user"
        self.username_index_prefix = "audit:username"  # username 인덱스 추가
        self.action_index_prefix = "audit:action"
        self.daily_index_prefix = "audit:daily"

        logger.info(f"AuditLogger initialized (retention={retention_days} days)")

    def log(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> str:
        """
        감사 로그 기록

        Args:
            action: 작업 유형
            user_id: 사용자 ID
            username: 사용자 이름
            ip_address: IP 주소
            user_agent: User-Agent
            resource: 대상 리소스 (문서명, 설정명 등)
            details: 추가 상세 정보
            success: 성공 여부
            error_message: 오류 메시지 (실패 시)

        Returns:
            로그 ID
        """
        try:
            # 로그 ID 생성 (타임스탬프 + 카운터)
            timestamp = int(time.time() * 1000)  # milliseconds
            log_id = f"{timestamp}:{self.redis.incr('audit:counter')}"

            # KST 변환
            kst_time = datetime.now(timezone.utc) + timedelta(hours=9)

            # 로그 데이터 구성
            log_entry = {
                "log_id": log_id,
                "timestamp": timestamp,
                "datetime": kst_time.isoformat(),
                "action": action.value,
                "user_id": user_id,
                "username": username or "anonymous",
                "ip_address": ip_address or "unknown",
                "user_agent": user_agent,
                "resource": resource,
                "details": details or {},
                "success": success,
                "error_message": error_message
            }

            # Redis에 저장
            log_key = f"{self.audit_prefix}:{log_id}"

            # 만료 시간 설정 (보관 기간)
            ttl = self.retention_days * 24 * 3600

            self.redis.setex(
                log_key,
                ttl,
                json.dumps(log_entry, ensure_ascii=False)
            )

            # 인덱싱 (빠른 조회용)
            today = kst_time.strftime("%Y-%m-%d")

            # 1. 사용자별 인덱스 (user_id)
            if user_id:
                user_key = f"{self.user_activity_prefix}:{user_id}"
                self.redis.zadd(user_key, {log_id: timestamp})
                self.redis.expire(user_key, ttl)

            # 2. 사용자명별 인덱스 (username) - 효율적인 username 필터링용
            if username:
                username_key = f"{self.username_index_prefix}:{username.lower()}"
                self.redis.zadd(username_key, {log_id: timestamp})
                self.redis.expire(username_key, ttl)

            # 3. 작업별 인덱스
            action_key = f"{self.action_index_prefix}:{action.value}"
            self.redis.zadd(action_key, {log_id: timestamp})
            self.redis.expire(action_key, ttl)

            # 4. 일별 인덱스
            daily_key = f"{self.daily_index_prefix}:{today}"
            self.redis.zadd(daily_key, {log_id: timestamp})
            self.redis.expire(daily_key, ttl)

            # 통계 업데이트
            self._update_stats(action, success, kst_time)

            logger.debug(
                f"Audit log: {action.value} by {username or 'anonymous'} "
                f"(success={success}, resource={resource})"
            )

            return log_id

        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            return ""

    def _update_stats(self, action: AuditAction, success: bool, kst_time: datetime):
        """감사 로그 통계 업데이트"""
        try:
            today = kst_time.strftime("%Y-%m-%d")

            # 일별 통계
            stats_key = f"audit:stats:{today}"
            self.redis.hincrby(stats_key, f"total", 1)
            self.redis.hincrby(stats_key, f"action:{action.value}", 1)

            if success:
                self.redis.hincrby(stats_key, "success", 1)
            else:
                self.redis.hincrby(stats_key, "failed", 1)

            # 7일간 보관
            self.redis.expire(stats_key, 7 * 24 * 3600)

        except Exception as e:
            logger.error(f"Failed to update audit stats: {e}")

    def get_logs(
        self,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        action: Optional[AuditAction] = None,
        start_date: Optional[str] = None,  # YYYY-MM-DD
        end_date: Optional[str] = None,    # YYYY-MM-DD
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        감사 로그 조회

        Args:
            user_id: 사용자 ID 필터
            username: 사용자명 필터 (정확히 일치)
            action: 작업 유형 필터
            start_date: 시작 날짜
            end_date: 종료 날짜
            limit: 최대 반환 개수
            offset: 오프셋 (페이지네이션)

        Returns:
            로그 목록
        """
        try:
            # 인덱스 키 결정 (우선순위: user_id > username > action > daily)
            if user_id:
                index_key = f"{self.user_activity_prefix}:{user_id}"
            elif username:
                index_key = f"{self.username_index_prefix}:{username.lower()}"
            elif action:
                index_key = f"{self.action_index_prefix}:{action.value}"
            else:
                # 기본: 오늘 날짜
                if not end_date:
                    end_date = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
                index_key = f"{self.daily_index_prefix}:{end_date}"

            # 시간 범위 설정
            if start_date:
                start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            else:
                start_ts = 0

            if end_date:
                end_ts = int((datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).timestamp() * 1000)
            else:
                end_ts = int(time.time() * 1000)

            # 로그 ID 조회 (최신순)
            log_ids = self.redis.zrevrangebyscore(
                index_key,
                max=end_ts,
                min=start_ts,
                start=offset,
                num=limit
            )

            if not log_ids:
                return []

            # 로그 데이터 배치 조회 (Pipeline 사용)
            pipe = self.redis.pipeline()
            for log_id in log_ids:
                log_id_str = log_id.decode() if isinstance(log_id, bytes) else log_id
                log_key = f"{self.audit_prefix}:{log_id_str}"
                pipe.get(log_key)

            results = pipe.execute()

            logs = []
            for log_data in results:
                if log_data:
                    logs.append(json.loads(log_data))

            return logs

        except Exception as e:
            logger.error(f"Failed to get audit logs: {e}")
            return []

    def get_user_activity(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """특정 사용자의 최근 활동 조회"""
        return self.get_logs(user_id=user_id, limit=limit)

    def get_stats(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        감사 로그 통계 조회

        Args:
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)

        Returns:
            통계 데이터
        """
        try:
            kst_now = datetime.now(timezone.utc) + timedelta(hours=9)

            if not end_date:
                end_date = kst_now.strftime("%Y-%m-%d")

            if not start_date:
                start_date = (kst_now - timedelta(days=7)).strftime("%Y-%m-%d")

            # 날짜 범위 생성
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            daily_stats = {}
            current_dt = start_dt

            while current_dt <= end_dt:
                date_str = current_dt.strftime("%Y-%m-%d")
                stats_key = f"audit:stats:{date_str}"

                stats_data = self.redis.hgetall(stats_key)

                if stats_data:
                    daily_stats[date_str] = {
                        k.decode(): int(v.decode())
                        for k, v in stats_data.items()
                    }
                else:
                    daily_stats[date_str] = {"total": 0, "success": 0, "failed": 0}

                current_dt += timedelta(days=1)

            # 전체 통계 계산
            total_logs = sum(day.get("total", 0) for day in daily_stats.values())
            total_success = sum(day.get("success", 0) for day in daily_stats.values())
            total_failed = sum(day.get("failed", 0) for day in daily_stats.values())

            return {
                "period": {
                    "start": start_date,
                    "end": end_date
                },
                "summary": {
                    "total_logs": total_logs,
                    "successful": total_success,
                    "failed": total_failed,
                    "success_rate": round(total_success / total_logs * 100, 2) if total_logs > 0 else 0
                },
                "daily": daily_stats
            }

        except Exception as e:
            logger.error(f"Failed to get audit stats: {e}")
            return {
                "period": {"start": start_date, "end": end_date},
                "summary": {"total_logs": 0, "successful": 0, "failed": 0, "success_rate": 0},
                "daily": {}
            }

    def cleanup_old_logs(self):
        """오래된 로그 정리 (수동 실행용)"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            cutoff_ts = int(cutoff_date.timestamp() * 1000)

            # 인덱스에서 오래된 항목 제거
            # (실제 로그는 TTL로 자동 삭제됨)
            deleted_count = 0

            # 작업별 인덱스 정리
            for action in AuditAction:
                action_key = f"{self.action_index_prefix}:{action.value}"
                deleted = self.redis.zremrangebyscore(action_key, 0, cutoff_ts)
                deleted_count += deleted

            logger.info(f"Cleaned up {deleted_count} old audit log index entries")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
            return 0
