"""Authentication utilities

Password hashing, JWT token generation and verification utilities.
"""

from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from fastapi import Request, HTTPException
from redis import Redis
import os

# 비밀번호 해싱 컨텍스트
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
        "JWT_SECRET_KEY must be at least 32 characters long for security. "
        "Current length: {len(SECRET_KEY)}. "
        "Generate a strong key using: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
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
    redis_client: Optional[Redis] = None
) -> Optional[Dict]:
    """토큰 검증 및 디코딩

    Args:
        token: JWT 토큰
        expected_type: 예상되는 토큰 타입 ("access" 또는 "refresh")
        redis_client: Redis 클라이언트 (블랙리스트 확인용, 선택적)

    Returns:
        토큰 페이로드 딕셔너리 (검증 실패 시 None)
    """
    try:
        # 블랙리스트 확인 (Redis 사용 가능한 경우)
        if redis_client:
            from .token_blacklist import TokenBlacklist
            blacklist = TokenBlacklist(redis_client)
            if blacklist.is_blacklisted(token):
                from loguru import logger
                logger.warning(f"Attempt to use blacklisted token")
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


def get_user(user_id: str, redis_client) -> Optional[Dict]:
    """Redis에서 사용자 정보 조회

    Args:
        user_id: 사용자 ID
        redis_client: Redis 클라이언트 인스턴스

    Returns:
        사용자 정보 딕셔너리 (사용자 없으면 None)
    """
    try:
        user_data = redis_client.hgetall(f"user:{user_id}")
        if not user_data:
            return None

        # bytes를 문자열로 변환
        user_dict = {}
        for key, value in user_data.items():
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            value_str = value.decode('utf-8') if isinstance(value, bytes) else value
            user_dict[key_str] = value_str

        return user_dict
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


def get_current_user_from_request(request: Request, redis_client) -> Dict:
    """Request에서 현재 사용자 정보 추출 및 검증

    Args:
        request: FastAPI Request 객체
        redis_client: Redis 클라이언트 인스턴스

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
    user_data = verify_token(token, redis_client=redis_client)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    # 사용자 정보 조회
    user = get_user(user_data["user_id"], redis_client)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_admin(request: Request, redis_client) -> Dict:
    """관리자 권한 확인

    Args:
        request: FastAPI Request 객체
        redis_client: Redis 클라이언트 인스턴스

    Returns:
        관리자 사용자 정보 딕셔너리

    Raises:
        HTTPException: 인증 실패 또는 권한 없음 시 401 또는 403
    """
    user = get_current_user_from_request(request, redis_client)

    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    return user
