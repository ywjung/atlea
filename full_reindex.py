#!/usr/bin/env python3
"""
전체 재인덱싱 스크립트
모든 data/ 디렉토리의 파일을 재인덱싱합니다.
"""

import requests
import os
import glob
from pathlib import Path
from datetime import datetime
import json

# Server URL
SERVER_URL = "http://localhost:8000"

def create_default_group():
    """기본 그룹 생성"""
    print("🔧 기본 그룹 생성 중...")

    try:
        # 먼저 로그인 (admin 계정 사용)
        login_response = requests.post(
            f"{SERVER_URL}/api/auth/login",
            json={"username": "admin", "password": "admin"},
            timeout=10
        )

        if login_response.status_code != 200:
            print("   ⚠️  로그인 실패 - 그룹 생성 건너뜀")
            return None

        token = login_response.json().get('access_token')
        headers = {"Authorization": f"Bearer {token}"}

        # 기본 그룹 생성
        group_data = {
            "name": "기본",
            "description": "전체 재인덱싱 후 생성된 기본 그룹",
            "org_id": "default"
        }

        response = requests.post(
            f"{SERVER_URL}/api/groups",
            json=group_data,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            group_id = response.json().get('group_id')
            print(f"   ✅ 기본 그룹 생성 완료: {group_id}")
            return group_id
        else:
            print(f"   ⚠️  그룹 생성 실패: {response.status_code}")
            return None

    except Exception as e:
        print(f"   ⚠️  그룹 생성 오류: {e}")
        return None

def upload_file(file_path: str, group_id: str = None) -> bool:
    """단일 파일 업로드 및 인덱싱"""
    filename = os.path.basename(file_path)

    try:
        with open(file_path, 'rb') as f:
            files = {'file': (filename, f, 'application/octet-stream')}

            # group_id가 있으면 파라미터로 전달
            params = {}
            if group_id:
                params['group_id'] = group_id

            response = requests.post(
                f"{SERVER_URL}/api/documents/upload",
                files=files,
                params=params,
                timeout=300  # 5분 타임아웃
            )

        if response.status_code == 200:
            result = response.json()
            chunks_count = result.get('chunks_count', 0)
            print(f"   ✅ 인덱싱 완료: {chunks_count}개 청크")
            return True
        else:
            print(f"   ❌ 실패: {response.status_code} - {response.text[:100]}")
            return False

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return False

def main():
    print("=" * 60)
    print("전체 재인덱싱 시작")
    print("=" * 60)
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

    # 서버 상태 확인
    try:
        health = requests.get(f"{SERVER_URL}/health", timeout=5)
        if health.status_code != 200:
            print("❌ 서버가 실행되지 않았습니다. 먼저 서버를 시작하세요.")
            return
        print("✅ 서버 연결 확인")
    except Exception as e:
        print(f"❌ 서버 연결 실패: {e}")
        print("   서버를 먼저 시작하세요: ./run.sh")
        return

    # 기본 그룹 생성
    group_id = create_default_group()
    print("")

    # data/ 디렉토리의 모든 파일 찾기
    file_patterns = [
        'data/*.pdf',
        'data/*.txt',
        'data/*.hwp',
        'data/*.hwpx',
        'data/*.doc',
        'data/*.docx'
    ]

    all_files = []
    for pattern in file_patterns:
        all_files.extend(glob.glob(pattern))

    print(f"📁 총 {len(all_files)}개 파일 발견")
    print("")

    # 파일 처리
    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(all_files, 1):
        print(f"[{i}/{len(all_files)}] 📄 처리 중: {os.path.basename(file_path)}")

        if upload_file(file_path, group_id):
            success_count += 1
        else:
            fail_count += 1

        print("")

    # 결과 출력
    print("=" * 60)
    print("재인덱싱 완료")
    print("=" * 60)
    print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"✅ 성공: {success_count}개")
    print(f"❌ 실패: {fail_count}개")
    print(f"📊 총 파일: {len(all_files)}개")
    print(f"📈 성공률: {(success_count/len(all_files)*100):.1f}%")
    print("")

    if group_id:
        print("✅ 모든 문서가 '기본' 그룹에 추가되었습니다")
        print("   관리자 페이지에서 그룹을 생성하고 문서를 이동하세요")

    print("")

if __name__ == '__main__':
    main()
