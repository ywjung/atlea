#!/usr/bin/env python3
"""
Organization Migration Script

Migrates existing users and groups to organization-based structure.
Creates a default organization and assigns all existing data to it.

Usage:
    python scripts/migrate_to_organizations.py [--dry-run]

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

from src.organization_manager import OrganizationManager


class OrganizationMigration:
    """Handles migration to organization-based structure"""

    def __init__(self, redis_client: redis.Redis, dry_run: bool = False):
        self.client = redis_client
        self.dry_run = dry_run
        self.default_org_id = "default"
        self.stats = {
            'users_updated': 0,
            'groups_updated': 0,
            'root_groups': 0,
            'errors': []
        }

    def backup_redis(self):
        """Create Redis backup before migration"""
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

    def create_default_organization(self):
        """Create default organization if it doesn't exist"""
        logger.info(f"Creating default organization: {self.default_org_id}")

        if self.dry_run:
            logger.info("[DRY RUN] Would create default organization")
            return True

        org_manager = OrganizationManager(self.client)

        # Check if default org already exists
        if org_manager.get_organization(self.default_org_id):
            logger.info("Default organization already exists")
            return True

        # Organization is created automatically by OrganizationManager.__init__()
        logger.success(f"✓ Created default organization: {self.default_org_id}")
        return True

    def migrate_users(self):
        """Add org_id and org_role to all existing users"""
        logger.info("Migrating users...")

        # Get all user IDs
        user_ids = self.client.smembers('users:all')
        total_users = len(user_ids)

        logger.info(f"Found {total_users} users to migrate")

        for user_id_bytes in user_ids:
            user_id = user_id_bytes.decode('utf-8')
            user_key = f'user:{user_id}'

            # Get current user data
            user_data = self.client.hgetall(user_key)
            if not user_data:
                logger.warning(f"User not found: {user_id}")
                self.stats['errors'].append(f"User not found: {user_id}")
                continue

            # Check if already migrated
            if b'org_id' in user_data:
                logger.debug(f"User {user_id} already migrated")
                continue

            if self.dry_run:
                logger.info(f"[DRY RUN] Would update user {user_id}")
                self.stats['users_updated'] += 1
                continue

            # Add org_id and org_role
            pipe = self.client.pipeline()
            pipe.hset(user_key, 'org_id', self.default_org_id)
            pipe.hset(user_key, 'org_role', 'user')

            # Add to organization members
            pipe.sadd(f'org:members:{self.default_org_id}', user_id)

            pipe.execute()

            self.stats['users_updated'] += 1
            logger.debug(f"✓ Updated user {user_id}")

        logger.success(f"✓ Migrated {self.stats['users_updated']} users")
        return True

    def migrate_groups(self):
        """Add org_id to all existing groups"""
        logger.info("Migrating groups...")

        # Get all group keys
        group_count = 0
        root_groups = []

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

            # Check if already migrated
            if b'org_id' in group_data:
                logger.debug(f"Group {group_id} already migrated")
                continue

            # Check if this is a root group
            parent_id = group_data.get(b'parent_id', b'').decode('utf-8')
            if not parent_id:
                root_groups.append(group_id)

            if self.dry_run:
                logger.info(f"[DRY RUN] Would update group {group_id}")
                group_count += 1
                continue

            # Add org_id to group
            pipe = self.client.pipeline()
            pipe.hset(group_key, 'org_id', self.default_org_id)

            # Add to organization groups index
            pipe.sadd(f'org:groups:{self.default_org_id}', group_id)

            # If root group, add to org-specific root
            if not parent_id:
                pipe.sadd(f'org:groups:root:{self.default_org_id}', group_id)

            pipe.execute()

            group_count += 1
            logger.debug(f"✓ Updated group {group_id}")

        self.stats['groups_updated'] = group_count
        self.stats['root_groups'] = len(root_groups)

        logger.success(f"✓ Migrated {group_count} groups ({len(root_groups)} root groups)")
        return True

    def update_member_count(self):
        """Update member count in default organization"""
        if self.dry_run:
            logger.info("[DRY RUN] Would update organization member count")
            return True

        member_count = self.client.scard(f'org:members:{self.default_org_id}')
        self.client.hset(f'org:{self.default_org_id}', 'member_count', str(member_count))

        logger.info(f"✓ Updated organization member count: {member_count}")
        return True

    def validate_migration(self):
        """Validate that migration completed successfully"""
        logger.info("Validating migration...")

        errors = []

        # Check default organization exists
        org_data = self.client.hgetall(f'org:{self.default_org_id}')
        if not org_data:
            errors.append("Default organization not created")

        # Check all users have org_id
        user_ids = self.client.smembers('users:all')
        for user_id_bytes in user_ids:
            user_id = user_id_bytes.decode('utf-8')
            user_data = self.client.hgetall(f'user:{user_id}')

            if not user_data:
                errors.append(f"User data missing: {user_id}")
                continue

            if b'org_id' not in user_data:
                errors.append(f"User missing org_id: {user_id}")

            if b'org_role' not in user_data:
                errors.append(f"User missing org_role: {user_id}")

        # Check all groups have org_id
        for key in self.client.scan_iter(match="group:*", count=100):
            key_str = key.decode('utf-8')

            # Skip non-group keys
            if (key_str.startswith('group:children:') or
                key_str.startswith('group:docs:') or
                key_str == 'group:default'):
                continue

            group_id = key_str.split(':', 1)[1]
            group_data = self.client.hgetall(f'group:{group_id}')

            if group_data and b'org_id' not in group_data:
                errors.append(f"Group missing org_id: {group_id}")

        # Check org indexes
        org_members = self.client.scard(f'org:members:{self.default_org_id}')
        org_groups = self.client.scard(f'org:groups:{self.default_org_id}')

        logger.info(f"Organization members: {org_members}")
        logger.info(f"Organization groups: {org_groups}")

        if errors:
            logger.error(f"Validation found {len(errors)} errors:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        logger.success("✓ Validation passed - migration completed successfully")
        return True

    def run(self):
        """Execute migration"""
        logger.info("=" * 60)
        logger.info("Organization Migration")
        logger.info("=" * 60)

        if self.dry_run:
            logger.warning("DRY RUN MODE - No changes will be made")

        # Step 1: Backup
        logger.info("\n[Step 1/5] Creating backup...")
        if not self.backup_redis():
            logger.error("❌ Backup failed - aborting migration")
            return False

        # Step 2: Create default organization
        logger.info("\n[Step 2/5] Creating default organization...")
        if not self.create_default_organization():
            logger.error("❌ Failed to create default organization")
            return False

        # Step 3: Migrate users
        logger.info("\n[Step 3/5] Migrating users...")
        if not self.migrate_users():
            logger.error("❌ User migration failed")
            return False

        # Step 4: Migrate groups
        logger.info("\n[Step 4/5] Migrating groups...")
        if not self.migrate_groups():
            logger.error("❌ Group migration failed")
            return False

        # Step 5: Update member count
        logger.info("\n[Step 5/5] Updating organization stats...")
        if not self.update_member_count():
            logger.error("❌ Failed to update organization stats")
            return False

        # Validation
        if not self.dry_run:
            logger.info("\nValidating migration...")
            if not self.validate_migration():
                logger.error("❌ Validation failed")
                return False

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Migration Summary")
        logger.info("=" * 60)
        logger.info(f"Users updated: {self.stats['users_updated']}")
        logger.info(f"Groups updated: {self.stats['groups_updated']}")
        logger.info(f"Root groups: {self.stats['root_groups']}")

        if self.stats['errors']:
            logger.warning(f"Errors: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:10]:  # Show first 10
                logger.warning(f"  - {error}")

        if self.dry_run:
            logger.warning("\nDRY RUN COMPLETED - No actual changes were made")
            logger.info("Run without --dry-run to apply changes")
        else:
            logger.success("\n✓ Migration completed successfully!")
            logger.info("\nNext steps:")
            logger.info("1. Restart the application")
            logger.info("2. Verify all users can access their documents")
            logger.info("3. Test organization management features")

        return True


def main():
    parser = argparse.ArgumentParser(description='Migrate to organization-based structure')
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

    # Run migration
    migration = OrganizationMigration(client, dry_run=args.dry_run)

    try:
        success = migration.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
