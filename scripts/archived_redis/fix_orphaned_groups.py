#!/usr/bin/env python3
"""
고아 그룹 수정 스크립트
Orphaned groups fix script

부모가 없거나 삭제된 그룹을 찾아서 수정합니다.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import redis
from loguru import logger
import json
from typing import Set, Dict, List

# Redis 연결
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=False,
    socket_connect_timeout=5
)

def get_all_groups() -> Dict[str, Dict]:
    """모든 그룹 조회"""
    groups = {}

    for key in redis_client.scan_iter(match="group:*", count=100):
        key_str = key.decode('utf-8')

        # 메타데이터 키 제외
        if any(x in key_str for x in [':children', ':documents', ':stats', ':parent']):
            continue

        # UUID 형식 확인
        parts = key_str.split(':')
        if len(parts) != 2:
            continue

        group_id = parts[1]

        # 키 타입 확인 (hash가 아니면 스킵)
        try:
            key_type = redis_client.type(key).decode('utf-8')
            if key_type != 'hash':
                continue

            group_data = redis_client.hgetall(key)
        except Exception as e:
            logger.debug(f"Failed to read key {key_str}: {e}")
            continue

        if group_data:
            groups[group_id] = {
                k.decode('utf-8'): v.decode('utf-8')
                for k, v in group_data.items()
            }
            groups[group_id]['group_id'] = group_id

    return groups

def find_orphaned_groups(groups: Dict[str, Dict]) -> List[Dict]:
    """고아 그룹 찾기"""
    orphaned = []

    for group_id, group_data in groups.items():
        parent_id = group_data.get('parent_id')

        # 루트 그룹은 제외 (parent_id가 없거나 'root')
        if not parent_id or parent_id == 'root':
            continue

        # 부모 그룹이 존재하지 않으면 고아
        if parent_id not in groups:
            orphaned.append({
                'group_id': group_id,
                'name': group_data.get('name', 'Unknown'),
                'parent_id': parent_id,
                'org_id': group_data.get('org_id', 'default')
            })

    return orphaned

def get_root_group_for_org(org_id: str, groups: Dict[str, Dict]) -> str:
    """조직의 루트 그룹 찾기"""
    for group_id, group_data in groups.items():
        if (group_data.get('org_id') == org_id and
            (not group_data.get('parent_id') or group_data.get('parent_id') == 'root')):
            return group_id
    return None

def fix_orphaned_group(group_id: str, org_id: str, root_group_id: str):
    """고아 그룹을 루트 그룹의 자식으로 연결"""
    try:
        # 그룹의 parent_id를 루트 그룹으로 변경
        redis_client.hset(f"group:{group_id}", "parent_id", root_group_id)

        # 루트 그룹의 children에 추가
        redis_client.sadd(f"group:{root_group_id}:children", group_id)

        logger.info(f"✅ Fixed: {group_id} → parent: {root_group_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to fix {group_id}: {e}")
        return False

def main():
    """메인 실행 함수"""
    logger.info("🔍 고아 그룹 검색 시작...")

    # 모든 그룹 조회
    groups = get_all_groups()
    logger.info(f"📊 전체 그룹 수: {len(groups)}")

    # 고아 그룹 찾기
    orphaned = find_orphaned_groups(groups)

    if not orphaned:
        logger.success("✅ 고아 그룹이 없습니다!")
        return

    logger.warning(f"⚠️  고아 그룹 발견: {len(orphaned)}개")

    # 고아 그룹 출력
    print("\n발견된 고아 그룹:")
    print("-" * 80)
    for i, group in enumerate(orphaned, 1):
        print(f"{i}. {group['name']} (ID: {group['group_id'][:8]}...)")
        print(f"   존재하지 않는 부모: {group['parent_id'][:8]}...")
        print(f"   조직: {group['org_id']}")
        print()

    # 수정 여부 확인
    response = input(f"\n{len(orphaned)}개의 고아 그룹을 수정하시겠습니까? (y/N): ")

    if response.lower() != 'y':
        logger.info("❌ 작업이 취소되었습니다.")
        return

    # 고아 그룹 수정
    logger.info("\n🔧 고아 그룹 수정 시작...")
    fixed_count = 0

    for group in orphaned:
        group_id = group['group_id']
        org_id = group['org_id']

        # 조직의 루트 그룹 찾기
        root_group_id = get_root_group_for_org(org_id, groups)

        if not root_group_id:
            # 루트 그룹이 없으면 스킵 (심각한 문제)
            logger.error(f"❌ {group['name']}: 조직 {org_id}의 루트 그룹을 찾을 수 없습니다!")
            continue

        # 고아 그룹 수정
        if fix_orphaned_group(group_id, org_id, root_group_id):
            fixed_count += 1

    # 결과 출력
    print("\n" + "=" * 80)
    logger.success(f"✅ 수정 완료: {fixed_count}/{len(orphaned)}")

    if fixed_count < len(orphaned):
        logger.warning(f"⚠️  수정 실패: {len(orphaned) - fixed_count}개")
        logger.info("💡 실패한 그룹은 수동으로 확인이 필요합니다.")

    logger.info("\n💡 팁: 그룹 트리를 다시 로드하여 확인하세요.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 사용자가 작업을 중단했습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}", exc_info=True)
        sys.exit(1)
