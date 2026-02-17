# Docker Redis Stack 마이그레이션 (2026-01-10)

## 문제 상황

사용자가 챗봇 페이지에서 질문 시 **참고 문서(sources)**가 표시되지 않는 문제 보고.

### 증상
```javascript
// API 응답
{
  "answer": "...",
  "sources": [],  // ❌ 빈 배열
  "context": []   // ❌ 빈 배열
}
```

프론트엔드에서 참고 문서 섹션이 표시되지 않음.

## 원인 분석

### 1. Redis 모듈 확인
```bash
$ redis-cli MODULE LIST
name
vectorset
ver
1
...
```

**문제**: RediSearch 모듈이 로드되지 않음
- Homebrew Redis에는 RediSearch가 포함되지 않음
- `vectorset` 모듈만 있음 (기능 제한적)

### 2. 검색 실패 로그
```
ERROR: SEARCH: execute_command failed: unknown command 'FT.SEARCH'
```

**문제**: `FT.SEARCH` 명령을 사용할 수 없음
- 벡터 검색이 불가능
- 문서를 찾을 수 없음 → sources가 빈 배열

### 3. 코드 분석

**파일**: `src/vector_db.py:560-576`

```python
raw_results = self.client.execute_command(
    'FT.SEARCH', index_name,
    base_query,
    'PARAMS', '2', 'vec', query_bytes,
    ...
)
# ❌ FT.SEARCH 명령이 존재하지 않음
```

**결과**:
- 검색 실패 → context = []
- sources = [] → 프론트엔드에 참고 문서 표시 안 됨

## 해결 방법

### Docker Redis Stack으로 마이그레이션

Docker Redis Stack에는 다음 모듈이 포함되어 있습니다:
- **RediSearch**: 전문 검색 및 벡터 검색
- RedisJSON: JSON 데이터 지원
- RedisBloom: 확률적 데이터 구조
- RedisTimeSeries: 시계열 데이터
- RedisGears: 데이터 처리 파이프라인

### 마이그레이션 단계

#### 1. 로컬 Redis 중지
```bash
brew services stop redis
```

**결과**:
```
Successfully stopped `redis` (label: homebrew.mxcl.redis)
```

#### 2. Docker Desktop 시작
```bash
open -a Docker
# Docker가 준비될 때까지 대기
```

#### 3. Docker Redis Stack 시작
```bash
docker-compose up -d redis
```

**docker-compose.yml**:
```yaml
services:
  redis:
    image: redis/redis-stack:latest
    container_name: chatbot_redis
    ports:
      - "6379:6379"      # Redis
      - "8001:5432"      # RedisInsight UI
    volumes:
      - redis_data:/data
    environment:
      - REDIS_ARGS=--save 60 1 --loglevel warning
    restart: unless-stopped
```

#### 4. 모듈 검증
```bash
$ redis-cli MODULE LIST

# ✅ RediSearch 모듈 확인
name
search
ver
21020
path
/opt/redis-stack/lib/redisearch.so
```

#### 5. 웹 서버 재시작
```bash
# 기존 서버 중지
ps aux | grep uvicorn | grep -v grep | awk '{print $2}' | xargs kill

# 서버 시작
source venv/bin/activate
uvicorn src.web_server:app --host 0.0.0.0 --port 8085 --reload
```

#### 6. 상태 확인
```bash
$ curl http://localhost:8085/api/status

{
  "status": "ready",
  "chunk_count": 7487,  # ✅ 기존 데이터 유지
  "pdf_count": 44
}
```

## 검증

### 1. 쿼리 테스트
```bash
$ curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"운수좋은날 줄거리를 설명해줘","top_k":3}' \
  http://localhost:8085/api/query

{
  "answer": "## 운수좋은날 줄거리\n\n...",
  "sources": [
    "현진건-운수좋은날+B3356-개벽.pdf (로컬 문서)",
    "Harry Potter and the Goblet of Fire.pdf (로컬 문서)"
  ],  # ✅ 정상 반환
  "context": [
    {
      "text": "...",
      "filename": "현진건-운수좋은날+B3356-개벽.pdf",
      "score": 0.95
    },
    ...
  ]  # ✅ 3개 문서
}
```

