"""Organization Management API Router

Endpoints for organization CRUD operations and member management.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Dict
from pydantic import BaseModel, Field
from ..auth.middleware import (
    get_current_active_user,
    require_admin,
    require_org_access,
    require_org_admin_or_system_admin
)
from ..organization_manager import OrganizationManager
from loguru import logger

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


# ============================================================================
# Helper Functions
# ============================================================================

def get_safe_error_message(error: Exception, context: str = "") -> str:
    """
    Get sanitized error message for user display
    """
    error_type = type(error).__name__
    logger.error(f"Error in {context}: {error_type}: {str(error)}")

    error_messages = {
        "ValueError": "잘못된 입력값입니다.",
        "KeyError": "요청한 리소스를 찾을 수 없습니다.",
        "ConnectionError": "서비스 연결에 실패했습니다.",
        "TimeoutError": "요청 시간이 초과되었습니다.",
        "PermissionError": "접근 권한이 없습니다.",
    }

    return error_messages.get(
        error_type,
        "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    )


# ============================================================================
# Pydantic Models
# ============================================================================

class OrganizationCreate(BaseModel):
    """조직 생성 요청"""
    name: str = Field(..., min_length=1, max_length=100, description="조직 이름")
    description: str = Field("", description="조직 설명")


class OrganizationUpdate(BaseModel):
    """조직 업데이트 요청"""
    name: str | None = Field(None, min_length=1, max_length=100, description="조직 이름")
    description: str | None = Field(None, description="조직 설명")
    is_active: bool | None = Field(None, description="활성화 여부")


class OrganizationResponse(BaseModel):
    """조직 응답"""
    id: str
    name: str
    description: str
    created_at: str
    created_by: str
    updated_at: str
    is_active: str
    member_count: str


class MemberAdd(BaseModel):
    """멤버 추가 요청"""
    user_id: str = Field(..., description="추가할 사용자 ID")


class MemberRemove(BaseModel):
    """멤버 제거 요청"""
    user_id: str = Field(..., description="제거할 사용자 ID")


# ============================================================================
# Organization CRUD Endpoints (System Admin Only)
# ============================================================================

@router.post("", response_model=Dict, dependencies=[Depends(require_admin)])
async def create_organization(
    request: Request,
    org_data: OrganizationCreate,
    current_user: dict = Depends(get_current_active_user)
):
    """조직 생성 (시스템 관리자 전용)

    Args:
        request: FastAPI Request 객체
        org_data: 조직 생성 데이터
        current_user: 현재 사용자 (시스템 관리자)

    Returns:
        생성된 조직 ID

    Raises:
        HTTPException: 조직 생성 실패 시
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    try:
        org_id = org_manager.create_organization(
            name=org_data.name,
            description=org_data.description,
            created_by=current_user["user_id"]
        )

        return {
            "success": True,
            "message": "조직이 생성되었습니다",
            "org_id": org_id
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "create organization"))


