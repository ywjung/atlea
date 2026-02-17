#!/usr/bin/env python3
"""
관리자 페이지 API 엔드포인트 권한 검증 스크립트
"""
import re
from pathlib import Path

# admin.html에서 추출한 API 엔드포인트
admin_endpoints = {
    "대시보드": [
        '/api/auth/admin/stats',  # 사용자 통계
        '/api/documents',  # 문서 통계
        '/api/cache/stats',  # 캐시 통계
        '/api/admin/feedback/stats',  # 피드백 통계
    ],
    "사용자 관리": [
        '/api/auth/admin/stats',  # 사용자 목록
    ],
    "문서 관리": [
        '/api/documents',
        '/api/documents/upload',
    ],
    "그룹 관리": [
        '/api/groups',
    ],
    "보안 로그": [
        '/api/auth/admin/security-logs',  # 또는 /api/admin/security-logs
    ],
    "감사 로그": [
        '/api/admin/audit/logs',
        '/api/admin/audit/actions',
    ],
    "웹훅": [
        '/api/auth/webhooks',
    ],
    "모델 설정": [
        '/api/admin/models/backend',
        '/api/admin/models/config',
        '/api/admin/models/list',
    ],
    "시스템 설정": [
        '/api/admin/settings',
        '/api/admin/system-prompt',
        '/api/settings',
    ],
    "백업": [
        '/api/redis/backup/list',
        '/api/redis/backup/create',
        '/api/redis/backup/restore',
        '/api/redis/backup/delete',
        '/api/redis/backup/schedule',
    ],
    "재색인": [
        '/api/reindex',
        '/api/reindex/progress',
        '/api/reindex/cancel',
    ],
    "캐시": [
        '/api/cache/stats',
        '/api/cache/clear',
    ],
}

def check_endpoint(content, endpoint):
    """엔드포인트의 권한 상태 확인"""
    # Endpoint path를 정규식에서 사용할 수 있도록 이스케이프
    escaped = re.escape(endpoint)

    # 엔드포인트 정의 찾기 (GET/POST/PUT/DELETE/PATCH)
    # {} 파라미터를 고려한 패턴
    base_pattern = escaped.replace(r'\{filename\}', '[^"]*').replace(r'\{group_id\}', '[^"]*').replace(r'\{version\}', '[^"]*').replace(r'\{session_id\}', '[^"]*')
    pattern = rf'@app\.(get|post|put|delete|patch)\("{base_pattern}"[^)]*\)\s*\n\s*async def ([^(]+)\('

    match = re.search(pattern, content, re.MULTILINE)

    if not match:
        return {
            "exists": False,
            "function": None,
            "has_admin": False,
            "has_user_auth": False,
        }

    func_name = match.group(2)
    func_start = match.start()
    func_body = content[func_start:func_start + 5000]  # 함수 본문 일부 가져오기

    # 관리자 권한 확인
    has_require_admin = 'require_admin(' in func_body
    has_admin_role_check = ('role' in func_body and '"admin"' in func_body) or ('role' in func_body and "'admin'" in func_body)

    # 사용자 인증 확인
    has_current_user = 'current_user' in func_body or 'get_current_active_user' in func_body

    return {
        "exists": True,
        "function": func_name,
        "has_admin": has_require_admin or has_admin_role_check,
        "has_user_auth": has_current_user,
    }

def main():
    web_server_path = Path('src/web_server.py')
    content = web_server_path.read_text()

    print("\n" + "=" * 100)
    print("관리자 페이지 메뉴별 API 엔드포인트 권한 검증")
    print("=" * 100)

    all_endpoints = set()
    for endpoints in admin_endpoints.values():
        all_endpoints.update(endpoints)

    results = {
        "✅ 관리자 권한 있음": [],
        "⚠️  사용자 인증만 (관리자 권한 필요)": [],
        "❌ 엔드포인트 없음 (구현 필요)": [],
    }

    for category, endpoints in admin_endpoints.items():
        print(f"\n\n📁 {category}")
        print("-" * 100)

        for endpoint in endpoints:
            status = check_endpoint(content, endpoint)

            if not status["exists"]:
                icon = "❌"
                msg = f"엔드포인트 없음"
                results["❌ 엔드포인트 없음 (구현 필요)"].append(f"{endpoint} (from {category})")
            elif status["has_admin"]:
                icon = "✅"
                msg = f"관리자 권한 있음 ({status['function']})"
                results["✅ 관리자 권한 있음"].append(f"{endpoint} ({status['function']})")
            elif status["has_user_auth"]:
                icon = "⚠️ "
                msg = f"사용자 인증만 있음 - 관리자 권한 추가 필요 ({status['function']})"
                results["⚠️  사용자 인증만 (관리자 권한 필요)"].append(f"{endpoint} ({status['function']})")
            else:
                icon = "❌"
                msg = f"권한 없음 ({status['function']})"
                results["❌ 엔드포인트 없음 (구현 필요)"].append(f"{endpoint} ({status['function']})")

            print(f"  {icon} {endpoint}")
            print(f"     → {msg}")

    # 요약
    print("\n\n" + "=" * 100)
    print("📊 검증 결과 요약")
    print("=" * 100)

    for category, endpoints in results.items():
        if endpoints:
            print(f"\n{category} ({len(endpoints)}개)")
            print("-" * 100)
            for ep in sorted(set(endpoints)):
                print(f"  • {ep}")

    print("\n" + "=" * 100)
    print(f"총계:")
    print(f"  ✅ 관리자 권한 있음: {len(set(results['✅ 관리자 권한 있음']))}개")
    print(f"  ⚠️  사용자 인증만: {len(set(results['⚠️  사용자 인증만 (관리자 권한 필요)']))}개")
    print(f"  ❌ 엔드포인트 없음: {len(set(results['❌ 엔드포인트 없음 (구현 필요)']))}개")
    print("=" * 100)

if __name__ == "__main__":
    main()
