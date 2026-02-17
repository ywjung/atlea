#!/usr/bin/env python3
"""
Test login with admin@admin.com
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    import redis.asyncio as redis
    from src.auth.service import AuthService
    from src.auth.models import UserLogin

    # Connect to Redis
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        decode_responses=True
    )

    try:
        # Check connection
        await redis_client.ping()
        print("✅ Connected to Redis\n")

        # Test login
        auth_service = AuthService(redis_client)

        credentials = UserLogin(
            email="admin@admin.com",
            password="Admin123!@#"
        )

        print(f"🔐 Testing login for: {credentials.email}")
        print(f"📝 Password: {credentials.password}\n")

        try:
            result = await auth_service.authenticate_user(credentials, ip_address="127.0.0.1")
            print("✅ Login successful!")
            print(f"   User ID: {result['user']['user_id']}")
            print(f"   Username: {result['user']['username']}")
            print(f"   Role: {result['user']['role']}")
            print(f"   Access Token: {result['tokens']['access_token'][:50]}...")
        except ValueError as e:
            print(f"❌ Login failed: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
