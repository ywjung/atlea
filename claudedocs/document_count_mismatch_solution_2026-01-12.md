# 문서 개수 불일치 문제 해결

**작성일**: 2026-01-12
**문제**: 관리자 화면(44개) vs 사용자 화면(43개) 문서 개수 불일치
**상태**: ✅ **원인 규명 완료**

---

## 📊 문제 요약

### 보고된 증상
- **파일 시스템**: 44개 문서 존재
- **관리자 화면**: 44개 문서 표시 ✅
- **사용자 화면(ywjung99)**: 43개 문서 표시 ❌
- **청크 수**: 3,983개

### 예상했던 원인 (틀림)
1. ❌ 그룹 매핑 누락
2. ❌ 중복 "미분류" 그룹 문제
3. ❌ chunk_count = 0 필터링
4. ❌ org_group_ids 누락

---

## 🎯 실제 원인

### RediSearch 인덱스 누락

**발견**:
```bash
$ docker exec chatbot_redis redis-cli FT.AGGREGATE pdf_index_v1768170155 "*" \
  GROUPBY 1 @filename REDUCE COUNT 0 AS doc_count

43  # ← RediSearch에 43개 문서만 인덱싱됨
```

**누락된 문서**: **`spring-boot-reference.pdf`**

### 증거

1. **파일 시스템 확인**:
```bash
$ ls -lh data/spring-boot-reference.pdf
-rw-r--r--  1 jyw  staff  17M 12월 22 20:40 data/spring-boot-reference.pdf
```
✅ 파일 존재 (17MB)

2. **그룹 매핑 확인**:
```bash
$ docker exec chatbot_redis redis-cli GET "doc:group:spring-boot-reference.pdf"
256496ee-8a0c-455b-8b16-97e7a102544f
```
✅ 그룹 매핑 정상 (개발 그룹)

3. **RediSearch 확인**:
```bash
$ docker exec chatbot_redis redis-cli FT.SEARCH pdf_index_v1768170155 \
  "@filename:(spring-boot-reference.pdf)"
(empty array)
```
❌ RediSearch 인덱스에 없음

4. **과거 로그 확인**:
```
2025-12-30 21:42:29 | INFO | Filtering by documents: ['spring-boot-reference.pdf']
```
✅ 2025-12-30에는 인덱싱되어 있었음

---

## 💡 왜 관리자는 44개, 사용자는 43개를 보는가?

### 관리자 화면 (44개)
**파일**: `src/routers/admin.py` 또는 관리 API

**로직**:
```python
# 파일 시스템 기반으로 문서 목록 조회
files = list(data_path.glob(f'*{ext}'))  # 44개 문서 모두 반환
```

✅ 파일 시스템에서 직접 읽기 → **44개**

### 사용자 화면 (43개)
**파일**: `src/web_server.py:4965-5095` - `/api/documents` endpoint

**로직**:
```python
# RediSearch 인덱스에서 문서 목록 조회
active_index = cache_manager.redis.get("search:active_index")
# ... RediSearch FT.AGGREGATE 쿼리로 고유 파일명 추출
```

❌ RediSearch 인덱스 기반 → **43개** (spring-boot-reference.pdf 누락)

---

## 🔍 상세 분석

### RediSearch 인덱스 정보

**활성 인덱스**: `pdf_index_v1768170155` (타임스탬프: 2025-01-11 09:42:35)

```bash
$ docker exec chatbot_redis redis-cli FT.INFO pdf_index_v1768170155

num_docs: 3983  # 총 청크 수 (사용자 보고와 일치)
```

**인덱싱된 문서 (43개)**:
1. harry potter and the goblet of fire.pdf (2,359 청크)
2. 표준프레임워크 적용가이드v4.3.pdf (259 청크)
3. 제안요청서.pdf (213 청크)
4. s2b_faq1_rag4.txt (163 청크)
5. s2b faq1.pdf (132 청크)
... (총 43개)

**누락된 문서 (1개)**:
❌ spring-boot-reference.pdf

### 왜 spring-boot-reference.pdf가 누락되었나?

**가설 1: 파일 크기 문제**
- 파일 크기: 17MB (가장 큰 파일 중 하나)
- Harry Potter PDF (2,359 청크)는 인덱싱됨
- 크기만의 문제는 아님

