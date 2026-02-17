# 시스템 상태 "초기화 중" 문제 수정 (2026-01-10)

## 문제 상황

사용자가 메인 챗봇 페이지(index.html)에서 시스템 상태가 계속 "초기화 중..."으로 표시되는 문제 보고.

### 증상
```
상태: 초기화 중...
문서: 0개 (청크 0개)
```

실제로는 44개 문서, 7487개 청크가 색인되어 있음.

### API 응답 확인
```bash
$ curl http://localhost:8085/api/status

{
  "status": "initializing",
  "document_count": 0,
  "chunk_count": 0,
  "pdf_count": 44,
  ...
}
```

## 원인 분석

### 1. RediSearch 모듈 미사용
시스템이 RediSearch FT.INFO 명령을 사용할 수 없는 환경:
```bash
$ redis-cli FT.INFO pdf_index_v1768031482
ERR unknown command 'FT.INFO'
```

### 2. count_documents() 메서드 문제
**파일**: `src/vector_db.py:627-633`

```python
def count_documents(self) -> int:
    """Get total number of documents (chunks) in database"""
    try:
        info = self.client.ft(self.index_name).info()  # ❌ RediSearch 필수
        return int(info.get("num_docs", 0))
    except:
        return 0  # ❌ 실패 시 무조건 0 반환
```

**문제점**:
- RediSearch 명령 실패 시 무조건 0 반환
- 대안 카운트 방법 없음
- 결과: `chunk_count: 0` → `status: "initializing"`

### 3. count_unique_files() 메서드 문제
**파일**: `src/vector_db.py:657-700`

```python
def count_unique_files(self) -> int:
    # ...
    for key in self.client.scan_iter(match="doc:*", count=batch_size):
        # ❌ 모든 인덱스를 스캔 (활성 인덱스만 필요)
```

**문제점**:
- 모든 doc:* 키를 스캔 (비효율적)
- 활성 인덱스만 카운트해야 함

## 해결 방법

### 1. count_documents() 수정

**파일**: `src/vector_db.py:627-655`

```python
def count_documents(self) -> int:
    """Get total number of documents (chunks) in database"""
    try:
        # Try RediSearch first (most efficient)
        info = self.client.ft(self.active_index_name).info()
        return int(info.get("num_docs", 0))
    except:
        # Fallback: Count keys manually if RediSearch is unavailable
        try:
            index_name = self.active_index_name
            cursor = 0
            count = 0

            while True:
                cursor, keys = self.client.scan(cursor, match=f"doc:{index_name}:*", count=100)
                # Filter out non-document keys
                for key in keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    # Skip metadata keys like doc:hash:, doc:group:, etc.
                    if not any(x in key_str for x in [':hash:', ':group:', ':version:', ':counts:', ':files']):
                        count += 1

                if cursor == 0:
                    break

            return count
        except Exception as e:
            logger.warning(f"Failed to count documents: {e}")
            return 0
```

**변경 사항**:
1. ✅ `self.index_name` → `self.active_index_name` (활성 인덱스 사용)
2. ✅ RediSearch 실패 시 SCAN 기반 대안 카운트 추가
3. ✅ 메타데이터 키 필터링 (doc:hash:, doc:group: 등 제외)

### 2. count_unique_files() 수정

**파일**: `src/vector_db.py:657-702`

```python
def count_unique_files(self) -> int:
    """
    Get total number of unique PDF files (optimized with SCAN + pipeline)
    ...
    - Scans only the active index  # ← 새로 추가
    """
    try:
        filenames = set()
        batch_size = 100
        key_batch = []

        # Get active index name
        index_name = self.active_index_name  # ← 활성 인덱스 사용

        # Scan only the active index: doc:index_name:*
        for key in self.client.scan_iter(match=f"doc:{index_name}:*", count=batch_size):
            key_str = key.decode('utf-8')

            # Skip non-document keys
            parts = key_str.split(':')
            if len(parts) < 3:
                continue
            # Skip metadata keys
            if any(x in key_str for x in [':hash:', ':group:', ':version:', ':counts:', ':files']):
                continue

            key_batch.append(key)
            # ... (배치 처리 로직)

        return len(filenames)
    except Exception as e:
        logger.error(f"Error counting unique files: {e}")
        return 0
```

**변경 사항**:
1. ✅ `match="doc:*"` → `match=f"doc:{index_name}:*"` (활성 인덱스만 스캔)
2. ✅ 메타데이터 키 필터링 로직 개선

## 검증

### 1. 서버 재시작
```bash
# 가상 환경 활성화 및 서버 재시작
source venv/bin/activate
uvicorn src.web_server:app --host 0.0.0.0 --port 8085 --reload
```

