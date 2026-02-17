"""
Database Backup Management Router

PostgreSQL backup management via pg_dump/psql.
"""

import os
import re
import subprocess
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ..auth.rate_limiter import create_rate_limit_dependency
from ..auth.middleware import get_current_active_user
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from loguru import logger


router = APIRouter(prefix="/api/db/backup", tags=["Admin", "Database Backup"])


# ==================== Pydantic Models ====================

class BackupCreateRequest(BaseModel):
    type: str = "manual"


class BackupRestoreRequest(BaseModel):
    filename: str


class BackupDeleteRequest(BaseModel):
    filename: str


class BackupScheduleRequest(BaseModel):
    enabled: bool
    interval: str
    day_of_week: Optional[int] = None
    hour: Optional[int] = None
    minute: Optional[int] = None


# ==================== Constants ====================

BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

_FILENAME_PATTERN = re.compile(r'^pg_backup_\d{8}_\d{6}(_auto)?\.sql$')


# ==================== Helpers ====================

def _parse_pg_conn() -> dict:
    """DATABASE_URL에서 pg_dump/psql 연결 파라미터 추출"""
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://chatbot_user:chatbot_secret@localhost:5432/chatbot")
    # +asyncpg 등 드라이버 접두사 제거
    parts = url.split("://", 1)
    clean_url = "postgresql://" + parts[1] if len(parts) > 1 else url
    parsed = urlparse(clean_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "chatbot_user",
        "db": parsed.path.lstrip("/") or "chatbot",
        "password": parsed.password or "",
    }


def _validate_filename(filename: str) -> None:
    """백업 파일 이름 검증 (path traversal 방지)"""
    if not _FILENAME_PATTERN.match(filename):
        raise HTTPException(status_code=400, detail="잘못된 파일 이름입니다")


