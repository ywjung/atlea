"""JWT Token Blacklist Service

Redis 기반 토큰 무효화 시스템.
로그아웃, 비밀번호 변경, 권한 변경 시 기존 토큰을 즉시 무효화합니다.
"""

from typing import Optional
from datetime import datetime, timedelta, timezone
from redis import Redis
from jose import jwt, JWTError
from loguru import logger


class TokenBlacklist:
    """JWT 토큰 블랙리스트 관리

    Redis를 사용하여 무효화된 토큰을 추적합니다.
    토큰의 만료 시간까지만 Redis에 보관하여 메모리를 효율적으로 사용합니다.
    """

    def __init__(self, redis_client: Redis):
        """초기화

        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client
        self.prefix = "token_blacklist:"

    def _get_token_key(self, token: str) -> str:
        """토큰 키 생성

        Args:
            token: JWT 토큰 문자열

        Returns:
            Redis 키
        """
        return f"{self.prefix}{token}"

    def _get_user_tokens_key(self, user_id: str) -> str:
        """사용자별 토큰 세트 키 생성

        Args:
            user_id: 사용자 ID

        Returns:
            Redis 세트 키
        """
        return f"{self.prefix}user:{user_id}"

    def _get_token_expiration(self, token: str, secret_key: str) -> Optional[int]:
        """토큰의 만료 시간(초) 계산

        Args:
            token: JWT 토큰
            secret_key: JWT 시크릿 키

        Returns:
            만료까지 남은 초, 또는 None (파싱 실패 시)
        """
        try:
            # 토큰 디코딩 (검증 없이 exp만 추출)
            payload = jwt.decode(token, secret_key, algorithms=["HS256"], options={"verify_signature": True})
            exp = payload.get("exp")

            if exp is None:
                return None

            # 만료까지 남은 시간 계산
            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
            now = datetime.now(timezone.utc)

            if exp_datetime <= now:
                # 이미 만료된 토큰
                return 0

            remaining_seconds = int((exp_datetime - now).total_seconds())
            return max(remaining_seconds, 0)

        except JWTError as e:
            logger.warning(f"Failed to decode token for expiration: {e}")
            # 디코딩 실패 시 기본 TTL 사용 (7일)
            return 7 * 24 * 60 * 60
        except Exception as e:
            logger.error(f"Error calculating token expiration: {e}")
            return None

    def add_token(self, token: str, secret_key: str, reason: str = "logout") -> bool:
        """토큰을 블랙리스트에 추가

        Args:
            token: 무효화할 JWT 토큰
            secret_key: JWT 시크릿 키
            reason: 무효화 사유 (로그용)

        Returns:
            성공 여부
        """
        try:
            # 토큰의 만료 시간 계산
            ttl = self._get_token_expiration(token, secret_key)

            if ttl is None:
                logger.error("Cannot add token to blacklist: failed to get expiration")
                return False

            if ttl == 0:
                # 이미 만료된 토큰은 블랙리스트에 추가할 필요 없음
                logger.debug("Token already expired, skipping blacklist")
                return True

            # Redis에 토큰 추가 (만료 시간까지만 보관)
            key = self._get_token_key(token)
            self.redis.setex(
                key,
                ttl,
                f"{reason}:{datetime.now(timezone.utc).isoformat()}"
            )

            # 사용자별 토큰 세트에도 추가 (선택적)
            try:
                payload = jwt.decode(token, secret_key, algorithms=["HS256"])
                user_id = payload.get("sub")
                if user_id:
                    user_tokens_key = self._get_user_tokens_key(user_id)
                    self.redis.sadd(user_tokens_key, token)
                    # 사용자 세트도 동일한 TTL 설정
                    self.redis.expire(user_tokens_key, ttl)
            except Exception:
                pass  # 사용자별 추적 실패해도 블랙리스트는 작동

            logger.info(f"Token added to blacklist: reason={reason}, ttl={ttl}s")
            return True

        except Exception as e:
            logger.error(f"Failed to add token to blacklist: {e}")
            return False

    def is_blacklisted(self, token: str) -> bool:
        """토큰이 블랙리스트에 있는지 확인

        Args:
            token: 확인할 JWT 토큰

        Returns:
            블랙리스트에 있으면 True, 없으면 False
        """
        try:
            key = self._get_token_key(token)
            exists = self.redis.exists(key)

            if exists:
                logger.debug(f"Token found in blacklist")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking token blacklist: {e}")
            # Redis 오류 시 안전하게 True 반환 (fail-closed)
            # 블랙리스트 확인 불가 시 토큰을 거부하여 보안 유지
            return True

    def revoke_user_tokens(self, user_id: str, secret_key: str, reason: str = "security") -> int:
        """특정 사용자의 모든 토큰 무효화

        Args:
            user_id: 사용자 ID
            secret_key: JWT 시크릿 키
            reason: 무효화 사유

        Returns:
            무효화된 토큰 수
        """
        try:
            user_tokens_key = self._get_user_tokens_key(user_id)

            # Get all tokens using SSCAN to avoid blocking
            tokens = []
            cursor = 0

            while True:
                cursor, toks = self.redis.sscan(
                    user_tokens_key,
                    cursor=cursor,
                    count=100
                )
                tokens.extend(toks)

                if cursor == 0:
                    break

            count = 0
            for token in tokens:
                if self.add_token(token.decode(), secret_key, reason):
                    count += 1

            # 사용자 토큰 세트 삭제
            self.redis.delete(user_tokens_key)

            logger.info(f"Revoked {count} tokens for user {user_id}, reason={reason}")
            return count

        except Exception as e:
            logger.error(f"Failed to revoke user tokens: {e}")
            return 0

    def get_blacklist_stats(self) -> dict:
        """블랙리스트 통계 조회

        Returns:
            통계 정보 딕셔너리
        """
        try:
            # 블랙리스트 토큰 수 카운트
            pattern = f"{self.prefix}*"
            cursor = 0
            total_tokens = 0

            while True:
                cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
                # user: 키 제외하고 실제 토큰만 카운트
                tokens = [k for k in keys if ":user:" not in k.decode()]
                total_tokens += len(tokens)

                if cursor == 0:
                    break

            return {
                "total_blacklisted_tokens": total_tokens,
                "prefix": self.prefix
            }

        except Exception as e:
            logger.error(f"Error getting blacklist stats: {e}")
            return {
                "total_blacklisted_tokens": 0,
                "error": str(e)
            }
