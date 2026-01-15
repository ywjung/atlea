"""Authentication middleware

FastAPI dependencies for JWT token authentication and authorization.
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from .utils import verify_token
from .service import AuthService

# HTTP Bearer 토큰 스키마
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """현재 사용자 조회 (JWT 검증)

    Args:
        request: FastAPI Request 객체
        credentials: HTTP Bearer 인증 정보

    Returns:
        사용자 정보 딕셔너리

    Raises:
        HTTPException: 인증 실패 시 401
    """

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 사용자 조회를 위한 cache_manager 가져오기
    cache_manager = request.app.state.cache_manager

    # JWT 토큰 검증 (블랙리스트 확인 포함)
    token = credentials.credentials
    payload = verify_token(token, expected_type="access", redis_client=cache_manager.redis)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 사용자 조회
    auth_service = AuthService(cache_manager.redis)

    user_id = payload.get("user_id")
    user = await auth_service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다"
        )

    return user.model_dump()


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """활성 사용자만 허용

    Args:
        current_user: 현재 사용자 정보

    Returns:
        활성 사용자 정보

    Raises:
        HTTPException: 비활성 계정 시 403
    """

    if not current_user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다"
        )

    return current_user


async def require_admin(
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """관리자 권한 필요 (시스템 관리자)

    Args:
        current_user: 현재 활성 사용자

    Returns:
        관리자 사용자 정보

    Raises:
        HTTPException: 권한 부족 시 403
    """

    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다"
        )

    return current_user


async def require_org_access(
    org_id: str,
    current_user: dict = Depends(get_current_active_user)
) -> bool:
    """조직 접근 권한 검증

    사용자가 지정된 조직에 접근할 수 있는지 검증합니다.
    시스템 관리자는 모든 조직에 접근 가능하고,
    일반 사용자는 자신의 조직에만 접근 가능합니다.

    Args:
        org_id: 접근하려는 조직 ID
        current_user: 현재 활성 사용자

    Returns:
        True (접근 가능)

    Raises:
        HTTPException: 접근 권한이 없을 경우 403
    """
    # 시스템 관리자는 모든 조직 접근 가능
    if current_user.get("role") == "admin":
        return True

    # 일반 사용자는 자신의 조직만 접근 가능
    user_org_id = current_user.get("org_id")
    if user_org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="해당 조직에 접근할 수 없습니다"
        )

    return True


async def require_org_admin_or_system_admin(
    org_id: str,
    current_user: dict = Depends(get_current_active_user)
) -> bool:
    """조직 관리자 또는 시스템 관리자 권한 검증

    조직 관리 작업을 수행하기 위한 권한을 검증합니다.
    시스템 관리자는 모든 조직을 관리할 수 있고,
    조직 관리자는 자신의 조직만 관리할 수 있습니다.

    Args:
        org_id: 관리하려는 조직 ID
        current_user: 현재 활성 사용자

    Returns:
        True (권한 있음)

    Raises:
        HTTPException: 권한이 없을 경우 403
    """
    # 시스템 관리자는 모든 조직 관리 가능
    if current_user.get("role") == "admin":
        return True

    # 사용자의 조직이 일치하는지 확인
    user_org_id = current_user.get("org_id")
    if user_org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="조직 관리자 권한이 필요합니다"
        )

    # 조직 관리자 권한 확인
    org_role = current_user.get("org_role")
    if org_role != "org_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="조직 관리자 권한이 필요합니다"
        )

    return True
