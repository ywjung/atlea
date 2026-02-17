#!/usr/bin/env python3
"""
[DEPRECATED] Fix groups that are incorrectly in root indexes when they have parents

This script uses Redis directly and is no longer compatible with the
PostgreSQL-based architecture (v3.0+). Kept for historical reference only.
"""

import sys
import os
import redis as redis_module

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

def fix_root_indexes():
    """Fix groups incorrectly placed in root indexes"""

    # Initialize Redis connection
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))

    redis = redis_module.Redis(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        decode_responses=False
    )

    logger.info("🔧 Fixing root index inconsistencies...")

    # Get all group keys
    all_group_keys = list(redis.scan_iter(match="group:*", count=100))
    group_data_keys = [
        k for k in all_group_keys
        if not (k.decode('utf-8').startswith('group:children:') or
                k.decode('utf-8').startswith('group:docs:') or
                k.decode('utf-8').startswith('group:orgs:'))
    ]

    fixed_global = 0
    fixed_org = 0

    for key in group_data_keys:
        group_id = key.decode('utf-8').split(':', 1)[1]
        if group_id in ['default', 'children', 'docs', 'orgs']:
            continue

        group_data = redis.hgetall(key)
        if not group_data:
            continue

        name = group_data.get(b'name', b'').decode('utf-8')
        parent_id = group_data.get(b'parent_id', b'').decode('utf-8')

        # Check global root
        is_in_global_root = redis.sismember('group:children:root', group_id)

        if parent_id and is_in_global_root:
            # Has parent but in global root - WRONG!
            redis.srem('group:children:root', group_id)
            logger.info(f"  🔧 Removed {name} from global root (has parent: {parent_id[:8]}...)")
            fixed_global += 1

        elif not parent_id and not is_in_global_root:
            # No parent but not in global root - WRONG!
            redis.sadd('group:children:root', group_id)
            logger.info(f"  ✅ Added {name} to global root (no parent)")
            fixed_global += 1

        # Check organization roots
        org_ids_bytes = redis.smembers(f'group:orgs:{group_id}')
        org_ids = [oid.decode('utf-8') for oid in org_ids_bytes]

        for org_id in org_ids:
            is_in_org_root = redis.sismember(f'org:groups:root:{org_id}', group_id)

            if parent_id:
                # Has parent - check if parent is in same org
                parent_in_org = redis.sismember(f'org:groups:{org_id}', parent_id)

                if parent_in_org and is_in_org_root:
                    # Parent in org but child in org root - WRONG!
                    redis.srem(f'org:groups:root:{org_id}', group_id)
                    logger.info(f"  🔧 Removed {name} from org root {org_id[:8]}... (parent in same org)")
                    fixed_org += 1

                elif not parent_in_org and not is_in_org_root:
                    # Parent not in org but child not in org root - WRONG!
                    redis.sadd(f'org:groups:root:{org_id}', group_id)
                    logger.info(f"  ✅ Added {name} to org root {org_id[:8]}... (parent not in org)")
                    fixed_org += 1

            else:
                # No parent - should be in org root
                if not is_in_org_root:
                    redis.sadd(f'org:groups:root:{org_id}', group_id)
                    logger.info(f"  ✅ Added {name} to org root {org_id[:8]}... (no parent)")
                    fixed_org += 1

    logger.success(f"✅ Fix complete! Fixed {fixed_global} global root issues, {fixed_org} org root issues")


if __name__ == '__main__':
    try:
        fix_root_indexes()
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
