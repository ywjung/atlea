"""
Brute Force Protection
IP 기반 및 계정 기반 브루트 포스 공격 방어
PostgreSQL + 인메모리 캐시 기반.
"""
from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta, timezone
from loguru import logger

from ..services.config_service import config_get_sync, config_set_sync


# 인메모리 IP 실패 카운트 캐시
_ip_failure_cache: Dict[str, Dict] = {}
_ip_block_cache: Dict[str, float] = {}  # ip -> block_expires_at


def get_brute_force_config() -> Dict:
    """브루트 포스 보호 설정 조회 (PostgreSQL)"""
    try:
        max_attempts = config_get_sync("config:bf_max_attempts")
        lockout_duration = config_get_sync("config:bf_lockout_duration")
        ip_max_attempts = config_get_sync("config:bf_ip_max_attempts")
        ip_lockout_duration = config_get_sync("config:bf_ip_lockout_duration")

        return {
            "max_attempts": int(max_attempts) if max_attempts else 5,
            "lockout_duration": int(lockout_duration) if lockout_duration else 900,
            "ip_max_attempts": int(ip_max_attempts) if ip_max_attempts else 10,
            "ip_lockout_duration": int(ip_lockout_duration) if ip_lockout_duration else 1800
        }
    except Exception as e:
        logger.error(f"브루트 포스 설정 조회 실패: {e}")
        return {
            "max_attempts": 5,
            "lockout_duration": 900,
            "ip_max_attempts": 10,
            "ip_lockout_duration": 1800
        }


def update_brute_force_config(config: Dict) -> bool:
    """브루트 포스 보호 설정 업데이트 (PostgreSQL)"""
    try:
        if "max_attempts" in config:
            config_set_sync("config:bf_max_attempts", str(config["max_attempts"]), "string")
        if "lockout_duration" in config:
            config_set_sync("config:bf_lockout_duration", str(config["lockout_duration"]), "string")
        if "ip_max_attempts" in config:
            config_set_sync("config:bf_ip_max_attempts", str(config["ip_max_attempts"]), "string")
        if "ip_lockout_duration" in config:
            config_set_sync("config:bf_ip_lockout_duration", str(config["ip_lockout_duration"]), "string")

        logger.info(f"브루트 포스 설정 업데이트: {config}")
        return True
    except Exception as e:
        logger.error(f"브루트 포스 설정 업데이트 실패: {e}")
        return False