@router.get("", response_model=Dict)
async def list_organizations(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """조직 목록 조회

    시스템 관리자는 모든 조직을 볼 수 있고,
    일반 사용자는 자신의 조직만 볼 수 있습니다.

    Args:
        request: FastAPI Request 객체
        current_user: 현재 사용자

    Returns:
        조직 목록
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    # 시스템 관리자는 모든 조직 조회
    if current_user.get("role") == "admin":
        organizations = org_manager.list_organizations()
    else:
        # 일반 사용자는 자신의 조직만 조회
        user_org_id = current_user.get("org_id")
        org = org_manager.get_organization(user_org_id)
        organizations = [org] if org else []

    return {
        "success": True,
        "organizations": organizations,
        "count": len(organizations)
    }


@router.get("/{org_id}", response_model=Dict)
async def get_organization(
    request: Request,
    org_id: str,
    current_user: dict = Depends(get_current_active_user),
    _: bool = Depends(require_org_access)
):
    """조직 상세 조회

    Args:
        request: FastAPI Request 객체
        org_id: 조직 ID
        current_user: 현재 사용자
        _: 조직 접근 권한 검증

    Returns:
        조직 상세 정보

    Raises:
        HTTPException: 조직을 찾을 수 없을 경우 404
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    org = org_manager.get_organization(org_id)

    if not org:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다")

    # 조직 통계 추가
    stats = org_manager.get_organization_stats(org_id)
    org["stats"] = stats

    return {
        "success": True,
        "organization": org
    }


@router.put("/{org_id}", response_model=Dict, dependencies=[Depends(require_admin)])
async def update_organization(
    request: Request,
    org_id: str,
    org_data: OrganizationUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    """조직 수정 (시스템 관리자 전용)

    Args:
        request: FastAPI Request 객체
        org_id: 조직 ID
        org_data: 조직 업데이트 데이터
        current_user: 현재 사용자 (시스템 관리자)

    Returns:
        업데이트 성공 여부

    Raises:
        HTTPException: 조직 업데이트 실패 시
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    try:
        success = org_manager.update_organization(
            org_id=org_id,
            name=org_data.name,
            description=org_data.description,
            is_active=org_data.is_active
        )

        return {
            "success": success,
            "message": "조직이 업데이트되었습니다" if success else "업데이트할 내용이 없습니다"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "update organization"))


@router.delete("/{org_id}", response_model=Dict, dependencies=[Depends(require_admin)])
async def delete_organization(
    request: Request,
    org_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """조직 삭제 (시스템 관리자 전용)

    Args:
        request: FastAPI Request 객체
        org_id: 조직 ID
        current_user: 현재 사용자 (시스템 관리자)

    Returns:
        삭제 성공 여부

    Raises:
        HTTPException: 조직 삭제 실패 시
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    try:
        # 기본 조직은 삭제 불가
        if org_id == "default":
            raise HTTPException(
                status_code=400, 
                detail="기본 조직은 삭제할 수 없습니다. 기본 조직은 시스템에 필수적입니다."
            )

        success = org_manager.delete_organization(org_id)

        return {
            "success": success,
            "message": "조직이 삭제되었습니다"
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "delete organization"))


# ============================================================================
# Member Management Endpoints (Org Admin or System Admin)
# ============================================================================

@router.get("/{org_id}/members", response_model=Dict)
async def get_organization_members(
    request: Request,
    org_id: str,
    current_user: dict = Depends(get_current_active_user),
    _: bool = Depends(require_org_access)
):
    """조직 멤버 목록 조회

    Args:
        request: FastAPI Request 객체
        org_id: 조직 ID
        current_user: 현재 사용자
        _: 조직 접근 권한 검증

    Returns:
        멤버 목록
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    members = org_manager.get_members(org_id)
    admins = org_manager.get_org_admins(org_id)

    # 멤버 정보 배치 조회 (Pipeline 사용으로 N+1 쿼리 제거)
    from ..auth.service import AuthService
    auth_service = AuthService(cache_manager.redis)

    # 모든 멤버 정보를 한 번의 Pipeline으로 조회
    users_dict = await auth_service.get_users_by_ids(list(members))

    member_list = []
    for user_id in members:
        user = users_dict.get(user_id)
        if user:
            member_list.append({
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "is_org_admin": user_id in admins,
                "org_role": user.org_role
            })

    return {
        "success": True,
        "members": member_list,
        "count": len(member_list)
    }


@router.post("/{org_id}/members", response_model=Dict)
async def add_organization_member(
    request: Request,
    org_id: str,
    member_data: MemberAdd,
    current_user: dict = Depends(get_current_active_user)
):
    """조직 멤버 추가 또는 이동
    
    - 조직 관리자/시스템 관리자: 다른 사용자를 추가/이동 가능
    - 일반 사용자: 자기 자신만 이동 가능
    
    사용자가 이미 다른 조직에 속한 경우, 자동으로 이전 조직에서 제거하고 새 조직으로 이동합니다.

    Args:
        request: FastAPI Request 객체
        org_id: 조직 ID
        member_data: 멤버 추가 데이터
        current_user: 현재 사용자

    Returns:
        추가 또는 이동 성공 여부

    Raises:
        HTTPException: 권한 없음 또는 멤버 추가/이동 실패 시
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)
    
    # 권한 확인: 자기 자신을 이동하는 경우는 누구나 가능, 다른 사람을 추가하는 경우는 관리자만 가능
    is_self_transfer = member_data.user_id == current_user["user_id"]
    is_system_admin = current_user.get("role") == "admin"
    is_org_admin = (
        current_user.get("org_id") == org_id and 
        current_user.get("org_role") == "org_admin"
    )
    
    # 다른 사람을 추가하려는 경우 관리자 권한 필요
    if not is_self_transfer and not is_system_admin and not is_org_admin:
        raise HTTPException(
            status_code=403, 
            detail="다른 사용자를 추가하려면 조직 관리자 권한이 필요합니다"
        )

    try:
        # 사용자 존재 확인
        from ..auth.service import AuthService
        auth_service = AuthService(cache_manager.redis)
        user = await auth_service.get_user_by_id(member_data.user_id)

        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

        # 사용자의 현재 조직 확인
        user_key = f'user:{member_data.user_id}'
        current_org_id = cache_manager.redis.hget(user_key, 'org_id')
        current_org_id = current_org_id.decode('utf-8') if current_org_id else None
        
        was_transferred = False
        old_org_name = None

        # 이미 다른 조직에 속한 경우 이전 조직에서 제거
        if current_org_id and current_org_id != org_id:
            # 이전 조직 이름 가져오기 (메시지용)
            old_org = org_manager.get_organization(current_org_id)
            old_org_name = old_org.get('name') if old_org else current_org_id
            
            # 이전 조직에서 제거
            org_manager.remove_member(current_org_id, member_data.user_id)
            was_transferred = True

        # 새 조직에 멤버 추가
        success = org_manager.add_member(org_id, member_data.user_id)

        # 사용자의 org_id 업데이트
        if success or was_transferred:
            cache_manager.redis.hset(user_key, 'org_id', org_id)
            
            # 일반 사용자로 초기화 (이전 조직에서 관리자였을 수 있음)
            cache_manager.redis.hset(user_key, 'org_role', 'user')

        # 응답 메시지 생성
        if was_transferred:
            if is_self_transfer:
                message = f"'{old_org_name}'에서 이동되었습니다"
            else:
                message = f"멤버가 '{old_org_name}'에서 이동되었습니다"
        elif success:
            message = "멤버가 추가되었습니다"
        else:
            message = "이미 조직의 멤버입니다"

        return {
            "success": True,
            "message": message,
            "transferred": was_transferred,
            "is_self_transfer": is_self_transfer
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "add member"))


