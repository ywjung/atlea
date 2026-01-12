#!/usr/bin/env python3
"""
Redis 데이터 마이그레이션 스크립트
로컬 Redis (포트 6380)에서 Docker Redis (포트 6379)로 데이터 마이그레이션

사용법:
    python scripts/migrate_redis_data.py
"""

import redis
import sys

# Redis 연결
source_redis = redis.Redis(host='localhost', port=6380, decode_responses=True)
target_redis = redis.Redis(host='localhost', port=6379, decode_responses=True)

def migrate_all_keys():
    """모든 키 마이그레이션"""

    # 마이그레이션할 패턴들
    patterns = [
        "user:*",        # 개별 사용자 데이터
        "users:*",       # users:all 등 집계 Sets (aggregate)
        "org:*",         # 개별 조직 데이터
        "orgs:*",        # orgs:all 등 집계 Sets (aggregate)
        "group:*",       # 개별 그룹 데이터
        "groups:*",      # groups:all 등 집계 Sets (aggregate)
        "doc:*",
        "conversation:*",
        "session:*",
        "audit:*",
        "security:*",
        "feedback:*",    # 피드백 데이터 (2026-01-12 추가)
        "config:*",      # 설정 데이터 (API 키 등) (2026-01-12 추가)
        "*:all"          # 모든 :all 패턴 Sets 명시적 추가
    ]

    total_migrated = 0
    total_skipped = 0
    total_errors = 0

    for pattern in patterns:
        print(f"\n🔍 Migrating pattern: {pattern}")

        # 소스에서 모든 키 조회
        keys = source_redis.keys(pattern)

        if not keys:
            print(f"   ℹ️  No keys found for pattern: {pattern}")
            continue

        print(f"   📊 Found {len(keys)} keys")

        for key in keys:
            try:
                # 키 타입 확인
                key_type = source_redis.type(key)

                # 타겟에 이미 있는지 확인
                if target_redis.exists(key):
                    print(f"   ⏭️  Skipping existing key: {key}")
                    total_skipped += 1
                    continue

                # 키 타입에 따라 복사
                if key_type == 'string':
                    value = source_redis.get(key)
                    target_redis.set(key, value)

                elif key_type == 'hash':
                    data = source_redis.hgetall(key)
                    if data:
                        target_redis.hset(key, mapping=data)

                elif key_type == 'list':
                    values = source_redis.lrange(key, 0, -1)
                    if values:
                        target_redis.rpush(key, *values)

                elif key_type == 'set':
                    values = source_redis.smembers(key)
                    if values:
                        target_redis.sadd(key, *values)

                elif key_type == 'zset':
                    values = source_redis.zrange(key, 0, -1, withscores=True)
                    if values:
                        target_redis.zadd(key, dict(values))

                # TTL 복사
                ttl = source_redis.ttl(key)
                if ttl > 0:
                    target_redis.expire(key, ttl)

                print(f"   ✅ Migrated: {key} (type: {key_type})")
                total_migrated += 1

            except Exception as e:
                print(f"   ❌ Error migrating {key}: {e}")
                total_errors += 1

    return total_migrated, total_skipped, total_errors


def verify_user_data():
    """사용자 데이터 검증"""
    print("\n🔍 Verifying user data migration...")

    # 소스에서 사용자 조회
    source_users = source_redis.keys("user:email:*")
    target_users = target_redis.keys("user:email:*")

    print(f"   Source users: {len(source_users)}")
    print(f"   Target users: {len(target_users)}")

    for user_key in source_users:
        email = user_key.replace("user:email:", "")
        user_id = source_redis.get(user_key)

        # 타겟에서 확인
        target_user_id = target_redis.get(user_key)

        if target_user_id == user_id:
            # 사용자 해시 데이터 확인
            source_data = source_redis.hgetall(f"user:{user_id}")
            target_data = target_redis.hgetall(f"user:{user_id}")

            if source_data == target_data:
                print(f"   ✅ Verified: {email}")
            else:
                print(f"   ⚠️  Data mismatch for: {email}")
        else:
            print(f"   ❌ Missing in target: {email}")


if __name__ == "__main__":
    print("="*60)
    print("Redis Data Migration Tool")
    print("="*60)

    # 연결 테스트
    try:
        source_redis.ping()
        print("✅ Connected to source Redis (port 6380)")
    except Exception as e:
        print(f"❌ Failed to connect to source Redis: {e}")
        sys.exit(1)

    try:
        target_redis.ping()
        print("✅ Connected to target Redis (port 6379)")
    except Exception as e:
        print(f"❌ Failed to connect to target Redis: {e}")
        sys.exit(1)

    # 마이그레이션 실행
    print("\n" + "="*60)
    print("Starting Migration...")
    print("="*60)

    migrated, skipped, errors = migrate_all_keys()

    print("\n" + "="*60)
    print("Migration Summary")
    print("="*60)
    print(f"✅ Migrated: {migrated} keys")
    print(f"⏭️  Skipped: {skipped} keys (already exist)")
    print(f"❌ Errors: {errors} keys")

    # 사용자 데이터 검증
    verify_user_data()

    print("\n" + "="*60)
    print("Migration Complete!")
    print("="*60)
