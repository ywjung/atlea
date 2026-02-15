"""Authentication utilities

Password hashing, JWT token generation and verification utilities.
"""

from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from fastapi import Request, HTTPException
import os

# JWT 설정 (환경 변수에서 읽기)
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY environment variable is required. "
        "Please set a strong secret key in your .env file. "
        "You can generate one using: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )

# SECRET_KEY 보안 검증
if len(SECRET_KEY) < 32:
    raise ValueError(
        f"JWT_SECRET_KEY must be at least 32 characters long for security. "
        f"Current length: {len(SECRET_KEY)}. "
        f"Generate a strong key using: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def hash_password(password: str) -> str:
    """비밀번호 해싱

    Args:
        password: 평문 비밀번호

    Returns:
        bcrypt 해시된 비밀번호
    """
    import bcrypt
    # Convert to bytes and hash
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증

    Args:
        plain_password: 평문 비밀번호
        hashed_password: 해시된 비밀번호

    Returns:
        비밀번호 일치 여부
    """
    import bcrypt
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """Access Token 생성

    Args:
        data: 토큰에 포함할 데이터 (예: {"user_id": "xxx"})
        expires_delta: 만료 시간 (기본: 1시간)

    Returns:
        JWT access token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def create_refresh_token(data: Dict) -> str:
    """Refresh Token 생성

    Args:
        data: 토큰에 포함할 데이터 (예: {"user_id": "xxx"})

    Returns:
        JWT refresh token
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def verify_token(
    token: str,
    expected_type: str = "access",

) -> Optional[Dict]:
    """토큰 검증 및 디코딩

    Args:
        token: JWT 토큰
        expected_type: 예상되는 토큰 타입 ("access" 또는 "refresh")

    Returns:
        토큰 페이로드 딕셔너리 (검증 실패 시 None)
    """
    try:
        # 블랙리스트 확인 (PostgreSQL 기반)
        from .token_blacklist import TokenBlacklist
        blacklist = TokenBlacklist()
        if blacklist.is_blacklisted(token):
            from loguru import logger
            logger.warning("Attempt to use blacklisted token")
            return None

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 토큰 타입 확인
        if payload.get("type") != expected_type:
            return None

        return payload

    except JWTError:
        return None


def create_token_pair(user_id: str, username: Optional[str] = None) -> Dict[str, str]:
    """Access Token + Refresh Token 쌍 생성

    Args:
        user_id: 사용자 ID
        username: 사용자명 (선택적)

    Returns:
        토큰 쌍 딕셔너리
    """
    token_data = {"user_id": user_id}
    if username:
        token_data["username"] = username

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


def get_user(user_id: str) -> Optional[Dict]:
    """PostgreSQL에서 사용자 정보 조회

    Args:
        user_id: 사용자 ID

    Returns:
        사용자 정보 딕셔너리 (사용자 없으면 None)
    """
    try:
        from ..database.connection import SyncSessionFactory
        from ..database.models.user import User
        from sqlalchemy import select

        with SyncSessionFactory() as session:
            stmt = select(User).where(User.id == user_id)
            result = session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                return None

            return {
                "user_id": str(user.id),
                "email": user.email or "",
                "username": user.username or "",
                "hashed_password": user.hashed_password or "",
                "role": user.role or "user",
                "is_active": str(user.is_active) if user.is_active is not None else "true",
                "org_id": str(user.org_id) if user.org_id else "default",
                "org_role": user.org_role or "user",
                "created_at": user.created_at.isoformat() if user.created_at else "",
                "updated_at": user.updated_at.isoformat() if user.updated_at else "",
            }
    except Exception:
        return None


def update_user_fields(user_id: str, **fields) -> bool:
    """PostgreSQL에서 사용자 필드 업데이트

    Args:
        user_id: 사용자 ID
        **fields: 업데이트할 필드 (예: org_id="abc", org_role="admin")

    Returns:
        업데이트 성공 여부
    """
    if not fields:
        return False

    try:
        from ..database.connection import SyncSessionFactory
        from ..database.models.user import User
        from sqlalchemy import update

        with SyncSessionFactory() as session:
            stmt = update(User).where(User.id == user_id).values(**fields)
            result = session.execute(stmt)
            session.commit()
            return result.rowcount > 0
    except Exception:
        return False


def get_user_field(user_id: str, field: str) -> Optional[str]:
    """PostgreSQL에서 사용자 특정 필드 조회

    Args:
        user_id: 사용자 ID
        field: 필드 이름 (예: "org_id", "org_role")

    Returns:
        필드 값 (문자열) 또는 None
    """
    try:
        from ..database.connection import SyncSessionFactory
        from ..database.models.user import User
        from sqlalchemy import select

        with SyncSessionFactory() as session:
            stmt = select(getattr(User, field)).where(User.id == user_id)
            result = session.execute(stmt)
            val = result.scalar_one_or_none()
            return str(val) if val is not None else None
    except Exception:
        return None


def extract_token_from_request(request: Request) -> Optional[str]:
    """Request에서 JWT 토큰 추출

    Authorization 헤더 또는 쿠키에서 토큰을 추출합니다.

    Args:
        request: FastAPI Request 객체

    Returns:
        JWT 토큰 문자열 (없으면 None)
    """
    # Authorization 헤더에서 시도
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]

    # 쿠키에서 시도
    return request.cookies.get("access_token")


def get_current_user_from_request(request: Request) -> Dict:
    """Request에서 현재 사용자 정보 추출 및 검증

    Args:
        request: FastAPI Request 객체

    Returns:
        사용자 정보 딕셔너리

    Raises:
        HTTPException: 인증 실패 시 401 또는 403
    """
    # 토큰 추출
    token = extract_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # 토큰 검증 (블랙리스트 확인 포함)
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    # 사용자 정보 조회
    user = get_user(user_data["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_admin(request: Request) -> Dict:
    """관리자 권한 확인

    Args:
        request: FastAPI Request 객체

    Returns:
        관리자 사용자 정보 딕셔너리

    Raises:
        HTTPException: 인증 실패 또는 권한 없음 시 401 또는 403
    """
    user = get_current_user_from_request(request)

    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    return user