### 2. API 응답 확인
```bash
$ curl http://localhost:8085/api/status

{
  "status": "ready",  # ✅ "initializing" → "ready"
  "document_count": 7487,  # ✅ 0 → 7487
  "chunk_count": 7487,  # ✅ 0 → 7487
  "pdf_count": 44,
  "embedding_model": "daynice/kure-v1:latest",
  "llm_model": "alibayram/Qwen3-30B-A3B-Instruct-2507:latest",
  "is_reindexing": false,
  "index_state": {
    "indexed_at": "2026-01-10T16:54:02.977323",
    "total_chunks": 7487,
    "total_files": 44
  },
  "changes": {
    "needs_reindex": false,
    "total_changes": 0
  }
}
```

### 3. 프론트엔드 확인
메인 챗봇 페이지(http://localhost:8085/static/index.html):
```
상태: 준비 완료  # ✅ "초기화 중..." → "준비 완료"
문서: 44개 (청크 7487개)  # ✅ 정확한 카운트 표시
```

## 기술적 세부사항

### RediSearch vs SCAN 방식

| 방식 | 장점 | 단점 |
|------|------|------|
| **RediSearch** | - 매우 빠름 (O(1))<br>- 인덱스 메타데이터 활용 | - RediSearch 모듈 필수<br>- 모듈 미설치 시 사용 불가 |
| **SCAN** | - 추가 모듈 불필요<br>- 표준 Redis 명령<br>- 100% 호환성 | - 상대적으로 느림 (O(N))<br>- 대량 키 스캔 필요 |

### 코드 로직

1. **1차 시도**: RediSearch FT.INFO (가장 빠름)
2. **2차 시도**: SCAN 기반 수동 카운트 (대안)
3. **3차 시도**: 예외 처리 및 0 반환

이중 안전장치로 RediSearch 미설치 환경에서도 정상 작동 보장.

### 활성 인덱스 사용

```python
# Before
self.client.ft(self.index_name).info()
# 문제: self.index_name이 활성 인덱스가 아닐 수 있음

# After
self.client.ft(self.active_index_name).info()
# 해결: active_index_name 속성이 항상 Redis의 index:active 키 조회
```

**active_index_name 구현**:
```python
@property
def active_index_name(self) -> str:
    """Get the currently active index name"""
    active = self.client.get("index:active")
    if active:
        return active.decode('utf-8')
    return self.index_name  # Fallback
```

## 영향 분석

### ✅ 긍정적 영향
1. **RediSearch 선택적 사용**: 모듈이 없어도 시스템 정상 작동
2. **정확한 상태 표시**: 사용자가 시스템 준비 상태 정확히 파악
3. **향상된 호환성**: 다양한 Redis 환경에서 작동
4. **성능 최적화**: 활성 인덱스만 스캔 (불필요한 키 스캔 제거)

### ⚠️ 주의사항
1. **SCAN 성능**: 문서 수가 많을 경우 (>100k) SCAN 방식이 느릴 수 있음
   - 해결: RediSearch 모듈 설치 권장
2. **캐시 TTL**: 상태 API는 5초 캐시 사용
   - 실시간 반영까지 최대 5초 지연 가능

## 관련 파일

- **수정**: `src/vector_db.py:627-702`
- **영향**: `src/web_server.py:6029-6108` (status 엔드포인트)
- **UI**: `static/script.js:875-894` (상태 표시 로직)
- **프론트엔드**: `static/index.html` (사용자 화면)

## 사용자 경험 개선

### Before (문제 상황)
```
상태: 초기화 중...
문서: 0개 (청크 0개)
→ 사용자: "시스템이 준비되지 않았나?"
→ 질문 입력 불가능
```

### After (수정 후)
```
상태: 준비 완료
문서: 44개 (청크 7487개)
→ 사용자: 정확한 상태 파악
→ 즉시 질문 가능
```

## 결론

### 핵심 수정사항
1. ✅ RediSearch 실패 시 SCAN 기반 대안 카운트
2. ✅ 활성 인덱스만 정확하게 카운트
3. ✅ 메타데이터 키 필터링 개선

### 결과
- **시스템 상태**: "initializing" → "ready"
- **문서 카운트**: 0 → 7487 청크, 44개 파일
- **사용자 경험**: 즉시 질문 가능한 상태로 개선

---

**작성일**: 2026-01-10
**작성자**: Claude (Assistant)
**관련 이슈**: 사용자 검색 페이지 "초기화 중" 상태 고정 문제
**해결 방법**: RediSearch 대안 카운트 로직 추가 + 활성 인덱스 사용
