"""
Scheduler Service

Background schedulers for maintenance tasks:
- Audit log cleanup (daily at 3 AM)
- Redis backup (configurable interval: hourly/daily/weekly)
"""

import json
import shutil
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import logging

from ..security_validators import SubprocessValidator

logger = logging.getLogger(__name__)

# Global dependencies (injected from web_server.py)
cache_manager = None
audit_logger = None


def inject_dependencies(cache_mgr, audit_log):
    """
    Inject dependencies from web_server.py

    Args:
        cache_mgr: Cache manager instance with Redis client
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
                logger.success(f"✅ Audit log cleanup completed: {deleted_count} logs deleted")
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
            # Redis에서 백업 스케줄 확인
            redis_client = cache_manager.redis
            schedule_data = redis_client.get("backup:schedule")

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

                    # 백업 실행
                    try:
                        logger.info(f"🔄 Executing scheduled backup (interval: {interval})")

                        # 백업 파일명 생성
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"dump_auto_{timestamp}.rdb"

                        # Redis BGSAVE 명령 실행
                        redis_client.bgsave()

                        # BGSAVE 완료 대기 (최대 60초)
                        for _ in range(60):
                            await asyncio.sleep(1)
                            info = redis_client.info("persistence")
                            if info.get("rdb_bgsave_in_progress") == 0:
                                break

                        # dump.rdb 파일을 백업 디렉토리로 복사
                        backup_dir = Path("backups")
                        backup_dir.mkdir(exist_ok=True)
                        backup_path = backup_dir / filename

                        # Get Redis data directory and filename
                        redis_config = redis_client.config_get("dir")
                        redis_dir = redis_config.get("dir", "/data")
                        redis_dbfilename = redis_client.config_get("dbfilename").get("dbfilename", "dump.rdb")

                        # Check if Redis is running in Docker
                        docker_container = None
                        try:
                            # Check if Redis container exists
                            result = subprocess.run(
                                ["docker", "ps", "--filter", "name=chatbot_redis", "--format", "{{.Names}}"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                # 컨테이너 이름 검증 및 정제
                                container_name = result.stdout.strip()
                                sanitized_name = SubprocessValidator.sanitize_for_shell(container_name)
                                is_valid, error = SubprocessValidator.validate_docker_container_name(sanitized_name)
                                if is_valid:
                                    docker_container = sanitized_name
                                    logger.debug(f"📦 Detected Redis in Docker: {docker_container}")
                                else:
                                    logger.error(f"❌ Invalid Docker container name: {error}")
                        except Exception as e:
                            logger.debug(f"Docker check skipped: {e}")

                        # Copy dump file from Docker or local filesystem
                        backup_success = False
                        if docker_container:
                            # Copy from Docker container
                            # 경로 검증
                            is_dir_valid, dir_error = SubprocessValidator.validate_path_for_subprocess(redis_dir)
                            is_file_valid, file_error = SubprocessValidator.validate_path_for_subprocess(redis_dbfilename)
                            if not is_dir_valid or not is_file_valid:
                                logger.error(f"❌ Invalid Redis path: {dir_error or file_error}")
                            else:
                                source_path = f"{redis_dir}/{redis_dbfilename}"
                                docker_source = f"{docker_container}:{source_path}"

                                try:
                                    result = subprocess.run(
                                        ["docker", "cp", docker_source, str(backup_path)],
                                        capture_output=True,
                                        text=True,
                                        timeout=30
                                    )

                                    if result.returncode == 0:
                                        logger.success(f"✅ Scheduled backup completed: {filename} (from Docker: {docker_source})")
                                        backup_success = True
                                    else:
                                        logger.error(f"❌ Docker copy failed: {result.stderr}")

                                except Exception as e:
                                    logger.error(f"❌ Docker copy error: {e}")
                        else:
                            # Copy from local filesystem
                            source_dump = Path(redis_dir) / redis_dbfilename
                            if source_dump.exists():
                                shutil.copy2(source_dump, backup_path)
                                logger.success(f"✅ Scheduled backup completed: {filename} (from {source_dump})")
                                backup_success = True
                            else:
                                logger.warning(f"⚠️ Redis dump file not found at: {source_dump}")

                        if not backup_success:
                            logger.error("❌ Scheduled backup failed: Could not copy dump file")

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
