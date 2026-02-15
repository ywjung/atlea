"""
Organization Management System

Handles CRUD operations for organizations with PostgreSQL backend.
Supports multi-tenant architecture with organization-based access control.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from loguru import logger

from sqlalchemy import select, func

from .database.connection import SyncSessionFactory
from .database.models.organization import Organization


# Well-known UUID for the default organization
DEFAULT_ORG_UUID = uuid.UUID("00000000-0000-4000-8000-000000000001")


class OrganizationManager:
    """Manages organizations with PostgreSQL storage"""

    def __init__(self):
        """
        Initialize OrganizationManager

        Args:
        """
        self._ensure_default_organization()

    def _ensure_default_organization(self) -> str:
        """
        Ensure default organization exists

        Returns:
            Default organization ID (UUID string)
        """
        with SyncSessionFactory() as db:
            org = db.get(Organization, DEFAULT_ORG_UUID)
            if org:
                return str(org.id)

            now = datetime.now(timezone.utc)
            org = Organization(
                id=DEFAULT_ORG_UUID,
                name="기본 조직",
                display_name="기본 조직",
                description="기존 사용자 및 데이터를 위한 기본 조직",
                is_active=True,
                settings={"members": [], "admins": [], "member_count": 0},
            )
            db.add(org)
            db.commit()

        logger.info(f"Created default organization: {DEFAULT_ORG_UUID}")
        return str(DEFAULT_ORG_UUID)

    def get_default_organization_id(self) -> str:
        """Get default organization ID"""
        return str(DEFAULT_ORG_UUID)

    def create_organization(
        self,
        name: str,
        description: str = '',
        created_by: str = 'system'
    ) -> str:
        """
        Create a new organization

        Returns:
            New organization ID (UUID string)

        Raises:
            ValueError: If validation fails
        """
        if not name or not name.strip():
            raise ValueError("조직 이름은 필수입니다.")

        if len(name) > 100:
            raise ValueError("조직 이름은 100자를 초과할 수 없습니다.")

        # Check for duplicate name
        if self._name_exists(name):
            raise ValueError(f"'{name}' 조직명이 이미 존재합니다.")

        org_id = uuid.uuid4()

        with SyncSessionFactory() as db:
            org = Organization(
                id=org_id,
                name=name.strip(),
                display_name=name.strip(),
                description=description.strip() if description else '',
                is_active=True,
                settings={
                    "members": [],
                    "admins": [],
                    "member_count": 0,
                    "created_by": created_by,
                },
            )
            db.add(org)
            db.commit()

        logger.info(f"Created organization: {org_id} ({name})")
        return str(org_id)

    def _name_exists(self, name: str) -> bool:
        """Check if organization name already exists"""
        with SyncSessionFactory() as db:
            stmt = select(Organization).where(
                func.lower(Organization.name) == name.lower()
            )
            result = db.execute(stmt).scalar_one_or_none()
            return result is not None

    def get_organization(self, org_id: str) -> Optional[Dict[str, str]]:
        """
        Get organization by ID

        Returns:
            Organization data dict or None if not found
        """
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return None

        with SyncSessionFactory() as db:
            org = db.get(Organization, oid)
            if not org:
                return None

            settings = org.settings or {}
            members = settings.get("members", [])

            return {
                'id': str(org.id),
                'name': org.name,
                'description': org.description or '',
                'created_at': org.created_at.isoformat() if org.created_at else '',
                'created_by': settings.get('created_by', 'system'),
                'updated_at': org.updated_at.isoformat() if org.updated_at else '',
                'is_active': 'true' if org.is_active else 'false',
                'member_count': str(len(members)),
            }

    def update_organization(
        self,
        org_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Update organization

        Returns:
            True if updated successfully

        Raises:
            ValueError: If validation fails or organization not found
        """
        org = self.get_organization(org_id)
        if not org:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        if name is not None:
            if not name.strip():
                raise ValueError("조직 이름은 필수입니다.")
            if len(name) > 100:
                raise ValueError("조직 이름은 100자를 초과할 수 없습니다.")
            if name.lower() != org['name'].lower():
                if self._name_exists(name):
                    raise ValueError(f"'{name}' 조직명이 이미 존재합니다.")

        has_updates = name is not None or description is not None or is_active is not None
        if not has_updates:
            return False

        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

            if name is not None:
                org_row.name = name.strip()
                org_row.display_name = name.strip()
            if description is not None:
                org_row.description = description.strip() if description else ''
            if is_active is not None:
                org_row.is_active = is_active

            db.commit()

        logger.info(f"Updated organization: {org_id}")
        return True

    def delete_organization(self, org_id: str) -> bool:
        """
        Delete organization

        Raises:
            ValueError: If organization has members or is default org
        """
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        # Prevent deletion of default organization
        if oid == DEFAULT_ORG_UUID:
            raise ValueError("기본 조직은 삭제할 수 없습니다.")

        org = self.get_organization(org_id)
        if not org:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        member_count = self.get_member_count(org_id)
        if member_count > 0:
            raise ValueError(f"멤버가 있는 조직은 삭제할 수 없습니다. (멤버 수: {member_count})")

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if org_row:
                db.delete(org_row)  # CASCADE deletes group_organizations links
                db.commit()

        logger.info(f"Deleted organization: {org_id} ({org['name']})")
        return True

    def list_organizations(self) -> List[Dict[str, str]]:
        """List all organizations"""
        with SyncSessionFactory() as db:
            stmt = select(Organization).order_by(Organization.name)
            result = db.execute(stmt)
            rows = result.scalars().all()

        organizations = []
        for org in rows:
            settings = org.settings or {}
            members = settings.get("members", [])
            organizations.append({
                'id': str(org.id),
                'name': org.name,
                'description': org.description or '',
                'created_at': org.created_at.isoformat() if org.created_at else '',
                'created_by': settings.get('created_by', 'system'),
                'updated_at': org.updated_at.isoformat() if org.updated_at else '',
                'is_active': 'true' if org.is_active else 'false',
                'member_count': str(len(members)),
            })

        return organizations

    # ===== Member Management =====

    def _get_settings(self, org_id: str) -> tuple:
        """Get organization settings dict and the DB row. Returns (settings_dict, org_row) or (None, None)."""
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return None, None

        db = SyncSessionFactory()
        org_row = db.get(Organization, oid)
        if not org_row:
            db.close()
            return None, None
        return org_row.settings or {}, org_row

    def add_member(self, org_id: str, user_id: str) -> bool:
        """Add user to organization"""
        org = self.get_organization(org_id)
        if not org:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_id}")

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                return False

            settings = dict(org_row.settings or {})
            members = list(settings.get("members", []))

            if user_id in members:
                return False  # Already a member

            members.append(user_id)
            settings["members"] = members
            settings["member_count"] = len(members)
            org_row.settings = settings
            db.commit()

        logger.info(f"Added member {user_id} to organization {org_id}")
        return True

    def remove_member(self, org_id: str, user_id: str) -> bool:
        """Remove user from organization"""
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                return False

            settings = dict(org_row.settings or {})
            members = list(settings.get("members", []))
            admins = list(settings.get("admins", []))

            if user_id not in members:
                return False

            members.remove(user_id)
            if user_id in admins:
                admins.remove(user_id)

            settings["members"] = members
            settings["admins"] = admins
            settings["member_count"] = len(members)
            org_row.settings = settings
            db.commit()

        logger.info(f"Removed member {user_id} from organization {org_id}")
        return True

    def get_members(self, org_id: str) -> Set[str]:
        """Get all members of organization"""
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return set()

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                return set()

            settings = org_row.settings or {}
            return set(settings.get("members", []))

    def get_member_count(self, org_id: str) -> int:
        """Get member count for organization"""
        return len(self.get_members(org_id))

    def is_member(self, org_id: str, user_id: str) -> bool:
        """Check if user is member of organization"""
        return user_id in self.get_members(org_id)

    # ===== Organization Admin Management =====

    def add_org_admin(self, org_id: str, user_id: str) -> bool:
        """Promote user to organization admin"""
        if not self.is_member(org_id, user_id):
            raise ValueError(f"사용자가 조직의 멤버가 아닙니다: {user_id}")

        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                return False

            settings = dict(org_row.settings or {})
            admins = list(settings.get("admins", []))

            if user_id in admins:
                return False  # Already admin

            admins.append(user_id)
            settings["admins"] = admins
            org_row.settings = settings
            db.commit()

        logger.info(f"Promoted user {user_id} to org admin in {org_id}")
        return True

    def remove_org_admin(self, org_id: str, user_id: str) -> bool:
        """Demote user from organization admin"""
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                return False

            settings = dict(org_row.settings or {})
            admins = list(settings.get("admins", []))

            if user_id not in admins:
                return False

            admins.remove(user_id)
            settings["admins"] = admins
            org_row.settings = settings
            db.commit()

        logger.info(f"Demoted user {user_id} from org admin in {org_id}")
        return True

    def is_org_admin(self, org_id: str, user_id: str) -> bool:
        """Check if user is organization admin"""
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                return False

            settings = org_row.settings or {}
            return user_id in settings.get("admins", [])

    def get_org_admins(self, org_id: str) -> Set[str]:
        """Get all organization admins"""
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return set()

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                return set()

            settings = org_row.settings or {}
            return set(settings.get("admins", []))

    # ===== Validation =====

    def validate_org_access(self, org_id: str, user_id: str, is_system_admin: bool = False) -> bool:
        """Validate if user has access to organization"""
        if is_system_admin:
            return True

        if not self.is_member(org_id, user_id):
            raise ValueError(f"사용자가 조직에 접근할 수 없습니다: {org_id}")

        return True

    def get_organization_stats(self, org_id: str) -> Dict[str, int]:
        """Get statistics for organization"""
        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            return {'members': 0, 'admins': 0, 'groups': 0}

        with SyncSessionFactory() as db:
            org_row = db.get(Organization, oid)
            if not org_row:
                return {'members': 0, 'admins': 0, 'groups': 0}

            settings = org_row.settings or {}
            members = settings.get("members", [])
            admins = settings.get("admins", [])

            # Count groups linked to this org
            from .database.models.group_organization import GroupOrganization
            group_count_stmt = (
                select(func.count())
                .select_from(GroupOrganization)
                .where(GroupOrganization.org_id == oid)
            )
            group_count = db.execute(group_count_stmt).scalar_one()

        return {
            'members': len(members),
            'admins': len(admins),
            'groups': group_count,
        }

    def cleanup_stale_group_org_references(self) -> Dict[str, int]:
        """
        Clean up stale organization references in group_organizations table.
        With PG FK constraints and CASCADE, this is largely unnecessary,
        but kept for API compatibility.
        """
        logger.info("Cleanup not needed with PG CASCADE constraints")
        return {
            'groups_scanned': 0,
            'stale_refs_removed': 0,
            'affected_groups': 0
        }