@router.delete("/{org_id}/members/{user_id}", response_model=Dict)
async def remove_organization_member(
    request: Request,
    org_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """조직 멤버 제거
    
    - 조직 관리자/시스템 관리자: 다른 사용자 제거 가능
    - 일반 사용자: 자기 자신만 제거 가능
    
    사용자를 조직에서 제거하고 기본 조직으로 이동합니다.

    Args:
        request: FastAPI Request 객체
        org_id: 조직 ID
        user_id: 제거할 사용자 ID
        current_user: 현재 사용자

    Returns:
        제거 성공 여부

    Raises:
        HTTPException: 권한 없음 또는 멤버 제거 실패 시
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    # 권한 확인: 자기 자신을 제거하는 경우는 누구나 가능, 다른 사람을 제거하는 경우는 관리자만 가능
    is_self_removal = user_id == current_user["user_id"]
    is_system_admin = current_user.get("role") == "admin"
    is_org_admin = (
        current_user.get("org_id") == org_id and 
        current_user.get("org_role") == "org_admin"
    )
    
    # 다른 사람을 제거하려는 경우 관리자 권한 필요
    if not is_self_removal and not is_system_admin and not is_org_admin:
        raise HTTPException(
            status_code=403, 
            detail="다른 사용자를 제거하려면 조직 관리자 권한이 필요합니다"
        )

    try:
        # 기본 조직에서는 제거 불가 (기본 조직에는 모두 속해있어야 함)
        if org_id == "default":
            raise HTTPException(status_code=400, detail="기본 조직에서는 사용자를 제거할 수 없습니다")

        # 현재 조직에서 제거
        success = org_manager.remove_member(org_id, user_id)

        if success:
            # 기본 조직으로 이동
            org_manager.add_member("default", user_id)
            
            # 사용자의 org_id를 기본 조직으로 업데이트
            user_key = f'user:{user_id}'
            cache_manager.redis.hset(user_key, 'org_id', 'default')
            cache_manager.redis.hset(user_key, 'org_role', 'user')

        # 응답 메시지
        if is_self_removal:
            message = "기본 조직으로 이동되었습니다"
        else:
            message = "멤버가 기본 조직으로 이동되었습니다"

        return {
            "success": success,
            "message": message if success else "조직의 멤버가 아닙니다",
            "is_self_removal": is_self_removal
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "remove member"))


# ============================================================================
# Group Management Endpoints
# ============================================================================

@router.get("/{org_id}/groups", response_model=Dict)
async def get_organization_groups(
    request: Request,
    org_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get all groups belonging to an organization

    Permissions:
    - System admin: Can view any organization's groups
    - Org admin: Can view own organization's groups
    - Regular user: Can view own organization's groups
    """
    try:
        from ..group_manager import GroupManager
        import logging
        logger = logging.getLogger(__name__)

        cache_manager = request.app.state.cache_manager
        group_manager = GroupManager(cache_manager.redis)
        org_manager = OrganizationManager(cache_manager.redis)

        # Permission check
        is_system_admin = current_user.get("role") == "admin"
        is_own_org = current_user.get("org_id") == org_id

        if not is_system_admin and not is_own_org:
            raise HTTPException(
                status_code=403,
                detail="해당 조직의 그룹을 조회할 권한이 없습니다"
            )

        # Validate organization exists
        org = org_manager.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다")

        logger.info(f"📂 [조직 그룹 조회] 조직: {org['name']} (ID: {org_id[:8] if len(org_id) > 8 else org_id}...)")

        # Get groups for this organization
        groups = group_manager.get_all_groups(org_id=org_id)
        logger.info(f"📂 [조직 그룹 조회 결과] {org['name']}의 그룹 개수: {len(groups)}")
        if groups:
            logger.info(f"📂 [조직 그룹 목록] {[g['name'] for g in groups[:5]]}{'...' if len(groups) > 5 else ''}")

        # 배치로 모든 그룹의 문서 수와 조직 수를 한 번에 조회 (N+1 쿼리 제거)
        group_ids = [g['id'] for g in groups]
        group_counts = group_manager.batch_get_group_counts(group_ids)

        # Add document count and organization count for each group
        for group in groups:
            counts = group_counts.get(group['id'], {'document_count': 0, 'org_count': 0})
            group['document_count'] = counts['document_count']
            group['org_count'] = counts['org_count']

        # Get root group IDs (groups explicitly assigned to this organization as top-level)
        root_group_ids_bytes = cache_manager.redis.smembers(f'org:groups:root:{org_id}')
        root_group_ids = [gid.decode('utf-8') for gid in root_group_ids_bytes]
        logger.info(f"📂 [최상위 그룹] {org['name']}의 최상위 그룹 개수: {len(root_group_ids)}")

        return {
            "success": True,
            "organization": org,
            "groups": groups,
            "root_group_ids": root_group_ids,  # 최상위 그룹 ID 목록
            "total": len(groups)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "list groups"))


