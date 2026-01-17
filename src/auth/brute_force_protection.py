"""
Brute Force Protection
IP 기반 및 계정 기반 브루트 포스 공격 방어
"""
from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta, timezone
from redis import Redis
from loguru import logger


def get_brute_force_config(redis: Redis) -> Dict:
    """
    브루트 포스 보호 설정 조회

    Returns:
        설정 딕셔너리 (max_attempts, lockout_duration, ip_max_attempts, ip_lockout_duration)
    """
    try:
        # Redis에서 설정 읽기
        max_attempts = redis.get("config:bf_max_attempts")
        lockout_duration = redis.get("config:bf_lockout_duration")
        ip_max_attempts = redis.get("config:bf_ip_max_attempts")
        ip_lockout_duration = redis.get("config:bf_ip_lockout_duration")

        # 기본값 설정
        return {
            "max_attempts": int(max_attempts.decode()) if max_attempts else 5,
            "lockout_duration": int(lockout_duration.decode()) if lockout_duration else 900,  # 15분
            "ip_max_attempts": int(ip_max_attempts.decode()) if ip_max_attempts else 10,
            "ip_lockout_duration": int(ip_lockout_duration.decode()) if ip_lockout_duration else 1800  # 30분
        }
    except Exception as e:
        logger.error(f"브루트 포스 설정 조회 실패: {e}")
        # 에러 시 기본값 반환
        return {
            "max_attempts": 5,
            "lockout_duration": 900,
            "ip_max_attempts": 10,
            "ip_lockout_duration": 1800
        }


def update_brute_force_config(redis: Redis, config: Dict) -> bool:
    """
    브루트 포스 보호 설정 업데이트

    Args:
        redis: Redis 클라이언트
        config: 설정 딕셔너리

    Returns:
        성공 여부
    """
    try:
        if "max_attempts" in config:
            redis.set("config:bf_max_attempts", str(config["max_attempts"]))
        if "lockout_duration" in config:
            redis.set("config:bf_lockout_duration", str(config["lockout_duration"]))
        if "ip_max_attempts" in config:
            redis.set("config:bf_ip_max_attempts", str(config["ip_max_attempts"]))
        if "ip_lockout_duration" in config:
            redis.set("config:bf_ip_lockout_duration", str(config["ip_lockout_duration"]))

        logger.info(f"브루트 포스 설정 업데이트: {config}")
        return True
    except Exception as e:
        logger.error(f"브루트 포스 설정 업데이트 실패: {e}")
        return False


