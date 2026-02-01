"""
Document Group Management System

Handles CRUD operations for hierarchical document groups with Redis backend.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set
import redis
from loguru import logger


class GroupManager:
    """Manages hierarchical document groups with Redis storage"""

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize GroupManager

        Args:
            redis_client: Redis client instance
        """
        self.client = redis_client
        self._ensure_default_group()

    def _ensure_default_group(self) -> str:
        """
        Ensure default 'uncategorized' group exists

        Returns:
            Default group ID
        """
        default_key = 'group:default'
        default_id = self.client.get(default_key)

        if default_id:
            return default_id.decode('utf-8')

        # Create default group
        group_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        group_data = {
            'id': group_id,
            'name': '미분류',
            'description': '그룹에 할당되지 않은 문서',
            'color': '#9CA3AF',
            'icon': '📂',
            'parent_id': '',
            'created_at': now,
            'created_by': 'system',
            'updated_at': now,
            'updated_by': 'system',
            'document_count': '0'
        }

        self.client.hset(f'group:{group_id}', mapping=group_data)
        self.client.set(default_key, group_id)
        self.client.sadd('groups:all', group_id)  # Add to global groups index

        logger.info(f"Created default group: {group_id}")
        return group_id

    def get_default_group_id(self) -> str:
        """Get default group ID"""
        default_id = self.client.get('group:default')
        if not default_id:
            return self._ensure_default_group()
        return default_id.decode('utf-8')

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

        Args:
            name: Group name (max 100 chars)
            org_id: Organization ID (optional - can be assigned later)
            description: Group description
            color: Hex color code (e.g., #4A90E2)
            icon: Emoji icon (e.g., 📁)
            parent_id: Parent group ID (None for root)
            created_by: Username who created the group

        Returns:
            New group ID

        Raises:
            ValueError: If validation fails
        """
        # Validate inputs
        if not name or not name.strip():
            raise ValueError("그룹 이름은 필수입니다.")

        if len(name) > 100:
            raise ValueError("그룹 이름은 100자를 초과할 수 없습니다.")

        # Validate parent exists and belongs to same organization (if org_id is provided)
        if parent_id:
            parent_data = self.client.hgetall(f'group:{parent_id}')
            if not parent_data:
                raise ValueError("상위 그룹이 존재하지 않습니다.")

            parent_org_id = parent_data.get(b'org_id', b'').decode('utf-8')
            # Only validate org match if this group has an org_id
            if org_id and parent_org_id and parent_org_id != org_id:
                raise ValueError("상위 그룹은 같은 조직에 속해야 합니다.")

        # Generate group ID
        group_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # Prepare group data
        group_data = {
            'id': group_id,
            'name': name.strip(),
            'description': description.strip(),
            'color': color,
            'icon': icon,
            'parent_id': parent_id or '',
            'org_id': org_id or '',  # Organization ID (empty if not assigned)
            'created_at': now,
            'created_by': created_by,
            'updated_at': now,
            'updated_by': created_by,
            'document_count': '0'
        }

        # Store group and update indices
        pipe = self.client.pipeline()
        pipe.hset(f'group:{group_id}', mapping=group_data)

        # Add to global groups index (for efficient lookup without org_id)
        pipe.sadd('groups:all', group_id)

        # Add to organization's groups index only if org_id is provided
        if org_id:
            pipe.sadd(f'org:groups:{org_id}', group_id)

            if parent_id:
                pipe.sadd(f'group:children:{parent_id}', group_id)
            else:
                # Add to org-specific root
                pipe.sadd(f'org:groups:root:{org_id}', group_id)
        else:
            # No organization assignment
            if parent_id:
                pipe.sadd(f'group:children:{parent_id}', group_id)
            else:
                # Add to global root (for admin view without org filter)
                pipe.sadd(f'group:children:root', group_id)

        pipe.execute()

        org_info = f"in org {org_id}" if org_id else "without org assignment"
        logger.info(f"Created group: {group_id} ({name}) {org_info}")
        return group_id

    def _is_descendant(self, potential_descendant_id: str, ancestor_id: str) -> bool:
        """
        Check if potential_descendant is a descendant of ancestor
        
        Used to prevent circular references when changing parent_id
        
        Args:
            potential_descendant_id: ID of potential descendant
            ancestor_id: ID of potential ancestor
            
        Returns:
            True if potential_descendant is a descendant of ancestor
        """
        visited = set()
        current_id = potential_descendant_id
        
        while current_id and current_id not in visited:
            if current_id == ancestor_id:
                return True
            
            visited.add(current_id)
            
            # Get parent of current group
            group_data = self.client.hgetall(f'group:{current_id}')
            if not group_data:
                break
            
            parent_id = group_data.get(b'parent_id', b'').decode('utf-8')
            current_id = parent_id if parent_id else None
        
        return False

    def update_group(
        self,
        group_id: str,
        updated_by: str = 'user',
        **updates
    ) -> bool:
        """
        Update group metadata

        Args:
            group_id: Group ID to update
            updated_by: Username who updated the group
            **updates: Fields to update (name, description, color, icon, parent_id)

        Returns:
            True if successful

        Raises:
            ValueError: If group doesn't exist or validation fails
        """
        group_key = f'group:{group_id}'

        if not self.client.exists(group_key):
            raise ValueError("그룹이 존재하지 않습니다.")

        # Prevent updating default group name
        if group_id == self.get_default_group_id() and 'name' in updates:
            raise ValueError("기본 그룹의 이름은 변경할 수 없습니다.")

        # Validate updates
        allowed_fields = {'name', 'description', 'color', 'icon', 'parent_id'}
        update_data = {k: v for k, v in updates.items() if k in allowed_fields}

        if 'name' in update_data:
            if not update_data['name'] or not update_data['name'].strip():
                raise ValueError("그룹 이름은 필수입니다.")
            if len(update_data['name']) > 100:
                raise ValueError("그룹 이름은 100자를 초과할 수 없습니다.")
            update_data['name'] = update_data['name'].strip()

        if 'description' in update_data:
            update_data['description'] = update_data['description'].strip()

        # Handle parent_id changes
        if 'parent_id' in update_data:
            new_parent_id = update_data['parent_id']

            # Get current parent_id to update children indexes
            current_group_data = self.client.hgetall(group_key)
            old_parent_id = current_group_data.get(b'parent_id', b'').decode('utf-8') if current_group_data else ''

            # Validate parent_id
            if new_parent_id:
                # Can't set parent to itself
                if new_parent_id == group_id:
                    raise ValueError("그룹을 자신의 하위로 설정할 수 없습니다.")

                # Parent must exist
                if not self.client.exists(f'group:{new_parent_id}'):
                    raise ValueError("상위 그룹이 존재하지 않습니다.")

                # Can't set parent to a descendant (circular reference prevention)
                if self._is_descendant(new_parent_id, group_id):
                    raise ValueError("하위 그룹을 상위 그룹으로 설정할 수 없습니다.")

            # Update parent-child relationship indexes
            pipe = self.client.pipeline()

            # Remove from old parent's children (if had a parent)
            if old_parent_id:
                pipe.srem(f'group:children:{old_parent_id}', group_id)
                logger.info(f"Removing {group_id} from children of {old_parent_id}")

            # Add to new parent's children (if has a new parent)
            if new_parent_id:
                pipe.sadd(f'group:children:{new_parent_id}', group_id)
                logger.info(f"Adding {group_id} to children of {new_parent_id}")

            pipe.execute()

            # Update GLOBAL root index (for admin view without org filter)
            if new_parent_id:
                # Has parent → remove from global root
                self.client.srem('group:children:root', group_id)
                logger.info(f"Removed group {group_id} from global root (new parent: {new_parent_id})")
            else:
                # No parent → add to global root
                self.client.sadd('group:children:root', group_id)
                logger.info(f"Added group {group_id} to global root (no parent)")

            # Update organization root indexes
            # Get all organizations this group belongs to
            group_orgs = self.get_group_organizations(group_id)

            for org_id in group_orgs:
                # Check if new parent is in the same organization
                parent_in_org = False
                if new_parent_id:
                    parent_in_org = self.is_group_in_organization(new_parent_id, org_id)

                # Update root index
                if new_parent_id and parent_in_org:
                    # Has parent in same org → remove from root
                    self.client.srem(f'org:groups:root:{org_id}', group_id)
                    logger.info(f"Removed group {group_id} from root of organization {org_id} (new parent: {new_parent_id})")
                else:
                    # No parent or parent not in org → add to root
                    self.client.sadd(f'org:groups:root:{org_id}', group_id)
                    logger.info(f"Added group {group_id} to root of organization {org_id} (parent: {new_parent_id or 'none'})")

            # Store empty string instead of None for consistency
            update_data['parent_id'] = new_parent_id if new_parent_id else ''

        # Add metadata
        update_data['updated_at'] = datetime.now().isoformat()
        update_data['updated_by'] = updated_by

        # Update
        self.client.hset(group_key, mapping=update_data)

        logger.info(f"Updated group: {group_id}")
        return True

    def change_group_organization(
        self,
        group_id: str,
        new_org_id: str,
        updated_by: str = 'user'
    ) -> bool:
        """
        Change the organization of a group and all its descendants

        Args:
            group_id: Group ID to move
            new_org_id: Target organization ID
            updated_by: Username who performed the change

        Returns:
            True if successful

        Raises:
            ValueError: If group doesn't exist, is default group, or org doesn't exist
        """
        from .organization_manager import OrganizationManager

        group_key = f'group:{group_id}'

        # Validate group exists
        if not self.client.exists(group_key):
            raise ValueError("그룹이 존재하지 않습니다.")

        # Prevent moving default group
        if group_id == self.get_default_group_id():
            raise ValueError("기본 그룹은 다른 조직으로 이동할 수 없습니다.")

        # Get current organization
        group_data = self.client.hgetall(group_key)
        old_org_id = group_data.get(b'org_id', b'').decode('utf-8')

        if old_org_id == new_org_id:
            raise ValueError("그룹이 이미 해당 조직에 속해 있습니다.")

        # Validate new organization exists
        org_manager = OrganizationManager(self.client)
        if not org_manager.get_organization(new_org_id):
            raise ValueError("대상 조직이 존재하지 않습니다.")

        # Get all descendant groups (children, grandchildren, etc.)
        def get_all_descendants(gid: str) -> list:
            """Recursively get all descendant group IDs"""
            descendants = [gid]
            children_key = f'group:children:{gid}'
            children_ids = self.client.smembers(children_key)

            for child_id_bytes in children_ids:
                child_id = child_id_bytes.decode('utf-8')
                descendants.extend(get_all_descendants(child_id))

            return descendants

        all_group_ids = get_all_descendants(group_id)

        # Update all groups in a transaction
        pipe = self.client.pipeline()

        for gid in all_group_ids:
            # Update group's org_id
            pipe.hset(f'group:{gid}', 'org_id', new_org_id)
            pipe.hset(f'group:{gid}', 'updated_at', datetime.now().isoformat())
            pipe.hset(f'group:{gid}', 'updated_by', updated_by)

            # Update organization indices
            pipe.srem(f'org:groups:{old_org_id}', gid)
            pipe.sadd(f'org:groups:{new_org_id}', gid)

        # Update parent references if this is a root group
        parent_id = group_data.get(b'parent_id', b'').decode('utf-8')
        if not parent_id:
            # Remove from old org root and add to new org root
            pipe.srem(f'org:groups:root:{old_org_id}', group_id)
            pipe.sadd(f'org:groups:root:{new_org_id}', group_id)

        pipe.execute()

        logger.info(f"Moved group {group_id} and {len(all_group_ids)-1} descendants from org {old_org_id} to {new_org_id}")
        return True

    def delete_group(
        self,
        group_id: str,
        reassign_to: Optional[str] = None
    ) -> int:
        """
        Delete group and reassign documents

        Args:
            group_id: Group ID to delete
            reassign_to: Group ID to reassign documents to (None = parent or default)

        Returns:
            Number of documents reassigned

        Raises:
            ValueError: If group doesn't exist or is default group
        """
        group_key = f'group:{group_id}'

        if not self.client.exists(group_key):
            raise ValueError("그룹이 존재하지 않습니다.")

        # Prevent deleting default group
        if group_id == self.get_default_group_id():
            raise ValueError("기본 그룹은 삭제할 수 없습니다.")

        # Get group data
        group_data = self.client.hgetall(group_key)
        parent_id = group_data.get(b'parent_id', b'').decode('utf-8')

        # Determine reassignment target
        if reassign_to is None:
            reassign_to = parent_id if parent_id else self.get_default_group_id()

        if not self.client.exists(f'group:{reassign_to}'):
            raise ValueError("재할당 대상 그룹이 존재하지 않습니다.")

        # Get documents in this group
        doc_set_key = f'group:docs:{group_id}'
        documents = self.client.smembers(doc_set_key)
        filenames = [doc.decode('utf-8') for doc in documents]

        # Reassign documents
        reassigned_count = 0
        if filenames:
            reassigned_count = self.batch_assign_documents(filenames, reassign_to)

        # Move child groups to parent
        children_key = f'group:children:{group_id}'
        children = self.client.smembers(children_key)

        pipe = self.client.pipeline()

        for child_id_bytes in children:
            child_id = child_id_bytes.decode('utf-8')
            # Update child's parent_id
            pipe.hset(f'group:{child_id}', 'parent_id', parent_id or '')
            # Move to parent's children set
            if parent_id:
                pipe.sadd(f'group:children:{parent_id}', child_id)
            else:
                pipe.sadd('group:children:root', child_id)

        # Remove group from parent's children
        if parent_id:
            pipe.srem(f'group:children:{parent_id}', group_id)
        else:
            pipe.srem('group:children:root', group_id)

        # Remove from global groups index
        pipe.srem('groups:all', group_id)

        # Delete group data
        pipe.delete(group_key)
        pipe.delete(doc_set_key)
        pipe.delete(children_key)

        pipe.execute()

        logger.info(f"Deleted group: {group_id}, reassigned {reassigned_count} documents")
        return reassigned_count

    def move_group(
        self,
        group_id: str,
        new_parent_id: Optional[str],
        updated_by: str = 'user'
    ) -> bool:
        """
        Move group to a new parent

        Args:
            group_id: Group ID to move
            new_parent_id: New parent group ID (None for root)
            updated_by: Username who moved the group

        Returns:
            True if successful

        Raises:
            ValueError: If circular hierarchy or group doesn't exist
        """
        group_key = f'group:{group_id}'

        if not self.client.exists(group_key):
            raise ValueError("그룹이 존재하지 않습니다.")

        # Prevent moving default group
        if group_id == self.get_default_group_id():
            raise ValueError("기본 그룹은 이동할 수 없습니다.")

        # Validate new parent exists
        if new_parent_id and not self.client.exists(f'group:{new_parent_id}'):
            raise ValueError("새 상위 그룹이 존재하지 않습니다.")

        # Prevent circular hierarchy
        if new_parent_id and not self.validate_hierarchy(new_parent_id, group_id):
            raise ValueError("순환 참조가 발생합니다.")

        # Get current parent
        group_data = self.client.hgetall(group_key)
        old_parent_id = group_data.get(b'parent_id', b'').decode('utf-8')

        # Update parent
        pipe = self.client.pipeline()

        # Remove from old parent's children
        if old_parent_id:
            pipe.srem(f'group:children:{old_parent_id}', group_id)
        else:
            pipe.srem('group:children:root', group_id)

        # Add to new parent's children
        if new_parent_id:
            pipe.sadd(f'group:children:{new_parent_id}', group_id)
        else:
            pipe.sadd('group:children:root', group_id)

        # Update group's parent_id
        pipe.hset(group_key, mapping={
            'parent_id': new_parent_id or '',
            'updated_at': datetime.now().isoformat(),
            'updated_by': updated_by
        })

        pipe.execute()

        logger.info(f"Moved group: {group_id} from {old_parent_id} to {new_parent_id}")
        return True

    def validate_hierarchy(self, parent_id: str, child_id: str) -> bool:
        """
        Check if making child_id a parent of parent_id would create a cycle

        Args:
            parent_id: Proposed parent group ID
            child_id: Proposed child group ID

        Returns:
            True if valid (no cycle), False if cycle detected
        """
        if parent_id == child_id:
            return False

        # Traverse up the tree from parent_id
        current = parent_id
        visited = set()

        while current:
            if current in visited:
                # Circular reference in existing data
                logger.warning(f"Circular reference detected at {current}")
                return False

            if current == child_id:
                # Would create a cycle
                return False

            visited.add(current)

            # Get parent of current
            group_data = self.client.hgetall(f'group:{current}')
            if not group_data:
                break

            parent = group_data.get(b'parent_id', b'').decode('utf-8')
            current = parent if parent else None

        return True

    def assign_document(self, filename: str, group_id: str) -> bool:
        """
        Assign a document to a group

        Args:
            filename: Document filename
            group_id: Target group ID

        Returns:
            True if successful

        Raises:
            ValueError: If group doesn't exist
        """
        group_key = f'group:{group_id}'

        if not self.client.exists(group_key):
            raise ValueError("그룹이 존재하지 않습니다.")

        # Get old group
        old_group_key = f'doc:group:{filename}'
        old_group_id = self.client.get(old_group_key)

        if old_group_id:
            old_group_id = old_group_id.decode('utf-8')

        # Use pipeline for atomic updates
        pipe = self.client.pipeline()

        # Get active index for efficient scanning
        active_index = self.client.get("index:active")
        if active_index:
            active_index = active_index.decode('utf-8')
            index_pattern = f"doc:{active_index}:*"
        else:
            # Fallback to all docs if no active index
            index_pattern = "doc:*"

        # Step 1: Collect all candidate keys (with higher count for efficiency)
        candidate_keys = []
        for key in self.client.scan_iter(match=index_pattern, count=5000):
            key_str = key.decode('utf-8')
            # Skip special keys (doc:group:, doc:hash:, doc:counts:, doc:version:, doc:files)
            parts = key_str.split(':')
            if len(parts) >= 2 and parts[1] in ['group', 'hash', 'counts', 'version', 'files']:
                continue
            candidate_keys.append(key)

        # Step 2: Batch fetch all filenames using pipeline (N+1 방지)
        if candidate_keys:
            filename_pipe = self.client.pipeline()
            for key in candidate_keys:
                filename_pipe.hget(key, 'filename')
            filenames_result = filename_pipe.execute()

            # Step 3: Filter and queue updates for matching files
            for key, chunk_filename in zip(candidate_keys, filenames_result):
                if chunk_filename and chunk_filename.decode('utf-8') == filename:
                    pipe.hset(key, 'group_id', group_id)

        # Update group sets
        if old_group_id and old_group_id != group_id:
            pipe.srem(f'group:docs:{old_group_id}', filename)
            # Decrement old group count
            pipe.hincrby(f'group:{old_group_id}', 'document_count', -1)

        pipe.sadd(f'group:docs:{group_id}', filename)
        pipe.set(old_group_key, group_id)

        # Increment new group count
        pipe.hincrby(group_key, 'document_count', 1)

        pipe.execute()

        logger.info(f"Assigned document '{filename}' to group {group_id}")
        return True

    def batch_assign_documents(self, filenames: List[str], group_id: str) -> int:
        """
        Assign multiple documents to a group (optimized for batch operations)

        Args:
            filenames: List of document filenames
            group_id: Target group ID

        Returns:
            Number of documents assigned

        Raises:
            ValueError: If group doesn't exist
        """
        if not self.client.exists(f'group:{group_id}'):
            raise ValueError("그룹이 존재하지 않습니다.")

        if not filenames:
            return 0

        # First, check which files need to be reassigned (skip already assigned)
        files_to_assign = {}  # {filename: old_group_id}
        for filename in filenames:
            old_group_key = f'doc:group:{filename}'
            current_group_id = self.client.get(old_group_key)

            if current_group_id:
                current_group_id = current_group_id.decode('utf-8')
                # Skip if already in target group
                if current_group_id == group_id:
                    continue
                files_to_assign[filename] = current_group_id
            else:
                files_to_assign[filename] = None

        # If no files need assignment, return early
        if not files_to_assign:
            logger.info(f"All {len(filenames)} documents are already in group {group_id}")
            return 0

        # Convert to set for faster lookups
        filenames_to_assign = set(files_to_assign.keys())

        # Track old groups and their document counts
        old_groups = {}  # {old_group_id: count}

        # Use pipeline for atomic batch updates
        pipe = self.client.pipeline()

        # Get active index for efficient scanning
        active_index = self.client.get("index:active")
        if active_index:
            active_index = active_index.decode('utf-8')
            index_pattern = f"doc:{active_index}:*"
        else:
            # Fallback to all docs if no active index
            index_pattern = "doc:*"

        # Step 1: Collect all candidate keys (with higher count for efficiency)
        candidate_keys = []
        for key in self.client.scan_iter(match=index_pattern, count=5000):
            key_str = key.decode('utf-8')

            # Skip special keys (doc:group:, doc:hash:, doc:counts:, doc:version:, doc:files)
            parts = key_str.split(':')
            if len(parts) >= 2 and parts[1] in ['group', 'hash', 'counts', 'version', 'files']:
                continue
            candidate_keys.append(key)

        # Step 2: Batch fetch all filenames using pipeline (N+1 방지)
        if candidate_keys:
            filename_pipe = self.client.pipeline()
            for key in candidate_keys:
                filename_pipe.hget(key, 'filename')
            filenames_result = filename_pipe.execute()

            # Step 3: Filter and queue updates for matching files
            for key, chunk_filename in zip(candidate_keys, filenames_result):
                if chunk_filename:
                    fname = chunk_filename.decode('utf-8')
                    if fname in filenames_to_assign:
                        # Update group_id for this chunk
                        pipe.hset(key, 'group_id', group_id)

        # Update group sets and counts
        for filename, old_group_id in files_to_assign.items():
            # Remove from old group if exists
            if old_group_id:
                pipe.srem(f'group:docs:{old_group_id}', filename)
                # Track for count decrement
                old_groups[old_group_id] = old_groups.get(old_group_id, 0) + 1

            # Add to new group
            pipe.sadd(f'group:docs:{group_id}', filename)
            pipe.set(f'doc:group:{filename}', group_id)

        # Decrement old group counts
        for old_group_id, count in old_groups.items():
            pipe.hincrby(f'group:{old_group_id}', 'document_count', -count)

        # Increment new group count
        pipe.hincrby(f'group:{group_id}', 'document_count', len(files_to_assign))

        # Execute all operations atomically
        pipe.execute()

        logger.info(f"Batch assigned {len(files_to_assign)} documents to group {group_id} (skipped {len(filenames) - len(files_to_assign)} already assigned)")
        return len(files_to_assign)

    def remove_document_from_group(self, filename: str, group_id: str) -> bool:
        """
        Remove a document from a group (reassign to default group)

        Args:
            filename: Document filename
            group_id: Group ID to remove from

        Returns:
            True if successful

        Raises:
            ValueError: If group doesn't exist or document not in group
        """
        group_key = f'group:{group_id}'

        if not self.client.exists(group_key):
            raise ValueError("그룹이 존재하지 않습니다.")

        # Check if document is in this group
        doc_group_key = f'doc:group:{filename}'
        current_group_id = self.client.get(doc_group_key)

        if not current_group_id:
            raise ValueError("문서가 그룹에 할당되어 있지 않습니다.")

        current_group_id = current_group_id.decode('utf-8')
        if current_group_id != group_id:
            raise ValueError("문서가 지정된 그룹에 속해 있지 않습니다.")

        # Reassign to default group
        default_group_id = self.get_default_group_id()
        success = self.assign_document(filename, default_group_id)

        if success:
            logger.info(f"Removed document '{filename}' from group {group_id}, reassigned to default")

        return success

    def delete_document_from_all_groups(self, filename: str) -> bool:
        """
        Completely remove a document from all groups (used when deleting document)

        Args:
            filename: Document filename

        Returns:
            True if successful
        """
        try:
            # Get the group this document belongs to
            doc_group_key = f'doc:group:{filename}'
            group_id = self.client.get(doc_group_key)

            if group_id:
                group_id = group_id.decode('utf-8')

                # Remove from group's document set
                self.client.srem(f'group:docs:{group_id}', filename)

                # Decrement group's document count
                self.client.hincrby(f'group:{group_id}', 'document_count', -1)

                logger.info(f"Removed document '{filename}' from group {group_id}")

            # Delete the document-group mapping
            self.client.delete(doc_group_key)

            return True

        except Exception as e:
            logger.error(f"Failed to delete document from groups: {e}")
            return False

    def get_group(self, group_id: str) -> Optional[Dict]:
        """
        Get group data

        Args:
            group_id: Group ID

        Returns:
            Group data dictionary or None if not found
        """
        group_data = self.client.hgetall(f'group:{group_id}')

        if not group_data:
            return None

        # Convert bytes to strings
        result = {k.decode('utf-8'): v.decode('utf-8') for k, v in group_data.items()}

        # Add children
        children = self.client.smembers(f'group:children:{group_id}')
        result['children'] = [c.decode('utf-8') for c in children]

        # Add organization name if org_id exists
        org_id = result.get('org_id')
        if org_id:
            org_data = self.client.hgetall(f'org:{org_id}')
            if org_data:
                org_name = org_data.get(b'name')
                if org_name:
                    result['org_name'] = org_name.decode('utf-8')

        return result

    def get_all_groups(self, org_id: Optional[str] = None) -> List[Dict]:
        """
        Get all groups, optionally filtered by organization (Pipeline 최적화)

        Args:
            org_id: Organization ID to filter by (None = all groups, for system admin)

        Returns:
            List of group dictionaries
        """
        # Step 1: Collect group IDs
        group_id_list = []
        if org_id:
            group_ids_bytes = self.client.smembers(f'org:groups:{org_id}')
            group_id_list = [gid.decode('utf-8') for gid in group_ids_bytes]
        else:
            # Use global groups index (O(1) instead of scan_iter O(n))
            group_ids_bytes = self.client.smembers('groups:all')
            group_id_list = [gid.decode('utf-8') for gid in group_ids_bytes]

            # Fallback: rebuild index if groups:all is empty but group keys exist
            if not group_id_list:
                import re
                uuid_pattern = re.compile(r'^group:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$')
                for key in self.client.scan_iter(match='group:*', count=100):
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    m = uuid_pattern.match(key_str)
                    if m and self.client.type(key) == b'hash':
                        group_id_list.append(m.group(1))
                if group_id_list:
                    self.client.sadd('groups:all', *group_id_list)
                    logger.warning(f"Rebuilt groups:all index with {len(group_id_list)} groups")

        if not group_id_list:
            return []

        # Step 2: Batch fetch group data and children using Pipeline
        pipe = self.client.pipeline()
        for gid in group_id_list:
            pipe.hgetall(f'group:{gid}')
            pipe.smembers(f'group:children:{gid}')
        results = pipe.execute()

        # Step 3: Parse group data and collect org_ids for batch lookup
        groups = []
        org_ids_to_fetch = set()
        for i, group_id in enumerate(group_id_list):
            group_data = results[i * 2]
            children_data = results[i * 2 + 1]

            if not group_data:
                continue

            # Convert bytes to strings
            result = {k.decode('utf-8'): v.decode('utf-8') for k, v in group_data.items()}
            result['id'] = group_id
            result['children'] = [c.decode('utf-8') for c in children_data]

            org_id_val = result.get('org_id')
            if org_id_val:
                org_ids_to_fetch.add(org_id_val)

            groups.append(result)

        # Step 4: Batch fetch org names using Pipeline
        if org_ids_to_fetch:
            org_id_list = list(org_ids_to_fetch)
            pipe = self.client.pipeline()
            for oid in org_id_list:
                pipe.hget(f'org:{oid}', 'name')
            org_name_results = pipe.execute()

            org_names = {}
            for oid, name in zip(org_id_list, org_name_results):
                if name:
                    org_names[oid] = name.decode('utf-8') if isinstance(name, bytes) else name

            # Attach org_name to groups
            for group in groups:
                oid = group.get('org_id')
                if oid and oid in org_names:
                    group['org_name'] = org_names[oid]

        return groups

    def get_group_tree(self, org_id: Optional[str] = None) -> Dict:
        """
        Get hierarchical group tree, optionally filtered by organization

        Args:
            org_id: Organization ID to filter by (None = all groups, for system admin)

        Returns:
            Tree structure with nested children
        """
        # Get all groups for organization
        all_groups = {g['id']: g for g in self.get_all_groups(org_id=org_id)}

        # Track which groups are included in the tree
        included_groups = set()

        # Build tree structure
        def build_tree(parent_id: Optional[str]) -> List[Dict]:
            if parent_id:
                children_key = f'group:children:{parent_id}'
            else:
                # Use org-specific root or global root
                if org_id:
                    children_key = f'org:groups:root:{org_id}'
                else:
                    children_key = 'group:children:root'

            children_ids = self.client.smembers(children_key)

            result = []
            for child_id_bytes in children_ids:
                child_id = child_id_bytes.decode('utf-8')
                if child_id in all_groups:
                    group = all_groups[child_id].copy()
                    included_groups.add(child_id)
                    group['children'] = build_tree(child_id)
                    result.append(group)

            # Sort by name
            result.sort(key=lambda x: x['name'])
            return result

        # Build tree starting from root
        tree_children = build_tree(None)

        # Find orphaned groups (in org but not in tree structure)
        orphaned_groups = []
        for group_id, group_data in all_groups.items():
            if group_id not in included_groups:
                orphaned = group_data.copy()
                orphaned['children'] = []
                orphaned_groups.append(orphaned)
                logger.warning(f"Orphaned group found: {group_id} ({group_data.get('name')})")

        # Add orphaned groups to root level
        if orphaned_groups:
            orphaned_groups.sort(key=lambda x: x['name'])
            tree_children.extend(orphaned_groups)

        return {
            'id': 'root',
            'name': '전체' if not org_id else f'조직 그룹',
            'children': tree_children
        }

    def get_group_documents(self, group_id: str) -> List[str]:
        """
        Get filenames of documents in a group

        Args:
            group_id: Group ID

        Returns:
            List of filenames
        """
        if not self.client.exists(f'group:{group_id}'):
            raise ValueError("그룹이 존재하지 않습니다.")

        docs = self.client.smembers(f'group:docs:{group_id}')
        return sorted([d.decode('utf-8') for d in docs])

    def get_document_group(self, filename: str) -> Optional[str]:
        """
        Get the group ID of a document

        Args:
            filename: Document filename

        Returns:
            Group ID or None if not assigned
        """
        group_id = self.client.get(f'doc:group:{filename}')
        return group_id.decode('utf-8') if group_id else None

    def sync_document_counts(self):
        """Recalculate and update document counts for all groups"""
        all_groups = self.get_all_groups()

        pipe = self.client.pipeline()
        for group in all_groups:
            group_id = group['id']
            actual_count = self.client.scard(f'group:docs:{group_id}')
            pipe.hset(f'group:{group_id}', 'document_count', actual_count)

        pipe.execute()
        logger.info("Synced document counts for all groups")

    def get_descendant_group_ids(self, group_id: str) -> List[str]:
        """
        Get all descendant group IDs (children, grandchildren, etc.)

        Args:
            group_id: Parent group ID

        Returns:
            List of all descendant group IDs including the parent
        """
        result = [group_id]
        all_groups = self.get_all_groups()

        # Build parent-children mapping
        children_map = {}
        for group in all_groups:
            parent_id = group.get('parent_id', '')
            if parent_id:
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(group['id'])

        # Recursively collect all descendants
        def collect_descendants(parent_id: str):
            if parent_id in children_map:
                for child_id in children_map[parent_id]:
                    result.append(child_id)
                    collect_descendants(child_id)

        collect_descendants(group_id)
        return result

    # ========================================================================
    # N:M Relationship Methods (Group ↔ Organization)
    # ========================================================================

    def add_group_to_organization(
        self,
        group_id: str,
        org_id: str,
        updated_by: str = 'system'
    ) -> bool:
        """
        Add a group to an organization (N:M relationship)

        A group can belong to multiple organizations.
        This adds the relationship without removing existing ones.

        Root group logic:
        - If the group has NO parent_id → always root
        - If the group HAS parent_id BUT parent is NOT in this org → root
        - If the group HAS parent_id AND parent IS in this org → NOT root (child)

        Args:
            group_id: Group ID to add
            org_id: Organization ID to add to
            updated_by: Username who performed the action

        Returns:
            True if successful

        Raises:
            ValueError: If group or organization doesn't exist
        """
        from datetime import datetime

        # Validate group exists
        group_key = f'group:{group_id}'
        if not self.client.exists(group_key):
            raise ValueError("그룹이 존재하지 않습니다")

        # Check if already assigned
        if self.is_group_in_organization(group_id, org_id):
            logger.info(f"Group {group_id} is already in organization {org_id}")
            return True

        # 🆕 Cascade addition: Get all ancestors (parents, grandparents, etc.)
        def get_all_ancestors(gid: str) -> list:
            """Recursively get all ancestor group IDs"""
            ancestors = []

            # Get group data to check parent_id
            gid_key = f'group:{gid}'
            group_data = self.client.hgetall(gid_key)
            parent_id = group_data.get(b'parent_id', b'').decode('utf-8') if b'parent_id' in group_data else ''

            if parent_id:
                ancestors.append(parent_id)
                ancestors.extend(get_all_ancestors(parent_id))

            return ancestors

        # 🆕 Cascade addition: Get all descendants (children, grandchildren, etc.)
        def get_all_descendants(gid: str) -> list:
            """Recursively get all descendant group IDs"""
            descendants = [gid]
            children_key = f'group:children:{gid}'
            children_ids = self.client.smembers(children_key)

            for child_id_bytes in children_ids:
                child_id = child_id_bytes.decode('utf-8') if isinstance(child_id_bytes, bytes) else child_id_bytes
                descendants.extend(get_all_descendants(child_id))

            return descendants

        # Get all groups to add (ancestors + target group + descendants)
        # This maintains tree structure: when adding a child, parents are auto-added
        ancestors = get_all_ancestors(group_id)
        descendants = get_all_descendants(group_id)

        # Combine all groups: ancestors first (for proper tree order), then descendants
        all_group_ids = ancestors + descendants

        # Remove duplicates while preserving order
        seen = set()
        all_group_ids = [x for x in all_group_ids if not (x in seen or seen.add(x))]

        logger.info(f"Adding {len(all_group_ids)} groups to organization {org_id} "
                   f"({len(ancestors)} ancestors + {len(descendants)} including target and descendants)")

        # Convert to set for faster lookup
        groups_being_added = set(all_group_ids)

        # Add bidirectional relationship for all groups
        pipe = self.client.pipeline()

        for gid in all_group_ids:
            # Get group data to check parent_id
            gid_key = f'group:{gid}'
            group_data = self.client.hgetall(gid_key)
            parent_id = group_data.get(b'parent_id', b'').decode('utf-8') if b'parent_id' in group_data else ''

            # Check if parent is in the same organization
            # Parent is considered "in org" if:
            # 1. It's being added in this transaction, OR
            # 2. It's already in the organization
            parent_in_org = False
            if parent_id:
                parent_in_org = (parent_id in groups_being_added) or self.is_group_in_organization(parent_id, org_id)

            # Add org to group's organizations
            pipe.sadd(f'group:orgs:{gid}', org_id)

            # Add group to org's groups
            pipe.sadd(f'org:groups:{org_id}', gid)

            # Add to root index only if:
            # 1. No parent_id at all, OR
            # 2. Has parent_id but parent is NOT in this organization
            if not parent_id or not parent_in_org:
                pipe.sadd(f'org:groups:root:{org_id}', gid)
                logger.debug(f"Adding group {gid} to organization {org_id} as ROOT (parent_id={parent_id or 'none'}, parent_in_org={parent_in_org})")
            else:
                logger.debug(f"Adding group {gid} to organization {org_id} as CHILD of {parent_id}")

            # Update group metadata
            pipe.hset(gid_key, 'updated_at', datetime.now().isoformat())
            pipe.hset(gid_key, 'updated_by', updated_by)

        pipe.execute()

        logger.info(f"Added group {group_id} and {len(all_group_ids) - 1} descendants to organization {org_id}")
        return True

    def remove_group_from_organization(
        self,
        group_id: str,
        org_id: str,
        updated_by: str = 'system'
    ) -> bool:
        """
        Remove a group from an organization

        Args:
            group_id: Group ID to remove
            org_id: Organization ID to remove from
            updated_by: Username who performed the action

        Returns:
            True if successful

        Raises:
            ValueError: If this is the last organization or group doesn't exist
        """
        from datetime import datetime

        # Validate group exists
        group_key = f'group:{group_id}'
        if not self.client.exists(group_key):
            raise ValueError("그룹이 존재하지 않습니다")

        # Check if group is in this organization
        if not self.is_group_in_organization(group_id, org_id):
            raise ValueError("그룹이 해당 조직에 속하지 않습니다")

        # Prevent removing from default organization only
        # Default organization serves as the home for all groups (including "미분류")
        if org_id == "default":
            raise ValueError("기본 조직에서는 그룹을 제거할 수 없습니다. 기본 조직은 모든 그룹의 홈입니다.")

        # For non-default organizations, allow free removal of any group
        # This includes the "미분류" (uncategorized) group
        # Each organization can choose which groups to use

        # 🆕 Cascade removal: Get all descendants (children, grandchildren, etc.)
        def get_all_descendants(gid: str) -> list:
            """Recursively get all descendant group IDs"""
            descendants = [gid]
            children_key = f'group:children:{gid}'
            children_ids = self.client.smembers(children_key)

            for child_id_bytes in children_ids:
                child_id = child_id_bytes.decode('utf-8') if isinstance(child_id_bytes, bytes) else child_id_bytes
                descendants.extend(get_all_descendants(child_id))

            return descendants

        # Get all groups to remove (parent + all descendants)
        all_group_ids = get_all_descendants(group_id)
        logger.info(f"Removing {len(all_group_ids)} groups from organization {org_id} (including descendants)")

        # Remove bidirectional relationship for all groups
        pipe = self.client.pipeline()

        for gid in all_group_ids:
            # Remove org from group's organizations
            pipe.srem(f'group:orgs:{gid}', org_id)

            # Remove group from org's groups
            pipe.srem(f'org:groups:{org_id}', gid)

            # Remove from root groups index (only applies to top-level groups)
            pipe.srem(f'org:groups:root:{org_id}', gid)

            # Update group metadata
            pipe.hset(f'group:{gid}', 'updated_at', datetime.now().isoformat())
            pipe.hset(f'group:{gid}', 'updated_by', updated_by)

        pipe.execute()

        logger.info(f"Removed group {group_id} and {len(all_group_ids) - 1} descendants from organization {org_id}")
        return True

    def get_group_organizations(self, group_id: str) -> List[str]:
        """
        Get all organizations that a group belongs to

        Args:
            group_id: Group ID

        Returns:
            List of organization IDs
        """
        org_ids_bytes = self.client.smembers(f'group:orgs:{group_id}')
        org_ids = [org_id.decode('utf-8') for org_id in org_ids_bytes]

        # Fallback: if no orgs found, check legacy org_id field
        if not org_ids:
            group_key = f'group:{group_id}'
            if self.client.exists(group_key):
                group_data = self.client.hgetall(group_key)
                if b'org_id' in group_data:
                    legacy_org_id = group_data[b'org_id'].decode('utf-8')
                    if legacy_org_id:
                        return [legacy_org_id]

        return org_ids

    def batch_get_group_counts(self, group_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """
        배치로 그룹별 문서 수와 조직 수를 조회 (Pipeline 사용으로 N+1 쿼리 제거)

        Args:
            group_ids: 그룹 ID 목록

        Returns:
            {group_id: {'document_count': int, 'org_count': int}} 딕셔너리
        """
        if not group_ids:
            return {}

        # Pipeline으로 모든 그룹의 문서 수와 조직 수를 한 번에 조회
        pipe = self.client.pipeline()
        for group_id in group_ids:
            pipe.scard(f'group:docs:{group_id}')  # 문서 수
            pipe.scard(f'group:orgs:{group_id}')  # 조직 수
        results = pipe.execute()

        counts = {}
        for i, group_id in enumerate(group_ids):
            doc_count = results[i * 2] or 0
            org_count = results[i * 2 + 1] or 0
            counts[group_id] = {
                'document_count': doc_count,
                'org_count': org_count
            }

        return counts

    def is_group_in_organization(self, group_id: str, org_id: str) -> bool:
        """
        Check if a group belongs to an organization

        Args:
            group_id: Group ID
            org_id: Organization ID

        Returns:
            True if group belongs to organization
        """
        # Check N:M relationship
        is_member = self.client.sismember(f'group:orgs:{group_id}', org_id)
        if is_member:
            return True

        # Fallback: check legacy org_id field
        group_key = f'group:{group_id}'
        if self.client.exists(group_key):
            group_data = self.client.hgetall(group_key)
            if b'org_id' in group_data:
                legacy_org_id = group_data[b'org_id'].decode('utf-8')
                return legacy_org_id == org_id

        return False
