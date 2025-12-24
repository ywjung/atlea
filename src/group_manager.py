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

        # Validate parent exists
        if parent_id:
            if not self.client.exists(f'group:{parent_id}'):
                raise ValueError("상위 그룹이 존재하지 않습니다.")

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
            'created_at': now,
            'created_by': created_by,
            'updated_at': now,
            'updated_by': created_by,
            'document_count': '0'
        }

        # Store group and update parent's children
        pipe = self.client.pipeline()
        pipe.hset(f'group:{group_id}', mapping=group_data)

        if parent_id:
            pipe.sadd(f'group:children:{parent_id}', group_id)
        else:
            pipe.sadd('group:children:root', group_id)

        pipe.execute()

        logger.info(f"Created group: {group_id} ({name})")
        return group_id

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
            **updates: Fields to update (name, description, color, icon)

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
        allowed_fields = {'name', 'description', 'color', 'icon'}
        update_data = {k: v for k, v in updates.items() if k in allowed_fields}

        if 'name' in update_data:
            if not update_data['name'] or not update_data['name'].strip():
                raise ValueError("그룹 이름은 필수입니다.")
            if len(update_data['name']) > 100:
                raise ValueError("그룹 이름은 100자를 초과할 수 없습니다.")
            update_data['name'] = update_data['name'].strip()

        if 'description' in update_data:
            update_data['description'] = update_data['description'].strip()

        # Add metadata
        update_data['updated_at'] = datetime.now().isoformat()
        update_data['updated_by'] = updated_by

        # Update
        self.client.hset(group_key, mapping=update_data)

        logger.info(f"Updated group: {group_id}")
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

        # Update all chunks of this document
        for key in self.client.scan_iter(match="doc:*", count=100):
            key_str = key.decode('utf-8')
            # Skip special keys
            if ':' in key_str[4:]:  # doc:group:, doc:hash:, etc.
                continue

            # Check if this chunk belongs to the file
            chunk_filename = self.client.hget(key, 'filename')
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

        # Single scan through all documents - update all matching files
        for key in self.client.scan_iter(match="doc:*", count=1000):
            key_str = key.decode('utf-8')

            # Skip special keys
            if ':' in key_str[4:]:  # doc:group:, doc:hash:, etc.
                continue

            # Check if this chunk belongs to one of the target files
            chunk_filename = self.client.hget(key, 'filename')
            if chunk_filename:
                filename = chunk_filename.decode('utf-8')
                if filename in filenames_to_assign:
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

        return result

    def get_all_groups(self) -> List[Dict]:
        """
        Get all groups

        Returns:
            List of group dictionaries
        """
        groups = []

        for key in self.client.scan_iter(match="group:*", count=100):
            key_str = key.decode('utf-8')

            # Skip non-group keys
            if key_str.startswith('group:children:') or key_str.startswith('group:docs:') or key_str == 'group:default':
                continue

            # Extract group ID
            group_id = key_str.split(':', 1)[1]
            group_data = self.get_group(group_id)

            if group_data:
                groups.append(group_data)

        return groups

    def get_group_tree(self) -> Dict:
        """
        Get hierarchical group tree

        Returns:
            Tree structure with nested children
        """
        # Get all groups
        all_groups = {g['id']: g for g in self.get_all_groups()}

        # Build tree structure
        def build_tree(parent_id: Optional[str]) -> List[Dict]:
            children_key = f'group:children:{parent_id}' if parent_id else 'group:children:root'
            children_ids = self.client.smembers(children_key)

            result = []
            for child_id_bytes in children_ids:
                child_id = child_id_bytes.decode('utf-8')
                if child_id in all_groups:
                    group = all_groups[child_id].copy()
                    group['children'] = build_tree(child_id)
                    result.append(group)

            # Sort by name
            result.sort(key=lambda x: x['name'])
            return result

        return {
            'id': 'root',
            'name': '전체',
            'children': build_tree(None)
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
