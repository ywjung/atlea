#!/usr/bin/env python3
"""
Restore basic group-organization structure

This script:
1. Links default group to default organization
2. Adds admin user to default organization
3. Syncs document counts
4. Creates N:M relationships
"""
import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    import redis.asyncio as redis

    # Initialize Redis
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        decode_responses=False  # Binary data for embeddings
    )

    try:
        # Check connection
        await redis_client.ping()
        print("✅ Connected to Redis")

        # Get default group ID
        default_group_id_bytes = await redis_client.get('group:default')
        if not default_group_id_bytes:
            print("❌ No default group found")
            return
        default_group_id = default_group_id_bytes.decode('utf-8')
        print(f"📁 Default group ID: {default_group_id}")

        # Get default organization ID
        default_org_id = "default"
        org_data = await redis_client.hgetall(f"org:{default_org_id}")
        if not org_data:
            print("❌ No default organization found")
            return
        print(f"🏢 Default organization ID: {default_org_id}")

        # Get admin user
        admin_email = "admin@admin.com"
        admin_user_id_bytes = await redis_client.get(f"user:email:{admin_email}")
        if not admin_user_id_bytes:
            print("❌ Admin user not found")
            return
        admin_user_id = admin_user_id_bytes.decode('utf-8')
        print(f"👤 Admin user ID: {admin_user_id}")

        print("\n🔨 Restoring structure...")

        pipe = redis_client.pipeline()

        # 1. Link group to organization (N:M relationship)
        print("  1️⃣ Linking default group to default organization...")
        pipe.sadd(f"org:groups:{default_org_id}", default_group_id)  # org → groups
        pipe.sadd(f"group:orgs:{default_group_id}", default_org_id)  # group → orgs

        # 2. Add admin user to organization
        print("  2️⃣ Adding admin user to default organization...")
        pipe.sadd(f"org:members:{default_org_id}", admin_user_id)  # org → members
        pipe.sadd(f"user:orgs:{admin_user_id}", default_org_id)    # user → orgs

        # 3. Update organization member count
        pipe.hset(f"org:{default_org_id}", "member_count", 1)

        # 4. Update group document count
        # Count actual documents in group:docs set
        actual_doc_count = await redis_client.scard(f"group:docs:{default_group_id}")
        pipe.hset(f"group:{default_group_id}", "document_count", actual_doc_count)
        print(f"  3️⃣ Setting document count to {actual_doc_count}...")

        # Execute all operations
        await pipe.execute()

        print("\n✅ Structure restored!")

        # Verify
        print("\n📊 Verification:")

        # Check org-group link
        org_groups = await redis_client.smembers(f"org:groups:{default_org_id}")
        print(f"  - Default org groups: {len(org_groups)}")

        # Check group-org link
        group_orgs = await redis_client.smembers(f"group:orgs:{default_group_id}")
        print(f"  - Default group orgs: {len(group_orgs)}")

        # Check user-org link
        user_orgs = await redis_client.smembers(f"user:orgs:{admin_user_id}")
        print(f"  - Admin user orgs: {len(user_orgs)}")

        # Check org members
        org_members = await redis_client.smembers(f"org:members:{default_org_id}")
        print(f"  - Default org members: {len(org_members)}")

        # Check group document count
        group_data = await redis_client.hgetall(f"group:{default_group_id}")
        doc_count = group_data.get(b'document_count', b'0').decode('utf-8')
        print(f"  - Default group documents: {doc_count}")

        print("\n✨ All done!")
        print("\n⚠️  Note: This only restores the basic structure.")
        print("   If you had custom groups/organizations, you'll need to recreate them.")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
