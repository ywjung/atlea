#!/usr/bin/env python3
"""
[DEPRECATED] Test parent_id removal functionality

This script uses Redis directly and is no longer compatible with the
PostgreSQL-based architecture (v3.0+). Kept for historical reference only.
"""

import sys
import os
import redis as redis_module

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

def test():
    redis = redis_module.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=int(os.getenv("REDIS_DB", 0)),
        decode_responses=False  # GroupManager expects bytes
    )

    logger.info("🧪 Testing parent_id removal...")

    # Import group_manager
    from src.group_manager import GroupManager

    group_manager = GroupManager(redis)

    # Find a test group (1313 that we know has parent 1414)
    test_group_id = None
    for key in redis.scan_iter(match="group:*", count=100):
        if redis.type(key) != b'hash':
            continue
        key_str = key.decode('utf-8')
        if ':' in key_str[6:]:
            continue

        name = redis.hget(key, b'name')
        if name and name.decode('utf-8') == '1313':
            test_group_id = key_str.split(':', 1)[1]
            break

    if not test_group_id:
        logger.error("❌ Test group 1313 not found")
        return

    logger.info(f"📂 Test group: 1313 (ID: {test_group_id[:8]}...)")

    # Check current state
    current_parent_bytes = redis.hget(f'group:{test_group_id}', b'parent_id')
    current_parent = current_parent_bytes.decode('utf-8') if current_parent_bytes else ''
    is_in_root = redis.sismember('group:children:root', test_group_id)

    logger.info(f"\n현재 상태:")
    logger.info(f"  parent_id: {current_parent[:8] if current_parent else '(없음)'}...")
    logger.info(f"  in global root: {is_in_root}")

    # Simulate removing parent (like UI does)
    logger.info(f"\n🔧 Simulating parent removal (setting parent_id to None)...")

    try:
        success = group_manager.update_group(
            group_id=test_group_id,
            updated_by="test",
            parent_id=None  # Remove parent
        )

        if success:
            logger.success("✅ update_group() succeeded")
        else:
            logger.error("❌ update_group() failed")
            return

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Check new state
    new_parent_bytes = redis.hget(f'group:{test_group_id}', b'parent_id')
    new_parent = new_parent_bytes.decode('utf-8') if new_parent_bytes else ''
    is_in_root = redis.sismember('group:children:root', test_group_id)

    logger.info(f"\n수정 후 상태:")
    logger.info(f"  parent_id: {new_parent if new_parent else '(없음 - 빈 문자열)'}")
    logger.info(f"  in global root: {is_in_root}")

    if not new_parent and is_in_root:
        logger.success("\n✅ Parent removal works correctly!")
        logger.info("  - parent_id cleared")
        logger.info("  - Added to global root")
    else:
        logger.error("\n❌ Parent removal NOT working correctly!")
        if new_parent:
            logger.error(f"  - parent_id still set: {new_parent}")
        if not is_in_root:
            logger.error(f"  - NOT in global root")

    # Restore original state
    if current_parent:
        logger.info(f"\n🔄 Restoring original parent...")
        group_manager.update_group(
            group_id=test_group_id,
            updated_by="test",
            parent_id=current_parent
        )
        logger.info("✅ Restored")

if __name__ == '__main__':
    try:
        test()
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
