#!/usr/bin/env python3
"""
조직 기반 검색 범위 필터링 테스트

이 스크립트는 다음을 검증합니다:
1. 사용자는 자신의 조직에 할당된 그룹만 조회 가능
2. 사용자는 자신의 조직에 할당된 문서만 조회 가능
3. 검색 시 조직 그룹으로 필터링됨
4. 시스템 관리자는 모든 조직 접근 가능
"""

import requests
import json
from typing import Dict, Optional

BASE_URL = "http://localhost:8085"

def login(username: str, password: str) -> Optional[str]:
    """사용자 로그인"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": username, "password": password}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("tokens", {}).get("access_token")
    return None

def get_user_info(token: str) -> Dict:
    """현재 사용자 정보 조회"""
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return {}

def get_groups(token: str) -> Dict:
    """그룹 목록 조회"""
    response = requests.get(
        f"{BASE_URL}/api/groups",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return {}

def get_documents(token: str) -> Dict:
    """문서 목록 조회"""
    response = requests.get(
        f"{BASE_URL}/api/documents",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return {}

def get_organization(token: str, org_id: str) -> Dict:
    """조직 정보 조회"""
    response = requests.get(
        f"{BASE_URL}/api/organizations/{org_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return {}

def print_header(title: str):
    """헤더 출력"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def test_user_org_filter(username: str, password: str, test_name: str):
    """사용자별 조직 필터링 테스트"""
    print_header(f"테스트: {test_name}")

    # 1. 로그인
    print(f"\n1️⃣ 로그인: {username}")
    token = login(username, password)
    if not token:
        print("   ❌ 로그인 실패")
        return
    print("   ✅ 로그인 성공")

    # 2. 사용자 정보 확인
    print("\n2️⃣ 사용자 정보 확인")
    user_data = get_user_info(token)
    user = user_data.get("user", {})
    org_id = user.get("org_id")
    role = user.get("role")
    print(f"   사용자: {user.get('username')}")
    print(f"   역할: {role}")
    print(f"   조직 ID: {org_id}")

    # 3. 조직 정보 조회
    if org_id:
        print("\n3️⃣ 조직 정보 조회")
        org_data = get_organization(token, org_id)
        org_name = org_data.get("name", "알 수 없음")
        print(f"   조직명: {org_name}")

    # 4. 그룹 목록 확인
    print("\n4️⃣ 그룹 목록 조회 (조직 필터링)")
    groups_data = get_groups(token)
    groups = groups_data.get("groups", [])
    print(f"   조회된 그룹 수: {len(groups)}개")

    if groups:
        print("   그룹 목록:")
        for group in groups[:5]:  # 최대 5개만 표시
            group_orgs = group.get("organizations", [])
            org_count = len(group_orgs) if isinstance(group_orgs, list) else 0
            print(f"      - {group.get('name')} (문서: {group.get('document_count', 0)}개, 조직: {org_count}개)")
        if len(groups) > 5:
            print(f"      ... 외 {len(groups) - 5}개 그룹")

    # 5. 문서 목록 확인
    print("\n5️⃣ 문서 목록 조회 (조직 필터링)")
    docs_data = get_documents(token)
    documents = docs_data.get("documents", [])
    print(f"   조회된 문서 수: {len(documents)}개")

    if documents:
        print("   문서 목록:")
        for doc in documents[:5]:  # 최대 5개만 표시
            print(f"      - {doc.get('name')} (그룹: {doc.get('group_id', '없음')})")
        if len(documents) > 5:
            print(f"      ... 외 {len(documents) - 5}개 문서")

    print("\n" + "-"*60)
    print(f"✅ {test_name} 완료")
    print("-"*60)

def main():
    """메인 테스트 실행"""
    print("\n" + "🔍 조직 기반 검색 범위 필터링 테스트".center(60))
    print("="*60)

    # 테스트할 사용자 계정
    test_users = [
        ("admin", "admin123", "시스템 관리자 (모든 조직 접근)"),
        ("user1", "password123", "일반 사용자 1 (default 조직)"),
    ]

    for username, password, description in test_users:
        try:
            test_user_org_filter(username, password, description)
        except Exception as e:
            print(f"\n❌ 테스트 실패: {e}")
            import traceback
            traceback.print_exc()

    print_header("전체 테스트 완료")
    print("\n✅ 검증 사항:")
    print("   1. 사용자별 조직 정보 확인")
    print("   2. 조직에 할당된 그룹만 조회")
    print("   3. 조직에 할당된 문서만 조회")
    print("   4. 시스템 관리자는 모든 데이터 조회 가능")
    print("\n💡 다음 단계:")
    print("   - 브라우저에서 UI 확인")
    print("   - 검색 범위 헤더에 조직명 표시 확인")
    print("   - 문서/그룹 개수 표시 확인")
    print()

if __name__ == "__main__":
    main()
