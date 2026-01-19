"""
Organization Management System

Handles CRUD operations for organizations with Redis backend.
Supports multi-tenant architecture with organization-based access control.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set
import redis
from loguru import logger


class OrganizationManager:
    """Manages organizations with Redis storage"""

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize OrganizationManager

        Args:
            redis_client: Redis client instance
        """
        self.client = redis_client
        self._ensure_default_organization()

    def _ensure_default_organization(self) -> str:
        """
        Ensure default organization exists for existing data migration

        Returns:
            Default organization ID
        """
        default_org_id = "default"
        org_key = f'org:{default_org_id}'

        # Check if default org already exists
        if self.client.exists(org_key):
            return default_org_id

        # Create default organization
        now = datetime.now().isoformat()
        org_data = {
            'id': default_org_id,
            'name': '기본 조직',
            'description': '기존 사용자 및 데이터를 위한 기본 조직',
            'created_at': now,
            'created_by': 'system',
            'updated_at': now,
            'is_active': 'true',
            'member_count': '0'
        }

        pipe = self.client.pipeline()
        pipe.hset(org_key, mapping=org_data)
        pipe.sadd('orgs:all', default_org_id)
        pipe.execute()

        logger.info(f"Created default organization: {default_org_id}")
        return default_org_id

    def get_default_organization_id(self) -> str:
        """Get default organization ID"""
        return "default"

    def create_organization(
        self,
        name: str,
        description: str = '',
        created_by: str = 'system'
    ) -> str:
        """
        Create a new organization

        Args:
            name: Organization name (required, max 100 chars)
            description: Organization description
            created_by: User ID who created the organization

        Returns:
            New organization ID

        Raises:
            ValueError: If validation fails
        """
        # Validate inputs
        if not name or not name.strip():
            raise ValueError("조직 이름은 필수입니다.")

        if len(name) > 100:
            raise ValueError("조직 이름은 100자를 초과할 수 없습니다.")

        # Check for duplicate name
        if self._name_exists(name):
            raise ValueError(f"'{name}' 조직명이 이미 존재합니다.")

        # Generate organization ID
        org_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        org_data = {
            'id': org_id,
            'name': name.strip(),
            'description': description.strip() if description else '',
            'created_at': now,
            'created_by': created_by,
            'updated_at': now,
            'is_active': 'true',
            'member_count': '0'
        }

        # Store organization in Redis
        pipe = self.client.pipeline()
        pipe.hset(f'org:{org_id}', mapping=org_data)
        pipe.sadd('orgs:all', org_id)
        pipe.set(f'org:name:{name.lower()}', org_id)  # Name lookup index
        pipe.execute()

        logger.info(f"Created organization: {org_id} ({name})")
        return org_id

    def _name_exists(self, name: str) -> bool:
        """Check if organization name already exists"""
        return self.client.exists(f'org:name:{name.lower()}') > 0

    def get_organization(self, org_id: str) -> Optional[Dict[str, str]]:
        """
        Get organization by ID

        Args:
            org_id: Organization ID

        Returns:
            Organization data dict or None if not found
        """
        org_data = self.client.hgetall(f'org:{org_id}')
        if not org_data:
            return None

        # Decode bytes to strings
        return {k.decode('utf-8'): v.decode('utf-8') for k, v in org_data.items()}

    def update_organization(
        self,
        org_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Update organization

        Args:
            org_id: Organization ID
            name: New name (optional)
            description: New description (optional)
            is_active: New active status (optional)

        Returns:
            True if updated successfully

        Raises:
            ValueError: If validation fails or organization not found
        """
        org = self.get_organization(org_id)
        if not org:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        updates = {}

        # Validate and prepare name update
        if name is not None:
            if not name.strip():
                raise ValueError("조직 이름은 필수입니다.")
            if len(name) > 100:
                raise ValueError("조직 이름은 100자를 초과할 수 없습니다.")

            # Check for duplicate name (if changing name)
            if name.lower() != org['name'].lower():
                if self._name_exists(name):
                    raise ValueError(f"'{name}' 조직명이 이미 존재합니다.")

            updates['name'] = name.strip()

        if description is not None:
            updates['description'] = description.strip() if description else ''

        if is_active is not None:
            updates['is_active'] = 'true' if is_active else 'false'

        if not updates:
            return False  # No updates to make

        # Update timestamp
        updates['updated_at'] = datetime.now().isoformat()

        # Apply updates
        pipe = self.client.pipeline()
        pipe.hset(f'org:{org_id}', mapping=updates)

        # Update name index if name changed
        if 'name' in updates and updates['name'].lower() != org['name'].lower():
            pipe.delete(f'org:name:{org["name"].lower()}')
            pipe.set(f'org:name:{updates["name"].lower()}', org_id)

        pipe.execute()

        logger.info(f"Updated organization: {org_id} - {updates}")
        return True

    def delete_organization(self, org_id: str) -> bool:
        """
        Delete organization

        Args:
            org_id: Organization ID

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If organization has members or is default org
        """
        # Prevent deletion of default organization
        if org_id == "default":
            raise ValueError("기본 조직은 삭제할 수 없습니다.")

        org = self.get_organization(org_id)
        if not org:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        # Check for members
        member_count = self.get_member_count(org_id)
        if member_count > 0:
            raise ValueError(f"멤버가 있는 조직은 삭제할 수 없습니다. (멤버 수: {member_count})")

        # Get all groups belonging to this organization before deletion
        group_ids_bytes = self.client.smembers(f'org:groups:{org_id}')
        group_ids = [gid.decode('utf-8') if isinstance(gid, bytes) else gid for gid in group_ids_bytes]

        # Delete organization and indexes
        pipe = self.client.pipeline()
        pipe.delete(f'org:{org_id}')
        pipe.srem('orgs:all', org_id)
        pipe.delete(f'org:name:{org["name"].lower()}')
        pipe.delete(f'org:members:{org_id}')
        pipe.delete(f'org:admins:{org_id}')
        pipe.delete(f'org:groups:{org_id}')

        # Clean up group:orgs:{group_id} references (fix stale count bug)
        for group_id in group_ids:
            pipe.srem(f'group:orgs:{group_id}', org_id)

        pipe.execute()

        logger.info(f"Deleted organization: {org_id} ({org['name']})")
        return True

    def list_organizations(self) -> List[Dict[str, str]]:
        """
        List all organizations

        Returns:
            List of organization data dicts
        """
        org_ids = self.client.smembers('orgs:all')
        organizations = []

        for org_id in org_ids:
            org_id_str = org_id.decode('utf-8')
            org = self.get_organization(org_id_str)
            if org:
                # Add real-time member count
                org['member_count'] = str(self.get_member_count(org_id_str))
                organizations.append(org)

        # Sort by name
        organizations.sort(key=lambda x: x['name'])
        return organizations

    # ===== Member Management =====

    def add_member(self, org_id: str, user_id: str) -> bool:
        """
        Add user to organization

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            True if added successfully

        Raises:
            ValueError: If organization not found
        """
        org = self.get_organization(org_id)
        if not org:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        # Add to members set
        result = self.client.sadd(f'org:members:{org_id}', user_id)

        # Update member count
        if result:
            count = self.get_member_count(org_id)
            self.client.hset(f'org:{org_id}', 'member_count', str(count))
            logger.info(f"Added member {user_id} to organization {org_id}")

        return bool(result)

    def remove_member(self, org_id: str, user_id: str) -> bool:
        """
        Remove user from organization

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            True if removed successfully
        """
        result = self.client.srem(f'org:members:{org_id}', user_id)

        # Also remove from admins if present
        if result:
            self.client.srem(f'org:admins:{org_id}', user_id)

            # Update member count
            count = self.get_member_count(org_id)
            self.client.hset(f'org:{org_id}', 'member_count', str(count))
            logger.info(f"Removed member {user_id} from organization {org_id}")

        return bool(result)

    def get_members(self, org_id: str) -> Set[str]:
        """
        Get all members of organization

        Args:
            org_id: Organization ID

        Returns:
            Set of user IDs
        """
        members = self.client.smembers(f'org:members:{org_id}')
        return {m.decode('utf-8') for m in members}

    def get_member_count(self, org_id: str) -> int:
        """
        Get member count for organization

        Args:
            org_id: Organization ID

        Returns:
            Number of members
        """
        return self.client.scard(f'org:members:{org_id}')

    def is_member(self, org_id: str, user_id: str) -> bool:
        """
        Check if user is member of organization

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            True if user is member
        """
        return self.client.sismember(f'org:members:{org_id}', user_id)

    # ===== Organization Admin Management =====

    def add_org_admin(self, org_id: str, user_id: str) -> bool:
        """
        Promote user to organization admin

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            True if promoted successfully

        Raises:
            ValueError: If user is not a member
        """
        # Verify user is a member
        if not self.is_member(org_id, user_id):
            raise ValueError(f"사용자가 조직의 멤버가 아닙니다: {user_id}")

        result = self.client.sadd(f'org:admins:{org_id}', user_id)
        if result:
            logger.info(f"Promoted user {user_id} to org admin in {org_id}")
        return bool(result)

    def remove_org_admin(self, org_id: str, user_id: str) -> bool:
        """
        Demote user from organization admin

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            True if demoted successfully
        """
        result = self.client.srem(f'org:admins:{org_id}', user_id)
        if result:
            logger.info(f"Demoted user {user_id} from org admin in {org_id}")
        return bool(result)

    def is_org_admin(self, org_id: str, user_id: str) -> bool:
        """
        Check if user is organization admin

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            True if user is org admin
        """
        return self.client.sismember(f'org:admins:{org_id}', user_id)

    def get_org_admins(self, org_id: str) -> Set[str]:
        """
        Get all organization admins

        Args:
            org_id: Organization ID

        Returns:
            Set of user IDs who are org admins
        """
        admins = self.client.smembers(f'org:admins:{org_id}')
        return {a.decode('utf-8') for a in admins}

    # ===== Validation =====

    def validate_org_access(self, org_id: str, user_id: str, is_system_admin: bool = False) -> bool:
        """
        Validate if user has access to organization

        Args:
            org_id: Organization ID
            user_id: User ID
            is_system_admin: Whether user is system admin

        Returns:
            True if user has access

        Raises:
            ValueError: If user does not have access
        """
        # System admins have access to all organizations
        if is_system_admin:
            return True

        # Check if user is member of organization
        if not self.is_member(org_id, user_id):
            raise ValueError(f"사용자가 조직에 접근할 수 없습니다: {org_id}")

        return True

    def get_organization_stats(self, org_id: str) -> Dict[str, int]:
        """
        Get statistics for organization

        Args:
            org_id: Organization ID

        Returns:
            Dict with stats (members, admins, groups)
        """
        return {
            'members': self.get_member_count(org_id),
            'admins': self.client.scard(f'org:admins:{org_id}'),
            'groups': self.client.scard(f'org:groups:{org_id}')
        }


    def cleanup_stale_group_org_references(self) -> Dict[str, int]:
        """
        Clean up stale organization references in group:orgs sets.

        This fixes the bug where deleted organizations still count in group org_count.
        Scans all group:orgs:* sets and removes references to non-existent organizations.

        Returns:
            Dict with cleanup statistics:
                - groups_scanned: Number of groups checked
                - stale_refs_removed: Number of stale references removed
                - affected_groups: Number of groups that had stale references
        """
        # Get all existing organization IDs
        existing_orgs = set()
        for org_id_bytes in self.client.smembers('orgs:all'):
            org_id = org_id_bytes.decode('utf-8') if isinstance(org_id_bytes, bytes) else org_id_bytes
            existing_orgs.add(org_id)

        groups_scanned = 0
        stale_refs_removed = 0
        affected_groups = 0

        # Scan all group:orgs:* keys
        for key in self.client.scan_iter(match='group:orgs:*', count=100):
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            group_id = key_str.replace('group:orgs:', '')
            groups_scanned += 1

            # Get all org IDs in this group's set
            org_ids_bytes = self.client.smembers(key_str)
            stale_in_group = []

            for org_id_bytes in org_ids_bytes:
                org_id = org_id_bytes.decode('utf-8') if isinstance(org_id_bytes, bytes) else org_id_bytes
                if org_id not in existing_orgs:
                    stale_in_group.append(org_id)

            # Remove stale references
            if stale_in_group:
                pipe = self.client.pipeline()
                for org_id in stale_in_group:
                    pipe.srem(key_str, org_id)
                pipe.execute()

                affected_groups += 1
                stale_refs_removed += len(stale_in_group)
                logger.info(f"Cleaned up {len(stale_in_group)} stale org refs from group {group_id}: {stale_in_group}")

        logger.info(f"Cleanup complete: {groups_scanned} groups scanned, {stale_refs_removed} stale refs removed, {affected_groups} groups affected")

        return {
            'groups_scanned': groups_scanned,
            'stale_refs_removed': stale_refs_removed,
            'affected_groups': affected_groups
        }
