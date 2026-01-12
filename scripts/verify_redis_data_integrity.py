#!/usr/bin/env python3
"""
Redis 데이터 무결성 검증 스크립트
Aggregate Sets와 실제 데이터 간의 일관성 검증

사용법:
    python scripts/verify_redis_data_integrity.py
    python scripts/verify_redis_data_integrity.py --fix  # 자동 수정
"""

import redis
import sys
import re
import argparse
from typing import Set, Dict, List

# Redis 연결
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)


def verify_users_all(fix: bool = False) -> Dict:
    """users:all Set 무결성 검증"""
    print("\n🔍 Verifying users:all Set...")

    # users:all Set의 내용
    users_all = set(redis_client.smembers("users:all"))
    print(f"   users:all Set: {len(users_all)} users")

    # 실제 존재하는 사용자들 (user:email:* 키로부터)
    email_keys = redis_client.keys("user:email:*")
    actual_users = set()

    for key in email_keys:
        user_id = redis_client.get(key)
        if user_id:
            actual_users.add(user_id)

    print(f"   Actual users: {len(actual_users)} users")

    # 차이 분석
    missing_in_set = actual_users - users_all
    extra_in_set = users_all - actual_users

    result = {
        'total_in_set': len(users_all),
        'total_actual': len(actual_users),
        'missing': list(missing_in_set),
        'extra': list(extra_in_set),
        'consistent': len(missing_in_set) == 0 and len(extra_in_set) == 0
    }

    if result['consistent']:
        print("   ✅ users:all Set is consistent")
    else:
        if missing_in_set:
            print(f"   ❌ Missing in users:all: {len(missing_in_set)} users")
            for user_id in missing_in_set:
                # 사용자 정보 조회
                user_data = redis_client.hgetall(f"user:{user_id}")
                email = user_data.get('email', 'unknown')
                username = user_data.get('username', 'unknown')
                print(f"      - {user_id}: {email} ({username})")

                if fix:
                    redis_client.sadd("users:all", user_id)
                    print(f"      ✅ Added to users:all")

        if extra_in_set:
            print(f"   ⚠️  Extra in users:all (orphaned): {len(extra_in_set)} users")
            for user_id in extra_in_set:
                print(f"      - {user_id}")

                if fix:
                    # 실제 사용자 데이터가 없으면 Set에서 제거
                    if not redis_client.exists(f"user:{user_id}"):
                        redis_client.srem("users:all", user_id)
                        print(f"      ✅ Removed from users:all")

    return result


def verify_orgs_all(fix: bool = False) -> Dict:
    """orgs:all Set 무결성 검증"""
    print("\n🔍 Verifying orgs:all Set...")

    # orgs:all Set의 내용
    orgs_all = set(redis_client.smembers("orgs:all"))
    print(f"   orgs:all Set: {len(orgs_all)} orgs")

    # 실제 존재하는 조직들 (org:{id} 또는 org:default)
    org_keys = redis_client.keys("org:*")
    actual_orgs = set()

    for key in org_keys:
        # org:{uuid} 형태 또는 org:default만
        if key == "org:default":
            actual_orgs.add("default")
        elif re.match(r"^org:[a-f0-9-]{36}$", key):
            org_id = key.replace("org:", "")
            actual_orgs.add(org_id)

    print(f"   Actual orgs: {len(actual_orgs)} orgs")

    # 차이 분석
    missing_in_set = actual_orgs - orgs_all
    extra_in_set = orgs_all - actual_orgs

    result = {
        'total_in_set': len(orgs_all),
        'total_actual': len(actual_orgs),
        'missing': list(missing_in_set),
        'extra': list(extra_in_set),
        'consistent': len(missing_in_set) == 0 and len(extra_in_set) == 0
    }

    if result['consistent']:
        print("   ✅ orgs:all Set is consistent")
    else:
        if missing_in_set:
            print(f"   ❌ Missing in orgs:all: {len(missing_in_set)} orgs")
            for org_id in missing_in_set:
                # 조직 정보 조회
                org_data = redis_client.hgetall(f"org:{org_id}")
                name = org_data.get('name', 'unknown')
                print(f"      - {org_id}: {name}")

                if fix:
                    redis_client.sadd("orgs:all", org_id)
                    print(f"      ✅ Added to orgs:all")

        if extra_in_set:
            print(f"   ⚠️  Extra in orgs:all (orphaned): {len(extra_in_set)} orgs")
            for org_id in extra_in_set:
                print(f"      - {org_id}")

                if fix:
                    # 실제 조직 데이터가 없으면 Set에서 제거
                    if not redis_client.exists(f"org:{org_id}"):
                        redis_client.srem("orgs:all", org_id)
                        print(f"      ✅ Removed from orgs:all")

    return result


def verify_all_aggregate_sets(fix: bool = False) -> Dict:
    """모든 aggregate Sets 검증"""
    print("\n" + "="*60)
    print("Redis Data Integrity Verification")
    print("="*60)

    # Redis 연결 테스트
    try:
        redis_client.ping()
        print("✅ Connected to Redis (port 6379)")
    except Exception as e:
        print(f"❌ Failed to connect to Redis: {e}")
        sys.exit(1)

    if fix:
        print("\n⚠️  AUTO-FIX MODE ENABLED")
        print("   Will automatically fix detected issues")

    # 검증 실행
    results = {
        'users': verify_users_all(fix),
        'orgs': verify_orgs_all(fix)
    }

    # 결과 요약
    print("\n" + "="*60)
    print("Verification Summary")
    print("="*60)

    all_consistent = True
    for name, result in results.items():
        status = "✅ PASS" if result['consistent'] else "❌ FAIL"
        print(f"{status} {name}:all")
        print(f"     Set: {result['total_in_set']} | Actual: {result['total_actual']}")

        if not result['consistent']:
            all_consistent = False
            if result['missing']:
                print(f"     Missing: {len(result['missing'])}")
            if result['extra']:
                print(f"     Extra: {len(result['extra'])}")

    print("\n" + "="*60)
    if all_consistent:
        print("✅ All aggregate Sets are consistent!")
    else:
        print("❌ Data integrity issues detected!")
        if not fix:
            print("\n💡 Run with --fix flag to automatically fix issues:")
            print("   python scripts/verify_redis_data_integrity.py --fix")

    print("="*60)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Verify Redis data integrity')
    parser.add_argument('--fix', action='store_true',
                        help='Automatically fix detected issues')

    args = parser.parse_args()

    try:
        results = verify_all_aggregate_sets(fix=args.fix)

        # Exit code
        all_consistent = all(r['consistent'] for r in results.values())
        sys.exit(0 if all_consistent else 1)

    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