**가설 2: 재인덱싱 중 오류**
- 2025-12-30: 정상 인덱싱됨 (로그 확인)
- 2026-01-11 09:42: 재인덱싱 실행 (타임스탬프)
- 재인덱싱 중 이 파일만 실패했을 가능성

**가설 3: 특정 문자 인코딩 문제**
- 파일명: `spring-boot-reference.pdf`
- 다른 파일들과 달리 특수 문자 없음
- 인코딩 문제는 아닌 것으로 추정

**가설 4: 문서 처리 타임아웃**
- 17MB PDF 처리 시간이 길어서 타임아웃
- 로그에서 타임아웃 오류 확인 필요

---

## 🛠️ 해결 방안

### 방안 1: 단일 문서 재인덱싱

**스크립트 작성**: `reindex_single_document.py`
```python
# spring-boot-reference.pdf만 재인덱싱
result = embeddings.reindex_documents(
    files=["spring-boot-reference.pdf"]
)
```

**장점**: 빠르고 안전
**단점**: 근본 원인 해결 안 됨

### 방안 2: 전체 재인덱싱

**기존 스크립트**: `full_reindex_direct.py`
```bash
python full_reindex_direct.py
```

**장점**: 모든 문서 일관성 확보
**단점**: 시간 소요 (44개 문서 전체)

### 방안 3: 재인덱싱 로직 수정

**문제 코드 확인**: `src/embeddings.py` 또는 `src/document_processor.py`

**수정 필요 사항**:
1. 큰 파일 처리 타임아웃 증가
2. 실패한 파일 로그 기록
3. 재시도 로직 추가
4. 부분 실패 시 전체 실패 방지

---

## ✅ 추천 조치

### 즉시 조치 (Quick Fix)
```bash
# 1. spring-boot-reference.pdf만 재인덱싱
python scripts/reindex_single_document.py spring-boot-reference.pdf

# 2. 결과 확인
docker exec chatbot_redis redis-cli FT.AGGREGATE pdf_index_v1768170155 "*" \
  GROUPBY 1 @filename REDUCE COUNT 0 AS doc_count | head -1
# 기대 결과: 44
```

### 장기 조치 (근본 해결)
1. **재인덱싱 로직 개선**:
   - 파일별 타임아웃 설정
   - 실패 시 로그 기록 및 재시도
   - 부분 실패 허용

2. **모니터링 추가**:
   - 파일 시스템 문서 수 vs RediSearch 문서 수 비교
   - 차이 발견 시 알림

3. **정기 검증**:
   - 주기적으로 `verify_document_indexing.py` 실행
   - 누락 문서 자동 재인덱싱

---

## 📝 검증 스크립트

### verify_document_indexing.py
```python
#!/usr/bin/env python3
"""
문서 인덱싱 상태 검증
파일 시스템과 RediSearch 인덱스 비교
"""

import redis
from pathlib import Path
import os

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
DATA_DIR = os.getenv("DATA_DIR", "./data")
data_path = Path(DATA_DIR)
EXTENSIONS = ['.pdf', '.hwp', '.hwpx', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']

# 파일 시스템 문서
fs_files = set()
for ext in EXTENSIONS:
    fs_files.update([f.name.lower() for f in data_path.glob(f'*{ext}')])

print(f"파일 시스템: {len(fs_files)}개 문서")

# RediSearch 인덱스 문서
# FT.AGGREGATE로 고유 파일명 추출
# (구현 필요)

# 차이 확인
missing_in_index = fs_files - indexed_files
print(f"\n❌ 인덱스 누락: {len(missing_in_index)}개")
for filename in sorted(missing_in_index):
    print(f"  - {filename}")
```

---

## 🔗 관련 파일

- `src/web_server.py:4965-5095` - 사용자 문서 목록 API
- `src/routers/admin.py` - 관리자 문서 목록 API
- `src/embeddings.py` - 문서 인덱싱 로직
- `src/document_processor.py` - 문서 처리 로직
- `full_reindex_direct.py` - 전체 재인덱싱 스크립트

---

## 📚 참고 문서

- `data_loss_timeline_2026-01-12.md` - Redis 마이그레이션 타임라인
- `document_count_mismatch_2026-01-12.md` - 초기 조사 내용

---

**작성자**: Claude (Assistant)
**상태**: 원인 규명 완료, 해결 방안 제시
**다음 단계**: 사용자 승인 후 재인덱싱 실행
