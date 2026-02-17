#!/usr/bin/env python3
"""
문서 인덱싱 상태 검증 스크립트
파일 시스템과 RediSearch 인덱스를 비교하여 누락된 문서 확인

사용법:
    python scripts/verify_document_indexing.py
"""

import redis
import os
from pathlib import Path

# Redis 연결
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

# 데이터 디렉토리
DATA_DIR = os.getenv("DATA_DIR", "./data")
data_path = Path(DATA_DIR)

# 지원하는 파일 확장자
EXTENSIONS = ['.pdf', '.hwp', '.hwpx', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']

print("="*80)
print("문서 인덱싱 상태 검증")
print("="*80)

# 1. 파일 시스템 문서 수집
print("\n🔍 파일 시스템 문서 수집 중...")
fs_files = set()
for ext in EXTENSIONS:
    for f in data_path.glob(f'*{ext}'):
        fs_files.add(f.name.lower())

print(f"✅ 파일 시스템: {len(fs_files)}개 문서")

# 2. 활성 인덱스 확인
active_index = redis_client.get("search:active_index")
if active_index:
    print(f"✅ 활성 인덱스: {active_index}")
else:
    # 인덱스 목록 조회
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "exec", "chatbot_redis", "redis-cli", "FT._LIST"],
            capture_output=True,
            text=True,
            check=True
        )
        indices = result.stdout.strip().split('\n')
        if indices and indices[0]:
            # 가장 최근 인덱스 사용 (타임스탬프 기준)
            active_index = sorted(indices)[-1]
            print(f"⚠️  활성 인덱스 없음, 최신 인덱스 사용: {active_index}")
        else:
            print(f"❌ RediSearch 인덱스가 없습니다")
            exit(1)
    except Exception as e:
        print(f"❌ 인덱스 조회 실패: {e}")
        exit(1)

# 3. RediSearch 인덱스 문서 수집
print(f"\n🔍 RediSearch 인덱스 문서 수집 중...")
try:
    import subprocess
    result = subprocess.run(
        [
            "docker", "exec", "chatbot_redis", "redis-cli",
            "FT.AGGREGATE", active_index, "*",
            "GROUPBY", "1", "@filename",
            "REDUCE", "COUNT", "0", "AS", "doc_count"
        ],
        capture_output=True,
        text=True,
        check=True
    )

    lines = result.stdout.strip().split('\n')

    # 첫 줄: 문서 수
    total_docs = int(lines[0]) if lines else 0

    # 나머지: filename, actual_filename, doc_count, actual_count 반복
    # 패턴: [filename, value, doc_count, count, filename, value, doc_count, count, ...]
    indexed_files = set()
    i = 1
    while i < len(lines):
        if lines[i] == "filename" and i + 1 < len(lines):
            filename = lines[i + 1].lower()
            indexed_files.add(filename)
            i += 4  # Skip to next filename (filename, value, doc_count, count)
        else:
            i += 1

    print(f"✅ RediSearch 인덱스: {len(indexed_files)}개 문서 ({total_docs}개 고유 파일명)")

    # 청크 수 확인
    result2 = subprocess.run(
        ["docker", "exec", "chatbot_redis", "redis-cli", "FT.INFO", active_index],
        capture_output=True,
        text=True,
        check=True
    )
    info_lines = result2.stdout.strip().split('\n')
    for i, line in enumerate(info_lines):
        if line == "num_docs":
            chunk_count = info_lines[i+1]
            print(f"   총 청크 수: {chunk_count}개")
            break

except Exception as e:
    print(f"❌ RediSearch 쿼리 실패: {e}")
    exit(1)

# 4. 차이 비교
print(f"\n📊 비교 결과:")
print(f"   파일 시스템: {len(fs_files)}개")
print(f"   RediSearch:  {len(indexed_files)}개")
print(f"   차이:       {len(fs_files) - len(indexed_files)}개")

missing_in_index = fs_files - indexed_files
extra_in_index = indexed_files - fs_files

# 5. 누락된 문서
if missing_in_index:
    print(f"\n❌ 인덱스에 누락된 문서 ({len(missing_in_index)}개):")
    for filename in sorted(missing_in_index):
        # 원본 파일명 찾기 (대소문자 보존)
        original_name = None
        for ext in EXTENSIONS:
            for f in data_path.glob(f'*{ext}'):
                if f.name.lower() == filename:
                    original_name = f.name
                    break
            if original_name:
                break

        if original_name:
            # 그룹 확인
            doc_group_id = redis_client.get(f'doc:group:{original_name}')
            if doc_group_id:
                group_data = redis_client.hgetall(f"group:{doc_group_id}")
                group_name = group_data.get('name', 'Unknown')
                print(f"  - {original_name}")
                print(f"    그룹: {group_name} ({doc_group_id})")
            else:
                print(f"  - {original_name}")
                print(f"    그룹: 없음")
        else:
            print(f"  - {filename}")

    print(f"\n💡 재인덱싱 명령어:")
    for filename in sorted(missing_in_index):
        # 원본 파일명 찾기
        for ext in EXTENSIONS:
            for f in data_path.glob(f'*{ext}'):
                if f.name.lower() == filename:
                    print(f'python scripts/reindex_single_document.py "{f.name}"')
                    break
else:
    print(f"\n✅ 모든 문서가 인덱스에 있습니다")

# 6. 인덱스에만 있는 문서 (파일 삭제됨)
if extra_in_index:
    print(f"\n⚠️  파일 시스템에 없는 인덱스 문서 ({len(extra_in_index)}개):")
    for filename in sorted(extra_in_index):
        print(f"  - {filename}")
    print(f"\n💡 인덱스 정리가 필요할 수 있습니다")

# 7. 그룹별 분포
print(f"\n📋 파일 시스템 그룹별 분포:")
group_dist = {}
for ext in EXTENSIONS:
    for f in data_path.glob(f'*{ext}'):
        doc_group_id = redis_client.get(f'doc:group:{f.name}')
        if doc_group_id:
            if doc_group_id not in group_dist:
                group_dist[doc_group_id] = []
            group_dist[doc_group_id].append(f.name)

for group_id in sorted(group_dist.keys(), key=lambda x: len(group_dist[x]), reverse=True):
    group_data = redis_client.hgetall(f"group:{group_id}")
    group_name = group_data.get('name', 'Unknown')
    doc_count = len(group_dist[group_id])
    print(f"  {group_name:20s} ({group_id}): {doc_count:3d}개")

print("\n" + "="*80)
if missing_in_index:
    print(f"❌ 검증 실패: {len(missing_in_index)}개 문서 누락")
else:
    print(f"✅ 검증 성공: 모든 문서 인덱싱됨")
print("="*80)
