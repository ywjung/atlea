# 문서 표시 문제 해결 (2026-01-10)

## 문제 요약

재색인 후 관리자 페이지에서 문서가 표시되지 않는 문제가 발생했습니다.

### 증상
- 재색인 완료 메시지: "7487 chunks from 44 documents"
- API `/api/documents` 응답: `{"documents":[],"total_count":0}`
- `data/` 디렉토리: 44개 파일 존재
- Redis: 7487개 문서 청크 존재

### 근본 원인

재색인 과정에서 **문서 그룹 매핑 키(`doc:group:{filename}`)가 재생성되지 않음**.

#### 기술적 세부사항

1. **문서 데이터 저장 위치**
   - 문서 청크 해시: `doc:{index_name}:{id}` → 여기에 `group_id` 필드 포함
   - 그룹 매핑 키: `doc:group:{filename}` → 이 키가 누락됨

2. **재색인 프로세스 (`src/vector_db.py:377-385`)**
   ```python
   # 기존 그룹 할당 읽기 시도
   existing_group = self.client.get(f'doc:group:{filename}')
   if existing_group:
       filename_group_cache[filename] = existing_group.decode('utf-8')
   else:
       filename_group_cache[filename] = default_group_id

   # 문서 데이터에 group_id 저장 (청크 해시에)
   doc_data = {
       "group_id": assigned_group_id,  # ✅ 저장됨
       ...
   }
   ```

3. **문제점**
   - `doc:group:{filename}` 키를 **읽기**는 하지만 **쓰기**는 하지 않음
   - 재색인 후 이 키가 없어짐

4. **문서 목록 API 필터링 (`src/web_server.py:4894-4902`)**
   ```python
   # 문서 그룹 확인
   doc_group_id = cache_manager.redis.get(f'doc:group:{pdf_file.name}')
   if doc_group_id:
       # 그룹 ID가 있으면 처리
       ...
   else:
       continue  # ❌ 그룹이 없으면 건너뜀 → 문서 숨김
   ```

## 해결 방법

### 1. 즉시 수정: 매핑 재구축 스크립트

**파일**: `scripts/rebuild_doc_group_mappings.py`

```python
# 문서 청크에서 filename → group_id 매핑 추출
for key in doc_keys:
    doc_data = redis_client.hgetall(key)
    filename = doc_data.get('filename')
    group_id = doc_data.get('group_id')
    file_to_group[filename] = group_id

# doc:group:{filename} 키 생성
for filename, group_id in file_to_group.items():
    pipe.set(f"doc:group:{filename}", group_id)
    pipe.sadd(f"group:docs:{group_id}", filename)
```

**실행 결과**:
- ✅ 44개 문서 그룹 매핑 생성
- ✅ API에서 44개 문서 정상 표시

### 2. 영구 수정: 재색인 프로세스 통합

**파일**: `src/web_server.py`

#### 추가된 함수 (`run_reindex_task` 이전에 정의됨)
```python
async def rebuild_doc_group_mappings():
    """
    Rebuild doc:group:{filename} mappings from indexed document data

    This ensures that all documents have proper group assignments after reindex.
    Document data contains group_id, so we extract it and create the reverse mapping.
    """
    # 현재 인덱스의 모든 문서 청크 스캔
    cursor = 0
    file_to_group = {}

    while True:
        cursor, keys = vector_db.client.scan(cursor, match=f"doc:{index_name}:*", count=100)

        for key in keys:
            doc_data = vector_db.client.hgetall(key)
            filename = doc_data.get('filename')
            group_id = doc_data.get('group_id')

            if filename and group_id and filename not in file_to_group:
                file_to_group[filename] = group_id

        if cursor == 0:
            break

    # doc:group:{filename} 키와 group:docs:{group_id} 세트 재생성
    pipe = vector_db.client.pipeline()
    for filename, group_id in file_to_group.items():
        pipe.set(f"doc:group:{filename}", group_id)
        pipe.sadd(f"group:docs:{group_id}", filename)
    pipe.execute()
```

