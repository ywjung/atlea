#!/usr/bin/env python3
"""
Organization Rollback Script

Rolls back organization migration to restore the original data structure.
Removes organization-related fields and indices from users and groups.

Usage:
    python scripts/rollback_organizations.py [--dry-run]

Options:
    --dry-run    Show what would be changed without actually modifying data
"""

import sys
import os
import redis
from datetime import datetime
import argparse
from loguru import logger

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class OrganizationRollback:
    """Handles rollback of organization-based structure"""

    def __init__(self, redis_client: redis.Redis, dry_run: bool = False):
        self.client = redis_client
        self.dry_run = dry_run
        self.stats = {
            'users_updated': 0,
            'groups_updated': 0,
            'orgs_deleted': 0,
            'errors': []
        }

    def backup_redis(self):
        """Create Redis backup before rollback"""
        if self.dry_run:
            logger.info("[DRY RUN] Would create Redis backup")
            return True

        logger.info("Creating Redis backup...")
        try:
            self.client.bgsave()
            logger.success("✓ Redis backup initiated (BGSAVE)")
            return True
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False

    def rollback_users(self):
        """Remove org_id and org_role from all users"""
        logger.info("Rolling back user data...")

        # Get all user IDs
        user_ids = self.client.smembers('users:all')
        total_users = len(user_ids)

        logger.info(f"Found {total_users} users to rollback")

        for user_id_bytes in user_ids:
            user_id = user_id_bytes.decode('utf-8')
            user_key = f'user:{user_id}'

            # Get current user data
            user_data = self.client.hgetall(user_key)
            if not user_data:
                logger.warning(f"User not found: {user_id}")
                self.stats['errors'].append(f"User not found: {user_id}")
                continue

            # Check if org_id exists
            if b'org_id' not in user_data:
                logger.debug(f"User {user_id} already rolled back")
                continue

            if self.dry_run:
                logger.info(f"[DRY RUN] Would remove org fields from user {user_id}")
                self.stats['users_updated'] += 1
                continue

            # Remove org_id and org_role fields
            pipe = self.client.pipeline()
            pipe.hdel(user_key, 'org_id')
            pipe.hdel(user_key, 'org_role')
            pipe.execute()

            self.stats['users_updated'] += 1
            logger.debug(f"✓ Rolled back user {user_id}")

        logger.success(f"✓ Rolled back {self.stats['users_updated']} users")
        return True

    def rollback_groups(self):
        """Remove org_id from all groups"""
        logger.info("Rolling back group data...")

        group_count = 0

        for key in self.client.scan_iter(match="group:*", count=100):
            key_str = key.decode('utf-8')

            # Skip non-group keys
            if (key_str.startswith('group:children:') or
                key_str.startswith('group:docs:') or
                key_str == 'group:default'):
                continue

            group_id = key_str.split(':', 1)[1]
            group_key = f'group:{group_id}'

            # Get group data
            group_data = self.client.hgetall(group_key)
            if not group_data:
                continue

            # Check if org_id exists
            if b'org_id' not in group_data:
                logger.debug(f"Group {group_id} already rolled back")
                continue

            if self.dry_run:
                logger.info(f"[DRY RUN] Would remove org_id from group {group_id}")
                group_count += 1
                continue

            # Remove org_id field
            self.client.hdel(group_key, 'org_id')

            group_count += 1
            logger.debug(f"✓ Rolled back group {group_id}")

        self.stats['groups_updated'] = group_count

        logger.success(f"✓ Rolled back {group_count} groups")
        return True

    def delete_organization_data(self):
        """Delete all organization-related Redis keys"""
        logger.info("Deleting organization data...")

        if self.dry_run:
            logger.info("[DRY RUN] Would delete organization data")
            # Count organizations
            org_ids = self.client.smembers('orgs:all')
            self.stats['orgs_deleted'] = len(org_ids)
            return True

        deleted_keys = []

        # Delete all organization keys
        for key in self.client.scan_iter(match="org:*", count=100):
            key_str = key.decode('utf-8')
            self.client.delete(key)
            deleted_keys.append(key_str)
            logger.debug(f"✓ Deleted key: {key_str}")

        # Delete orgs:all set
        if self.client.exists('orgs:all'):
            org_count = self.client.scard('orgs:all')
            self.stats['orgs_deleted'] = org_count
            self.client.delete('orgs:all')
            deleted_keys.append('orgs:all')

        # Delete organization name indices
        for key in self.client.scan_iter(match="org:name:*", count=100):
            key_str = key.decode('utf-8')
            self.client.delete(key)
            deleted_keys.append(key_str)

        logger.success(f"✓ Deleted {len(deleted_keys)} organization-related keys")
        return True

    def validate_rollback(self):
        """Validate that rollback completed successfully"""
        logger.info("Validating rollback...")

        errors = []

        # Check no organization keys exist
        org_keys = list(self.client.scan_iter(match="org:*", count=100))
        if org_keys:
            errors.append(f"Organization keys still exist: {len(org_keys)} keys")

        if self.client.exists('orgs:all'):
            errors.append("orgs:all set still exists")

        # Check all users have no org_id
        user_ids = self.client.smembers('users:all')
        for user_id_bytes in user_ids:
            user_id = user_id_bytes.decode('utf-8')
            user_data = self.client.hgetall(f'user:{user_id}')

            if not user_data:
                errors.append(f"User data missing: {user_id}")
                continue

            if b'org_id' in user_data:
                errors.append(f"User still has org_id: {user_id}")

            if b'org_role' in user_data:
                errors.append(f"User still has org_role: {user_id}")

        # Check all groups have no org_id
        for key in self.client.scan_iter(match="group:*", count=100):
            key_str = key.decode('utf-8')

            # Skip non-group keys
            if (key_str.startswith('group:children:') or
                key_str.startswith('group:docs:') or
                key_str == 'group:default'):
                continue

            group_id = key_str.split(':', 1)[1]
            group_data = self.client.hgetall(f'group:{group_id}')

            if group_data and b'org_id' in group_data:
                errors.append(f"Group still has org_id: {group_id}")

        if errors:
            logger.error(f"Validation found {len(errors)} errors:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        logger.success("✓ Validation passed - rollback completed successfully")
        return True

    def run(self):
        """Execute rollback"""
        logger.info("=" * 60)
        logger.info("Organization Rollback")
        logger.info("=" * 60)

        if self.dry_run:
            logger.warning("DRY RUN MODE - No changes will be made")

        # Step 1: Backup
        logger.info("\n[Step 1/4] Creating backup...")
        if not self.backup_redis():
            logger.error("❌ Backup failed - aborting rollback")
            return False

        # Step 2: Rollback users
        logger.info("\n[Step 2/4] Rolling back users...")
        if not self.rollback_users():
            logger.error("❌ User rollback failed")
            return False

        # Step 3: Rollback groups
        logger.info("\n[Step 3/4] Rolling back groups...")
        if not self.rollback_groups():
            logger.error("❌ Group rollback failed")
            return False

        # Step 4: Delete organization data
        logger.info("\n[Step 4/4] Deleting organization data...")
        if not self.delete_organization_data():
            logger.error("❌ Failed to delete organization data")
            return False

        # Validation
        if not self.dry_run:
            logger.info("\nValidating rollback...")
            if not self.validate_rollback():
                logger.error("❌ Validation failed")
                return False

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Rollback Summary")
        logger.info("=" * 60)
        logger.info(f"Users updated: {self.stats['users_updated']}")
        logger.info(f"Groups updated: {self.stats['groups_updated']}")
        logger.info(f"Organizations deleted: {self.stats['orgs_deleted']}")

        if self.stats['errors']:
            logger.warning(f"Errors: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:10]:  # Show first 10
                logger.warning(f"  - {error}")

        if self.dry_run:
            logger.warning("\nDRY RUN COMPLETED - No actual changes were made")
            logger.info("Run without --dry-run to apply changes")
        else:
            logger.success("\n✓ Rollback completed successfully!")
            logger.info("\nNext steps:")
            logger.info("1. Restart the application")
            logger.info("2. Verify users can access their documents")
            logger.info("3. Verify groups work as before")

        return True


def main():
    parser = argparse.ArgumentParser(description='Rollback organization-based structure')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be changed without modifying data')
    parser.add_argument('--redis-host', default='localhost',
                        help='Redis host (default: localhost)')
    parser.add_argument('--redis-port', type=int, default=6379,
                        help='Redis port (default: 6379)')
    parser.add_argument('--redis-db', type=int, default=0,
                        help='Redis database number (default: 0)')

    args = parser.parse_args()

    # Connect to Redis
    try:
        client = redis.Redis(
            host=args.redis_host,
            port=args.redis_port,
            db=args.redis_db,
            decode_responses=False
        )
        client.ping()
        logger.info(f"Connected to Redis at {args.redis_host}:{args.redis_port}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    # Run rollback
    rollback = OrganizationRollback(client, dry_run=args.dry_run)

    try:
        success = rollback.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\nRollback interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Rollback failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
