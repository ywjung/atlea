#!/usr/bin/env python3
"""
Rebuild doc:group:{filename} mappings from document data

This script scans all indexed documents and recreates the doc:group:{filename}
keys based on the group_id stored in each document's data.

Usage:
    python scripts/rebuild_doc_group_mappings.py
"""
import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    import redis.asyncio as redis
    from src.cache_manager import CacheManager

    # Initialize Redis (don't decode responses - embeddings are binary)
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        decode_responses=False
    )

    try:
        # Check connection
        await redis_client.ping()
        print("✅ Connected to Redis")

        # Get current index name
        index_name_bytes = await redis_client.get('index:active')
        index_name = index_name_bytes.decode('utf-8') if index_name_bytes else 'pdf_index'
        print(f"📋 Active index: {index_name}")

        # Count existing doc:group mappings
        existing_mappings = 0
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="doc:group:*", count=1000)
            existing_mappings += len(keys)
            if cursor == 0:
                break

        print(f"📊 Existing doc:group mappings: {existing_mappings}")

        # Scan all document chunks
        print("\n🔍 Scanning document chunks...")
        cursor = 0
        processed_files = set()
        file_to_group = {}  # filename -> group_id mapping

        while True:
            cursor, keys = await redis_client.scan(cursor, match=f"doc:{index_name}:*", count=100)

            for key in keys:
                # Decode key for checking
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key

                # Skip non-document keys
                if any(x in key_str for x in [':hash:', ':group:', ':version:', ':counts:', ':files']):
                    continue

                # Get document data
                doc_data = await redis_client.hgetall(key)
                if not doc_data:
                    continue

                # Decode binary fields
                filename_bytes = doc_data.get(b'filename')
                group_id_bytes = doc_data.get(b'group_id')

                if filename_bytes and group_id_bytes:
                    filename = filename_bytes.decode('utf-8')
                    group_id = group_id_bytes.decode('utf-8')

                    if filename not in processed_files:
                        file_to_group[filename] = group_id
                        processed_files.add(filename)

            if cursor == 0:
                break

        print(f"✅ Found {len(file_to_group)} unique documents with group assignments")

        if not file_to_group:
            print("⚠️  No documents found. Exiting.")
            return

        # Get default group ID
        default_group_id_bytes = await redis_client.get('group:default')
        if default_group_id_bytes:
            default_group_id = default_group_id_bytes.decode('utf-8')
            print(f"📌 Default group ID: {default_group_id}")
        else:
            print("⚠️  No default group found")

        # Rebuild doc:group mappings
        print("\n🔨 Rebuilding doc:group mappings...")
        pipe = redis_client.pipeline()
        created_count = 0
        updated_count = 0

        for filename, group_id in file_to_group.items():
            # Check if mapping already exists
            existing_group_bytes = await redis_client.get(f"doc:group:{filename}")
            existing_group = existing_group_bytes.decode('utf-8') if existing_group_bytes else None

            if existing_group:
                if existing_group != group_id:
                    # Update if different
                    pipe.set(f"doc:group:{filename}", group_id)
                    updated_count += 1
                # else: already correct, skip
            else:
                # Create new mapping
                pipe.set(f"doc:group:{filename}", group_id)
                created_count += 1

            # Also ensure document is in group's document set
            pipe.sadd(f"group:docs:{group_id}", filename)

        # Execute all operations
        await pipe.execute()

        print(f"✅ Created {created_count} new mappings")
        print(f"✅ Updated {updated_count} existing mappings")

        # Verify
        cursor = 0
        total_mappings = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="doc:group:*", count=1000)
            total_mappings += len(keys)
            if cursor == 0:
                break

        print(f"\n📊 Total doc:group mappings after rebuild: {total_mappings}")

        # Show sample mappings
        print("\n📋 Sample mappings:")
        sample_count = 0
        for filename, group_id in list(file_to_group.items())[:5]:
            verified_bytes = await redis_client.get(f"doc:group:{filename}")
            verified = verified_bytes.decode('utf-8') if verified_bytes else None
            status = "✅" if verified == group_id else "❌"
            print(f"   {status} {filename} → {group_id}")
            sample_count += 1

        print(f"\n✨ Rebuild complete!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
