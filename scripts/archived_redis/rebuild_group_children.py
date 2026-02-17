#!/usr/bin/env python3
"""
Rebuild group:children:{parent_id} Redis sets based on existing parent_id values

This script scans all groups and rebuilds the parent-child relationship indexes
that are used by get_group_tree() to build the hierarchical structure.
"""

import sys
import os
import redis as redis_module

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def rebuild_group_children():
    """Rebuild all group:children:{parent_id} sets"""

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

    logger.info("🔧 Starting group children index rebuild...")

    # Get all group keys
    group_keys = list(redis.scan_iter(match="group:*", count=100))

    # Filter to only group data keys (not children, docs, orgs, etc.)
    group_data_keys = [
        k for k in group_keys
        if not (k.decode('utf-8').startswith('group:children:') or
                k.decode('utf-8').startswith('group:docs:') or
                k.decode('utf-8').startswith('group:orgs:'))
    ]

    logger.info(f"📂 Found {len(group_data_keys)} groups")

    # Clear all existing children sets
    children_keys = list(redis.scan_iter(match="group:children:*", count=100))
    if children_keys:
        logger.info(f"🗑️ Clearing {len(children_keys)} existing children sets...")
        redis.delete(*children_keys)

    # Rebuild children sets
    groups_with_parents = 0
    root_groups = 0

    for key in group_data_keys:
        group_id = key.decode('utf-8').split(':', 1)[1]

        # Skip special keys
        if group_id in ['default', 'children', 'docs', 'orgs']:
            continue

        # Get group data
        group_data = redis.hgetall(key)
        if not group_data:
            continue

        # Get parent_id
        parent_id = group_data.get(b'parent_id', b'').decode('utf-8')

        if parent_id:
            # Add this group to parent's children set
            redis.sadd(f'group:children:{parent_id}', group_id)
            groups_with_parents += 1

            group_name = group_data.get(b'name', b'').decode('utf-8')
            logger.info(f"  ✅ {group_name} ({group_id[:8]}...) → parent: {parent_id[:8]}...")
        else:
            # No parent - add to global root (for admin view without org filter)
            redis.sadd(f'group:children:root', group_id)
            root_groups += 1

            group_name = group_data.get(b'name', b'').decode('utf-8')
            logger.info(f"  🌳 {group_name} ({group_id[:8]}...) → ROOT group")

    logger.success(f"✅ Rebuild complete! {groups_with_parents} groups with parents, {root_groups} root groups")

    # Verify by checking a few
    logger.info("\n🔍 Verification sample:")
    count = 0
    for key in group_data_keys[:5]:
        group_id = key.decode('utf-8').split(':', 1)[1]
        if group_id in ['default', 'children', 'docs', 'orgs']:
            continue

        group_data = redis.hgetall(key)
        parent_id = group_data.get(b'parent_id', b'').decode('utf-8')

        if parent_id:
            children = redis.smembers(f'group:children:{parent_id}')
            children_count = len(children)
            parent_name = redis.hget(f'group:{parent_id}', 'name')
            if parent_name:
                parent_name = parent_name.decode('utf-8')

            group_name = group_data.get(b'name', b'').decode('utf-8')
            logger.info(f"  📁 {parent_name} has {children_count} children (including {group_name})")
            count += 1

        if count >= 3:
            break


if __name__ == '__main__':
    try:
        rebuild_group_children()
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