class BruteForceProtection:
    """브루트 포스 공격 방어 시스템"""

    def __init__(
        self,
        redis: Redis,
        max_attempts: Optional[int] = None,
        lockout_duration: Optional[int] = None,
        ip_max_attempts: Optional[int] = None,
        ip_lockout_duration: Optional[int] = None
    ):
        """
        Args:
            redis: Redis 클라이언트
            max_attempts: 계정당 최대 실패 시도 횟수 (None이면 Redis 설정 사용)
            lockout_duration: 계정 잠금 시간 (초, None이면 Redis 설정 사용)
            ip_max_attempts: IP당 최대 실패 시도 횟수 (None이면 Redis 설정 사용)
            ip_lockout_duration: IP 차단 시간 (초, None이면 Redis 설정 사용)
        """
        self.redis = redis

        # Redis에서 설정 읽기
        config = get_brute_force_config(redis)

        # 매개변수로 전달된 값이 있으면 우선 사용, 없으면 Redis 설정 사용
        self.max_attempts = max_attempts if max_attempts is not None else config["max_attempts"]
        self.lockout_duration = lockout_duration if lockout_duration is not None else config["lockout_duration"]
        self.ip_max_attempts = ip_max_attempts if ip_max_attempts is not None else config["ip_max_attempts"]
        self.ip_lockout_duration = ip_lockout_duration if ip_lockout_duration is not None else config["ip_lockout_duration"]

    def check_ip_blocked(self, ip_address: str) -> Tuple[bool, Optional[int]]:
        """
        IP 주소가 차단되었는지 확인

        Args:
            ip_address: 클라이언트 IP 주소

        Returns:
            (is_blocked, remaining_seconds) tuple
        """
        if not ip_address or ip_address == "unknown":
            return False, None

        block_key = f"ip_blocked:{ip_address}"
        ttl = self.redis.ttl(block_key)

        if ttl > 0:
            return True, ttl
        return False, None

    def check_account_blocked(self, user_id: str) -> Tuple[bool, Optional[int]]:
        """
        계정이 차단되었는지 확인

        Args:
            user_id: 사용자 ID

        Returns:
            (is_blocked, remaining_seconds) tuple
        """
        user_data = self.redis.hgetall(f"user:{user_id}")
        locked_until = user_data.get(b"locked_until") or user_data.get("locked_until")

        if locked_until and locked_until not in [b"", ""]:
            locked_until_str = locked_until.decode() if isinstance(locked_until, bytes) else locked_until
            locked_until_dt = datetime.fromisoformat(locked_until_str)

            if datetime.now(timezone.utc).replace(tzinfo=None) < locked_until_dt:
                remaining = int((locked_until_dt - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds())
                return True, remaining

        return False, None

    def record_failed_attempt(
        self,
        email: str,
        ip_address: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Tuple[int, int]:
        """
        실패한 로그인 시도 기록

        Args:
            email: 이메일 주소
            ip_address: IP 주소
            user_id: 사용자 ID (있는 경우)

        Returns:
            (account_failures, ip_failures) tuple
        """
        account_failures = 0
        ip_failures = 0

        # 1. IP 기반 실패 카운트 (Redis Sorted Set 사용)
        if ip_address and ip_address != "unknown":
            ip_key = f"login_failed_ip:{ip_address}"
            now = datetime.now(timezone.utc).timestamp()

            # 현재 시간을 score로 사용하여 추가
            self.redis.zadd(ip_key, {email: now})

            # 오래된 시도 제거 (30분 이상 지난 것)
            cutoff = now - self.ip_lockout_duration
            self.redis.zremrangebyscore(ip_key, 0, cutoff)

            # 현재 IP의 실패 횟수
            ip_failures = self.redis.zcard(ip_key)

            # TTL 설정
            self.redis.expire(ip_key, self.ip_lockout_duration)

            # IP 차단 확인 (임계값 초과 시)
            if ip_failures >= self.ip_max_attempts:
                block_key = f"ip_blocked:{ip_address}"
                self.redis.setex(
                    block_key,
                    self.ip_lockout_duration,
                    f"Blocked due to {ip_failures} failed attempts"
                )
                logger.warning(f"🚨 IP {ip_address} blocked for {self.ip_lockout_duration}s")

        # 2. 계정 기반 실패 카운트 (기존 로직 유지)
        if user_id:
            failed_attempts_raw = self.redis.hget(f"user:{user_id}", "failed_login_attempts")
            failed_attempts_str = failed_attempts_raw.decode() if isinstance(failed_attempts_raw, bytes) else (failed_attempts_raw or "0")
            account_failures = int(failed_attempts_str) + 1

            self.redis.hset(f"user:{user_id}", "failed_login_attempts", account_failures)

            # 계정 잠금 (5회 이상)
            if account_failures >= self.max_attempts:
                locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=self.lockout_duration)
                self.redis.hset(
                    f"user:{user_id}",
                    "locked_until",
                    locked_until.isoformat()
                )
                logger.warning(f"🔒 Account {user_id} locked until {locked_until}")

        return account_failures, ip_failures

    def reset_account_failures(self, user_id: str):
        """
        계정의 실패 카운터 초기화 (로그인 성공 시)

        Args:
            user_id: 사용자 ID
        """
        pipe = self.redis.pipeline()
        pipe.hset(f"user:{user_id}", "failed_login_attempts", "0")
        pipe.hset(f"user:{user_id}", "locked_until", "")
        pipe.execute()

    def get_failure_stats(
        self,
        email: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> dict:
        """
        실패 통계 조회

        Args:
            email: 이메일 주소
            ip_address: IP 주소

        Returns:
            통계 정보
        """
        stats = {}

        if ip_address and ip_address != "unknown":
            ip_key = f"login_failed_ip:{ip_address}"
            now = datetime.now(timezone.utc).timestamp()
            cutoff = now - self.ip_lockout_duration

            # 최근 실패 시도
            recent_failures = self.redis.zrangebyscore(
                ip_key,
                cutoff,
                now,
                withscores=True
            )

            stats["ip_failures"] = len(recent_failures)
            stats["ip_blocked"] = self.redis.exists(f"ip_blocked:{ip_address}") > 0

            if recent_failures:
                # 가장 최근 시도
                latest_attempt = max(score for _, score in recent_failures)
                stats["last_attempt"] = datetime.fromtimestamp(latest_attempt).isoformat()

        return stats

    def cleanup_old_records(self):
        """
        오래된 차단 기록 정리 (주기적 실행)
        """
        try:
            # IP 차단 키 정리
            cursor = 0
            pattern = "login_failed_ip:*"
            now = datetime.now(timezone.utc).timestamp()
            cutoff = now - (self.ip_lockout_duration * 2)  # 2배 안전 마진

            while True:
                cursor, keys = self.redis.scan(cursor, match=pattern, count=100)

                for key in keys:
                    # 오래된 엔트리 제거
                    self.redis.zremrangebyscore(key, 0, cutoff)

                    # 비어있으면 키 삭제
                    count = self.redis.zcard(key)
                    if count == 0:
                        self.redis.delete(key)

                if cursor == 0:
                    break

            logger.debug("Brute force protection cleanup completed")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