class BruteForceProtection:
    """브루트 포스 공격 방어 시스템"""

    def __init__(
        self,
        
        max_attempts: Optional[int] = None,
        lockout_duration: Optional[int] = None,
        ip_max_attempts: Optional[int] = None,
        ip_lockout_duration: Optional[int] = None
    ):
        """
        Args:

            max_attempts: 계정당 최대 실패 시도 횟수
            lockout_duration: 계정 잠금 시간 (초)
            ip_max_attempts: IP당 최대 실패 시도 횟수
            ip_lockout_duration: IP 차단 시간 (초)
        """
        config = get_brute_force_config()

        self.max_attempts = max_attempts if max_attempts is not None else config["max_attempts"]
        self.lockout_duration = lockout_duration if lockout_duration is not None else config["lockout_duration"]
        self.ip_max_attempts = ip_max_attempts if ip_max_attempts is not None else config["ip_max_attempts"]
        self.ip_lockout_duration = ip_lockout_duration if ip_lockout_duration is not None else config["ip_lockout_duration"]

    def check_ip_blocked(self, ip_address: str) -> Tuple[bool, Optional[int]]:
        """IP 주소가 차단되었는지 확인"""
        if not ip_address or ip_address == "unknown":
            return False, None

        import time
        now = time.time()
        block_expires = _ip_block_cache.get(ip_address)

        if block_expires and block_expires > now:
            remaining = int(block_expires - now)
            return True, remaining

        # 만료된 블록 제거
        if block_expires:
            del _ip_block_cache[ip_address]

        return False, None

    def check_account_blocked(self, user_id: str) -> Tuple[bool, Optional[int]]:
        """계정이 차단되었는지 확인 (PostgreSQL users 테이블)"""
        try:
            from ..database.connection import SyncSessionFactory
            from ..database.models.user import User
            from sqlalchemy import select
            import uuid

            with SyncSessionFactory() as session:
                stmt = select(User).where(User.id == uuid.UUID(user_id))
                result = session.execute(stmt)
                user = result.scalar_one_or_none()

            if not user or not user.locked_until:
                return False, None

            now = datetime.now(timezone.utc)
            locked_until = user.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)

            if now < locked_until:
                remaining = int((locked_until - now).total_seconds())
                return True, remaining

            return False, None

        except Exception as e:
            logger.error(f"계정 차단 확인 실패: {e}")
            return False, None

    def record_failed_attempt(
        self,
        email: str,
        ip_address: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Tuple[int, int]:
        """실패한 로그인 시도 기록"""
        import time
        account_failures = 0
        ip_failures = 0

        # 1. IP 기반 실패 카운트 (인메모리)
        if ip_address and ip_address != "unknown":
            now = time.time()
            entry = _ip_failure_cache.get(ip_address)

            if entry is None or entry.get("expires", 0) < now:
                _ip_failure_cache[ip_address] = {
                    "count": 1,
                    "expires": now + self.ip_lockout_duration,
                }
                ip_failures = 1
            else:
                entry["count"] += 1
                ip_failures = entry["count"]

            # IP 차단 확인
            if ip_failures >= self.ip_max_attempts:
                _ip_block_cache[ip_address] = now + self.ip_lockout_duration
                logger.warning(f"IP {ip_address} blocked for {self.ip_lockout_duration}s")

        # 2. 계정 기반 실패 카운트 (PostgreSQL users 테이블)
        if user_id:
            try:
                from ..database.connection import SyncSessionFactory
                from ..database.models.user import User
                from sqlalchemy import select
                import uuid

                with SyncSessionFactory() as session:
                    stmt = select(User).where(User.id == uuid.UUID(user_id))
                    result = session.execute(stmt)
                    user = result.scalar_one_or_none()

                    if user:
                        user.failed_login_attempts += 1
                        account_failures = user.failed_login_attempts

                        if account_failures >= self.max_attempts:
                            locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=self.lockout_duration)
                            user.locked_until = locked_until
                            logger.warning(f"Account {user_id} locked until {locked_until}")

                        session.commit()
            except Exception as e:
                logger.error(f"계정 실패 기록 실패: {e}")

        return account_failures, ip_failures

    def reset_account_failures(self, user_id: str):
        """계정의 실패 카운터 초기화 (로그인 성공 시)"""
        try:
            from ..database.connection import SyncSessionFactory
            from ..database.models.user import User
            from sqlalchemy import select
            import uuid

            with SyncSessionFactory() as session:
                stmt = select(User).where(User.id == uuid.UUID(user_id))
                result = session.execute(stmt)
                user = result.scalar_one_or_none()

                if user:
                    user.failed_login_attempts = 0
                    user.locked_until = None
                    session.commit()
        except Exception as e:
            logger.error(f"계정 실패 초기화 실패: {e}")

    def get_failure_stats(
        self,
        email: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> dict:
        """실패 통계 조회"""
        import time
        stats = {}

        if ip_address and ip_address != "unknown":
            now = time.time()
            entry = _ip_failure_cache.get(ip_address)

            if entry and entry.get("expires", 0) > now:
                stats["ip_failures"] = entry["count"]
            else:
                stats["ip_failures"] = 0

            stats["ip_blocked"] = ip_address in _ip_block_cache and _ip_block_cache[ip_address] > now

        return stats

    def cleanup_old_records(self):
        """오래된 차단 기록 정리"""
        import time
        now = time.time()

        # 만료된 IP 실패 기록 정리
        expired_ips = [k for k, v in _ip_failure_cache.items() if v.get("expires", 0) < now]
        for ip in expired_ips:
            del _ip_failure_cache[ip]

        # 만료된 IP 블록 정리
        expired_blocks = [k for k, v in _ip_block_cache.items() if v < now]
        for ip in expired_blocks:
            del _ip_block_cache[ip]

        logger.debug("Brute force protection cleanup completed")