#### 재색인 프로세스 수정 (`run_reindex_task` 함수 내)
```python
logger.info("🔄 Synchronizing group document counts...")
group_manager.sync_document_counts()

# ✨ 새로 추가된 단계
logger.info("🔨 Rebuilding document group mappings...")
await rebuild_doc_group_mappings()

# Schedule cleanup of old index (async, non-blocking)
logger.info(f"🗑️ Scheduling cleanup of old index: {old_index_name}")
asyncio.create_task(cleanup_old_index_async(old_index_name))
```

## 수정된 파일

### 1. `scripts/rebuild_doc_group_mappings.py` (신규)
- 독립 실행형 스크립트
- 문서 그룹 매핑 재구축 유틸리티
- 문제 발생 시 수동으로 실행 가능

### 2. `src/web_server.py`
- **라인 4035-4091**: `rebuild_doc_group_mappings()` 함수 추가
- **라인 4108-4109**: 재색인 프로세스에 매핑 재구축 단계 추가

## 재색인 프로세스 (수정 후)

### Blue-Green 재색인 흐름

```
1. 새 인덱스 생성 (pdf_index_v{timestamp})
   ↓
2. 문서 처리 및 임베딩
   ↓
3. 새 인덱스에 문서 추가
   ├─ 문서 청크: doc:{new_index}:{id}
   └─ 청크 데이터에 group_id 포함
   ↓
4. 인덱스 전환 (atomic swap)
   - index:active → new_index
   ↓
5. 문서 카운트 동기화
   ↓
6. 🆕 문서 그룹 매핑 재구축
   ├─ doc:group:{filename} 키 생성
   └─ group:docs:{group_id} 세트 업데이트
   ↓
7. 이전 인덱스 정리 (5분 후)
   ↓
8. 완료
```

## 검증

### 재색인 전
```bash
$ redis-cli KEYS "doc:group:*" | wc -l
0
```

### 스크립트 실행
```bash
$ python scripts/rebuild_doc_group_mappings.py
✅ Created 44 new mappings
```

### 재색인 후
```bash
$ redis-cli KEYS "doc:group:*" | wc -l
44
```

### API 확인
```bash
$ curl -H "Authorization: Bearer $TOKEN" http://localhost:8085/api/documents
{
  "documents": [...],  # 44개 문서
  "total_count": 44
}
```

## 향후 방지 방법

### 1. 자동 복구
- 재색인 프로세스에 매핑 재구축 단계 포함 (완료)
- 향후 재색인 시 자동으로 문제 해결

### 2. 모니터링
다음 지표 추적 권장:
```python
# 문서 청크 수
doc_chunks = redis_client.dbsize("doc:{index}:*")

# 그룹 매핑 수
doc_mappings = redis_client.dbsize("doc:group:*")

# 불일치 감지
if unique_files != doc_mappings:
    logger.warning("⚠️ Document-group mapping mismatch detected")
```

### 3. 데이터 무결성 검사
재색인 완료 후 검증:
```python
# 모든 파일에 그룹 매핑이 있는지 확인
for file in data_directory:
    if not redis.exists(f"doc:group:{file}"):
        logger.error(f"Missing group mapping for {file}")
```

## 영향 분석

### 영향받은 기능
- ✅ 관리자 문서 목록 (수정됨)
- ✅ 문서 검색 (정상 작동 - 청크 데이터의 group_id 사용)
- ✅ 문서 그룹 관리 (수정됨)

### 영향받지 않은 기능
- ✅ 벡터 검색 (문제 없음)
- ✅ 대화 시스템 (문제 없음)
- ✅ 사용자 인증 (문제 없음)

## 결론

**문제**: 재색인 시 `doc:group:{filename}` 키 누락으로 문서가 API에서 필터링됨

**해결**:
1. ✅ 즉시 수정: `rebuild_doc_group_mappings.py` 스크립트로 매핑 복구
2. ✅ 영구 수정: 재색인 프로세스에 자동 매핑 재구축 통합

**결과**: 44개 문서 모두 정상 표시, 향후 재색인 시 자동 해결

---

**작성일**: 2026-01-10
**작성자**: Claude (Assistant)
**관련 이슈**: 재색인 후 문서 표시 안 됨
