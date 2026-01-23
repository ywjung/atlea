"""Authentication Service

Core service for user authentication, session management, and admin operations.
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
from redis import Redis
from loguru import logger
import uuid
import json

from .models import (
    User, UserCreate, UserLogin, LoginResponse, TokenPair, Session,
    ProfileUpdate, PasswordChange
)
from .utils import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, verify_token
)
from .brute_force_protection import BruteForceProtection
from .security_logger import SecurityLogger
from .password_reset import PasswordResetService
from src.redis_helpers import decode_bytes, decode_redis_hash
from src.utils.pagination import calculate_total_pages
from src.constants import Limits, RedisKeys


class AuthService:
    """인증 서비스

    사용자 등록, 로그인, 세션 관리, 관리자 작업 등을 처리합니다.
    """

    def __init__(self, redis_client: Redis):
        """초기화

        Args:
            redis_client: Redis 클라이언트
        """
        self.redis = redis_client
        self.brute_force_protection = BruteForceProtection(redis_client)
        # SecurityLogger는 클래스 메서드를 사용하므로 인스턴스 생성 불필요
        SecurityLogger.set_redis(redis_client)
        self.password_reset_service = PasswordResetService(redis_client)

    async def create_user(self, user_data: UserCreate) -> User:
        """사용자 생성

        Args:
            user_data: 사용자 생성 데이터

        Returns:
            생성된 사용자

        Raises:
            ValueError: 이메일이 이미 존재하는 경우
        """
        # 이메일 중복 확인
        existing_user_id = self.redis.get(f"user:email:{user_data.email}")
        if existing_user_id:
            raise ValueError("이미 사용 중인 이메일입니다")

        # 사용자 ID 생성
        user_id = str(uuid.uuid4())

        # 비밀번호 해시
        password_hash = hash_password(user_data.password)

        # 사용자 데이터 생성
        user = User(
            user_id=user_id,
            email=user_data.email,
            username=user_data.username,
            created_at=datetime.now(timezone.utc),
            is_active=True,
            role="user"
        )

        # Redis에 저장
        user_key = f"user:{user_id}"
        user_data_dict = user.model_dump()
        user_data_dict['password_hash'] = password_hash
        user_data_dict['created_at'] = user_data_dict['created_at'].isoformat()
        if user_data_dict.get('last_login'):
            user_data_dict['last_login'] = user_data_dict['last_login'].isoformat()
        if user_data_dict.get('locked_until'):
            user_data_dict['locked_until'] = user_data_dict['locked_until'].isoformat()

        # Remove None values and convert all values to strings for Redis
        user_data_dict = {k: str(v) for k, v in user_data_dict.items() if v is not None}

        self.redis.hset(user_key, mapping=user_data_dict)
        self.redis.set(f"user:email:{user_data.email}", user_id)
        self.redis.sadd("users:all", user_id)

        logger.info(f"✅ User created: {user_id} ({user_data.email})")

        # 보안 로그 기록
        SecurityLogger.log_event(
            event_type="user_created",
            level="info",
            user_id=user_id,
            email=user_data.email,
            username=user_data.username,
            details={"action": "register"}
        )

        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """사용자 ID로 사용자 조회

        Args:
            user_id: 사용자 ID

        Returns:
            사용자 정보 (없으면 None)
        """
        user_data = self.redis.hgetall(f"user:{user_id}")
        if not user_data:
            return None

        # bytes를 string으로 변환
        user_dict = decode_redis_hash(user_data)

        # datetime 필드 처리 (빈 문자열은 None으로 처리)
        if user_dict.get('created_at') and user_dict['created_at']:
            user_dict['created_at'] = datetime.fromisoformat(user_dict['created_at'].replace('Z', '+00:00'))
        if user_dict.get('last_login') and user_dict['last_login']:
            user_dict['last_login'] = datetime.fromisoformat(user_dict['last_login'].replace('Z', '+00:00'))
        else:
            user_dict['last_login'] = None
        if user_dict.get('locked_until') and user_dict['locked_until']:
            user_dict['locked_until'] = datetime.fromisoformat(user_dict['locked_until'].replace('Z', '+00:00'))
        else:
            user_dict['locked_until'] = None

        # boolean 필드 처리
        if 'is_active' in user_dict:
            user_dict['is_active'] = user_dict['is_active'].lower() in ('true', '1', 'yes')

        # integer 필드 처리
        if 'failed_login_attempts' in user_dict:
            user_dict['failed_login_attempts'] = int(user_dict['failed_login_attempts'])

        return User(**user_dict)

    async def get_users_by_ids(self, user_ids: list) -> dict:
        """여러 사용자 ID로 배치 조회 (Pipeline 사용)

        Args:
            user_ids: 사용자 ID 목록

        Returns:
            {user_id: User} 딕셔너리 (없는 사용자는 제외)
        """
        if not user_ids:
            return {}

        # Pipeline으로 모든 사용자 데이터 일괄 조회
        pipe = self.redis.pipeline()
        for user_id in user_ids:
            pipe.hgetall(f"user:{user_id}")
        results = pipe.execute()

        users = {}
        for user_id, user_data in zip(user_ids, results):
            if not user_data:
                continue

            # bytes를 string으로 변환
            user_dict = decode_redis_hash(user_data)

            # datetime 필드 처리
            if user_dict.get('created_at') and user_dict['created_at']:
                user_dict['created_at'] = datetime.fromisoformat(user_dict['created_at'].replace('Z', '+00:00'))
            if user_dict.get('last_login') and user_dict['last_login']:
                user_dict['last_login'] = datetime.fromisoformat(user_dict['last_login'].replace('Z', '+00:00'))
            else:
                user_dict['last_login'] = None
            if user_dict.get('locked_until') and user_dict['locked_until']:
                user_dict['locked_until'] = datetime.fromisoformat(user_dict['locked_until'].replace('Z', '+00:00'))
            else:
                user_dict['locked_until'] = None

            # boolean 필드 처리
            if 'is_active' in user_dict:
                user_dict['is_active'] = user_dict['is_active'].lower() in ('true', '1', 'yes')

            # integer 필드 처리
            if 'failed_login_attempts' in user_dict:
                user_dict['failed_login_attempts'] = int(user_dict['failed_login_attempts'])

            try:
                users[user_id] = User(**user_dict)
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Failed to parse user {user_id}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error parsing user {user_id}: {e}", exc_info=True)
                continue

        return users

    def record_login_history(
        self, user_id: str, email: str, ip_address: Optional[str],
        status: str, username: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None
    ):
        """로그인 히스토리 기록

        Args:
            user_id: 사용자 ID
            email: 이메일
            ip_address: IP 주소
            status: 로그인 상태 (success/failed/blocked)
            username: 사용자명
            user_agent: User Agent
            failure_reason: 실패 사유
        """
        import json
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc)
        score = timestamp.timestamp()

        history_entry = {
            "timestamp": timestamp.isoformat() + 'Z',
            "email": email,
            "username": username or "unknown",
            "ip_address": ip_address or "unknown",
            "status": status,
            "user_agent": user_agent,
            "failure_reason": failure_reason
        }

        # Redis ZSET에 저장 (사용자별, 타임스탬프로 정렬)
        self.redis.zadd(
            f"login_history:{user_id}",
            {json.dumps(history_entry): score}
        )

        # 전체 로그인 히스토리도 저장 (관리자용)
        history_entry["user_id"] = user_id
        self.redis.zadd(
            "login_history:all",
            {json.dumps(history_entry): score}
        )

        # 최대 1000개까지만 유지 (오래된 것 삭제)
        self.redis.zremrangebyrank(f"login_history:{user_id}", 0, -1001)
        self.redis.zremrangebyrank("login_history:all", 0, -10001)

    async def authenticate_user(
        self, credentials: UserLogin, ip_address: Optional[str] = None, user_agent: Optional[str] = None
    ) -> dict:
        """사용자 인증

        Args:
            credentials: 로그인 자격 증명
            ip_address: IP 주소
            user_agent: 사용자 에이전트

        Returns:
            사용자 정보 및 토큰

        Raises:
            ValueError: 인증 실패 시
        """
        # IP 차단 체크
        ip_blocked, ip_ttl = self.brute_force_protection.check_ip_blocked(ip_address)
        if ip_blocked:
            logger.warning(f"🚨 IP blocked: {ip_address}")
            # 로그인 히스토리 기록 (IP 차단)
            self.record_login_history(
                user_id="unknown",
                email=credentials.email,
                ip_address=ip_address,
                status="blocked",
                failure_reason=f"IP blocked for {ip_ttl // 60} minutes"
            )
            raise ValueError(
                f"IP 주소가 차단되었습니다. {ip_ttl // 60}분 후 다시 시도하세요"
            )

        # 사용자 조회
        user_id = self.redis.get(f"user:email:{credentials.email}")
        if not user_id:
            self.brute_force_protection.record_failed_attempt(
                credentials.email, ip_address, None
            )
            # 로그인 히스토리 기록 (사용자 없음)
            self.record_login_history(
                user_id="unknown",
                email=credentials.email,
                ip_address=ip_address,
                status="failed",
                failure_reason="Invalid email"
            )
            raise ValueError("유효하지 않은 이메일 또는 비밀번호입니다")

        user_id = decode_bytes(user_id)

        # 사용자 데이터 먼저 조회 (username 필요)
        user_data = self.redis.hgetall(f"user:{user_id}")
        if not user_data:
            self.brute_force_protection.record_failed_attempt(
                credentials.email, ip_address, user_id
            )
            raise ValueError("유효하지 않은 이메일 또는 비밀번호입니다")

        # username 추출 (decode_redis_hash로 미리 변환)
        decoded_user_data = decode_redis_hash(user_data)
        username = decoded_user_data.get('username', 'unknown')

        # 계정 잠금 체크
        account_blocked, account_ttl = self.brute_force_protection.check_account_blocked(user_id)
        if account_blocked:
            logger.warning(f"🚨 Account locked: {credentials.email}")
            # 로그인 히스토리 기록 (계정 잠금)
            self.record_login_history(
                user_id=user_id,
                email=credentials.email,
                ip_address=ip_address,
                status="blocked",
                username=username,
                failure_reason=f"Account locked for {account_ttl // 60} minutes"
            )
            raise ValueError(
                f"계정이 잠겼습니다. {account_ttl // 60}분 후 다시 시도하세요"
            )

        # 계정 활성화 상태 확인
        is_active_str = decoded_user_data.get('is_active', 'true')
        if is_active_str.lower() != 'true':
            raise ValueError("비활성화된 계정입니다")

        # 비밀번호 확인
        password_hash_str = decoded_user_data.get('password_hash', '')

        if not verify_password(credentials.password, password_hash_str):
            self.brute_force_protection.record_failed_attempt(
                credentials.email, ip_address, user_id
            )
            # 로그인 히스토리 기록 (비밀번호 틀림)
            self.record_login_history(
                user_id=user_id,
                email=credentials.email,
                ip_address=ip_address,
                status="failed",
                username=username,
                failure_reason="Invalid password"
            )
            logger.warning(f"⚠️  Failed login: {credentials.email}")
            raise ValueError("유효하지 않은 이메일 또는 비밀번호입니다")

        # 2FA 검증 (활성화된 경우)
        from .totp import TOTPService
        totp_service = TOTPService(self.redis)
        if totp_service.is_enabled():
            # 사용자의 totp_secret 확인
            totp_secret_str = decoded_user_data.get('totp_secret', '')

            # totp_secret이 None이나 빈 문자열이 아닌 경우에만 검증
            if totp_secret_str and totp_secret_str != 'None' and totp_secret_str != '':
                    # TOTP 토큰이 제공되지 않았거나 잘못된 경우
                    if not credentials.totp_token or not totp_service.verify_token(totp_secret_str, credentials.totp_token):
                        self.brute_force_protection.record_failed_attempt(
                            credentials.email, ip_address, user_id
                        )
                        # 로그인 히스토리 기록 (2FA 실패)
                        self.record_login_history(
                            user_id=user_id,
                            email=credentials.email,
                            ip_address=ip_address,
                            status="failed",
                            username=username,
                            failure_reason="Invalid 2FA code"
                        )
                        logger.warning(f"⚠️  Failed 2FA: {credentials.email}")
                        raise ValueError("2FA 코드가 유효하지 않습니다")

        # 로그인 성공 - 실패 횟수 초기화
        self.brute_force_protection.reset_account_failures(user_id)

        # 로그인 히스토리 기록 (성공)
        self.record_login_history(
            user_id=user_id,
            email=credentials.email,
            ip_address=ip_address,
            status="success",
            username=username
        )

        # 사용자 데이터 파싱
        decoded_data = decode_redis_hash(user_data)
        user_dict = {}
        for key_str, value_str in decoded_data.items():
            if key_str in ['created_at', 'last_login', 'locked_until']:
                try:
                    user_dict[key_str] = datetime.fromisoformat(value_str) if value_str and value_str != 'None' else None
                except Exception:
                    user_dict[key_str] = None
            elif key_str == 'is_active':
                user_dict[key_str] = value_str.lower() == 'true'
            elif key_str == 'failed_login_attempts':
                user_dict[key_str] = int(value_str) if value_str else 0
            elif key_str != 'password_hash':
                user_dict[key_str] = value_str

        user = User(**user_dict)

        # 마지막 로그인 시간 업데이트
        user.last_login = datetime.now(timezone.utc)
        self.redis.hset(f"user:{user_id}", "last_login", user.last_login.isoformat())

        # 세션 생성
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=Limits.SESSION_EXPIRY_DAYS),
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Redis에 세션 저장
        session_key = f"session:{session_id}"
        session_data = session.model_dump()
        session_data['created_at'] = session_data['created_at'].isoformat()
        session_data['expires_at'] = session_data['expires_at'].isoformat()

        # None 값 제거 (Redis는 None을 저장할 수 없음)
        session_data = {k: v for k, v in session_data.items() if v is not None}

        self.redis.hset(session_key, mapping=session_data)
        self.redis.sadd(f"user:sessions:{user_id}", session_id)
        self.redis.expire(session_key, 30 * 24 * 60 * 60)  # 30일

        # JWT 토큰 생성
        access_token = create_access_token(
            data={"user_id": user_id, "sub": user.username, "role": user.role}
        )
        refresh_token = create_refresh_token(
            data={"user_id": user_id, "sub": user.username, "session_id": session_id}
        )

        logger.info(f"✅ Login successful: {user.email}")

        # 보안 로그 기록
        SecurityLogger.log_event(
            event_type="login_success",
            level="info",
            user_id=user_id,
            email=user.email,
            username=user.username,
            ip_address=ip_address,
            details={"session_id": session_id}
        )

        return {
            "user": user,
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer"
            },
            "session_id": session_id
        }

    async def logout(
        self, session_id: str, ip_address: Optional[str] = None,
        username: Optional[str] = None
    ):
        """로그아웃

        Args:
            session_id: 세션 ID
            ip_address: IP 주소
            username: 사용자명
        """
        # 세션 삭제
        session_data = self.redis.hgetall(f"session:{session_id}")
        if session_data:
            user_id = session_data.get(b'user_id' if isinstance(list(session_data.keys())[0], bytes) else 'user_id')
            user_id = decode_bytes(user_id)

            self.redis.delete(f"session:{session_id}")
            self.redis.srem(f"user:sessions:{user_id}", session_id)

            logger.info(f"🔓 Logout: {username or user_id}")

            # 보안 로그 기록
            SecurityLogger.log_event(
                event_type="logout",
                level="info",
                user_id=user_id,
                username=username,
                ip_address=ip_address,
                details={"session_id": session_id}
            )

    async def refresh_access_token(
        self, refresh_token: str, ip_address: Optional[str] = None
    ) -> dict:
        """액세스 토큰 갱신

        Args:
            refresh_token: Refresh Token
            ip_address: IP 주소

        Returns:
            새로운 사용자 정보 및 토큰

        Raises:
            ValueError: 토큰 검증 실패 시
        """
        # Refresh Token 검증
        payload = verify_token(refresh_token)
        if not payload:
            raise ValueError("유효하지 않은 Refresh Token입니다")

        user_id = payload.get("user_id")
        session_id = payload.get("session_id")

        # 세션 확인
        session_data = self.redis.hgetall(f"session:{session_id}")
        if not session_data:
            raise ValueError("세션이 만료되었습니다")

        # 사용자 조회
        user_data = self.redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise ValueError("사용자를 찾을 수 없습니다")

        # 사용자 데이터 파싱
        decoded_data = decode_redis_hash(user_data)
        user_dict = {}
        for key_str, value_str in decoded_data.items():
            if key_str in ['created_at', 'last_login', 'locked_until']:
                try:
                    user_dict[key_str] = datetime.fromisoformat(value_str) if value_str and value_str != 'None' else None
                except Exception:
                    user_dict[key_str] = None
            elif key_str == 'is_active':
                user_dict[key_str] = value_str.lower() == 'true'
            elif key_str == 'failed_login_attempts':
                user_dict[key_str] = int(value_str) if value_str else 0
            elif key_str != 'password_hash':
                user_dict[key_str] = value_str

        user = User(**user_dict)

        # 새로운 토큰 생성
        new_access_token = create_access_token(
            data={"user_id": user_id, "sub": user.username, "role": user.role}
        )
        new_refresh_token = create_refresh_token(
            data={"user_id": user_id, "sub": user.username, "session_id": session_id}
        )

        logger.info(f"🔄 Token refreshed: {user.email}")

        return {
            "user": user,
            "tokens": {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer"
            }
        }

    async def request_password_reset(self, email: str) -> str:
        """비밀번호 재설정 요청

        Args:
            email: 이메일 주소

        Returns:
            재설정 토큰

        Raises:
            ValueError: 사용자를 찾을 수 없는 경우
        """
        user_id = self.redis.get(f"user:email:{email}")
        if not user_id:
            raise ValueError("사용자를 찾을 수 없습니다")

        user_id = decode_bytes(user_id)
        reset_token = await self.password_reset_service.create_reset_token(user_id, email)

        logger.info(f"🔑 Password reset requested: {email}")

        # 보안 로그 기록
        SecurityLogger.log_event(
            event_type="password_reset_requested",
            level="info",
            user_id=user_id,
            email=email,
            details={"action": "request_password_reset"}
        )

        return reset_token

    async def reset_password(self, token: str, new_password: str):
        """비밀번호 재설정

        Args:
            token: 재설정 토큰
            new_password: 새 비밀번호

        Raises:
            ValueError: 토큰 검증 실패 시
        """
        user_id = await self.password_reset_service.verify_reset_token(token)
        if not user_id:
            raise ValueError("유효하지 않거나 만료된 토큰입니다")

        # 비밀번호 업데이트
        password_hash = hash_password(new_password)
        self.redis.hset(f"user:{user_id}", "password_hash", password_hash)

        # 모든 세션 무효화 (Pipeline으로 배치 삭제)
        session_ids = self.redis.smembers(f"user:sessions:{user_id}")
        if session_ids:
            pipe = self.redis.pipeline()
            for session_id in session_ids:
                session_id_str = decode_bytes(session_id)
                pipe.delete(f"session:{session_id_str}")
            pipe.delete(f"user:sessions:{user_id}")
            pipe.execute()
        else:
            self.redis.delete(f"user:sessions:{user_id}")

        logger.info(f"🔐 Password reset: {user_id}")

        # 보안 로그 기록
        user_data = self.redis.hgetall(f"user:{user_id}")
        email = user_data.get(b'email' if isinstance(list(user_data.keys())[0], bytes) else 'email')
        email = decode_bytes(email)

        SecurityLogger.log_event(
            event_type="password_reset_completed",
            level="info",
            user_id=user_id,
            email=email,
            details={"action": "reset_password"}
        )

    async def update_profile(self, user_id: str, username: Optional[str] = None) -> User:
        """프로필 업데이트

        Args:
            user_id: 사용자 ID
            username: 새 사용자명

        Returns:
            업데이트된 사용자

        Raises:
            ValueError: 사용자를 찾을 수 없는 경우
        """
        user_data = self.redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise ValueError("사용자를 찾을 수 없습니다")

        if username:
            self.redis.hset(f"user:{user_id}", "username", username)

        # 업데이트된 사용자 조회
        user_data = self.redis.hgetall(f"user:{user_id}")
        decoded_data = decode_redis_hash(user_data)
        user_dict = {}
        for key_str, value_str in decoded_data.items():
            if key_str in ['created_at', 'last_login', 'locked_until']:
                try:
                    user_dict[key_str] = datetime.fromisoformat(value_str) if value_str and value_str != 'None' else None
                except Exception:
                    user_dict[key_str] = None
            elif key_str == 'is_active':
                user_dict[key_str] = value_str.lower() == 'true'
            elif key_str == 'failed_login_attempts':
                user_dict[key_str] = int(value_str) if value_str else 0
            elif key_str != 'password_hash':
                user_dict[key_str] = value_str

        user = User(**user_dict)

        logger.info(f"👤 Profile updated: {user_id}")

        return user

    async def change_password(
        self, user_id: str, old_password: str, new_password: str
    ):
        """비밀번호 변경

        Args:
            user_id: 사용자 ID
            old_password: 현재 비밀번호
            new_password: 새 비밀번호

        Raises:
            ValueError: 비밀번호 검증 실패 시
        """
        user_data = self.redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise ValueError("사용자를 찾을 수 없습니다")

        # 현재 비밀번호 확인
        password_hash = user_data.get(b'password_hash' if isinstance(list(user_data.keys())[0], bytes) else 'password_hash')
        password_hash_str = decode_bytes(password_hash)

        if not verify_password(old_password, password_hash_str):
            raise ValueError("현재 비밀번호가 일치하지 않습니다")

        # 새 비밀번호 해시 및 저장
        new_password_hash = hash_password(new_password)
        self.redis.hset(f"user:{user_id}", "password_hash", new_password_hash)

        # 모든 세션 무효화 (Pipeline으로 배치 삭제)
        session_ids = self.redis.smembers(f"user:sessions:{user_id}")
        if session_ids:
            pipe = self.redis.pipeline()
            for session_id in session_ids:
                session_id_str = decode_bytes(session_id)
                pipe.delete(f"session:{session_id_str}")
            pipe.delete(f"user:sessions:{user_id}")
            pipe.execute()
        else:
            self.redis.delete(f"user:sessions:{user_id}")

        logger.info(f"🔒 Password changed: {user_id}")

        # 보안 로그 기록
        email = user_data.get(b'email' if isinstance(list(user_data.keys())[0], bytes) else 'email')
        email = decode_bytes(email)

        SecurityLogger.log_event(
            event_type="password_changed",
            level="info",
            user_id=user_id,
            email=email,
            details={"action": "change_password"}
        )

    async def get_user_sessions(self, user_id: str) -> List[Session]:
        """사용자 세션 목록 조회

        Args:
            user_id: 사용자 ID

        Returns:
            세션 목록
        """
        session_ids = self.redis.smembers(f"user:sessions:{user_id}")
        if not session_ids:
            return []

        # Pipeline을 사용하여 모든 세션 데이터를 일괄 조회 (N+1 → 1 쿼리)
        session_id_strs = [decode_bytes(sid) for sid in session_ids]
        pipe = self.redis.pipeline()
        for session_id_str in session_id_strs:
            pipe.hgetall(f"session:{session_id_str}")
        session_data_list = pipe.execute()

        sessions = []
        for session_data in session_data_list:
            if session_data:
                decoded_session = decode_redis_hash(session_data)
                session_dict = {}
                for key_str, value_str in decoded_session.items():
                    if key_str in ['created_at', 'expires_at']:
                        try:
                            session_dict[key_str] = datetime.fromisoformat(value_str)
                        except Exception:
                            session_dict[key_str] = datetime.now(timezone.utc)
                    else:
                        session_dict[key_str] = value_str

                sessions.append(Session(**session_dict))

        return sessions

    async def revoke_session(self, user_id: str, session_id: str) -> bool:
        """세션 무효화

        Args:
            user_id: 사용자 ID
            session_id: 세션 ID

        Returns:
            성공 여부

        Raises:
            ValueError: 권한이 없는 경우
        """
        # 세션이 해당 사용자의 것인지 확인
        session_data = self.redis.hgetall(f"session:{session_id}")
        if not session_data:
            return False

        session_user_id = session_data.get(b'user_id' if isinstance(list(session_data.keys())[0], bytes) else 'user_id')
        session_user_id = decode_bytes(session_user_id)

        if session_user_id != user_id:
            raise ValueError("이 세션에 대한 권한이 없습니다")

        # 세션 삭제
        self.redis.delete(f"session:{session_id}")
        self.redis.srem(f"user:sessions:{user_id}", session_id)

        logger.info(f"🔓 Session revoked: {session_id}")

        return True

    async def revoke_all_sessions(self, user_id: str) -> int:
        """사용자의 모든 세션 무효화

        Args:
            user_id: 사용자 ID

        Returns:
            무효화된 세션 수
        """
        # 사용자의 모든 세션 ID 가져오기
        session_ids = self.redis.smembers(f"user:sessions:{user_id}")

        if not session_ids:
            return 0

        # 각 세션 삭제
        count = 0
        for session_id in session_ids:
            if isinstance(session_id, bytes):
                session_id = session_id.decode()

            # 세션 데이터 삭제
            if self.redis.delete(f"session:{session_id}"):
                count += 1

        # 사용자 세션 세트 삭제
        self.redis.delete(f"user:sessions:{user_id}")

        logger.info(f"🔓 All sessions revoked for user {user_id}: {count} sessions")

        return count

    # ============= Admin Methods =============

    async def get_system_stats(self) -> dict:
        """시스템 통계 조회 (Redis Pipeline 최적화)

        Returns:
            시스템 통계
        """
        # Helper function for bytes decoding
        def decode_value(val):
            return val.decode('utf-8') if isinstance(val, bytes) else val

        def decode_dict(d):
            if not d:
                return {}
            return {decode_value(k): decode_value(v) for k, v in d.items()}

        def parse_datetime(dt_str):
            """Parse datetime string handling Z suffix, returns naive datetime"""
            if not dt_str:
                return None
            try:
                if dt_str.endswith('Z'):
                    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                else:
                    dt = datetime.fromisoformat(dt_str)
                # Always return naive datetime for consistent comparison
                if dt.tzinfo is not None:
                    return dt.replace(tzinfo=None)
                return dt
            except (ValueError, AttributeError, TypeError):
                return None

        total_users = self.redis.scard("users:all")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        twenty_four_hours_ago = now - timedelta(hours=24)

        # 1. Get all user IDs
        all_user_ids = self.redis.smembers("users:all")
        user_id_list = [decode_value(uid) for uid in all_user_ids]

        if not user_id_list:
            return {
                "total_users": 0,
                "active_users": 0,
                "inactive_users": 0,
                "admin_users": 0,
                "active_sessions": 0,
                "recent_logins": [],
                "recent_logins_24h": 0,
                "security_events": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        # 2. Batch fetch all user data using Pipeline (N+1 → 1 query)
        pipe = self.redis.pipeline()
        for user_id in user_id_list:
            pipe.hgetall(f"user:{user_id}")
        user_data_list = pipe.execute()

        # Process user data
        active_users = 0
        admin_users = 0
        recent_logins = []
        recent_logins_24h = 0

        for user_id, user_data_raw in zip(user_id_list, user_data_list):
            if not user_data_raw:
                continue

            user_data = decode_dict(user_data_raw)

            # Count active users
            if user_data.get('is_active', '').lower() == 'true':
                active_users += 1

            # Count admin users
            role = user_data.get('role', 'user')
            if role == 'admin':
                admin_users += 1

            # Collect recent login info
            last_login_str = user_data.get('last_login')
            if last_login_str:
                last_login_dt = parse_datetime(last_login_str)
                if last_login_dt and last_login_dt > twenty_four_hours_ago:
                    recent_logins_24h += 1

                recent_logins.append({
                    "user_id": user_id,
                    "email": user_data.get('email', ''),
                    "username": user_data.get('username', ''),
                    "last_login": last_login_str,
                    "role": role
                })

        # Sort and limit recent logins
        recent_logins.sort(key=lambda x: x.get('last_login', ''), reverse=True)
        recent_logins = recent_logins[:10]

        # 3. Batch fetch all session IDs using Pipeline (N+1 → 1 query)
        pipe = self.redis.pipeline()
        for user_id in user_id_list:
            pipe.smembers(f"user:sessions:{user_id}")
        session_ids_list = pipe.execute()

        # Collect all session IDs
        all_session_ids = []
        for session_ids_raw in session_ids_list:
            if session_ids_raw:
                for sid in session_ids_raw:
                    all_session_ids.append(decode_value(sid))

        # 4. Batch fetch all session data using Pipeline (N*M → 1 query)
        active_sessions = 0
        if all_session_ids:
            pipe = self.redis.pipeline()
            for session_id in all_session_ids:
                pipe.hgetall(f"session:{session_id}")
            session_data_list = pipe.execute()

            for session_data_raw in session_data_list:
                if not session_data_raw:
                    continue

                session_data = decode_dict(session_data_raw)
                expires_at_str = session_data.get('expires_at')
                expires_at_dt = parse_datetime(expires_at_str)

                if expires_at_dt and expires_at_dt >= now:
                    active_sessions += 1

        # Security events count
        try:
            security_events = self.redis.zcard("security_logs:all") or 0
        except Exception:
            security_events = 0

        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "admin_users": admin_users,
            "active_sessions": active_sessions,
            "recent_logins": recent_logins,
            "recent_logins_24h": recent_logins_24h,
            "security_events": security_events,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def get_all_users(self, page: int = 1, page_size: int = 50) -> dict:
        """모든 사용자 조회

        Args:
            page: 페이지 번호
            page_size: 페이지당 사용자 수

        Returns:
            사용자 목록 및 페이지 정보
        """
        all_user_ids = list(self.redis.smembers("users:all"))
        total_users = len(all_user_ids)

        # 페이지네이션
        start = (page - 1) * page_size
        end = start + page_size
        page_user_ids = all_user_ids[start:end]

        # Pipeline으로 배치 조회 (N+1 쿼리 방지)
        user_id_strs = [decode_bytes(user_id) for user_id in page_user_ids]
        
        pipe = self.redis.pipeline()
        for user_id_str in user_id_strs:
            pipe.hgetall(f"user:{user_id_str}")
        user_data_list = pipe.execute()

        users = []
        for user_data in user_data_list:
            if user_data:
                decoded_data = decode_redis_hash(user_data)
                user_dict = {}
                for key_str, value_str in decoded_data.items():
                    if key_str in ['created_at', 'last_login', 'locked_until']:
                        try:
                            user_dict[key_str] = datetime.fromisoformat(value_str) if value_str and value_str != 'None' else None
                        except Exception:
                            user_dict[key_str] = None
                    elif key_str == 'is_active':
                        user_dict[key_str] = value_str.lower() == 'true'
                    elif key_str == 'failed_login_attempts':
                        user_dict[key_str] = int(value_str) if value_str else 0
                    elif key_str != 'password_hash':
                        user_dict[key_str] = value_str

                users.append(User(**user_dict).model_dump())

        return {
            "users": users,
            "total": total_users,
            "page": page,
            "page_size": page_size,
            "total_pages": calculate_total_pages(total_users, page_size)
        }

    async def update_user_status(
        self, user_id: str, is_active: bool, admin_user_id: str
    ) -> User:
        """사용자 활성화 상태 변경

        Args:
            user_id: 대상 사용자 ID
            is_active: 활성화 상태
            admin_user_id: 관리자 사용자 ID

        Returns:
            업데이트된 사용자

        Raises:
            ValueError: 사용자를 찾을 수 없는 경우
        """
        user_data = self.redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise ValueError("사용자를 찾을 수 없습니다")

        self.redis.hset(f"user:{user_id}", "is_active", str(is_active))

        # 비활성화 시 모든 세션 무효화 (Pipeline으로 배치 삭제)
        if not is_active:
            session_ids = self.redis.smembers(f"user:sessions:{user_id}")
            if session_ids:
                pipe = self.redis.pipeline()
                for session_id in session_ids:
                    session_id_str = decode_bytes(session_id)
                    pipe.delete(f"session:{session_id_str}")
                pipe.delete(f"user:sessions:{user_id}")
                pipe.execute()
            else:
                self.redis.delete(f"user:sessions:{user_id}")

        # 업데이트된 사용자 조회
        user_data = self.redis.hgetall(f"user:{user_id}")
        decoded_data = decode_redis_hash(user_data)
        user_dict = {}
        for key_str, value_str in decoded_data.items():
            if key_str in ['created_at', 'last_login', 'locked_until']:
                try:
                    user_dict[key_str] = datetime.fromisoformat(value_str) if value_str and value_str != 'None' else None
                except Exception:
                    user_dict[key_str] = None
            elif key_str == 'is_active':
                user_dict[key_str] = value_str.lower() == 'true'
            elif key_str == 'failed_login_attempts':
                user_dict[key_str] = int(value_str) if value_str else 0
            elif key_str != 'password_hash':
                user_dict[key_str] = value_str

        user = User(**user_dict)

        logger.info(f"⚙️  User status updated: {user_id} -> {is_active}")

        # 보안 로그 기록
        SecurityLogger.log_event(
            event_type="user_status_changed",
            level="info",
            user_id=admin_user_id,
            details={
                "target_user_id": user_id,
                "is_active": is_active,
                "action": "update_user_status"
            }
        )

        return user

    async def update_user_role(
        self, user_id: str, role: str, admin_user_id: str
    ) -> User:
        """사용자 역할 변경

        Args:
            user_id: 대상 사용자 ID
            role: 새 역할 (user/admin)
            admin_user_id: 관리자 사용자 ID

        Returns:
            업데이트된 사용자

        Raises:
            ValueError: 유효하지 않은 역할이거나 사용자를 찾을 수 없는 경우
        """
        if role not in ["user", "admin"]:
            raise ValueError("유효하지 않은 역할입니다")

        user_data = self.redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise ValueError("사용자를 찾을 수 없습니다")

        self.redis.hset(f"user:{user_id}", "role", role)

        # 업데이트된 사용자 조회
        user_data = self.redis.hgetall(f"user:{user_id}")
        decoded_data = decode_redis_hash(user_data)
        user_dict = {}
        for key_str, value_str in decoded_data.items():
            if key_str in ['created_at', 'last_login', 'locked_until']:
                try:
                    user_dict[key_str] = datetime.fromisoformat(value_str) if value_str and value_str != 'None' else None
                except Exception:
                    user_dict[key_str] = None
            elif key_str == 'is_active':
                user_dict[key_str] = value_str.lower() == 'true'
            elif key_str == 'failed_login_attempts':
                user_dict[key_str] = int(value_str) if value_str else 0
            elif key_str != 'password_hash':
                user_dict[key_str] = value_str

        user = User(**user_dict)

        logger.info(f"👑 User role updated: {user_id} -> {role}")

        # 보안 로그 기록
        SecurityLogger.log_event(
            event_type="user_role_changed",
            level="info",
            user_id=admin_user_id,
            details={
                "target_user_id": user_id,
                "new_role": role,
                "action": "update_user_role"
            }
        )

        return user

    async def delete_user(self, user_id: str, admin_user_id: str):
        """사용자 삭제

        Args:
            user_id: 삭제할 사용자 ID
            admin_user_id: 관리자 사용자 ID

        Raises:
            ValueError: 사용자를 찾을 수 없는 경우
        """
        user_data = self.redis.hgetall(f"user:{user_id}")
        if not user_data:
            raise ValueError("사용자를 찾을 수 없습니다")

        email = user_data.get(b'email' if isinstance(list(user_data.keys())[0], bytes) else 'email')
        email = decode_bytes(email)

        # 모든 세션 ID 조회
        session_ids = self.redis.smembers(f"user:sessions:{user_id}")

        # Pipeline으로 모든 삭제 작업을 일괄 처리 (N+1 → 1 쿼리)
        pipe = self.redis.pipeline()
        pipe.delete(f"user:{user_id}")
        pipe.delete(f"user:email:{email}")
        pipe.srem("users:all", user_id)
        for session_id in session_ids:
            session_id_str = decode_bytes(session_id)
            pipe.delete(f"session:{session_id_str}")
        pipe.delete(f"user:sessions:{user_id}")
        pipe.execute()

        logger.info(f"🗑️  User deleted: {user_id}")

        # 보안 로그 기록
        SecurityLogger.log_event(
            event_type="user_deleted",
            level="warning",
            user_id=admin_user_id,
            details={
                "target_user_id": user_id,
                "target_email": email,
                "action": "delete_user"
            }
        )

    async def get_security_logs(
        self,
        page: int = 1,
        page_size: int = 100,
        level: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> dict:
        """보안 로그 조회

        Args:
            page: 페이지 번호
            page_size: 페이지당 로그 수
            level: 로그 레벨 필터
            event_type: 이벤트 타입 필터
            start_time: 시작 시간
            end_time: 종료 시간

        Returns:
            보안 로그 목록
        """
        import time
        import json
        from datetime import datetime, timedelta

        # Redis 키 선택 (레벨 필터가 있으면 해당 레벨, 없으면 전체)
        redis_key = f"security_logs:{level}" if level else "security_logs:all"

        # 시간 범위 설정
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                max_score = end_dt.timestamp()
            except Exception:
                max_score = time.time()
        else:
            max_score = time.time()

        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                min_score = start_dt.timestamp()
            except Exception:
                min_score = max_score - (24 * 60 * 60)  # 24시간 전
        else:
            min_score = max_score - (24 * 60 * 60)  # 기본: 24시간 전

        # Redis에서 로그 조회 (ZSET, 점수 역순)
        try:
            all_logs = self.redis.zrevrangebyscore(
                redis_key,
                max_score,
                min_score,
                withscores=False
            )

            # JSON 파싱
            parsed_logs = []
            for log_data in all_logs:
                try:
                    log_str = decode_bytes(log_data)
                    log_dict = json.loads(log_str)

                    # 이벤트 타입 필터
                    if event_type and log_dict.get('event_type') != event_type:
                        continue

                    parsed_logs.append(log_dict)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse security log JSON: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing security log: {e}")
                    continue

            # 페이지네이션
            total_logs = len(parsed_logs)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_logs = parsed_logs[start_idx:end_idx]

            return {
                "logs": page_logs,
                "total": total_logs,
                "page": page,
                "page_size": page_size,
                "total_pages": calculate_total_pages(total_logs, page_size)
            }

        except Exception as e:
            logger.error(f"Failed to get security logs: {e}")
            return {
                "logs": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }

    async def get_login_history(
        self,
        user_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> dict:
        """로그인 히스토리 조회

        Args:
            user_id: 사용자 ID (None이면 전체 조회)
            start_time: 시작 시간 (ISO 8601 format)
            end_time: 종료 시간 (ISO 8601 format)
            status: 로그인 상태 필터 (success/failed/blocked, None이면 전체)
            page: 페이지 번호
            page_size: 페이지 크기

        Returns:
            로그인 히스토리 목록과 페이지네이션 정보
        """
        import json
        import time

        # Redis 키 결정
        if user_id:
            redis_key = f"login_history:{user_id}"
        else:
            redis_key = "login_history:all"

        # 시간 범위 설정
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                max_score = end_dt.timestamp()
            except Exception:
                max_score = time.time()
        else:
            max_score = time.time()

        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                min_score = start_dt.timestamp()
            except Exception:
                min_score = max_score - (7 * 24 * 60 * 60)  # 7일 전
        else:
            min_score = max_score - (7 * 24 * 60 * 60)  # 기본: 7일 전

        # Redis에서 로그인 히스토리 조회 (ZSET, 점수 역순)
        try:
            all_history = self.redis.zrevrangebyscore(
                redis_key,
                max_score,
                min_score,
                withscores=False
            )

            # JSON 파싱 및 필터링
            parsed_history = []
            for history_data in all_history:
                try:
                    history_str = decode_bytes(history_data)
                    history_dict = json.loads(history_str)

                    # 상태 필터
                    if status and history_dict.get('status') != status:
                        continue

                    parsed_history.append(history_dict)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse login history JSON: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing login history: {e}")
                    continue

            # 페이지네이션
            total_records = len(parsed_history)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_history = parsed_history[start_idx:end_idx]

            return {
                "history": page_history,
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": calculate_total_pages(total_records, page_size)
            }

        except Exception as e:
            logger.error(f"Failed to get login history: {e}")
            return {
                "history": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }
