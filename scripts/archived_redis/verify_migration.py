#!/usr/bin/env python3
"""
Redis 마이그레이션 검증 스크립트
소스와 타겟 Redis의 키 패턴별 수를 비교

사용법:
    python scripts/verify_migration.py
"""

import redis
import sys
from collections import defaultdict

def verify_migration():
    """마이그레이션 검증"""

    print("="*80)
    print("Redis 마이그레이션 검증")
    print("="*80)

    # Redis 연결
    try:
        source_redis = redis.Redis(host='localhost', port=6380, decode_responses=True)
        source_redis.ping()
        print("✅ 소스 Redis 연결 성공 (포트 6380)")
    except Exception as e:
        print(f"❌ 소스 Redis 연결 실패: {e}")
        return False

    try:
        target_redis = redis.Redis(host='localhost', port=6379, decode_responses=True)
        target_redis.ping()
        print("✅ 타겟 Redis 연결 성공 (포트 6379)")
    except Exception as e:
        print(f"❌ 타겟 Redis 연결 실패: {e}")
        return False

    # 전체 키 수 비교
    print(f"\n📊 전체 키 수 비교:")
    source_total = len(source_redis.keys("*"))
    target_total = len(target_redis.keys("*"))

    print(f"  소스: {source_total:,}개")
    print(f"  타겟: {target_total:,}개")
    print(f"  차이: {abs(source_total - target_total):,}개")

    if source_total == target_total:
        print(f"  ✅ 전체 키 수 일치")
    else:
        print(f"  ⚠️  전체 키 수 불일치")

    # 패턴별 비교
    patterns = [
        "user:*",
        "users:*",
        "org:*",
        "orgs:*",
        "group:*",
        "groups:*",
        "doc:*",
        "conversation:*",
        "session:*",
        "audit:*",
        "security:*",
        "feedback:*",
        "*:all"
    ]

    print(f"\n📋 패턴별 키 수 비교:")
    print(f"{'패턴':<30} {'소스':>10} {'타겟':>10} {'차이':>10} {'상태':>10}")
    print("-" * 80)

    all_match = True
    missing_patterns = []

    for pattern in patterns:
        source_keys = source_redis.keys(pattern)
        target_keys = target_redis.keys(pattern)

        source_count = len(source_keys)
        target_count = len(target_keys)
        diff = abs(source_count - target_count)

        if source_count == target_count:
            status = "✅"
        else:
            status = "❌"
            all_match = False
            if source_count > 0 and target_count == 0:
                missing_patterns.append(pattern)

        print(f"{pattern:<30} {source_count:>10,} {target_count:>10,} {diff:>10,} {status:>10}")

    # 자동 패턴 감지
    print(f"\n🔍 소스 Redis의 모든 키 패턴 자동 감지:")

    source_patterns = defaultdict(int)
    all_source_keys = source_redis.keys("*")

    for key in all_source_keys:
        if ':' in key:
            # 첫 번째 콜론까지를 패턴으로
            prefix = key.split(':')[0]
            source_patterns[prefix + ':*'] += 1
        else:
            source_patterns[key] += 1

    # 정의된 패턴에 없는 것들 찾기
    print(f"\n⚠️  마이그레이션 스크립트에 없는 패턴:")
    new_patterns_found = False
    for pattern, count in sorted(source_patterns.items(), key=lambda x: x[1], reverse=True):
        # 패턴이 정의된 patterns에 포함되지 않았는지 확인
        is_covered = any(p.replace('*', '') in pattern for p in patterns)

        if not is_covered and count > 0:
            new_patterns_found = True
            target_count = len(target_redis.keys(pattern))
            print(f"  {pattern:<30} {count:>10,}개 (타겟: {target_count:>10,}개)")

    if not new_patterns_found:
        print(f"  ✅ 모든 패턴이 마이그레이션 스크립트에 포함되어 있습니다")

    # 누락된 패턴 상세 분석
    if missing_patterns:
        print(f"\n❌ 완전히 누락된 패턴 ({len(missing_patterns)}개):")
        for pattern in missing_patterns:
            source_keys = source_redis.keys(pattern)
            print(f"\n  패턴: {pattern} ({len(source_keys)}개 키)")

            # 샘플 키 표시
            for key in list(source_keys)[:5]:
                key_type = source_redis.type(key)
                print(f"    - {key} (type: {key_type})")

            if len(source_keys) > 5:
                print(f"    ... 외 {len(source_keys) - 5}개")

    # 최종 결과
    print("\n" + "="*80)
    if all_match and source_total == target_total:
        print("✅ 마이그레이션 검증 성공: 모든 키가 정상 복사됨")
        return True
    else:
        print("❌ 마이그레이션 검증 실패: 누락된 키 있음")
        print(f"\n💡 권장 조치:")
        print(f"   1. 누락된 패턴을 migrate_redis_data.py에 추가")
        print(f"   2. 마이그레이션 재실행")
        print(f"   3. 이 검증 스크립트로 재확인")
        return False

if __name__ == "__main__":
    success = verify_migration()
    sys.exit(0 if success else 1)
