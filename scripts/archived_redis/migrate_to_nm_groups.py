#!/usr/bin/env python3
"""
Migration script: Convert group-organization relationship from 1:1 to N:M

This script:
1. Reads org_id from each group
2. Creates group:orgs:{group_id} SET with that org_id
3. Keeps org_id field for backward compatibility
4. Validates all relationships are correctly created
"""

import redis
import sys
from datetime import datetime


def migrate_to_nm_groups():
    """Migrate group-organization relationships to N:M"""

    # Connect to Redis
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)

    print("=" * 70)
    print("Group-Organization N:M Relationship Migration")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    # Step 1: Find all groups
    print("Step 1: Finding all groups...")
    group_keys = []
    for key in r.scan_iter('group:*'):
        # Only process group data keys (not indices)
        if not key.startswith('group:docs:') and \
           not key.startswith('group:children:') and \
           not key.startswith('group:orgs:') and \
           key != 'group:default':  # Skip group:default (not a group ID)
            group_keys.append(key)

    print(f"  Found {len(group_keys)} groups")
    print()

    # Step 2: Process each group
    print("Step 2: Converting relationships...")
    migrated_count = 0
    skipped_count = 0
    error_count = 0

    for group_key in group_keys:
        try:
            group_id = group_key.replace('group:', '')

            # Get current org_id
            org_id = r.hget(group_key, 'org_id')

            if not org_id:
                print(f"  ⚠️  Group {group_id} has no org_id, skipping")
                skipped_count += 1
                continue

            # Check if already migrated
            existing_orgs = r.smembers(f'group:orgs:{group_id}')
            if org_id in existing_orgs:
                print(f"  ⏭️  Group {group_id} already migrated to org {org_id}")
                skipped_count += 1
                continue

            # Create N:M relationship
            pipe = r.pipeline()

            # Add org to group's organizations
            pipe.sadd(f'group:orgs:{group_id}', org_id)

            # Verify org:groups:{org_id} already has this group
            # (it should have been created during group creation)
            pipe.sadd(f'org:groups:{org_id}', group_id)

            # Update metadata
            pipe.hset(group_key, 'updated_at', datetime.now().isoformat())
            pipe.hset(group_key, 'updated_by', 'migration_script')

            pipe.execute()

            print(f"  ✅ Migrated group {group_id} → org {org_id}")
            migrated_count += 1

        except Exception as e:
            print(f"  ❌ Error processing {group_key}: {str(e)}")
            error_count += 1

    print()
    print(f"Migration completed:")
    print(f"  ✅ Migrated: {migrated_count}")
    print(f"  ⏭️  Skipped: {skipped_count}")
    print(f"  ❌ Errors: {error_count}")
    print()

    # Step 3: Validation
    print("Step 3: Validating migration...")
    validation_errors = 0

    for group_key in group_keys:
        try:
            group_id = group_key.replace('group:', '')
            org_id = r.hget(group_key, 'org_id')

            if not org_id:
                continue

            # Check group:orgs exists
            group_orgs = r.smembers(f'group:orgs:{group_id}')
            if org_id not in group_orgs:
                print(f"  ❌ Group {group_id}: org_id {org_id} not in group:orgs")
                validation_errors += 1

            # Check org:groups contains this group
            org_groups = r.smembers(f'org:groups:{org_id}')
            if group_id not in org_groups:
                print(f"  ❌ Group {group_id}: not in org:groups:{org_id}")
                validation_errors += 1

        except Exception as e:
            print(f"  ❌ Validation error for {group_key}: {str(e)}")
            validation_errors += 1

    if validation_errors == 0:
        print("  ✅ All relationships validated successfully")
    else:
        print(f"  ❌ Found {validation_errors} validation errors")

    print()
    print("=" * 70)
    print(f"Finished at: {datetime.now().isoformat()}")
    print("=" * 70)

    return migrated_count, error_count, validation_errors


def rollback_migration():
    """Rollback N:M migration (remove group:orgs keys)"""

    r = redis.Redis(host='localhost', port=6379, decode_responses=True)

    print("=" * 70)
    print("Rollback: Remove N:M Relationships")
    print("=" * 70)

    # Find all group:orgs keys
    group_orgs_keys = list(r.scan_iter('group:orgs:*'))

    print(f"Found {len(group_orgs_keys)} group:orgs keys to delete")

    if group_orgs_keys:
        confirm = input("Delete all group:orgs keys? (yes/no): ")
        if confirm.lower() == 'yes':
            r.delete(*group_orgs_keys)
            print(f"✅ Deleted {len(group_orgs_keys)} keys")
        else:
            print("Rollback cancelled")
    else:
        print("No keys to delete")

    print("=" * 70)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        rollback_migration()
    else:
        print()
        print("This will migrate group-organization relationships to N:M (many-to-many)")
        print("Groups can belong to multiple organizations after migration")
        print()
        confirm = input("Continue with migration? (yes/no): ")

        if confirm.lower() == 'yes':
            print()
            migrated, errors, validation_errors = migrate_to_nm_groups()

            if errors > 0 or validation_errors > 0:
                print()
                print("⚠️  Migration completed with errors!")
                print("Run with --rollback to undo changes")
                sys.exit(1)
            else:
                print()
                print("✅ Migration successful!")
                sys.exit(0)
        else:
            print("Migration cancelled")
            sys.exit(0)