### 2. 프론트엔드 확인

**메인 챗봇 페이지** (`http://localhost:8085/static/index.html`):

```
사용자: 운수좋은날 줄거리를 설명해줘

봇: ## 운수좋은날 줄거리
    ...

────────────────────────────
📚 참고 문서:
[현진건-운수좋은날+B3356-개벽.pdf (로컬 문서)]
[Harry Potter and the Goblet of Fire.pdf (로컬 문서)]
```

✅ **참고 문서 섹션 정상 표시**

## 코드 수정 사항

### active_index_name 사용

**파일**: `src/vector_db.py`

#### 1. search() 메서드 (line 560-576)
```python
# Before
raw_results = self.client.execute_command(
    'FT.SEARCH', self.index_name,  # ❌ 잘못된 인덱스
    ...
)

# After
index_name = self.active_index_name  # ✅ 활성 인덱스 사용
raw_results = self.client.execute_command(
    'FT.SEARCH', index_name,
    ...
)
```

#### 2. bm25_search() 메서드 (line 1215)
```python
# Before
results = self.client.ft(self.index_name).search(query)

# After
results = self.client.ft(self.active_index_name).search(query)
```

#### 3. count_documents() 메서드 (line 630-655)
```python
# Before
info = self.client.ft(self.index_name).info()

# After
info = self.client.ft(self.active_index_name).info()
# + SCAN 기반 fallback 추가 (RediSearch 없을 때 대비)
```

#### 4. count_unique_files() 메서드 (line 673-677)
```python
# Before
for key in self.client.scan_iter(match="doc:*", count=batch_size):

# After
index_name = self.active_index_name
for key in self.client.scan_iter(match=f"doc:{index_name}:*", count=batch_size):
```

## 기술적 세부사항

### Blue-Green 인덱스 시스템

시스템은 무중단 재색인을 위해 Blue-Green 인덱스를 사용합니다:

```python
# 활성 인덱스 확인
$ redis-cli GET "index:active"
"pdf_index_v1768031482"

# 인덱스 목록
$ redis-cli KEYS "pdf_index_v*"
1) "pdf_index_v1768031482"  # 현재 활성
```

**active_index_name** 속성은 항상 현재 활성 인덱스를 반환:
```python
@property
def active_index_name(self) -> str:
    """Get the currently active index name"""
    active = self.client.get("index:active")
    if active:
        return active.decode('utf-8')
    return self.index_name  # Fallback
```

### RediSearch 벡터 검색

**FT.SEARCH 명령 구조**:
```
FT.SEARCH index_name
  "@group_id:{...}=>[KNN 3 @embedding $vec AS score]"
  PARAMS 2 vec <binary_embedding>
  RETURN 6 text filename source chunk_index group_id score
  DIALECT 2
```

**기능**:
- KNN (K-Nearest Neighbors) 벡터 검색
- 그룹 필터링 (@group_id)
- 하이브리드 검색 (Vector + BM25)

## 데이터 유지 확인

### Before (Homebrew Redis)
```bash
$ redis-cli DBSIZE
(integer) 15234

$ redis-cli SMEMBERS "org:groups:default"
1) "eea12d54-0c0b-4310-a122-efbfa3905a31"
2) "256496ee-8a0c-455b-8b16-97e7a102544f"
```

### After (Docker Redis Stack)
```bash
$ redis-cli DBSIZE
(integer) 15234  # ✅ 동일

$ redis-cli SMEMBERS "org:groups:default"
1) "eea12d54-0c0b-4310-a122-efbfa3905a31"
2) "256496ee-8a0c-455b-8b16-97e7a102544f"
# ✅ 데이터 유지됨
```

**참고**: Docker volume (`redis_data`)에 기존 데이터가 저장되어 있어서 데이터가 유지되었습니다.

