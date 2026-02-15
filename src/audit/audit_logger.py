"""
Audit Logger - 사용자 활동 기록 및 추적
User activity tracking and audit logging system

PostgreSQL 기반 저장.
"""
import uuid
import json
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta, timezone
from enum import Enum
from loguru import logger

from sqlalchemy import select, func, delete, case

from ..database.connection import SyncSessionFactory
from ..database.models.audit_log import AuditLog


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
    """감사 로그 시스템 (PostgreSQL 기반)"""

    def __init__(self, retention_days: int = 90):
        """
        Args:
            retention_days: 로그 보관 기간 (일)
        """
        self.retention_days = retention_days
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

        Returns:
            로그 ID (UUID string)
        """
        try:
            log_id = uuid.uuid4()

            full_details = dict(details) if details else {}
            if error_message:
                full_details["error_message"] = error_message

            with SyncSessionFactory() as db:
                entry = AuditLog(
                    id=log_id,
                    user_id=user_id,
                    username=username or "anonymous",
                    action=action.value,
                    resource_type=resource,
                    details=full_details,
                    ip_address=ip_address or "unknown",
                    user_agent=user_agent,
                    status="success" if success else "failed",
                )
                db.add(entry)
                db.commit()

            logger.debug(
                f"Audit log: {action.value} by {username or 'anonymous'} "
                f"(success={success}, resource={resource})"
            )

            return str(log_id)

        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            return ""

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
        """감사 로그 조회"""
        try:
            with SyncSessionFactory() as db:
                stmt = select(AuditLog)

                if user_id:
                    stmt = stmt.where(AuditLog.user_id == user_id)
                if username:
                    stmt = stmt.where(func.lower(AuditLog.username) == username.lower())
                if action:
                    stmt = stmt.where(AuditLog.action == action.value)
                if start_date:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    stmt = stmt.where(AuditLog.created_at >= start_dt)
                if end_date:
                    end_dt = (
                        datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    ).replace(tzinfo=timezone.utc)
                    stmt = stmt.where(AuditLog.created_at < end_dt)

                stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
                rows = db.execute(stmt).scalars().all()

            logs = []
            for row in rows:
                created = row.created_at
                kst_time = created + timedelta(hours=9) if created else None
                logs.append({
                    "log_id": str(row.id),
                    "timestamp": int(created.timestamp() * 1000) if created else 0,
                    "datetime": kst_time.isoformat() if kst_time else "",
                    "action": row.action,
                    "user_id": row.user_id,
                    "username": row.username or "anonymous",
                    "ip_address": row.ip_address or "unknown",
                    "user_agent": row.user_agent,
                    "resource": row.resource_type,
                    "details": row.details or {},
                    "success": row.status == "success",
                    "error_message": (row.details or {}).get("error_message"),
                })

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
        """감사 로그 통계 조회"""
        try:
            kst_now = datetime.now(timezone.utc) + timedelta(hours=9)

            if not end_date:
                end_date = kst_now.strftime("%Y-%m-%d")
            if not start_date:
                start_date = (kst_now - timedelta(days=7)).strftime("%Y-%m-%d")

            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt_excl = (
                datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            ).replace(tzinfo=timezone.utc)

            # Initialize all dates in range
            daily_stats = {}
            current_d = datetime.strptime(start_date, "%Y-%m-%d")
            end_d = datetime.strptime(end_date, "%Y-%m-%d")
            while current_d <= end_d:
                daily_stats[current_d.strftime("%Y-%m-%d")] = {
                    "total": 0, "success": 0, "failed": 0
                }
                current_d += timedelta(days=1)

            with SyncSessionFactory() as db:
                date_col = func.date(AuditLog.created_at)

                # Daily totals with success/failed breakdown
                daily_q = (
                    select(
                        date_col.label("log_date"),
                        func.count().label("total"),
                        func.sum(
                            case((AuditLog.status == "success", 1), else_=0)
                        ).label("success_cnt"),
                        func.sum(
                            case((AuditLog.status == "failed", 1), else_=0)
                        ).label("failed_cnt"),
                    )
                    .where(AuditLog.created_at >= start_dt)
                    .where(AuditLog.created_at < end_dt_excl)
                    .group_by(date_col)
                )
                daily_rows = db.execute(daily_q).all()

                # Action counts per day
                action_q = (
                    select(
                        date_col.label("log_date"),
                        AuditLog.action,
                        func.count().label("cnt"),
                    )
                    .where(AuditLog.created_at >= start_dt)
                    .where(AuditLog.created_at < end_dt_excl)
                    .group_by(date_col, AuditLog.action)
                )
                action_rows = db.execute(action_q).all()

            for row in daily_rows:
                ds = str(row.log_date)
                if ds in daily_stats:
                    daily_stats[ds] = {
                        "total": row.total,
                        "success": int(row.success_cnt or 0),
                        "failed": int(row.failed_cnt or 0),
                    }

            for row in action_rows:
                ds = str(row.log_date)
                if ds in daily_stats:
                    daily_stats[ds][f"action:{row.action}"] = row.cnt

            total_logs = sum(d.get("total", 0) for d in daily_stats.values())
            total_success = sum(d.get("success", 0) for d in daily_stats.values())
            total_failed = sum(d.get("failed", 0) for d in daily_stats.values())

            return {
                "period": {"start": start_date, "end": end_date},
                "summary": {
                    "total_logs": total_logs,
                    "successful": total_success,
                    "failed": total_failed,
                    "success_rate": round(
                        total_success / total_logs * 100, 2
                    ) if total_logs > 0 else 0
                },
                "daily": daily_stats,
            }

        except Exception as e:
            logger.error(f"Failed to get audit stats: {e}")
            return {
                "period": {"start": start_date, "end": end_date},
                "summary": {
                    "total_logs": 0, "successful": 0,
                    "failed": 0, "success_rate": 0
                },
                "daily": {},
            }

    def cleanup_old_logs(self) -> int:
        """오래된 로그 정리"""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

            with SyncSessionFactory() as db:
                stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
                result = db.execute(stmt)
                deleted_count = result.rowcount
                db.commit()

            logger.info(f"Cleaned up {deleted_count} old audit log entries")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
            return 0
