"""
Scheduler Service

Background schedulers for maintenance tasks:
- Audit log cleanup (daily at 3 AM)
- TTL cleanup (every 5 minutes for expired PG rows)
- PostgreSQL backup (configurable interval: hourly/daily/weekly)
"""

import json
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Global dependencies (injected from web_server.py)
cache_manager = None
audit_logger = None
_ttl_cleanup_task: Optional[asyncio.Task] = None


def inject_dependencies(cache_mgr, audit_log):
    """
    Inject dependencies from web_server.py

    Args:
        cache_mgr: Cache manager instance
        audit_log: Audit logger instance
    """
    global cache_manager, audit_logger
    cache_manager = cache_mgr
    audit_logger = audit_log



async def audit_cleanup_scheduler():
    """감사 로그 정리 스케줄러 - 매일 새벽 3시에 90일 이상 된 로그 삭제"""
    logger.info("🗑️ Audit log cleanup scheduler started")

    while True:
        try:
            # 현재 시간
            now = datetime.now()

            # 다음 실행 시간 계산 (다음날 새벽 3시)
            next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= next_run:
                # 이미 지났으면 다음날
                next_run += timedelta(days=1)

            # 대기 시간 계산
            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"📅 Next audit log cleanup scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds/3600:.1f} hours)")

            # 대기
            await asyncio.sleep(wait_seconds)

            # 정리 실행
            if audit_logger:
                logger.info("🗑️ Starting audit log cleanup...")
                deleted_count = audit_logger.cleanup_old_logs()
                logger.info(f"✅ Audit log cleanup completed: {deleted_count} logs deleted")
            else:
                logger.warning("⚠️ Audit logger not initialized, skipping cleanup")

        except asyncio.CancelledError:
            logger.info("🛑 Audit cleanup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Audit cleanup scheduler error: {e}")
            # 에러 발생 시 1시간 후 재시도
            await asyncio.sleep(3600)


async def backup_scheduler():
    """백그라운드 백업 스케줄러 - 설정된 간격에 따라 자동 백업 실행"""
    logger.info("🕐 Backup scheduler started")

    while True:
        try:
            # PostgreSQL에서 백업 스케줄 확인
            from .config_service import config_get_sync
            schedule_data = config_get_sync("backup:schedule")

            if schedule_data:
                schedule = json.loads(schedule_data)

                if schedule.get("enabled"):
                    interval = schedule.get("interval", "daily")
                    scheduled_minute = schedule.get("minute", 0)  # 기본값 0분

                    # 현재 시간
                    now = datetime.now()

                    # 다음 실행 시간 계산
                    if interval == "hourly":
                        # 매시 N분에 실행
                        next_run = now.replace(minute=scheduled_minute, second=0, microsecond=0)
                        if next_run <= now:
                            # 이미 지난 시간이면 다음 시간으로
                            next_run += timedelta(hours=1)
                    elif interval == "daily":
                        # 매일 N시 M분에 실행 (여기서는 간단히 24시간 후)
                        next_run = now + timedelta(days=1)
                        next_run = next_run.replace(minute=scheduled_minute, second=0, microsecond=0)
                    elif interval == "weekly":
                        # 매주 같은 요일 N시 M분에 실행
                        next_run = now + timedelta(weeks=1)
                        next_run = next_run.replace(minute=scheduled_minute, second=0, microsecond=0)
                    else:
                        next_run = now + timedelta(hours=1)

                    # 다음 실행까지 대기 시간 계산
                    wait_seconds = (next_run - now).total_seconds()

                    if wait_seconds > 0:
                        logger.info(f"⏰ Next backup scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S')} (in {int(wait_seconds)} seconds)")
                        await asyncio.sleep(wait_seconds)

                    # 백업 실행 (PostgreSQL pg_dump)
                    try:
                        logger.info(f"🔄 Executing scheduled backup (interval: {interval})")

                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_dir = Path("backups")
                        backup_dir.mkdir(exist_ok=True)
                        filename = f"pg_backup_{timestamp}.sql"
                        backup_path = backup_dir / filename

                        import subprocess
                        import os
                        pg_host = os.getenv("POSTGRES_HOST", "localhost")
                        pg_port = os.getenv("POSTGRES_PORT", "5432")
                        pg_user = os.getenv("POSTGRES_USER", "chatbot_user")
                        pg_db = os.getenv("POSTGRES_DB", "chatbot")
                        pg_password = os.getenv("POSTGRES_PASSWORD", "")

                        env = os.environ.copy()
                        if pg_password:
                            env["PGPASSWORD"] = pg_password

                        result = subprocess.run(
                            ["pg_dump", "-h", pg_host, "-p", pg_port, "-U", pg_user, pg_db],
                            capture_output=True, text=True, timeout=300, env=env
                        )
                        if result.returncode == 0:
                            backup_path.write_text(result.stdout)
                            logger.info(f"✅ Scheduled PG backup completed: {filename}")
                        else:
                            logger.error(f"❌ pg_dump failed: {result.stderr}")

                    except Exception as e:
                        logger.error(f"❌ Scheduled backup failed: {e}")

                    # 루프 계속 (다음 실행 시간은 루프 시작에서 다시 계산됨)
                else:
                    # 비활성화 상태면 1분마다 확인
                    await asyncio.sleep(60)
            else:
                # 스케줄 설정이 없으면 1분마다 확인
                await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("🛑 Backup scheduler stopped")
            break
        except Exception as e:
            logger.error(f"❌ Backup scheduler error: {e}")
            # 에러 발생 시 1분 후 재시도
            await asyncio.sleep(60)


def start_ttl_cleanup():
    """Start the TTL cleanup background task."""
    global _ttl_cleanup_task
    try:
        from .ttl_cleanup_service import ttl_cleanup_scheduler
        _ttl_cleanup_task = asyncio.create_task(ttl_cleanup_scheduler(300))
        logger.info("TTL cleanup scheduler registered (every 5 min)")
    except Exception as e:
        logger.error(f"Failed to start TTL cleanup scheduler: {e}")


def stop_ttl_cleanup():
    """Cancel the TTL cleanup background task."""
    global _ttl_cleanup_task
    if _ttl_cleanup_task and not _ttl_cleanup_task.done():
        _ttl_cleanup_task.cancel()
        logger.info("TTL cleanup scheduler stopped")
