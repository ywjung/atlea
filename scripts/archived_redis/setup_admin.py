#!/usr/bin/env python3
"""
Setup admin account script
Creates admin@admin.com account or upgrades existing user
"""
import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    import redis.asyncio as redis
    import uuid
    from datetime import datetime
    from src.auth.utils import hash_password

    # Connect to Redis
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        decode_responses=True
    )

    try:
        # Check connection
        await redis_client.ping()
        print("✅ Connected to Redis")

        # Admin credentials
        admin_email = "admin@admin.com"
        admin_username = "관리자"
        admin_password = "Admin123!@#"

        # Check if admin@admin.com exists
        existing_user_id = await redis_client.get(f"user:email:{admin_email}")

        # Hash password using same method as application
        hashed_password = hash_password(admin_password)

        if existing_user_id:
            print(f"ℹ️  User {admin_email} already exists (ID: {existing_user_id})")

            # Upgrade to admin
            await redis_client.hset(f"user:{existing_user_id}", "role", "admin")
            await redis_client.hset(f"user:{existing_user_id}", "username", admin_username)
            await redis_client.hset(f"user:{existing_user_id}", "password_hash", hashed_password)
            await redis_client.hset(f"user:{existing_user_id}", "is_active", "True")
            await redis_client.sadd("users:all", existing_user_id)  # Ensure in users set

            print(f"✅ Upgraded user to admin and reset password")
            print(f"   Email: {admin_email}")
            print(f"   Username: {admin_username}")
            print(f"   Password: {admin_password}")
        else:
            # Create new admin user
            user_id = str(uuid.uuid4())
            current_time = datetime.utcnow().isoformat()

            user_data = {
                "user_id": user_id,
                "email": admin_email,
                "username": admin_username,
                "password_hash": hashed_password,
                "role": "admin",
                "is_active": "True",
                "created_at": current_time,
                "updated_at": current_time
            }

            # Store in Redis
            await redis_client.hset(f"user:{user_id}", mapping=user_data)
            await redis_client.set(f"user:email:{admin_email}", user_id)
            await redis_client.sadd("users:all", user_id)  # Add to users set

            print(f"✅ Created new admin user")
            print(f"   Email: {admin_email}")
            print(f"   Username: {admin_username}")
            print(f"   Password: {admin_password}")
            print(f"   User ID: {user_id}")

        # List all admin users
        print("\n📋 Current admin users:")
        cursor = 0
        admin_count = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="user:*", count=100)
            for key in keys:
                if key.startswith("user:") and ":" in key and key.count(":") == 1:
                    user_data = await redis_client.hgetall(key)
                    if user_data.get("role") == "admin":
                        admin_count += 1
                        print(f"   - {user_data.get('email')} ({user_data.get('username')}) [ID: {user_data.get('user_id')}]")
            if cursor == 0:
                break

        print(f"\n✅ Total admin users: {admin_count}")
        print(f"\n⚠️  Please change the default admin password after first login!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
