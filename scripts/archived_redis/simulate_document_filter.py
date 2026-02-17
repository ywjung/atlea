#!/usr/bin/env python3
"""
문서 필터링 시뮬레이션
사용자가 실제로 볼 수 있는 문서 수를 계산

사용법:
    python scripts/simulate_document_filter.py
"""

import redis
import os
from pathlib import Path

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

DATA_DIR = os.getenv("DATA_DIR", "./data")
data_path = Path(DATA_DIR)

EXTENSIONS = ['.pdf', '.hwp', '.hwpx', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']

files = []
for ext in EXTENSIONS:
    files.extend(list(data_path.glob(f'*{ext}')))

print(f"파일 시스템: {len(files)}개 문서")

# org_group_ids (admin은 모든 그룹 볼 수 있음)
org_group_ids = {
    'db509513-b431-4cb6-9237-9ac2b1a646fc',
    '256496ee-8a0c-455b-8b16-97e7a102544f',
    'eea12d54-0c0b-4310-a122-efbfa3905a31'
}

print(f"\n사용자가 볼 수 있는 그룹 IDs:")
for gid in org_group_ids:
    group_data = redis_client.hgetall(f"group:{gid}")
    print(f"  - {gid}: {group_data.get('name', 'Unknown')}")

filtered_count = 0
no_group_count = 0
not_in_org_count = 0
filtered_files = []
excluded_files = []

for pdf_file in files:
    doc_group_id = redis_client.get(f'doc:group:{pdf_file.name}')

    if doc_group_id:
        if doc_group_id in org_group_ids:
            filtered_count += 1
            filtered_files.append((pdf_file.name, doc_group_id))
        else:
            not_in_org_count += 1
            excluded_files.append((pdf_file.name, doc_group_id, "Not in org groups"))
    else:
        no_group_count += 1
        excluded_files.append((pdf_file.name, None, "No group mapping"))

print(f"\n📊 필터링 결과:")
print(f"✅ 필터링 통과: {filtered_count}개")
print(f"❌ 그룹 없음: {no_group_count}개")
print(f"❌ 조직 그룹 아님: {not_in_org_count}개")

if excluded_files:
    print(f"\n❌ 제외된 문서 ({len(excluded_files)}개):")
    for filename, group_id, reason in excluded_files:
        print(f"  - {filename}")
        print(f"    Reason: {reason}")
        if group_id:
            print(f"    Group: {group_id}")

print(f"\n🎯 사용자 화면에 표시될 문서: {filtered_count}개")

# 그룹별 분포
group_dist = {}
for filename, group_id in filtered_files:
    if group_id not in group_dist:
        group_dist[group_id] = []
    group_dist[group_id].append(filename)

print(f"\n📋 그룹별 문서 분포:")
for group_id, docs in sorted(group_dist.items(), key=lambda x: len(x[1]), reverse=True):
    group_data = redis_client.hgetall(f"group:{group_id}")
    group_name = group_data.get('name', 'Unknown')
    print(f"  {group_name} ({group_id}): {len(docs)}개")
