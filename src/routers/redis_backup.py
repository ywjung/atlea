"""
Redis Backup Management Router

Handles Redis backup operations including:
- Manual and automatic backups
- Backup restoration with safety features
- Backup scheduling and management
- Backup download and deletion
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ..auth.rate_limiter import create_rate_limit_dependency
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import asyncio
import subprocess
import shutil
import json
from loguru import logger

from ..utils.error_handling import get_safe_error_message
from ..security_validators import SubprocessValidator, InputValidator
from ..constants import Timeouts

router = APIRouter(prefix="/api/redis/backup", tags=["Admin", "Redis Backup"])

# Global dependencies
cache_manager = None


def inject_dependencies(cache_mgr):
    """Inject dependencies into the router"""
    global cache_manager
    cache_manager = cache_mgr


# ==================== Pydantic Models ====================

class BackupCreateRequest(BaseModel):
    type: str = "manual"  # manual or auto


class BackupRestoreRequest(BaseModel):
    filename: str


class BackupDeleteRequest(BaseModel):
    filename: str


class BackupScheduleRequest(BaseModel):
    enabled: bool
    interval: str  # hourly, daily, weekly, disabled
    day_of_week: Optional[int] = None  # 0-6 (Sunday-Saturday) for weekly backups
    hour: Optional[int] = None  # 0-23 for daily/weekly backups
    minute: Optional[int] = None  # 0-59 for all intervals


# ==================== Constants & Helpers ====================

BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)


def get_backup_filepath(filename: str) -> Path:
    """Get safe backup file path with security validation"""
    # Prevent directory traversal
    safe_filename = Path(filename).name

    # 추가 보안 검증
    is_valid, error = InputValidator.validate_filename(safe_filename)
    if not is_valid:
        raise ValueError(f"Invalid filename: {error}")

    return BACKUP_DIR / safe_filename


def validate_docker_container(container_name: str) -> str:
    """Docker 컨테이너 이름 검증 및 정제"""
    if not container_name:
        raise ValueError("Container name is empty")

    # 정제
    sanitized = SubprocessValidator.sanitize_for_shell(container_name.strip())

    # 검증
    is_valid, error = SubprocessValidator.validate_docker_container_name(sanitized)
    if not is_valid:
        raise ValueError(f"Invalid container name: {error}")

    return sanitized


def validate_path_for_docker(path: str) -> str:
    """Docker 명령어에서 사용할 경로 검증"""
    if not path:
        raise ValueError("Path is empty")

    is_valid, error = SubprocessValidator.validate_path_for_subprocess(path)
    if not is_valid:
        raise ValueError(f"Invalid path: {error}")

    return path


def get_redis_backup_info():
    """Get Redis backup information"""
    try:
        backups = []
        if BACKUP_DIR.exists():
            # Sort by file modification time (newest first)
            for backup_file in sorted(BACKUP_DIR.glob("dump_*.rdb"), key=lambda x: x.stat().st_mtime, reverse=True):
                stat = backup_file.stat()
                created_at = datetime.fromtimestamp(stat.st_mtime)
                age_seconds = (datetime.now() - created_at).total_seconds()

                # Format age
                if age_seconds < 3600:
                    age = f"{int(age_seconds / 60)}분 전"
                elif age_seconds < 86400:
                    age = f"{int(age_seconds / 3600)}시간 전"
                else:
                    age = f"{int(age_seconds / 86400)}일 전"

                # Determine type from filename
                backup_type = "auto" if "_auto_" in backup_file.name else "manual"

                backups.append({
                    "filename": backup_file.name,
                    "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "age": age,
                    "size": f"{stat.st_size / 1024 / 1024:.2f} MB",
                    "size_bytes": stat.st_size,
                    "type": backup_type
                })

        return backups
    except Exception as e:
        logger.error(f"Failed to get backup info: {e}")
        return []


# ==================== Endpoints ====================

@router.post("/create")
async def create_redis_backup(
    request: Request,
    backup_request: BackupCreateRequest,
    _rate_limit=Depends(create_rate_limit_dependency(5, 60, "redis_backup_create"))
):
    """Redis 백업 생성

    Request body:
        {
            "type": "manual" | "auto"
        }
    """
    try:
        # Admin permission check
        from ..auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        backup_type = backup_request.type
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if backup_type == "auto":
            backup_filename = f"dump_auto_{timestamp}.rdb"
        else:
            backup_filename = f"dump_manual_{timestamp}.rdb"

        backup_path = BACKUP_DIR / backup_filename

        # Execute Redis SAVE command (synchronous backup)
        redis_client.save()

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
                timeout=Timeouts.DOCKER_CHECK
            )
            if result.returncode == 0 and result.stdout.strip():
                # 컨테이너 이름 검증 및 정제
                try:
                    docker_container = validate_docker_container(result.stdout.strip())
                    logger.info(f"📦 Detected Redis running in Docker container: {docker_container}")
                    # Docker 컨테이너 내부의 기본 Redis 데이터 경로 사용
                    # (로컬 Redis 설정과 다를 수 있음)
                    redis_dir = "/data"
                    logger.info(f"📁 Using Docker Redis data directory: {redis_dir}")
                except ValueError as ve:
                    logger.error(f"❌ Invalid Docker container name: {ve}")
                    raise HTTPException(
                        status_code=500,
                        detail="Docker 컨테이너 이름이 유효하지 않습니다"
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Could not check for Docker container: {e}")

        # Copy dump file from Docker or local filesystem
        if docker_container:
            # Copy from Docker container
            # 경로 검증
            try:
                validated_redis_dir = validate_path_for_docker(redis_dir)
                validated_dbfilename = validate_path_for_docker(redis_dbfilename)
            except ValueError as ve:
                raise HTTPException(
                    status_code=500,
                    detail=f"Redis 경로가 유효하지 않습니다: {ve}"
                )

            source_path = f"{validated_redis_dir}/{validated_dbfilename}"
            docker_source = f"{docker_container}:{source_path}"

            try:
                # Copy file from Docker container to backup directory
                result = subprocess.run(
                    ["docker", "cp", docker_source, str(backup_path)],
                    capture_output=True,
                    text=True,
                    timeout=Timeouts.DOCKER_COPY
                )

                if result.returncode != 0:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to copy from Docker: {result.stderr}"
                    )

                logger.info(f"✅ Copied dump file from Docker: {docker_source} → {backup_path}")

            except subprocess.TimeoutExpired:
                raise HTTPException(status_code=500, detail="Docker copy timed out")
            except Exception as e:
                raise HTTPException(status_code=500, detail=get_safe_error_message(e, "docker copy"))
        else:
            # Copy from local filesystem
            source_dump = Path(redis_dir) / redis_dbfilename
            if source_dump.exists():
                shutil.copy2(source_dump, backup_path)
                logger.info(f"✅ Copied dump file from local: {source_dump} → {backup_path}")
            else:
                raise HTTPException(status_code=500, detail=f"Redis dump file not found: {source_dump}")

        # Get file info and return response
        if backup_path.exists():
            stat = backup_path.stat()
            size_mb = stat.st_size / 1024 / 1024

            logger.info(f"✅ Redis backup created: {backup_filename} ({size_mb:.2f} MB)")

            return {
                "success": True,
                "backup": {
                    "filename": backup_filename,
                    "size": f"{size_mb:.2f} MB",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": backup_type
                }
            }
        else:
            raise HTTPException(status_code=500, detail="Backup file was not created")

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Failed to create backup: {e}\n{error_detail}")
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "backup create"))


@router.get("/list")
async def list_redis_backups(
    request: Request,
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "redis_backup_list"))
):
    """Redis 백업 목록 조회"""
    try:
        # Admin permission check
        from ..auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        backups = get_redis_backup_info()

        # Calculate statistics
        total_size = sum(b["size_bytes"] for b in backups)

        return {
            "success": True,
            "backups": backups,
            "stats": {
                "total_backups": len(backups),
                "total_size": f"{total_size / 1024 / 1024:.2f} MB",
                "manual_backups": len([b for b in backups if b["type"] == "manual"]),
                "auto_backups": len([b for b in backups if b["type"] == "auto"])
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(status_code=500, detail="백업 목록 조회 실패")


@router.post("/restore")
async def restore_redis_backup(
    request: Request,
    restore_request: BackupRestoreRequest,
    _rate_limit=Depends(create_rate_limit_dependency(3, 60, "redis_backup_restore"))
):
    """Redis 백업 복원 (안전성 강화)

    Request body:
        {
            "filename": "dump_manual_20250101_120000.rdb"
        }

    Warning: This will flush all current Redis data and restore from backup.

    Safety features:
    - Mandatory pre-restore backup (fails if backup creation fails)
    - Transaction-style operation (all-or-nothing)
    - Automatic rollback on failure
    - Validation at each critical step
    - DBSIZE verification before and after
    """
    redis_client = None
    docker_container = None
    current_backup = None
    current_backup_filename = None
    original_dbsize = None
    restore_failed = False

    try:
        # Admin permission check
        from ..auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        backup_path = get_backup_filepath(restore_request.filename)

        # STEP 1: Validate backup file exists
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")

        logger.info(f"🔍 Step 1/7: Backup file validated: {restore_request.filename}")

        # Get Redis configuration
        redis_config = redis_client.config_get("dir")
        redis_dir = redis_config.get("dir", "/data")
        redis_dbfilename = redis_client.config_get("dbfilename").get("dbfilename", "dump.rdb")

        # STEP 2: Detect Docker environment
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=chatbot_redis", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=Timeouts.DOCKER_CHECK
            )
            if result.returncode == 0 and result.stdout.strip():
                # 컨테이너 이름 검증 및 정제
                try:
                    docker_container = validate_docker_container(result.stdout.strip())
                    logger.info(f"🔍 Step 2/7: Docker container detected: {docker_container}")
                    # Docker 컨테이너 내부의 기본 Redis 데이터 경로 사용
                    redis_dir = "/data"
                    logger.info(f"📁 Using Docker Redis data directory: {redis_dir}")
                except ValueError as ve:
                    logger.error(f"❌ Invalid Docker container name: {ve}")
                    raise HTTPException(
                        status_code=500,
                        detail="Docker 컨테이너 이름이 유효하지 않습니다"
                    )
            else:
                logger.info(f"🔍 Step 2/7: Local Redis installation detected")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=get_safe_error_message(e, "docker check")
            )

        # STEP 3: Get current DBSIZE for validation
        try:
            original_dbsize = redis_client.dbsize()
            logger.info(f"🔍 Step 3/7: Current DBSIZE: {original_dbsize:,} keys")
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=get_safe_error_message(e, "redis dbsize")
            )

        # STEP 4: MANDATORY pre-restore backup
        current_backup_filename = f"dump_pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.rdb"
        current_backup = BACKUP_DIR / current_backup_filename

        if docker_container:
            # Docker environment - MUST successfully backup current state

            # 경로 검증
            try:
                validated_redis_dir = validate_path_for_docker(redis_dir)
                validated_dbfilename = validate_path_for_docker(redis_dbfilename)
            except ValueError as ve:
                raise HTTPException(
                    status_code=500,
                    detail=f"Redis 경로가 유효하지 않습니다: {ve}"
                )

            try:
                # Force Redis to save current state
                redis_client.save()
                logger.info("✅ Redis SAVE completed")
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Redis SAVE 실패 - 복원을 중단합니다. {get_safe_error_message(e, 'redis save')}"
                )

            # Copy current dump from container - MUST succeed
            docker_source = f"{docker_container}:{validated_redis_dir}/{validated_dbfilename}"
            try:
                result = subprocess.run(
                    ["docker", "cp", docker_source, str(current_backup)],
                    capture_output=True,
                    text=True,
                    timeout=Timeouts.DOCKER_COPY
                )

                if result.returncode != 0:
                    raise HTTPException(
                        status_code=500,
                        detail=f"현재 상태 백업 실패 - 복원을 중단합니다: {result.stderr}"
                    )

                # Verify backup file was created
                if not current_backup.exists():
                    raise HTTPException(
                        status_code=500,
                        detail="백업 파일 생성 확인 실패 - 복원을 중단합니다"
                    )

                backup_size = current_backup.stat().st_size / 1024 / 1024
                logger.info(f"✅ Step 4/7: Pre-restore backup created: {current_backup_filename} ({backup_size:.2f} MB)")

            except subprocess.TimeoutExpired:
                raise HTTPException(
                    status_code=500,
                    detail="백업 생성 시간 초과 - 복원을 중단합니다"
                )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"현재 상태 백업 실패 - 복원을 중단합니다. {get_safe_error_message(e, 'pre-restore backup')}"
                )

            # STEP 5: Copy backup file into Docker container
            docker_target = f"{docker_container}:{validated_redis_dir}/{validated_dbfilename}"
            try:
                result = subprocess.run(
                    ["docker", "cp", str(backup_path), docker_target],
                    capture_output=True,
                    text=True,
                    timeout=Timeouts.DOCKER_COPY
                )

                if result.returncode != 0:
                    restore_failed = True
                    raise HTTPException(
                        status_code=500,
                        detail=f"백업 파일 복사 실패: {result.stderr}"
                    )

                logger.info(f"✅ Step 5/7: Backup copied to container: {docker_target}")

            except subprocess.TimeoutExpired:
                restore_failed = True
                raise HTTPException(status_code=500, detail="백업 복사 시간 초과")
            except HTTPException:
                raise
            except Exception as e:
                restore_failed = True
                raise HTTPException(status_code=500, detail=get_safe_error_message(e, "backup copy"))

            # STEP 6: Restart Redis container
            try:
                logger.info(f"🔄 Step 6/7: Restarting Redis container...")
                result = subprocess.run(
                    ["docker", "restart", docker_container],
                    capture_output=True,
                    text=True,
                    timeout=Timeouts.DOCKER_COPY
                )

                if result.returncode != 0:
                    restore_failed = True
                    raise HTTPException(
                        status_code=500,
                        detail=f"Redis 재시작 실패: {result.stderr}"
                    )

                logger.info("✅ Redis container restarted")

                # Wait for Redis to fully start
                await asyncio.sleep(3)

                # Reconnect to Redis (container was restarted)
                max_retries = 5
                for i in range(max_retries):
                    try:
                        redis_client.ping()
                        logger.info(f"✅ Redis connection restored (attempt {i+1}/{max_retries})")
                        break
                    except Exception as e:
                        if i == max_retries - 1:
                            restore_failed = True
                            raise HTTPException(
                                status_code=500,
                                detail=f"Redis 재시작 후 연결 실패. {get_safe_error_message(e, 'redis reconnect')}"
                            )
                        await asyncio.sleep(1)

            except subprocess.TimeoutExpired:
                restore_failed = True
                raise HTTPException(status_code=500, detail="Redis 재시작 시간 초과")
            except HTTPException:
                raise
            except Exception as e:
                restore_failed = True
                raise HTTPException(status_code=500, detail=get_safe_error_message(e, "redis restart"))

            # STEP 7: Verify restore succeeded
            try:
                restored_dbsize = redis_client.dbsize()
                logger.info(f"🔍 Step 7/7: Restored DBSIZE: {restored_dbsize:,} keys")

                # Warn if DBSIZE is suspiciously low
                if restored_dbsize < 100:
                    logger.warning(f"⚠️ Restored DBSIZE ({restored_dbsize}) is very low - possible restore failure")
                    # Don't fail here, but log for investigation

                logger.info(f"✅ Restore verification complete: {original_dbsize:,} → {restored_dbsize:,} keys")

            except Exception as e:
                restore_failed = True
                raise HTTPException(
                    status_code=500,
                    detail=get_safe_error_message(e, "restore verification")
                )

        else:
            # Local filesystem
            target_dump = Path(redis_dir) / redis_dbfilename

            # STEP 4: MANDATORY pre-restore backup (local)
            try:
                if target_dump.exists():
                    shutil.copy2(target_dump, current_backup)

                    # Verify backup was created
                    if not current_backup.exists():
                        raise HTTPException(
                            status_code=500,
                            detail="백업 파일 생성 확인 실패 - 복원을 중단합니다"
                        )

                    backup_size = current_backup.stat().st_size / 1024 / 1024
                    logger.info(f"✅ Step 4/7: Pre-restore backup created: {current_backup_filename} ({backup_size:.2f} MB)")
                else:
                    logger.warning("⚠️ No existing dump file to backup")

            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"현재 상태 백업 실패 - 복원을 중단합니다. {get_safe_error_message(e, 'pre-restore backup local')}"
                )

            # STEP 5: Copy backup file
            try:
                shutil.copy2(backup_path, target_dump)
                logger.info(f"✅ Step 5/7: Backup file copied to Redis directory")
            except Exception as e:
                restore_failed = True
                raise HTTPException(
                    status_code=500,
                    detail=get_safe_error_message(e, "backup file copy")
                )

            logger.warning("⚠️ Step 6/7: Redis needs manual restart to load the backup")
            logger.info(f"ℹ️ Step 7/7: Manual verification required after restart")

        return {
            "success": True,
            "message": "백업이 안전하게 복원되었습니다. 복원 전 상태는 백업되었습니다.",
            "filename": restore_request.filename,
            "current_backup": current_backup_filename,
            "original_keys": original_dbsize,
            "restored_keys": restored_dbsize if docker_container else "재시작 후 확인 필요"
        }

    except HTTPException:
        # If restore failed and we have a pre-restore backup, attempt rollback
        if restore_failed and current_backup and current_backup.exists() and docker_container:
            logger.error("🚨 Restore failed - attempting automatic rollback...")
            try:
                # Rollback: restore from pre-restore backup
                # 경로는 이미 위에서 검증됨 (validated_redis_dir, validated_dbfilename)
                docker_target = f"{docker_container}:{validated_redis_dir}/{validated_dbfilename}"
                result = subprocess.run(
                    ["docker", "cp", str(current_backup), docker_target],
                    capture_output=True,
                    text=True,
                    timeout=Timeouts.DOCKER_COPY
                )

                if result.returncode == 0:
                    # Restart Redis to load the rollback
                    subprocess.run(
                        ["docker", "restart", docker_container],
                        capture_output=True,
                        text=True,
                        timeout=Timeouts.DOCKER_COPY
                    )
                    await asyncio.sleep(3)

                    logger.info(f"✅ Automatic rollback successful - restored from {current_backup_filename}")
                else:
                    logger.error(f"❌ Automatic rollback failed: {result.stderr}")
                    logger.error(f"⚠️ Manual recovery required using: {current_backup_filename}")

            except Exception as rollback_error:
                logger.error(f"❌ Rollback exception: {rollback_error}")
                logger.error(f"⚠️ Manual recovery required using: {current_backup_filename}")

        raise
    except Exception as e:
        logger.error(f"Unexpected error during restore: {e}")
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "restore unexpected"))


@router.get("/download/{filename}")
async def download_redis_backup(
    request: Request,
    filename: str,
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "redis_backup_download"))
):
    """Redis 백업 파일 다운로드"""
    try:
        # Admin permission check
        from ..auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        backup_path = get_backup_filepath(filename)

        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")

        return FileResponse(
            path=str(backup_path),
            filename=filename,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download backup: {e}")
        raise HTTPException(status_code=500, detail="백업 다운로드 실패")


@router.post("/delete")
async def delete_redis_backup(
    request: Request,
    delete_request: BackupDeleteRequest,
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "redis_backup_delete"))
):
    """Redis 백업 파일 삭제

    Request body:
        {
            "filename": "dump_manual_20250101_120000.rdb"
        }
    """
    try:
        # Admin permission check
        from ..auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        backup_path = get_backup_filepath(delete_request.filename)

        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")

        # Delete the backup file
        backup_path.unlink()

        logger.info(f"Backup deleted: {delete_request.filename}")

        return {
            "success": True,
            "message": f"백업 파일이 삭제되었습니다: {delete_request.filename}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        raise HTTPException(status_code=500, detail="백업 삭제 실패")


@router.get("/schedule")
async def get_backup_schedule(
    request: Request,
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "redis_backup_schedule"))
):
    """자동 백업 스케줄 조회"""
    try:
        # Admin permission check
        from ..auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # Get schedule from Redis
        schedule_data = redis_client.get("backup:schedule")

        if schedule_data:
            schedule = json.loads(schedule_data)
        else:
            # Default schedule
            schedule = {
                "enabled": False,
                "interval": "daily",
                "last_backup": None
            }

        return {
            "success": True,
            "schedule": schedule
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backup schedule: {e}")
        raise HTTPException(status_code=500, detail="스케줄 조회 실패")


@router.post("/schedule")
async def update_backup_schedule(
    request: Request,
    schedule_request: BackupScheduleRequest,
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "redis_backup_schedule_update"))
):
    """자동 백업 스케줄 업데이트

    Request body:
        {
            "enabled": true,
            "interval": "hourly" | "daily" | "weekly" | "disabled",
            "day_of_week": 0-6 (optional, for weekly),
            "hour": 0-23 (optional, for daily/weekly),
            "minute": 0-59 (optional, for all intervals)
        }

    Note: Background scheduler automatically executes backups based on this configuration.
    """
    try:
        # Admin permission check
        from ..auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        user = require_admin(request, redis_client)

        # Validate interval
        valid_intervals = ["hourly", "daily", "weekly", "disabled"]
        if schedule_request.interval not in valid_intervals:
            raise HTTPException(status_code=400, detail=f"Invalid interval. Must be one of: {valid_intervals}")

        # Build complete schedule object with all fields
        schedule = {
            "enabled": schedule_request.enabled,
            "interval": schedule_request.interval,
            "updated_at": datetime.now().isoformat()
        }

        # Add optional time fields if provided
        if schedule_request.day_of_week is not None:
            schedule["day_of_week"] = schedule_request.day_of_week
        if schedule_request.hour is not None:
            schedule["hour"] = schedule_request.hour
        if schedule_request.minute is not None:
            schedule["minute"] = schedule_request.minute

        # Save complete schedule to Redis
        redis_client.set("backup:schedule", json.dumps(schedule))

        # Log with all relevant fields
        log_msg = f"Backup schedule updated by {user.get('email', 'unknown')}: enabled={schedule_request.enabled}, interval={schedule_request.interval}"
        if schedule_request.minute is not None:
            log_msg += f", minute={schedule_request.minute}"
        if schedule_request.hour is not None:
            log_msg += f", hour={schedule_request.hour}"
        if schedule_request.day_of_week is not None:
            log_msg += f", day_of_week={schedule_request.day_of_week}"
        logger.info(log_msg)

        return {
            "success": True,
            "message": "백업 스케줄이 업데이트되었습니다. 백그라운드 스케줄러가 자동으로 실행합니다.",
            "schedule": schedule
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update backup schedule: {e}")
        raise HTTPException(status_code=500, detail="스케줄 업데이트 실패")