@router.post("/{org_id}/groups/{group_id}", response_model=Dict, dependencies=[Depends(require_admin)])
async def assign_group_to_organization(
    request: Request,
    org_id: str,
    group_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Add a group to an organization (N:M relationship)

    The group can belong to multiple organizations simultaneously.
    This adds the organization without removing existing relationships.

    Permissions:
    - System admin only
    """
    try:
        from ..group_manager import GroupManager
        import logging
        logger = logging.getLogger(__name__)

        cache_manager = request.app.state.cache_manager
        group_manager = GroupManager(cache_manager.redis)
        org_manager = OrganizationManager(cache_manager.redis)

        # Validate organization exists
        org = org_manager.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다")

        # Get group info
        group = group_manager.get_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

        logger.info(f"📌 [그룹 할당 요청] 그룹: {group['name']} (ID: {group_id[:8]}...) → 조직: {org['name']} (ID: {org_id[:8] if len(org_id) > 8 else org_id})")

        # Check if already assigned
        if group_manager.is_group_in_organization(group_id, org_id):
            logger.info(f"⚠️  [그룹 할당] 이미 할당됨: {group['name']} → {org['name']}")
            return {
                "success": True,
                "message": f"그룹 '{group['name']}'은(는) 이미 '{org['name']}' 조직에 속해 있습니다",
                "group_id": group_id,
                "org_id": org_id,
                "already_assigned": True
            }

        # Add group to organization (N:M relationship)
        logger.info(f"✅ [그룹 할당] 할당 시작: {group['name']} → {org['name']}")
        success = group_manager.add_group_to_organization(
            group_id=group_id,
            org_id=org_id,
            updated_by=current_user.get('username', 'admin')
        )

        # Get all organizations this group now belongs to
        group_orgs = group_manager.get_group_organizations(group_id)
        logger.info(f"✅ [그룹 할당 완료] {group['name']}이(가) 속한 조직 개수: {len(group_orgs)}, 조직 IDs: {group_orgs}")

        message = f"그룹 '{group['name']}'이(가) '{org['name']}' 조직에 추가되었습니다"
        if len(group_orgs) > 1:
            message += f" (총 {len(group_orgs)}개 조직에서 공유 중)"

        return {
            "success": success,
            "message": message,
            "group_id": group_id,
            "org_id": org_id,
            "total_organizations": len(group_orgs)
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "assign group"))


@router.delete("/{org_id}/groups/{group_id}", response_model=Dict, dependencies=[Depends(require_admin)])
async def remove_group_from_organization(
    request: Request,
    org_id: str,
    group_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Remove a group from an organization

    The group must belong to at least one organization.
    Cannot remove from the last organization.

    Permissions:
    - System admin only
    """
    try:
        from ..group_manager import GroupManager

        cache_manager = request.app.state.cache_manager
        group_manager = GroupManager(cache_manager.redis)
        org_manager = OrganizationManager(cache_manager.redis)

        # Validate organization exists
        org = org_manager.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다")

        # Get group info
        group = group_manager.get_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")

        # Remove group from organization
        success = group_manager.remove_group_from_organization(
            group_id=group_id,
            org_id=org_id,
            updated_by=current_user.get('username', 'admin')
        )

        # Get remaining organizations
        group_orgs = group_manager.get_group_organizations(group_id)

        message = f"그룹 '{group['name']}'이(가) '{org['name']}' 조직에서 제거되었습니다"
        if len(group_orgs) > 0:
            message += f" (남은 조직: {len(group_orgs)}개)"

        return {
            "success": success,
            "message": message,
            "group_id": group_id,
            "org_id": org_id,
            "remaining_organizations": len(group_orgs)
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "remove group"))


