#!/usr/bin/env python3
"""
Clear rate limits for login
"""
import redis

# Connect to Redis
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=True
)

try:
    # Check connection
    redis_client.ping()
    print("✅ Connected to Redis\n")

    # Clear rate limit keys
    keys = redis_client.keys("rate_limit:login:*")
    if keys:
        deleted = redis_client.delete(*keys)
        print(f"✅ Cleared {deleted} rate limit keys")
    else:
        print("ℹ️  No rate limit keys found")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    redis_client.close()
