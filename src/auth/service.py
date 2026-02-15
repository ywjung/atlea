"""Authentication Service

Core service for user authentication, session management, and admin operations.
PostgreSQL-based (via SQLAlchemy repositories).
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
from loguru import logger
import uuid

from .models import (
    User, UserCreate, UserLogin, LoginResponse, TokenPair, Session,
    ProfileUpdate, PasswordChange
)
from .utils import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, verify_token
)
from .brute_force_protection import BruteForceProtection
from .security_logger import SecurityLogger, SecurityEventType
from .password_reset import PasswordResetService
from src.utils.pagination import calculate_total_pages
from src.constants import Limits


class AuthService:
    """인증 서비스

    사용자 등록, 로그인, 세션 관리, 관리자 작업 등을 처리합니다.
    PostgreSQL 기반.
    """

    def __init__(self):
        """초기화

        Args:
        """
        self.brute_force_protection = BruteForceProtection()
        SecurityLogger.initialize()
        self.password_reset_service = PasswordResetService()

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _pg_user_to_pydantic(pg_user) -> User:
        """Convert a PG User ORM object to the Pydantic User model."""
        return User(
            user_id=str(pg_user.id),
            email=pg_user.email,
            username=pg_user.username,
            created_at=pg_user.created_at or datetime.now(timezone.utc),
            last_login=pg_user.last_login,
            is_active=pg_user.is_active,
            role=pg_user.role or "user",
            org_id=str(pg_user.org_id) if pg_user.org_id else "default",
            org_role=pg_user.org_role or "user",
            failed_login_attempts=pg_user.failed_login_attempts or 0,
            locked_until=pg_user.locked_until,
            totp_secret=pg_user.totp_secret,
        )

    @staticmethod
    def _pg_session_to_pydantic(pg_session) -> Session:
        """Convert a PG Session ORM object to the Pydantic Session model."""
        return Session(
            session_id=str(pg_session.id),
            user_id=str(pg_session.user_id),
            created_at=pg_session.created_at or datetime.now(timezone.utc),
            expires_at=pg_session.expires_at,
            ip_address=pg_session.ip_address,
            user_agent=pg_session.user_agent,
        )

    # ── user CRUD ───────────────────────────────────────────

    async def create_user(self, user_data: UserCreate) -> User:
        """사용자 생성"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository
        from ..database.models.user import User as PgUser

        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)

            # 이메일 중복 확인
            existing = await repo.get_by_email(user_data.email)
            if existing:
                raise ValueError("이미 사용 중인 이메일입니다")

            # 비밀번호 해시
            password_hash = hash_password(user_data.password)

            # PG에 저장
            pg_user = PgUser(
                email=user_data.email,
                username=user_data.username,
                hashed_password=password_hash,
                role="user",
                is_active=True,
            )
            session.add(pg_user)
            await session.commit()
            await session.refresh(pg_user)

            user = self._pg_user_to_pydantic(pg_user)

        logger.info(f"User created: {user.user_id} ({user_data.email})")

        SecurityLogger.log_event(
            event_type=SecurityEventType.USER_CREATED,
            level="info",
            user_id=user.user_id,
            email=user_data.email,
            username=user_data.username,
            details={"action": "register"},
        )

        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """사용자 ID로 사용자 조회"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository

        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            return None

        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_id(uid)
            if not pg_user:
                return None
            return self._pg_user_to_pydantic(pg_user)

    async def get_users_by_ids(self, user_ids: list) -> dict:
        """여러 사용자 ID로 배치 조회"""
        if not user_ids:
            return {}

        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository
        from ..database.models.user import User as PgUser
        from sqlalchemy import select

        uuids = []
        for uid in user_ids:
            try:
                uuids.append(uuid.UUID(uid))
            except ValueError:
                continue

        if not uuids:
            return {}

        async with AsyncSessionFactory() as session:
            stmt = select(PgUser).where(PgUser.id.in_(uuids))
            result = await session.execute(stmt)
            pg_users = result.scalars().all()

            users = {}
            for pg_user in pg_users:
                try:
                    users[str(pg_user.id)] = self._pg_user_to_pydantic(pg_user)
                except Exception as e:
                    logger.warning(f"Failed to parse user {pg_user.id}: {e}")

        return users

    def record_login_history(
        self, user_id: str, email: str, ip_address: Optional[str],
        status: str, username: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None
    ):
        """로그인 히스토리 기록 (PostgreSQL)"""
        from ..database.connection import SyncSessionFactory
        from ..database.models.login_history import LoginHistory

        try:
            # user_id가 valid UUID인 경우에만 FK로 저장
            uid = None
            if user_id and user_id != "unknown":
                try:
                    uid = uuid.UUID(user_id)
                except ValueError:
                    uid = None

            if uid is None:
                # FK 제약으로 unknown user_id는 저장 불가 → 로그만 남김
                logger.debug(f"Login history (no FK): email={email}, status={status}")
                return

            with SyncSessionFactory() as session:
                entry = LoginHistory(
                    user_id=uid,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=(status == "success"),
                    failure_reason=failure_reason,
                )
                session.add(entry)
                session.commit()

        except Exception as e:
            logger.error(f"Failed to record login history: {e}")

    # ── authentication ──────────────────────────────────────

    async def authenticate_user(
        self, credentials: UserLogin, ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> dict:
        """사용자 인증"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository
        from ..database.models.session import Session as PgSession

        # IP 차단 체크
        ip_blocked, ip_ttl = self.brute_force_protection.check_ip_blocked(ip_address)
        if ip_blocked:
            logger.warning(f"IP blocked: {ip_address}")
            self.record_login_history(
                user_id="unknown", email=credentials.email,
                ip_address=ip_address, status="blocked",
                failure_reason=f"IP blocked for {ip_ttl // 60} minutes",
            )
            raise ValueError(
                f"IP 주소가 차단되었습니다. {ip_ttl // 60}분 후 다시 시도하세요"
            )

        # 사용자 조회
        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_email(credentials.email)

            if not pg_user:
                self.brute_force_protection.record_failed_attempt(
                    credentials.email, ip_address, None
                )
                self.record_login_history(
                    user_id="unknown", email=credentials.email,
                    ip_address=ip_address, status="failed",
                    failure_reason="Invalid email",
                )
                raise ValueError("유효하지 않은 이메일 또는 비밀번호입니다")

            user_id = str(pg_user.id)
            username = pg_user.username or "unknown"

            # 계정 잠금 체크
            account_blocked, account_ttl = self.brute_force_protection.check_account_blocked(user_id)
            if account_blocked:
                logger.warning(f"Account locked: {credentials.email}")
                self.record_login_history(
                    user_id=user_id, email=credentials.email,
                    ip_address=ip_address, status="blocked",
                    username=username,
                    failure_reason=f"Account locked for {account_ttl // 60} minutes",
                )
                raise ValueError(
                    f"계정이 잠겼습니다. {account_ttl // 60}분 후 다시 시도하세요"
                )

            # 계정 활성화 상태 확인
            if not pg_user.is_active:
                raise ValueError("비활성화된 계정입니다")

            # 비밀번호 확인
            if not verify_password(credentials.password, pg_user.hashed_password):
                self.brute_force_protection.record_failed_attempt(
                    credentials.email, ip_address, user_id
                )
                self.record_login_history(
                    user_id=user_id, email=credentials.email,
                    ip_address=ip_address, status="failed",
                    username=username, failure_reason="Invalid password",
                )
                logger.warning(f"Failed login: {credentials.email}")
                raise ValueError("유효하지 않은 이메일 또는 비밀번호입니다")

            # 2FA 검증 (활성화된 경우)
            from .totp import TOTPService
            totp_service = TOTPService()
            if totp_service.is_enabled():
                totp_secret = pg_user.totp_secret
                if totp_secret:
                    if not credentials.totp_token or not totp_service.verify_token(totp_secret, credentials.totp_token):
                        self.brute_force_protection.record_failed_attempt(
                            credentials.email, ip_address, user_id
                        )
                        self.record_login_history(
                            user_id=user_id, email=credentials.email,
                            ip_address=ip_address, status="failed",
                            username=username, failure_reason="Invalid 2FA code",
                        )
                        logger.warning(f"Failed 2FA: {credentials.email}")
                        raise ValueError("2FA 코드가 유효하지 않습니다")

            # 로그인 성공 - 실패 횟수 초기화
            self.brute_force_protection.reset_account_failures(user_id)

            # 로그인 히스토리 기록 (성공)
            self.record_login_history(
                user_id=user_id, email=credentials.email,
                ip_address=ip_address, status="success",
                username=username,
            )

            # 마지막 로그인 시간 업데이트
            pg_user.last_login = datetime.now(timezone.utc)
            await session.flush()

            user = self._pg_user_to_pydantic(pg_user)

            # 세션 생성
            session_id = uuid.uuid4()
            pg_session = PgSession(
                id=session_id,
                user_id=pg_user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=Limits.SESSION_EXPIRY_DAYS),
                ip_address=ip_address,
                user_agent=user_agent,
                is_active=True,
            )
            session.add(pg_session)
            await session.commit()

        # JWT 토큰 생성
        access_token = create_access_token(
            data={"user_id": user_id, "sub": user.username, "role": user.role}
        )
        refresh_token = create_refresh_token(
            data={"user_id": user_id, "sub": user.username, "session_id": str(session_id)}
        )

        logger.info(f"Login successful: {user.email}")

        SecurityLogger.log_event(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            level="info",
            user_id=user_id,
            email=user.email,
            username=user.username,
            ip_address=ip_address,
            details={"session_id": str(session_id)},
        )

        return {
            "user": user,
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
            },
            "session_id": str(session_id),
        }

    async def logout(
        self, session_id: str, ip_address: Optional[str] = None,
        username: Optional[str] = None
    ):
        """로그아웃"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.session_repository import SessionRepository

        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return

        async with AsyncSessionFactory() as session:
            repo = SessionRepository(session)
            pg_session = await repo.get_by_id(sid)
            if pg_session:
                user_id = str(pg_session.user_id)
                await repo.deactivate(sid)
                await session.commit()

                logger.info(f"Logout: {username or user_id}")

                SecurityLogger.log_event(
                    event_type=SecurityEventType.LOGOUT,
                    level="info",
                    user_id=user_id,
                    username=username,
                    ip_address=ip_address,
                    details={"session_id": session_id},
                )

    async def refresh_access_token(
        self, refresh_token: str, ip_address: Optional[str] = None
    ) -> dict:
        """액세스 토큰 갱신"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository
        from ..repositories.session_repository import SessionRepository

        # Refresh Token 검증
        payload = verify_token(refresh_token)
        if not payload:
            raise ValueError("유효하지 않은 Refresh Token입니다")

        user_id = payload.get("user_id")
        session_id = payload.get("session_id")

        async with AsyncSessionFactory() as session:
            # 세션 확인
            try:
                sid = uuid.UUID(session_id)
            except (ValueError, TypeError):
                raise ValueError("세션이 만료되었습니다")

            s_repo = SessionRepository(session)
            pg_session = await s_repo.get_by_id(sid)
            if not pg_session or not pg_session.is_active:
                raise ValueError("세션이 만료되었습니다")
            if pg_session.expires_at < datetime.now(timezone.utc):
                raise ValueError("세션이 만료되었습니다")

            # 사용자 조회
            try:
                uid = uuid.UUID(user_id)
            except (ValueError, TypeError):
                raise ValueError("사용자를 찾을 수 없습니다")

            u_repo = UserRepository(session)
            pg_user = await u_repo.get_by_id(uid)
            if not pg_user:
                raise ValueError("사용자를 찾을 수 없습니다")

            user = self._pg_user_to_pydantic(pg_user)

        # 새로운 토큰 생성
        new_access_token = create_access_token(
            data={"user_id": user_id, "sub": user.username, "role": user.role}
        )
        new_refresh_token = create_refresh_token(
            data={"user_id": user_id, "sub": user.username, "session_id": session_id}
        )

        logger.info(f"Token refreshed: {user.email}")

        return {
            "user": user,
            "tokens": {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer",
            },
        }

    # ── password management ─────────────────────────────────

    async def request_password_reset(self, email: str) -> str:
        """비밀번호 재설정 요청"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository

        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_email(email)
            if not pg_user:
                raise ValueError("사용자를 찾을 수 없습니다")
            user_id = str(pg_user.id)

        reset_token = await self.password_reset_service.create_reset_token(user_id, email)

        logger.info(f"Password reset requested: {email}")

        SecurityLogger.log_event(
            event_type=SecurityEventType.PASSWORD_RESET_REQUESTED,
            level="info",
            user_id=user_id,
            email=email,
            details={"action": "request_password_reset"},
        )

        return reset_token

    async def reset_password(self, token: str, new_password: str):
        """비밀번호 재설정"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository
        from ..repositories.session_repository import SessionRepository

        user_id = await self.password_reset_service.verify_reset_token(token)
        if not user_id:
            raise ValueError("유효하지 않거나 만료된 토큰입니다")

        password_hash = hash_password(new_password)

        async with AsyncSessionFactory() as session:
            try:
                uid = uuid.UUID(user_id)
            except ValueError:
                raise ValueError("유효하지 않은 사용자 ID입니다")

            u_repo = UserRepository(session)
            pg_user = await u_repo.get_by_id(uid)
            if not pg_user:
                raise ValueError("사용자를 찾을 수 없습니다")

            pg_user.hashed_password = password_hash

            # 모든 세션 무효화
            s_repo = SessionRepository(session)
            await s_repo.deactivate_all_for_user(uid)

            email = pg_user.email
            await session.commit()

        logger.info(f"Password reset: {user_id}")

        SecurityLogger.log_event(
            event_type=SecurityEventType.PASSWORD_RESET_COMPLETED,
            level="info",
            user_id=user_id,
            email=email,
            details={"action": "reset_password"},
        )

    async def update_profile(self, user_id: str, username: Optional[str] = None) -> User:
        """프로필 업데이트"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository

        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise ValueError("사용자를 찾을 수 없습니다")

        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_id(uid)
            if not pg_user:
                raise ValueError("사용자를 찾을 수 없습니다")

            if username:
                pg_user.username = username

            await session.commit()
            await session.refresh(pg_user)
            user = self._pg_user_to_pydantic(pg_user)

        logger.info(f"Profile updated: {user_id}")
        return user

    async def change_password(
        self, user_id: str, old_password: str, new_password: str
    ):
        """비밀번호 변경"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository
        from ..repositories.session_repository import SessionRepository

        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise ValueError("사용자를 찾을 수 없습니다")

        async with AsyncSessionFactory() as session:
            u_repo = UserRepository(session)
            pg_user = await u_repo.get_by_id(uid)
            if not pg_user:
                raise ValueError("사용자를 찾을 수 없습니다")

            if not verify_password(old_password, pg_user.hashed_password):
                raise ValueError("현재 비밀번호가 일치하지 않습니다")

            pg_user.hashed_password = hash_password(new_password)

            # 모든 세션 무효화
            s_repo = SessionRepository(session)
            await s_repo.deactivate_all_for_user(uid)

            email = pg_user.email
            await session.commit()

        logger.info(f"Password changed: {user_id}")

        SecurityLogger.log_event(
            event_type=SecurityEventType.PASSWORD_CHANGED,
            level="info",
            user_id=user_id,
            email=email,
            details={"action": "change_password"},
        )

    # ── session management ──────────────────────────────────

    async def get_user_sessions(self, user_id: str) -> List[Session]:
        """사용자 세션 목록 조회"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.session_repository import SessionRepository

        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            return []

        async with AsyncSessionFactory() as session:
            repo = SessionRepository(session)
            pg_sessions = await repo.get_active_by_user(uid)
            return [self._pg_session_to_pydantic(s) for s in pg_sessions]

    async def revoke_session(self, user_id: str, session_id: str) -> bool:
        """세션 무효화"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.session_repository import SessionRepository

        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            return False

        async with AsyncSessionFactory() as session:
            repo = SessionRepository(session)
            pg_session = await repo.get_by_id(sid)
            if not pg_session:
                return False

            if str(pg_session.user_id) != user_id:
                raise ValueError("이 세션에 대한 권한이 없습니다")

            await repo.deactivate(sid)
            await session.commit()

        logger.info(f"Session revoked: {session_id}")
        return True

    async def revoke_all_sessions(self, user_id: str) -> int:
        """사용자의 모든 세션 무효화"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.session_repository import SessionRepository

        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            return 0

        async with AsyncSessionFactory() as session:
            repo = SessionRepository(session)
            count = await repo.deactivate_all_for_user(uid)
            await session.commit()

        logger.info(f"All sessions revoked for user {user_id}: {count} sessions")
        return count

    # ============= Admin Methods =============

    async def get_system_stats(self) -> dict:
        """시스템 통계 조회 (PostgreSQL)"""
        from ..database.connection import AsyncSessionFactory
        from ..database.models.user import User as PgUser
        from ..database.models.session import Session as PgSession
        from ..database.models.security_log import SecurityLog
        from sqlalchemy import select, func

        async with AsyncSessionFactory() as session:
            # 사용자 통계
            total_users = (await session.execute(
                select(func.count()).select_from(PgUser)
            )).scalar_one()

            active_users = (await session.execute(
                select(func.count()).select_from(PgUser).where(PgUser.is_active == True)
            )).scalar_one()

            admin_users = (await session.execute(
                select(func.count()).select_from(PgUser).where(PgUser.role == "admin")
            )).scalar_one()

            # 활성 세션 수
            now = datetime.now(timezone.utc)
            active_sessions = (await session.execute(
                select(func.count()).select_from(PgSession).where(
                    PgSession.is_active == True,
                    PgSession.expires_at > now,
                )
            )).scalar_one()

            # 최근 24시간 로그인
            twenty_four_hours_ago = now - timedelta(hours=24)
            recent_logins_24h = (await session.execute(
                select(func.count()).select_from(PgUser).where(
                    PgUser.last_login > twenty_four_hours_ago
                )
            )).scalar_one()

            # 최근 로그인한 사용자 10명
            recent_stmt = (
                select(PgUser)
                .where(PgUser.last_login.isnot(None))
                .order_by(PgUser.last_login.desc())
                .limit(10)
            )
            recent_users = (await session.execute(recent_stmt)).scalars().all()
            recent_logins = [
                {
                    "user_id": str(u.id),
                    "email": u.email,
                    "username": u.username,
                    "last_login": u.last_login.isoformat() if u.last_login else None,
                    "role": u.role,
                }
                for u in recent_users
            ]

            # 보안 이벤트 수
            try:
                security_events = (await session.execute(
                    select(func.count()).select_from(SecurityLog)
                )).scalar_one()
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_all_users(self, page: int = 1, page_size: int = 50) -> dict:
        """모든 사용자 조회"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository

        offset = (page - 1) * page_size

        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_users, total_users = await repo.search(offset=offset, limit=page_size)
            users = [self._pg_user_to_pydantic(u).model_dump() for u in pg_users]

        return {
            "users": users,
            "total": total_users,
            "page": page,
            "page_size": page_size,
            "total_pages": calculate_total_pages(total_users, page_size),
        }

    async def update_user_status(
        self, user_id: str, is_active: bool, admin_user_id: str
    ) -> User:
        """사용자 활성화 상태 변경"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository
        from ..repositories.session_repository import SessionRepository

        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise ValueError("사용자를 찾을 수 없습니다")

        async with AsyncSessionFactory() as session:
            u_repo = UserRepository(session)
            pg_user = await u_repo.get_by_id(uid)
            if not pg_user:
                raise ValueError("사용자를 찾을 수 없습니다")

            pg_user.is_active = is_active

            # 비활성화 시 모든 세션 무효화
            if not is_active:
                s_repo = SessionRepository(session)
                await s_repo.deactivate_all_for_user(uid)

            await session.commit()
            await session.refresh(pg_user)
            user = self._pg_user_to_pydantic(pg_user)

        logger.info(f"User status updated: {user_id} -> {is_active}")

        SecurityLogger.log_event(
            event_type=SecurityEventType.USER_STATUS_CHANGED,
            level="info",
            user_id=admin_user_id,
            details={
                "target_user_id": user_id,
                "is_active": is_active,
                "action": "update_user_status",
            },
        )

        return user

    async def update_user_role(
        self, user_id: str, role: str, admin_user_id: str
    ) -> User:
        """사용자 역할 변경"""
        if role not in ["user", "admin"]:
            raise ValueError("유효하지 않은 역할입니다")

        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository

        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise ValueError("사용자를 찾을 수 없습니다")

        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_id(uid)
            if not pg_user:
                raise ValueError("사용자를 찾을 수 없습니다")

            pg_user.role = role
            await session.commit()
            await session.refresh(pg_user)
            user = self._pg_user_to_pydantic(pg_user)

        logger.info(f"User role updated: {user_id} -> {role}")

        SecurityLogger.log_event(
            event_type=SecurityEventType.USER_ROLE_CHANGED,
            level="info",
            user_id=admin_user_id,
            details={
                "target_user_id": user_id,
                "new_role": role,
                "action": "update_user_role",
            },
        )

        return user

    async def delete_user(self, user_id: str, admin_user_id: str):
        """사용자 삭제"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.user_repository import UserRepository

        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise ValueError("사용자를 찾을 수 없습니다")

        async with AsyncSessionFactory() as session:
            repo = UserRepository(session)
            pg_user = await repo.get_by_id(uid)
            if not pg_user:
                raise ValueError("사용자를 찾을 수 없습니다")

            email = pg_user.email
            await session.delete(pg_user)
            await session.commit()

        logger.info(f"User deleted: {user_id}")

        SecurityLogger.log_event(
            event_type=SecurityEventType.USER_DELETED,
            level="warning",
            user_id=admin_user_id,
            details={
                "target_user_id": user_id,
                "target_email": email,
                "action": "delete_user",
            },
        )

    # ── security logs & login history ───────────────────────

    def _match_event_type(self, log_event_type: str, filter_event_type: str) -> bool:
        """이벤트 타입 매칭 (이전 형식 호환)"""
        if log_event_type == filter_event_type:
            return True

        legacy_to_new = {
            "login_success": "AUTH_LOGIN_SUCCESS",
            "login_failed": "AUTH_LOGIN_FAILED",
            "logout": "AUTH_LOGOUT",
            "user_created": "ACCOUNT_CREATED",
            "user_deleted": "ACCOUNT_DELETED",
            "user_status_changed": "ACCOUNT_STATUS_CHANGED",
            "user_role_changed": "ACCOUNT_ROLE_CHANGED",
            "password_reset_requested": "PASSWORD_RESET_REQUESTED",
            "password_reset_completed": "PASSWORD_RESET_COMPLETED",
            "password_changed": "PASSWORD_CHANGED",
        }

        if log_event_type in legacy_to_new:
            return legacy_to_new[log_event_type] == filter_event_type

        return False

    async def get_security_logs(
        self,
        page: int = 1,
        page_size: int = 100,
        level: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict:
        """보안 로그 조회 (PostgreSQL)"""
        from ..database.connection import AsyncSessionFactory
        from ..repositories.security_log_repository import SecurityLogRepository

        # 시간 범위 파싱
        start_date = None
        end_date = None

        if start_time:
            try:
                start_date = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except Exception:
                start_date = datetime.now(timezone.utc) - timedelta(hours=24)
        else:
            start_date = datetime.now(timezone.utc) - timedelta(hours=24)

        if end_time:
            try:
                end_date = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except Exception:
                end_date = datetime.now(timezone.utc)
        else:
            end_date = datetime.now(timezone.utc)

        offset = (page - 1) * page_size

        async with AsyncSessionFactory() as session:
            repo = SecurityLogRepository(session)
            logs, total = await repo.search(
                level=level,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                offset=offset,
                limit=page_size,
            )

            parsed_logs = []
            for log in logs:
                log_dict = {
                    "timestamp": log.created_at.isoformat() if log.created_at else None,
                    "event_type": log.event_type,
                    "level": log.level,
                    "user_id": log.user_id or "anonymous",
                    "ip_address": log.ip_address or "unknown",
                    "message": log.message or "",
                }
                if log.details:
                    log_dict.update(log.details)
                parsed_logs.append(log_dict)

        return {
            "logs": parsed_logs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": calculate_total_pages(total, page_size),
        }

    async def get_login_history(
        self,
        user_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """로그인 히스토리 조회 (PostgreSQL)"""
        from ..database.connection import AsyncSessionFactory
        from ..database.models.login_history import LoginHistory
        from sqlalchemy import select, func

        # 시간 범위 파싱
        start_date = None
        end_date = None

        if start_time:
            try:
                start_date = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except Exception:
                start_date = datetime.now(timezone.utc) - timedelta(days=7)
        else:
            start_date = datetime.now(timezone.utc) - timedelta(days=7)

        if end_time:
            try:
                end_date = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except Exception:
                end_date = datetime.now(timezone.utc)
        else:
            end_date = datetime.now(timezone.utc)

        async with AsyncSessionFactory() as session:
            # 기본 쿼리
            stmt = select(LoginHistory).where(
                LoginHistory.created_at >= start_date,
                LoginHistory.created_at <= end_date,
            )
            count_stmt = (
                select(func.count())
                .select_from(LoginHistory)
                .where(
                    LoginHistory.created_at >= start_date,
                    LoginHistory.created_at <= end_date,
                )
            )

            # 사용자 필터
            if user_id:
                try:
                    uid = uuid.UUID(user_id)
                    stmt = stmt.where(LoginHistory.user_id == uid)
                    count_stmt = count_stmt.where(LoginHistory.user_id == uid)
                except ValueError:
                    return {
                        "history": [], "total": 0, "page": page,
                        "page_size": page_size, "total_pages": 0,
                    }

            # 상태 필터
            if status:
                if status == "success":
                    stmt = stmt.where(LoginHistory.success == True)
                    count_stmt = count_stmt.where(LoginHistory.success == True)
                elif status in ("failed", "blocked"):
                    stmt = stmt.where(LoginHistory.success == False)
                    count_stmt = count_stmt.where(LoginHistory.success == False)

            total = (await session.execute(count_stmt)).scalar_one()

            offset = (page - 1) * page_size
            stmt = stmt.order_by(LoginHistory.created_at.desc()).offset(offset).limit(page_size)
            entries = (await session.execute(stmt)).scalars().all()

            # Pydantic User model 조회용
            from ..database.models.user import User as PgUser

            # 사용자 이름 일괄 조회
            user_ids = list({e.user_id for e in entries})
            user_map = {}
            if user_ids:
                u_stmt = select(PgUser).where(PgUser.id.in_(user_ids))
                u_result = (await session.execute(u_stmt)).scalars().all()
                user_map = {u.id: u for u in u_result}

            history = []
            for entry in entries:
                pg_user = user_map.get(entry.user_id)
                history.append({
                    "timestamp": entry.created_at.isoformat().replace("+00:00", "Z") if entry.created_at else None,
                    "email": pg_user.email if pg_user else "unknown",
                    "username": pg_user.username if pg_user else "unknown",
                    "ip_address": entry.ip_address or "unknown",
                    "status": "success" if entry.success else "failed",
                    "user_agent": entry.user_agent,
                    "failure_reason": entry.failure_reason,
                    "user_id": str(entry.user_id),
                })

        return {
            "history": history,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": calculate_total_pages(total, page_size),
        }