## RedisInsight UI

Docker Redis Stack에는 **RedisInsight** UI가 포함되어 있습니다:

**접속**: http://localhost:5432

**기능**:
- 키 브라우저
- 쿼리 실행
- 성능 모니터링
- 메모리 분석

## 영향 분석

### ✅ 긍정적 영향
1. **참고 문서 표시**: 사용자가 답변의 출처 확인 가능
2. **검색 정확도 향상**: RediSearch의 하이브리드 검색 (Vector + BM25)
3. **풍부한 기능**: RedisJSON, RedisBloom 등 추가 기능 활용 가능
4. **모니터링 도구**: RedisInsight로 데이터 및 성능 확인
5. **프로덕션 환경 준비**: Docker 기반 배포 가능

### ⚠️ 주의사항
1. **Docker 의존성**: Docker Desktop이 실행 중이어야 함
2. **리소스 사용**: Docker 컨테이너가 추가 메모리 사용
3. **포트 충돌**: 6379, 8001 포트가 이미 사용 중이면 안 됨

## 관련 파일

### 수정된 파일
- `src/vector_db.py:560-576` - search() 메서드
- `src/vector_db.py:1215` - bm25_search() 메서드
- `src/vector_db.py:630-655` - count_documents() 메서드
- `src/vector_db.py:673-677` - count_unique_files() 메서드

### 설정 파일
- `docker-compose.yml` - Redis Stack 설정

### 프론트엔드
- `static/script.js:1753-1794` - 참고 문서 표시 로직
- `static/index.html:1685-1703` - 참고 문서 모달

## 사용자 경험 개선

### Before (문제 상황)
```
사용자: 운수좋은날 줄거리를 설명해줘

봇: 제공된 문서에는 "운수좋은날"의 줄거리에 대한 정보가 포함되어 있지 않습니다.

→ 실제로는 문서가 있지만 검색 실패
→ 참고 문서 섹션 없음
→ 사용자는 출처를 알 수 없음
```

### After (수정 후)
```
사용자: 운수좋은날 줄거리를 설명해줘

봇: ## 운수좋은날 줄거리
    "운수좋은날"은 현진건이 쓴 단편 소설로...

────────────────────────────
📚 참고 문서:
[현진건-운수좋은날+B3356-개벽.pdf (로컬 문서)]

→ 정확한 답변 제공
→ 참고 문서 표시
→ 클릭 시 상세 내용 확인 가능
```

## 향후 유지보수

### Docker Redis Stack 관리

#### 시작
```bash
docker-compose up -d redis
```

#### 중지
```bash
docker-compose stop redis
```

#### 재시작
```bash
docker-compose restart redis
```

#### 로그 확인
```bash
docker-compose logs -f redis
```

#### 데이터 백업
```bash
# Redis 데이터 저장
redis-cli SAVE

# dump.rdb 파일 복사
docker cp chatbot_redis:/data/dump.rdb ./backup/
```

#### 데이터 복원
```bash
# dump.rdb 파일 복사
docker cp ./backup/dump.rdb chatbot_redis:/data/

# Redis 재시작
docker-compose restart redis
```

## 결론

### 핵심 수정사항
1. ✅ Homebrew Redis → Docker Redis Stack 마이그레이션
2. ✅ RediSearch 모듈 활성화
3. ✅ `self.index_name` → `self.active_index_name` 수정
4. ✅ 참고 문서 표시 기능 복원

### 결과
- **검색 기능**: 정상 작동 (Vector + BM25 하이브리드)
- **참고 문서**: 정상 표시 (sources 배열 반환)
- **데이터**: 모두 유지 (7487 청크, 44개 문서)
- **사용자 경험**: 크게 개선 (출처 확인 가능)

---

**작성일**: 2026-01-10
**작성자**: Claude (Assistant)
**관련 이슈**: 참고 문서 표시 기능 누락
**해결 방법**: Docker Redis Stack 마이그레이션 + RediSearch 활성화