def _require_admin(current_user: dict) -> None:
    """관리자 권한 확인"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")


def _get_backup_list() -> list:
    """백업 파일 목록 조회"""
    backups = []
    if not BACKUP_DIR.exists():
        return backups

    for backup_file in sorted(BACKUP_DIR.glob("pg_backup_*.sql"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = backup_file.stat()
        created_at = datetime.fromtimestamp(stat.st_mtime)
        age_seconds = (datetime.now() - created_at).total_seconds()

        if age_seconds < 3600:
            age = f"{int(age_seconds / 60)}분 전"
        elif age_seconds < 86400:
            age = f"{int(age_seconds / 3600)}시간 전"
        else:
            age = f"{int(age_seconds / 86400)}일 전"

        backup_type = "auto" if "_auto" in backup_file.name else "manual"

        backups.append({
            "filename": backup_file.name,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "age": age,
            "size": f"{stat.st_size / 1024 / 1024:.2f} MB",
            "size_bytes": stat.st_size,
            "type": backup_type
        })

    return backups


def inject_dependencies():
    """Backward-compatible injection hook (no dependencies needed)"""
    pass


# ==================== Endpoints ====================

@router.post("/create")
async def create_backup(
    request: Request,
    backup_request: BackupCreateRequest,
    current_user: dict = Depends(get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(5, 60, "db_backup_create"))
):
    """PostgreSQL 백업 생성"""
    _require_admin(current_user)

    try:
        conn = _parse_pg_conn()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_auto" if backup_request.type == "auto" else ""
        filename = f"pg_backup_{timestamp}{suffix}.sql"
        backup_path = BACKUP_DIR / filename

        env = os.environ.copy()
        if conn["password"]:
            env["PGPASSWORD"] = conn["password"]

        result = subprocess.run(
            ["pg_dump", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], conn["db"]],
            capture_output=True, text=True, timeout=300, env=env
        )

        if result.returncode != 0:
            logger.error(f"pg_dump failed: {result.stderr}")
            raise HTTPException(status_code=500, detail="백업 생성 실패")

        backup_path.write_text(result.stdout, encoding="utf-8")
        stat = backup_path.stat()
        logger.info(f"Backup created: {filename} ({stat.st_size / 1024 / 1024:.2f} MB)")

        return {
            "success": True,
            "message": "백업이 성공적으로 생성되었습니다",
            "backup": {
                "filename": filename,
                "size": f"{stat.st_size / 1024 / 1024:.2f} MB",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="백업 생성 시간 초과 (5분)")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="pg_dump 명령을 찾을 수 없습니다. PostgreSQL 클라이언트를 설치하세요.")
    except Exception as e:
        logger.error(f"Backup creation error: {e}")
        raise HTTPException(status_code=500, detail="백업 생성 중 오류가 발생했습니다")


@router.get("/list")
async def list_backups(
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "db_backup_list"))
):
    """백업 목록 조회"""
    _require_admin(current_user)

    backups = _get_backup_list()
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


@router.post("/restore")
async def restore_backup(
    request: Request,
    restore_request: BackupRestoreRequest,
    current_user: dict = Depends(get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(3, 60, "db_backup_restore"))
):
    """백업 복원 (psql로 SQL 파일 실행)"""
    _require_admin(current_user)

    filename = restore_request.filename
    _validate_filename(filename)

    backup_path = BACKUP_DIR / filename
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")

    try:
        conn = _parse_pg_conn()
        env = os.environ.copy()
        if conn["password"]:
            env["PGPASSWORD"] = conn["password"]

        # 복원 전 현재 상태 사전 백업
        pre_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_filename = f"pg_backup_{pre_timestamp}_auto.sql"
        pre_path = BACKUP_DIR / pre_filename

        pre_result = subprocess.run(
            ["pg_dump", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], conn["db"]],
            capture_output=True, text=True, timeout=300, env=env
        )
        if pre_result.returncode == 0:
            pre_path.write_text(pre_result.stdout, encoding="utf-8")
            logger.info(f"Pre-restore backup created: {pre_filename}")

        # psql로 복원 실행
        with open(backup_path, "r", encoding="utf-8") as f:
            result = subprocess.run(
                ["psql", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], conn["db"]],
                stdin=f, capture_output=True, text=True, timeout=600, env=env
            )

        if result.returncode != 0:
            logger.error(f"psql restore failed: {result.stderr}")
            raise HTTPException(status_code=500, detail="복원 실패")

        logger.info(f"Backup restored from: {filename}")

        return {
            "success": True,
            "message": "백업이 성공적으로 복원되었습니다",
            "current_backup": pre_filename if pre_result.returncode == 0 else None,
            "restored_from": filename
        }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="복원 시간 초과 (10분)")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="psql 명령을 찾을 수 없습니다. PostgreSQL 클라이언트를 설치하세요.")
    except Exception as e:
        logger.error(f"Restore error: {e}")
        raise HTTPException(status_code=500, detail="복원 중 오류가 발생했습니다")


@router.get("/download/{filename}")
async def download_backup(
    request: Request,
    filename: str,
    current_user: dict = Depends(get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "db_backup_download"))
):
    """백업 파일 다운로드"""
    _require_admin(current_user)
    _validate_filename(filename)

    backup_path = BACKUP_DIR / filename
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")

    return FileResponse(
        path=str(backup_path),
        filename=filename,
        media_type="application/sql"
    )


@router.post("/delete")
async def delete_backup(
    request: Request,
    delete_request: BackupDeleteRequest,
    current_user: dict = Depends(get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "db_backup_delete"))
):
    """백업 파일 삭제"""
    _require_admin(current_user)

    filename = delete_request.filename
    _validate_filename(filename)

    backup_path = BACKUP_DIR / filename
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")

    try:
        backup_path.unlink()
        logger.info(f"Backup deleted: {filename}")
        return {
            "success": True,
            "message": "백업 파일이 삭제되었습니다"
        }
    except Exception as e:
        logger.error(f"Backup delete error: {e}")
        raise HTTPException(status_code=500, detail=f"삭제 중 오류: {str(e)[:200]}")


@router.get("/schedule")
async def get_backup_schedule(
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(30, 60, "db_backup_schedule"))
):
    """자동 백업 스케줄 조회"""
    _require_admin(current_user)

    try:
        import json
        from ..services.config_service import config_get_sync
        schedule_data = config_get_sync("backup:schedule")

        if schedule_data:
            schedule = json.loads(schedule_data)
            return {
                "success": True,
                "schedule": schedule
            }

        return {
            "success": True,
            "schedule": {
                "enabled": False,
                "interval": "disabled",
                "last_backup": None
            }
        }
    except Exception as e:
        logger.error(f"Get schedule error: {e}")
        return {
            "success": True,
            "schedule": {
                "enabled": False,
                "interval": "disabled",
                "last_backup": None
            }
        }


@router.post("/schedule")
async def update_backup_schedule(
    request: Request,
    schedule_request: BackupScheduleRequest,
    current_user: dict = Depends(get_current_active_user),
    _rate_limit=Depends(create_rate_limit_dependency(10, 60, "db_backup_schedule_update"))
):
    """자동 백업 스케줄 업데이트"""
    _require_admin(current_user)

    try:
        import json
        from ..services.config_service import config_set_sync

        schedule = {
            "enabled": schedule_request.enabled,
            "interval": schedule_request.interval,
            "day_of_week": schedule_request.day_of_week,
            "hour": schedule_request.hour,
            "minute": schedule_request.minute,
        }

        config_set_sync("backup:schedule", json.dumps(schedule))
        logger.info(f"Backup schedule updated: {schedule}")

        return {
            "success": True,
            "message": "백업 스케줄이 저장되었습니다",
            "schedule": schedule
        }
    except Exception as e:
        logger.error(f"Update schedule error: {e}")
        raise HTTPException(status_code=500, detail=f"스케줄 저장 중 오류: {str(e)[:200]}")