# ============================================================================
# Organization Admin Management Endpoints
# ============================================================================

@router.post("/{org_id}/admins/{user_id}", response_model=Dict)
async def promote_to_org_admin(
    request: Request,
    org_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_active_user),
    _: bool = Depends(require_org_admin_or_system_admin)
):
    """조직 관리자로 승격 (조직 관리자 또는 시스템 관리자)

    Args:
        request: FastAPI Request 객체
        org_id: 조직 ID
        user_id: 승격할 사용자 ID
        current_user: 현재 사용자
        _: 조직 관리자 권한 검증

    Returns:
        승격 성공 여부

    Raises:
        HTTPException: 승격 실패 시
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    try:
        # 조직 관리자로 승격
        success = org_manager.add_org_admin(org_id, user_id)

        # 사용자의 org_role 업데이트
        if success:
            user_key = f'user:{user_id}'
            cache_manager.redis.hset(user_key, 'org_role', 'org_admin')

        return {
            "success": success,
            "message": "조직 관리자로 승격되었습니다" if success else "이미 조직 관리자입니다"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "promote org admin"))


@router.delete("/{org_id}/admins/{user_id}", response_model=Dict)
async def demote_from_org_admin(
    request: Request,
    org_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_active_user),
    _: bool = Depends(require_org_admin_or_system_admin)
):
    """조직 관리자에서 해제 (조직 관리자 또는 시스템 관리자)

    Args:
        request: FastAPI Request 객체
        org_id: 조직 ID
        user_id: 해제할 사용자 ID
        current_user: 현재 사용자
        _: 조직 관리자 권한 검증

    Returns:
        해제 성공 여부

    Raises:
        HTTPException: 해제 실패 시
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    try:
        success = org_manager.remove_org_admin(org_id, user_id)

        # 사용자의 org_role 업데이트
        if success:
            user_key = f'user:{user_id}'
            cache_manager.redis.hset(user_key, 'org_role', 'user')

        return {
            "success": success,
            "message": "조직 관리자에서 해제되었습니다" if success else "조직 관리자가 아닙니다"
        }

    except HTTPException:
        raise  # HTTPException은 그대로 전달 (400 에러 등)
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "demote org admin"))


@router.post("/maintenance/cleanup-stale-refs", response_model=Dict, dependencies=[Depends(require_admin)])
async def cleanup_stale_org_references(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Clean up stale organization references in group:orgs sets (Admin only)

    Fixes the bug where deleted organizations still count in group org_count.
    This scans all groups and removes references to non-existent organizations.

    Returns:
        Cleanup statistics including groups scanned, stale refs removed, etc.
    """
    cache_manager = request.app.state.cache_manager
    org_manager = OrganizationManager(cache_manager.redis)

    try:
        result = org_manager.cleanup_stale_group_org_references()

        return {
            "success": True,
            "message": f"정리 완료: {result['stale_refs_removed']}개의 잘못된 참조가 삭제되었습니다",
            "details": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=get_safe_error_message(e, "cleanup stale refs"))
