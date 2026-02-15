"""
Group Management Router

Handles group operations and document assignments including:
- Group CRUD operations (create, read, update, delete)
- Group hierarchy management (tree structure, parent/child relationships)
- Document assignment and removal
- Group document counts synchronization

All endpoints require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from loguru import logger

from ..auth.middleware import get_current_active_user
from ..utils.error_handling import get_safe_error_message

# Create router with prefix and tags
router = APIRouter(prefix="/api", tags=["Groups"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

group_manager = None


def inject_dependencies(grp_manager):
    """
    Inject dependencies from main application

    Args:
        grp_manager: GroupManager instance for group operations
    """
    global group_manager
    group_manager = grp_manager


# ============================================================================
# Pydantic Models
# ============================================================================

class GroupCreateRequest(BaseModel):
    name: str
    description: str = ""
    color: str = "#3B82F6"
    icon: str = "📁"
    parent_id: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[str] = None  # 상위 그룹 변경 지원


class GroupMoveRequest(BaseModel):
    new_parent_id: Optional[str] = None


class BatchDocumentAssignRequest(BaseModel):
    filenames: List[str]


# ============================================================================
# Group API Endpoints
# ============================================================================

@router.get("/groups", tags=["Groups"])
async def list_groups(
    filter_scope: str = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get all groups with hierarchy (로그인 필요)

    Returns groups with tree structure based on user's organization
    and permissions.

    Args:
        filter_scope: "user" - always filter by organization (for search filters)
                     None - admin sees all, users see organization only (for admin page)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Groups and tree structure
            - groups: List of all groups with metadata
            - tree: Hierarchical tree structure

    Raises:
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        # Get user's organization
        user_org_id = current_user.get("org_id")
        is_admin = current_user.get("role") == "admin"

        # Determine scope: if filter_scope="user", always use organization scope
        # Otherwise, admin sees all, regular users see organization only
        if filter_scope == "user" or not is_admin:
            groups = group_manager.get_all_groups(org_id=user_org_id)
            tree = group_manager.get_group_tree(org_id=user_org_id)
        else:
            groups = group_manager.get_all_groups()
            tree = group_manager.get_group_tree()

        return {
            "groups": groups,
            "tree": tree
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list groups: {e}")
        safe_message = get_safe_error_message(e, "list groups endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/groups", tags=["Groups"])
async def create_group(
    request: GroupCreateRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Create a new group (로그인 필요)

    Group is automatically assigned to the default organization.
    Admin can manually assign the group to additional organization(s) after creation.

    Args:
        request: Group creation parameters (name, description, color, icon, parent_id)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Created group details
            - success: True if created successfully
            - group_id: ID of the created group
            - group: Complete group object

    Raises:
        HTTPException: 400 if creation fails or validation error
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        group_id = group_manager.create_group(
            name=request.name,
            org_id=None,  # Will be assigned to default org below
            description=request.description,
            color=request.color,
            icon=request.icon,
            parent_id=request.parent_id,
            created_by=current_user.get("user_id", "system")
        )

        if not group_id:
            raise HTTPException(status_code=400, detail="Failed to create group")

        # Automatically assign to default organization (home for all groups)
        from ..organization_manager import OrganizationManager
        org_manager = OrganizationManager()
        default_org_id = org_manager.get_default_organization_id()

        try:
            group_manager.add_group_to_organization(
                group_id=group_id,
                org_id=default_org_id,
                updated_by=current_user.get("username", "system")
            )
            logger.info(f"Created group: {group_id} ({request.name}) - assigned to default organization")
        except Exception as e:
            logger.warning(f"Failed to assign group {group_id} to default organization: {e}")

        group = group_manager.get_group(group_id)

        return {
            "success": True,
            "group_id": group_id,
            "group": group
        }
    except ValueError as e:
        # Validation errors (e.g., invalid parent_id, parent org mismatch)
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create group: {e}")
        safe_message = get_safe_error_message(e, "create group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.put("/groups/{group_id}", tags=["Groups"])
async def update_group(
    group_id: str,
    request: GroupUpdateRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update group metadata (로그인 필요)

    Updates group properties like name, description, color, icon, and parent.

    Args:
        group_id: ID of the group to update
        request: Fields to update (only non-None fields are updated)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Updated group details
            - success: True if updated successfully
            - group: Complete updated group object

    Raises:
        HTTPException: 400 if no fields to update
        HTTPException: 404 if group not found
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        # Build update dict from non-None fields
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.color is not None:
            updates["color"] = request.color
        if request.icon is not None:
            updates["icon"] = request.icon
        # Handle parent_id: accept both None and empty string as "no parent"
        if request.parent_id is not None:
            updates["parent_id"] = request.parent_id if request.parent_id else None
        elif hasattr(request, 'parent_id'):  # Explicitly check if field is present even if None
            updates["parent_id"] = None

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        success = group_manager.update_group(
            group_id=group_id,
            updated_by="system",
            **updates
        )

        if not success:
            raise HTTPException(status_code=404, detail="Group not found")

        group = group_manager.get_group(group_id)
        logger.info(f"Updated group: {group_id}")

        return {
            "success": True,
            "group": group
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update group: {e}")
        safe_message = get_safe_error_message(e, "update group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.delete("/groups/{group_id}", tags=["Groups"])
async def delete_group(
    group_id: str,
    reassign_to: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete a group and reassign its documents (로그인 필요)

    Deletes a group and reassigns all its documents to another group.
    Cannot delete the default group.

    Args:
        group_id: ID of the group to delete
        reassign_to: Group ID to reassign documents to (defaults to parent or default group)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Deletion result
            - success: True if deleted successfully
            - reassigned_documents: Number of documents reassigned

    Raises:
        HTTPException: 400 if trying to delete default group or validation error
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        # Prevent deletion of default group
        default_group_id = group_manager.get_default_group_id()
        if group_id == default_group_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete default group"
            )

        reassigned_count = group_manager.delete_group(
            group_id=group_id,
            reassign_to=reassign_to
        )

        logger.info(f"Deleted group: {group_id}, reassigned {reassigned_count} documents")

        return {
            "success": True,
            "reassigned_documents": reassigned_count
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete group: {e}")
        safe_message = get_safe_error_message(e, "delete group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.patch("/groups/{group_id}/move", tags=["Groups"])
async def move_group(
    group_id: str,
    request: GroupMoveRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Move a group to a new parent (로그인 필요)

    Changes the group's position in the hierarchy by setting a new parent.

    Args:
        group_id: ID of the group to move
        request: New parent group ID (None for root level)
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Updated group details
            - success: True if moved successfully
            - group: Complete updated group object

    Raises:
        HTTPException: 400 if circular reference or validation error
        HTTPException: 404 if group not found
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        success = group_manager.move_group(
            group_id=group_id,
            new_parent_id=request.new_parent_id,
            updated_by="system"
        )

        if not success:
            raise HTTPException(status_code=404, detail="Group not found")

        group = group_manager.get_group(group_id)
        logger.info(f"Moved group: {group_id} to parent {request.new_parent_id}")

        return {
            "success": True,
            "group": group
        }
    except ValueError as e:
        # Circular reference or validation errors
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to move group: {e}")
        safe_message = get_safe_error_message(e, "move group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/groups/{group_id}/documents", tags=["Groups"])
async def batch_assign_documents(
    group_id: str,
    request: BatchDocumentAssignRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Batch assign multiple documents to a group (로그인 필요)

    Assigns multiple documents to a group in a single operation.

    Args:
        group_id: Target group ID
        request: List of filenames to assign
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Assignment result
            - success: True if operation completed
            - assigned_count: Number of documents successfully assigned
            - total_requested: Total number of documents requested to assign

    Raises:
        HTTPException: 400 if validation error
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        assigned_count = group_manager.batch_assign_documents(
            filenames=request.filenames,
            group_id=group_id
        )

        logger.info(f"Batch assigned {assigned_count}/{len(request.filenames)} documents to group {group_id}")

        return {
            "success": True,
            "assigned_count": assigned_count,
            "total_requested": len(request.filenames)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to batch assign documents: {e}")
        safe_message = get_safe_error_message(e, "batch assign documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.delete("/groups/{group_id}/documents/{filename}", tags=["Groups"])
async def remove_document_from_group(
    group_id: str,
    filename: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Remove a document from a group (로그인 필요)

    Removes a document from a group and reassigns it to the default group.

    Args:
        group_id: Group ID to remove document from
        filename: Document filename to remove
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Removal result
            - success: True if removed successfully
            - filename: Name of the removed document
            - group_id: ID of the group document was removed from
            - message: Confirmation message

    Raises:
        HTTPException: 400 if validation error
        HTTPException: 404 if document or group not found
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        success = group_manager.remove_document_from_group(
            filename=filename,
            group_id=group_id
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="문서 또는 그룹을 찾을 수 없습니다."
            )

        logger.info(f"Removed document '{filename}' from group {group_id}")

        return {
            "success": True,
            "filename": filename,
            "group_id": group_id,
            "message": "문서가 기본 그룹으로 이동되었습니다."
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove document from group: {e}")
        safe_message = get_safe_error_message(e, "remove document from group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.get("/groups/{group_id}/documents", tags=["Groups"])
async def list_group_documents(
    group_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get all documents in a group (로그인 필요)

    Returns the list of all documents assigned to a specific group.

    Args:
        group_id: Group ID to query
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Group documents
            - group_id: ID of the queried group
            - documents: List of document filenames in the group
            - count: Number of documents in the group

    Raises:
        HTTPException: 400 if validation error
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        documents = group_manager.get_group_documents(group_id)

        return {
            "group_id": group_id,
            "documents": documents,
            "count": len(documents)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list group documents: {e}")
        safe_message = get_safe_error_message(e, "list group documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@router.post("/groups/sync-counts", tags=["Groups"])
async def sync_group_document_counts(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Synchronize document counts for all groups (로그인 필요)

    Recalculates document counts from actual SET cardinality for all groups.
    Useful for fixing inconsistencies in document counts.

    Args:
        current_user: Authenticated user (injected by dependency)

    Returns:
        dict: Sync result
            - status: "success" if completed
            - message: Confirmation message

    Raises:
        HTTPException: 500 if group manager not initialized or error occurs
    """
    try:
        if not group_manager:
            raise HTTPException(status_code=500, detail="Group manager not initialized")

        group_manager.sync_document_counts()
        return {"status": "success", "message": "그룹별 문서 개수가 동기화되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync document counts: {e}")
        safe_message = get_safe_error_message(e, "sync document counts endpoint")
        raise HTTPException(status_code=500, detail=safe_message)
