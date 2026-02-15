"""
Document Group Management System

Handles CRUD operations for hierarchical document groups with PostgreSQL backend.
Supports multi-tenant architecture with organization-based group filtering.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from loguru import logger
from sqlalchemy import select, func, delete

from .database.connection import SyncSessionFactory
from .database.models.document_group import DocumentGroup
from .database.models.group_document import GroupDocument
from .database.models.group_organization import GroupOrganization


# Well-known UUID for the default group
DEFAULT_GROUP_UUID = uuid.UUID("00000000-0000-4000-8000-000000000002")


class GroupManager:
    """Manages hierarchical document groups with PostgreSQL storage"""

    def __init__(self):
        """
        Initialize GroupManager

        Args:
        """
        self._ensure_default_group()

    @property
    def client(self):
        """Backward-compat: return None (vector DB is now PostgreSQL)."""
        return None

    def _ensure_default_group(self) -> str:
        """
        Ensure default 'uncategorized' group exists

        Returns:
            Default group ID (UUID string)
        """
        try:
            with SyncSessionFactory() as db:
                grp = db.get(DocumentGroup, DEFAULT_GROUP_UUID)
                if grp:
                    return str(grp.id)

                grp = DocumentGroup(
                    id=DEFAULT_GROUP_UUID,
                    name="미분류",
                    description="그룹에 할당되지 않은 문서",
                    color="#9CA3AF",
                    icon="📂",
                    parent_id=None,
                    created_by="system",
                    updated_by="system",
                    document_count=0,
                )
                db.add(grp)
                db.commit()

            logger.info(f"Created default group: {DEFAULT_GROUP_UUID}")
        except Exception as e:
            logger.warning(f"Failed to ensure default group (PG may be unavailable): {e}")
        return str(DEFAULT_GROUP_UUID)

    def get_default_group_id(self) -> str:
        """Get default group ID"""
        return str(DEFAULT_GROUP_UUID)

    def create_group(
        self,
        name: str,
        org_id: Optional[str] = None,
        description: str = '',
        color: str = '#4A90E2',
        icon: str = '📁',
        parent_id: Optional[str] = None,
        created_by: str = 'user'
    ) -> str:
        """
        Create a new group

        Returns:
            New group ID (UUID string)

        Raises:
            ValueError: If validation fails
        """
        if not name or not name.strip():
            raise ValueError("그룹 이름은 필수입니다.")

        if len(name) > 100:
            raise ValueError("그룹 이름은 100자를 초과할 수 없습니다.")

        parent_uuid = None
        if parent_id:
            try:
                parent_uuid = uuid.UUID(parent_id)
            except ValueError:
                raise ValueError("상위 그룹이 존재하지 않습니다.")

            with SyncSessionFactory() as db:
                parent = db.get(DocumentGroup, parent_uuid)
                if not parent:
                    raise ValueError("상위 그룹이 존재하지 않습니다.")

                # Validate org match if both have org_id
                if org_id and parent:
                    parent_orgs = self._get_group_org_ids(db, parent_uuid)
                    if parent_orgs and org_id not in parent_orgs:
                        raise ValueError("상위 그룹은 같은 조직에 속해야 합니다.")

        group_id = uuid.uuid4()

        with SyncSessionFactory() as db:
            grp = DocumentGroup(
                id=group_id,
                name=name.strip(),
                description=description.strip(),
                color=color,
                icon=icon,
                parent_id=parent_uuid,
                created_by=created_by,
                updated_by=created_by,
                document_count=0,
            )
            db.add(grp)

            # Link to organization if provided
            if org_id:
                try:
                    org_uuid = uuid.UUID(org_id)
                except ValueError:
                    pass
                else:
                    is_root = parent_uuid is None
                    link = GroupOrganization(
                        group_id=group_id,
                        org_id=org_uuid,
                        is_root=is_root,
                    )
                    db.add(link)

            db.commit()

        org_info = f"in org {org_id}" if org_id else "without org assignment"
        logger.info(f"Created group: {group_id} ({name}) {org_info}")
        return str(group_id)

    def _get_group_org_ids(self, db, group_uuid: uuid.UUID) -> List[str]:
        """Get organization IDs for a group within an existing session."""
        stmt = select(GroupOrganization.org_id).where(
            GroupOrganization.group_id == group_uuid
        )
        result = db.execute(stmt)
        return [str(row[0]) for row in result.all()]

    def _is_descendant(self, potential_descendant_id: str, ancestor_id: str) -> bool:
        """Check if potential_descendant is a descendant of ancestor."""
        visited = set()
        current_id = potential_descendant_id

        with SyncSessionFactory() as db:
            while current_id and current_id not in visited:
                if current_id == ancestor_id:
                    return True

                visited.add(current_id)

                try:
                    grp = db.get(DocumentGroup, uuid.UUID(current_id))
                except ValueError:
                    break
                if not grp:
                    break

                current_id = str(grp.parent_id) if grp.parent_id else None

        return False

    def update_group(
        self,
        group_id: str,
        updated_by: str = 'user',
        **updates
    ) -> bool:
        """
        Update group metadata

        Raises:
            ValueError: If group doesn't exist or validation fails
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다.")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다.")

            # Prevent updating default group name
            if gid == DEFAULT_GROUP_UUID and 'name' in updates:
                raise ValueError("기본 그룹의 이름은 변경할 수 없습니다.")

            allowed_fields = {'name', 'description', 'color', 'icon', 'parent_id'}
            update_data = {k: v for k, v in updates.items() if k in allowed_fields}

            if 'name' in update_data:
                if not update_data['name'] or not update_data['name'].strip():
                    raise ValueError("그룹 이름은 필수입니다.")
                if len(update_data['name']) > 100:
                    raise ValueError("그룹 이름은 100자를 초과할 수 없습니다.")

            # Handle parent_id changes
            if 'parent_id' in update_data:
                new_parent_id = update_data['parent_id']

                if new_parent_id:
                    if new_parent_id == group_id:
                        raise ValueError("그룹을 자신의 하위로 설정할 수 없습니다.")

                    try:
                        new_parent_uuid = uuid.UUID(new_parent_id)
                    except ValueError:
                        raise ValueError("상위 그룹이 존재하지 않습니다.")

                    parent_grp = db.get(DocumentGroup, new_parent_uuid)
                    if not parent_grp:
                        raise ValueError("상위 그룹이 존재하지 않습니다.")

                    if self._is_descendant(new_parent_id, group_id):
                        raise ValueError("하위 그룹을 상위 그룹으로 설정할 수 없습니다.")

                    grp.parent_id = new_parent_uuid
                else:
                    grp.parent_id = None

                # Update is_root in group_organizations
                self._update_root_status(db, gid)

            if 'name' in update_data:
                grp.name = update_data['name'].strip()
            if 'description' in update_data:
                grp.description = update_data['description'].strip()
            if 'color' in update_data:
                grp.color = update_data['color']
            if 'icon' in update_data:
                grp.icon = update_data['icon']

            grp.updated_by = updated_by
            db.commit()

        logger.info(f"Updated group: {group_id}")
        return True

    def _update_root_status(self, db, group_uuid: uuid.UUID):
        """Update is_root flag for all org links of this group."""
        grp = db.get(DocumentGroup, group_uuid)
        if not grp:
            return

        stmt = select(GroupOrganization).where(
            GroupOrganization.group_id == group_uuid
        )
        links = db.execute(stmt).scalars().all()

        for link in links:
            if grp.parent_id is None:
                link.is_root = True
            else:
                # Check if parent is in same org
                parent_in_org_stmt = select(GroupOrganization).where(
                    GroupOrganization.group_id == grp.parent_id,
                    GroupOrganization.org_id == link.org_id,
                )
                parent_link = db.execute(parent_in_org_stmt).scalar_one_or_none()
                link.is_root = parent_link is None

    def change_group_organization(
        self,
        group_id: str,
        new_org_id: str,
        updated_by: str = 'user'
    ) -> bool:
        """
        Change the organization of a group and all its descendants

        Raises:
            ValueError: If group doesn't exist, is default group, or org doesn't exist
        """
        from .organization_manager import OrganizationManager

        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다.")

        if gid == DEFAULT_GROUP_UUID:
            raise ValueError("기본 그룹은 다른 조직으로 이동할 수 없습니다.")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다.")

            # Get current organizations
            old_org_ids = self._get_group_org_ids(db, gid)

            try:
                new_org_uuid = uuid.UUID(new_org_id)
            except ValueError:
                raise ValueError("대상 조직이 존재하지 않습니다.")

            if new_org_id in old_org_ids and len(old_org_ids) == 1:
                raise ValueError("그룹이 이미 해당 조직에 속해 있습니다.")

            # Validate new organization exists
            org_manager = OrganizationManager()
            if not org_manager.get_organization(new_org_id):
                raise ValueError("대상 조직이 존재하지 않습니다.")

            # Get all descendant group IDs
            all_group_ids = self._get_all_descendant_uuids(db, gid)

            # Remove old org links and add new ones
            for desc_uuid in all_group_ids:
                # Delete existing org links
                del_stmt = delete(GroupOrganization).where(
                    GroupOrganization.group_id == desc_uuid
                )
                db.execute(del_stmt)

                # Add new org link
                desc_grp = db.get(DocumentGroup, desc_uuid)
                is_root = desc_grp.parent_id is None or desc_grp.parent_id not in set(all_group_ids)
                link = GroupOrganization(
                    group_id=desc_uuid,
                    org_id=new_org_uuid,
                    is_root=(desc_uuid == gid and grp.parent_id is None),
                )
                db.add(link)

                desc_grp.updated_by = updated_by

            db.commit()

        logger.info(f"Moved group {group_id} and descendants to org {new_org_id}")
        return True

    def _get_all_descendant_uuids(self, db, group_uuid: uuid.UUID) -> List[uuid.UUID]:
        """Recursively get all descendant group UUIDs including the given group."""
        result = [group_uuid]
        stmt = select(DocumentGroup.id).where(
            DocumentGroup.parent_id == group_uuid
        )
        children = db.execute(stmt).scalars().all()
        for child_id in children:
            result.extend(self._get_all_descendant_uuids(db, child_id))
        return result

    def delete_group(
        self,
        group_id: str,
        reassign_to: Optional[str] = None
    ) -> int:
        """
        Delete group and reassign documents

        Returns:
            Number of documents reassigned

        Raises:
            ValueError: If group doesn't exist or is default group
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다.")

        if gid == DEFAULT_GROUP_UUID:
            raise ValueError("기본 그룹은 삭제할 수 없습니다.")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다.")

            parent_uuid = grp.parent_id

            # Determine reassignment target
            if reassign_to is None:
                reassign_uuid = parent_uuid if parent_uuid else DEFAULT_GROUP_UUID
            else:
                try:
                    reassign_uuid = uuid.UUID(reassign_to)
                except ValueError:
                    raise ValueError("재할당 대상 그룹이 존재하지 않습니다.")

            reassign_grp = db.get(DocumentGroup, reassign_uuid)
            if not reassign_grp:
                raise ValueError("재할당 대상 그룹이 존재하지 않습니다.")

            # Get documents in this group
            doc_stmt = select(GroupDocument.filename).where(
                GroupDocument.group_id == gid
            )
            filenames = [row[0] for row in db.execute(doc_stmt).all()]

            # Reassign documents
            reassigned_count = 0
            if filenames:
                reassigned_count = self._reassign_docs_in_session(
                    db, filenames, gid, reassign_uuid
                )

            # Move child groups to parent
            child_stmt = select(DocumentGroup).where(
                DocumentGroup.parent_id == gid
            )
            children = db.execute(child_stmt).scalars().all()
            for child in children:
                child.parent_id = parent_uuid

            # Delete the group (CASCADE handles group_documents, group_organizations)
            db.delete(grp)
            db.commit()

        # Update vector DB chunks
        if filenames:
            self._update_vector_chunks(filenames, str(reassign_uuid))

        logger.info(f"Deleted group: {group_id}, reassigned {reassigned_count} documents")
        return reassigned_count

    def _reassign_docs_in_session(
        self, db, filenames: List[str], old_group_uuid: uuid.UUID, new_group_uuid: uuid.UUID
    ) -> int:
        """Reassign documents within an existing session."""
        count = 0
        for fname in filenames:
            # Delete old link
            del_stmt = delete(GroupDocument).where(
                GroupDocument.group_id == old_group_uuid,
                GroupDocument.filename == fname,
            )
            db.execute(del_stmt)

            # Check if already in new group
            exists_stmt = select(GroupDocument).where(
                GroupDocument.group_id == new_group_uuid,
                GroupDocument.filename == fname,
            )
            if not db.execute(exists_stmt).scalar_one_or_none():
                db.add(GroupDocument(group_id=new_group_uuid, filename=fname))
                count += 1

        # Update document counts
        self._update_doc_count(db, old_group_uuid)
        self._update_doc_count(db, new_group_uuid)
        return count

    def _update_doc_count(self, db, group_uuid: uuid.UUID):
        """Update document_count for a group."""
        grp = db.get(DocumentGroup, group_uuid)
        if grp:
            cnt_stmt = select(func.count()).select_from(GroupDocument).where(
                GroupDocument.group_id == group_uuid
            )
            grp.document_count = db.execute(cnt_stmt).scalar_one()

    def move_group(
        self,
        group_id: str,
        new_parent_id: Optional[str],
        updated_by: str = 'user'
    ) -> bool:
        """
        Move group to a new parent

        Raises:
            ValueError: If circular hierarchy or group doesn't exist
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다.")

        if gid == DEFAULT_GROUP_UUID:
            raise ValueError("기본 그룹은 이동할 수 없습니다.")

        new_parent_uuid = None
        if new_parent_id:
            try:
                new_parent_uuid = uuid.UUID(new_parent_id)
            except ValueError:
                raise ValueError("새 상위 그룹이 존재하지 않습니다.")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다.")

            if new_parent_uuid:
                parent_grp = db.get(DocumentGroup, new_parent_uuid)
                if not parent_grp:
                    raise ValueError("새 상위 그룹이 존재하지 않습니다.")

                if not self.validate_hierarchy(new_parent_id, group_id):
                    raise ValueError("순환 참조가 발생합니다.")

            grp.parent_id = new_parent_uuid
            grp.updated_by = updated_by

            # Update is_root in group_organizations
            self._update_root_status(db, gid)

            db.commit()

        logger.info(f"Moved group: {group_id} to {new_parent_id}")
        return True

    def validate_hierarchy(self, parent_id: str, child_id: str) -> bool:
        """
        Check if making child_id a parent of parent_id would create a cycle

        Returns:
            True if valid (no cycle), False if cycle detected
        """
        if parent_id == child_id:
            return False

        current = parent_id
        visited = set()

        with SyncSessionFactory() as db:
            while current:
                if current in visited:
                    logger.warning(f"Circular reference detected at {current}")
                    return False

                if current == child_id:
                    return False

                visited.add(current)

                try:
                    grp = db.get(DocumentGroup, uuid.UUID(current))
                except ValueError:
                    break
                if not grp:
                    break

                current = str(grp.parent_id) if grp.parent_id else None

        return True

    def assign_document(self, filename: str, group_id: str) -> bool:
        """
        Assign a document to a group

        Raises:
            ValueError: If group doesn't exist
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다.")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다.")

            # Find current group for this document
            old_link_stmt = select(GroupDocument).where(
                GroupDocument.filename == filename
            )
            old_link = db.execute(old_link_stmt).scalar_one_or_none()
            old_group_uuid = old_link.group_id if old_link else None

            if old_group_uuid == gid:
                return True  # Already assigned

            # Remove from old group
            if old_link:
                db.delete(old_link)
                self._update_doc_count(db, old_group_uuid)

            # Add to new group
            db.add(GroupDocument(group_id=gid, filename=filename))
            self._update_doc_count(db, gid)

            db.commit()

        # Update vector DB chunks
        self._update_vector_chunks([filename], group_id)

        logger.info(f"Assigned document '{filename}' to group {group_id}")
        return True

    def batch_assign_documents(self, filenames: List[str], group_id: str) -> int:
        """
        Assign multiple documents to a group (optimized for batch operations)

        Returns:
            Number of documents assigned

        Raises:
            ValueError: If group doesn't exist
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다.")

        if not filenames:
            return 0

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다.")

            files_to_assign = []
            old_groups: Dict[uuid.UUID, int] = {}  # {old_group_uuid: count}

            for fname in filenames:
                existing_stmt = select(GroupDocument).where(
                    GroupDocument.filename == fname
                )
                existing = db.execute(existing_stmt).scalar_one_or_none()

                if existing:
                    if existing.group_id == gid:
                        continue  # Already in target group
                    old_gid = existing.group_id
                    old_groups[old_gid] = old_groups.get(old_gid, 0) + 1
                    db.delete(existing)

                files_to_assign.append(fname)

            if not files_to_assign:
                logger.info(f"All {len(filenames)} documents are already in group {group_id}")
                return 0

            # Add new links
            for fname in files_to_assign:
                db.add(GroupDocument(group_id=gid, filename=fname))

            # Update counts
            for old_gid in old_groups:
                self._update_doc_count(db, old_gid)
            self._update_doc_count(db, gid)

            db.commit()

        # Update vector DB chunks
        if files_to_assign:
            self._update_vector_chunks(files_to_assign, group_id)

        logger.info(
            f"Batch assigned {len(files_to_assign)} documents to group {group_id} "
            f"(skipped {len(filenames) - len(files_to_assign)} already assigned)"
        )
        return len(files_to_assign)

    def _update_vector_chunks(self, filenames: List[str], group_id: str):
        """Update group_id on vector DB document chunks (PostgreSQL).

        Updates the group_id column in document_chunks for matching filenames.
        """
        if not filenames:
            return

        try:
            from .database.connection import SyncSessionFactory
            from .database.models.document_chunk import DocumentChunk
            from sqlalchemy import update

            with SyncSessionFactory() as session:
                stmt = (
                    update(DocumentChunk)
                    .where(DocumentChunk.filename.in_(filenames))
                    .values(group_id=group_id)
                )
                session.execute(stmt)
                session.commit()
        except Exception as e:
            logger.warning(f"Failed to update vector DB chunks: {e}")

    def remove_document_from_group(self, filename: str, group_id: str) -> bool:
        """
        Remove a document from a group (reassign to default group)

        Raises:
            ValueError: If group doesn't exist or document not in group
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다.")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다.")

            link_stmt = select(GroupDocument).where(
                GroupDocument.filename == filename,
            )
            link = db.execute(link_stmt).scalar_one_or_none()

            if not link:
                raise ValueError("문서가 그룹에 할당되어 있지 않습니다.")

            if link.group_id != gid:
                raise ValueError("문서가 지정된 그룹에 속해 있지 않습니다.")

        # Reassign to default group
        return self.assign_document(filename, str(DEFAULT_GROUP_UUID))

    def delete_document_from_all_groups(self, filename: str) -> bool:
        """
        Completely remove a document from all groups (used when deleting document)
        """
        try:
            with SyncSessionFactory() as db:
                # Find and delete all links for this filename
                del_stmt = delete(GroupDocument).where(
                    GroupDocument.filename == filename
                )
                result = db.execute(del_stmt)
                db.commit()

                if result.rowcount > 0:
                    logger.info(f"Removed document '{filename}' from all groups")

            return True
        except Exception as e:
            logger.error(f"Failed to delete document from groups: {e}")
            return False

    def get_group(self, group_id: str) -> Optional[Dict]:
        """
        Get group data

        Returns:
            Group data dictionary or None if not found
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            return None

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                return None

            # Get children
            children_stmt = select(DocumentGroup.id).where(
                DocumentGroup.parent_id == gid
            )
            children = [str(c) for c in db.execute(children_stmt).scalars().all()]

            # Get org links
            org_stmt = select(GroupOrganization).where(
                GroupOrganization.group_id == gid
            )
            org_links = db.execute(org_stmt).scalars().all()

            result = {
                'id': str(grp.id),
                'name': grp.name,
                'description': grp.description or '',
                'color': grp.color or '#4A90E2',
                'icon': grp.icon or '📁',
                'parent_id': str(grp.parent_id) if grp.parent_id else '',
                'org_id': str(org_links[0].org_id) if org_links else '',
                'created_at': grp.created_at.isoformat() if grp.created_at else '',
                'created_by': grp.created_by or 'system',
                'updated_at': grp.updated_at.isoformat() if grp.updated_at else '',
                'updated_by': grp.updated_by or 'system',
                'document_count': str(grp.document_count),
                'children': children,
            }

            # Add organization name
            if org_links:
                from .database.models.organization import Organization
                org = db.get(Organization, org_links[0].org_id)
                if org:
                    result['org_name'] = org.name

            return result

    def get_all_groups(self, org_id: Optional[str] = None) -> List[Dict]:
        """
        Get all groups, optionally filtered by organization

        Args:
            org_id: Organization ID to filter by (None = all groups)

        Returns:
            List of group dictionaries
        """
        with SyncSessionFactory() as db:
            if org_id:
                try:
                    org_uuid = uuid.UUID(org_id)
                except ValueError:
                    return []

                stmt = (
                    select(DocumentGroup)
                    .join(GroupOrganization)
                    .where(GroupOrganization.org_id == org_uuid)
                    .order_by(DocumentGroup.name)
                )
            else:
                stmt = select(DocumentGroup).order_by(DocumentGroup.name)

            groups_rows = db.execute(stmt).scalars().all()

            if not groups_rows:
                return []

            # Collect all group IDs for batch lookups
            group_uuids = [g.id for g in groups_rows]

            # Batch fetch children
            children_stmt = select(
                DocumentGroup.parent_id, DocumentGroup.id
            ).where(
                DocumentGroup.parent_id.in_(group_uuids)
            )
            children_map: Dict[uuid.UUID, List[str]] = {}
            for parent_id, child_id in db.execute(children_stmt).all():
                children_map.setdefault(parent_id, []).append(str(child_id))

            # Batch fetch org links
            org_link_stmt = select(GroupOrganization).where(
                GroupOrganization.group_id.in_(group_uuids)
            )
            org_link_map: Dict[uuid.UUID, List[uuid.UUID]] = {}
            for link in db.execute(org_link_stmt).scalars().all():
                org_link_map.setdefault(link.group_id, []).append(link.org_id)

            # Batch fetch org names
            all_org_ids = set()
            for org_ids in org_link_map.values():
                all_org_ids.update(org_ids)

            org_names: Dict[uuid.UUID, str] = {}
            if all_org_ids:
                from .database.models.organization import Organization
                org_stmt = select(Organization.id, Organization.name).where(
                    Organization.id.in_(list(all_org_ids))
                )
                for oid, oname in db.execute(org_stmt).all():
                    org_names[oid] = oname

            # Build results
            results = []
            for grp in groups_rows:
                org_ids = org_link_map.get(grp.id, [])
                first_org_id = org_ids[0] if org_ids else None

                result = {
                    'id': str(grp.id),
                    'name': grp.name,
                    'description': grp.description or '',
                    'color': grp.color or '#4A90E2',
                    'icon': grp.icon or '📁',
                    'parent_id': str(grp.parent_id) if grp.parent_id else '',
                    'org_id': str(first_org_id) if first_org_id else '',
                    'created_at': grp.created_at.isoformat() if grp.created_at else '',
                    'created_by': grp.created_by or 'system',
                    'updated_at': grp.updated_at.isoformat() if grp.updated_at else '',
                    'updated_by': grp.updated_by or 'system',
                    'document_count': str(grp.document_count),
                    'children': children_map.get(grp.id, []),
                }

                if first_org_id and first_org_id in org_names:
                    result['org_name'] = org_names[first_org_id]

                results.append(result)

            return results

    def get_group_tree(self, org_id: Optional[str] = None) -> Dict:
        """
        Get hierarchical group tree, optionally filtered by organization

        Returns:
            Tree structure with nested children
        """
        all_groups = {g['id']: g for g in self.get_all_groups(org_id=org_id)}

        included_groups = set()

        def build_tree(parent_id: Optional[str]) -> List[Dict]:
            result = []
            for gid, grp in all_groups.items():
                grp_parent = grp.get('parent_id', '')
                if parent_id is None:
                    if grp_parent:
                        continue  # Has parent, skip for root level
                else:
                    if grp_parent != parent_id:
                        continue

                included_groups.add(gid)
                node = grp.copy()
                node['children'] = build_tree(gid)
                result.append(node)

            result.sort(key=lambda x: x['name'])
            return result

        tree_children = build_tree(None)

        # Find orphaned groups
        orphaned_groups = []
        for gid, grp_data in all_groups.items():
            if gid not in included_groups:
                orphaned = grp_data.copy()
                orphaned['children'] = []
                orphaned_groups.append(orphaned)
                logger.warning(f"Orphaned group found: {gid} ({grp_data.get('name')})")

        if orphaned_groups:
            orphaned_groups.sort(key=lambda x: x['name'])
            tree_children.extend(orphaned_groups)

        return {
            'id': 'root',
            'name': '전체' if not org_id else '조직 그룹',
            'children': tree_children
        }

    def get_group_documents(self, group_id: str) -> List[str]:
        """Get filenames of documents in a group"""
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다.")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다.")

            stmt = select(GroupDocument.filename).where(
                GroupDocument.group_id == gid
            ).order_by(GroupDocument.filename)
            return [row[0] for row in db.execute(stmt).all()]

    def get_document_group(self, filename: str) -> Optional[str]:
        """Get the group ID of a document"""
        with SyncSessionFactory() as db:
            stmt = select(GroupDocument.group_id).where(
                GroupDocument.filename == filename
            )
            result = db.execute(stmt).scalar_one_or_none()
            return str(result) if result else None

    def sync_document_counts(self):
        """Recalculate and update document counts for all groups"""
        with SyncSessionFactory() as db:
            stmt = select(DocumentGroup)
            groups = db.execute(stmt).scalars().all()

            for grp in groups:
                cnt_stmt = select(func.count()).select_from(GroupDocument).where(
                    GroupDocument.group_id == grp.id
                )
                grp.document_count = db.execute(cnt_stmt).scalar_one()

            db.commit()

        logger.info("Synced document counts for all groups")

    def get_descendant_group_ids(self, group_id: str) -> List[str]:
        """Get all descendant group IDs including the parent"""
        result = [group_id]
        all_groups = self.get_all_groups()

        children_map = {}
        for group in all_groups:
            parent_id = group.get('parent_id', '')
            if parent_id:
                children_map.setdefault(parent_id, []).append(group['id'])

        def collect_descendants(pid: str):
            if pid in children_map:
                for child_id in children_map[pid]:
                    result.append(child_id)
                    collect_descendants(child_id)

        collect_descendants(group_id)
        return result

    def get_descendant_group_ids_batch(self, group_ids: List[str]) -> List[str]:
        """Get all descendant group IDs for multiple groups in a single operation"""
        if not group_ids:
            return []

        result = set(group_ids)
        all_groups = self.get_all_groups()

        children_map = {}
        for group in all_groups:
            parent_id = group.get('parent_id', '')
            if parent_id:
                children_map.setdefault(parent_id, []).append(group['id'])

        def collect_descendants(pid: str):
            if pid in children_map:
                for child_id in children_map[pid]:
                    result.add(child_id)
                    collect_descendants(child_id)

        for gid in group_ids:
            collect_descendants(gid)

        return list(result)

    # ========================================================================
    # N:M Relationship Methods (Group <-> Organization)
    # ========================================================================

    def add_group_to_organization(
        self,
        group_id: str,
        org_id: str,
        updated_by: str = 'system'
    ) -> bool:
        """
        Add a group to an organization (N:M relationship)
        Cascades to ancestors and descendants.

        Returns:
            True if successful

        Raises:
            ValueError: If group or organization doesn't exist
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다")

        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            raise ValueError("조직이 존재하지 않습니다")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다")

            # Check if already assigned
            if self._is_group_in_org(db, gid, oid):
                logger.info(f"Group {group_id} is already in organization {org_id}")
                return True

            # Get all ancestors
            ancestors = self._get_all_ancestor_uuids(db, gid)

            # Get all descendants
            descendants = self._get_all_descendant_uuids(db, gid)

            # Combine: ancestors + descendants (descendants includes the group itself)
            all_group_uuids = list(dict.fromkeys(ancestors + descendants))

            # Collect set for fast lookup
            groups_being_added = set(all_group_uuids)

            logger.info(
                f"Adding {len(all_group_uuids)} groups to organization {org_id} "
                f"({len(ancestors)} ancestors + {len(descendants)} including target and descendants)"
            )

            for guuid in all_group_uuids:
                # Skip if already linked
                if self._is_group_in_org(db, guuid, oid):
                    continue

                g = db.get(DocumentGroup, guuid)
                if not g:
                    continue

                # Determine is_root
                parent_in_org = False
                if g.parent_id:
                    parent_in_org = (
                        g.parent_id in groups_being_added
                        or self._is_group_in_org(db, g.parent_id, oid)
                    )

                link = GroupOrganization(
                    group_id=guuid,
                    org_id=oid,
                    is_root=not g.parent_id or not parent_in_org,
                )
                db.add(link)

                g.updated_by = updated_by

            db.commit()

        logger.info(f"Added group {group_id} and relatives to organization {org_id}")
        return True

    def _get_all_ancestor_uuids(self, db, group_uuid: uuid.UUID) -> List[uuid.UUID]:
        """Recursively get all ancestor group UUIDs."""
        ancestors = []
        grp = db.get(DocumentGroup, group_uuid)
        if grp and grp.parent_id:
            ancestors.append(grp.parent_id)
            ancestors.extend(self._get_all_ancestor_uuids(db, grp.parent_id))
        return ancestors

    def _is_group_in_org(self, db, group_uuid: uuid.UUID, org_uuid: uuid.UUID) -> bool:
        """Check if group-org link exists within a session."""
        stmt = select(GroupOrganization).where(
            GroupOrganization.group_id == group_uuid,
            GroupOrganization.org_id == org_uuid,
        )
        return db.execute(stmt).scalar_one_or_none() is not None

    def remove_group_from_organization(
        self,
        group_id: str,
        org_id: str,
        updated_by: str = 'system'
    ) -> bool:
        """
        Remove a group from an organization (cascades to descendants)

        Raises:
            ValueError: If group doesn't exist or not in organization
        """
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            raise ValueError("그룹이 존재하지 않습니다")

        try:
            oid = uuid.UUID(org_id)
        except ValueError:
            raise ValueError("조직이 존재하지 않습니다")

        if org_id == "default":
            raise ValueError("기본 조직에서는 그룹을 제거할 수 없습니다. 기본 조직은 모든 그룹의 홈입니다.")

        with SyncSessionFactory() as db:
            grp = db.get(DocumentGroup, gid)
            if not grp:
                raise ValueError("그룹이 존재하지 않습니다")

            if not self._is_group_in_org(db, gid, oid):
                raise ValueError("그룹이 해당 조직에 속하지 않습니다")

            # Get all descendants (includes self)
            all_group_uuids = self._get_all_descendant_uuids(db, gid)
            logger.info(f"Removing {len(all_group_uuids)} groups from organization {org_id}")

            for guuid in all_group_uuids:
                del_stmt = delete(GroupOrganization).where(
                    GroupOrganization.group_id == guuid,
                    GroupOrganization.org_id == oid,
                )
                db.execute(del_stmt)

                g = db.get(DocumentGroup, guuid)
                if g:
                    g.updated_by = updated_by

            db.commit()

        logger.info(f"Removed group {group_id} and descendants from organization {org_id}")
        return True

    def get_group_organizations(self, group_id: str) -> List[str]:
        """Get all organizations that a group belongs to"""
        try:
            gid = uuid.UUID(group_id)
        except ValueError:
            return []

        with SyncSessionFactory() as db:
            stmt = select(GroupOrganization.org_id).where(
                GroupOrganization.group_id == gid
            )
            return [str(row[0]) for row in db.execute(stmt).all()]

    def batch_get_group_counts(self, group_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Batch get document count and org count for multiple groups
        """
        if not group_ids:
            return {}

        group_uuids = []
        for gid_str in group_ids:
            try:
                group_uuids.append(uuid.UUID(gid_str))
            except ValueError:
                continue

        if not group_uuids:
            return {}

        with SyncSessionFactory() as db:
            # Batch document counts
            doc_count_stmt = (
                select(GroupDocument.group_id, func.count())
                .where(GroupDocument.group_id.in_(group_uuids))
                .group_by(GroupDocument.group_id)
            )
            doc_counts = {str(gid): cnt for gid, cnt in db.execute(doc_count_stmt).all()}

            # Batch org counts
            org_count_stmt = (
                select(GroupOrganization.group_id, func.count())
                .where(GroupOrganization.group_id.in_(group_uuids))
                .group_by(GroupOrganization.group_id)
            )
            org_counts = {str(gid): cnt for gid, cnt in db.execute(org_count_stmt).all()}

        counts = {}
        for gid_str in group_ids:
            counts[gid_str] = {
                'document_count': doc_counts.get(gid_str, 0),
                'org_count': org_counts.get(gid_str, 0),
            }
        return counts

    def is_group_in_organization(self, group_id: str, org_id: str) -> bool:
        """Check if a group belongs to an organization"""
        try:
            gid = uuid.UUID(group_id)
            oid = uuid.UUID(org_id)
        except ValueError:
            return False

        with SyncSessionFactory() as db:
            return self._is_group_in_org(db, gid, oid)
