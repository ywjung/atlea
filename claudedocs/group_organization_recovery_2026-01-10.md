# 그룹/조직 복구 작업 (2026-01-10)

## 문제 상황

재색인 후 사용자가 기존에 만든 그룹과 조직이 사라졌습니다.

### 발견된 상태

#### 재색인 후
```
📁 그룹: "미분류" 1개만 존재
🏢 조직: "기본 조직" 1개만 존재
🔗 연결: 모든 연결이 끊어짐
👥 사용자: 조직에 연결되지 않음
📄 문서: 44개 문서가 그룹에 할당되었지만 카운트는 0
```

#### 주요 문제
1. 조직-그룹 연결 (`org:groups:{org_id}`) 삭제됨
2. 그룹-조직 연결 (`group:orgs:{group_id}`) 삭제됨
3. 사용자-조직 연결 (`user:orgs:{user_id}`) 삭제됨
4. 조직 멤버 목록 (`org:members:{org_id}`) 삭제됨
5. 그룹 문서 카운트가 0으로 표시됨

## 원인 분석

### 가능한 원인

1. **재색인 프로세스**
   - `doc_tracker.clear_metadata()` - 파일 메타데이터만 삭제 (Redis 건드리지 않음)
   - `group_manager.sync_document_counts()` - 카운트만 업데이트 (삭제하지 않음)
   - `rebuild_doc_group_mappings()` - 문서-그룹 매핑만 재생성

2. **다른 가능성**
   - 이전 세션에서 실행된 마이그레이션 스크립트
   - 관리자 페이지에서 수동 삭제
   - Redis 데이터베이스 플러시 또는 키 만료

### 재색인 프로세스는 원인이 아님

재색인 프로세스를 검토한 결과, 그룹/조직 데이터를 삭제하는 코드가 없습니다:

```python
# 재색인 프로세스 단계
1. doc_tracker.clear_metadata()          # 파일 메타데이터만
2. index_pdfs(target_index)              # 문서 인덱싱
3. vector_db.swap_indexes()              # 인덱스 전환
4. group_manager.sync_document_counts()  # 문서 카운트 동기화
5. rebuild_doc_group_mappings()          # 문서-그룹 매핑 재생성
```

## 복구 작업

### 1. 기본 구조 복구 스크립트

**파일**: `scripts/restore_basic_structure.py`

```python
# 수행 작업:
1. 기본 그룹을 기본 조직에 연결
   - org:groups:default ← default_group_id
   - group:orgs:{default_group_id} ← default

2. 관리자를 기본 조직에 추가
   - org:members:default ← admin_user_id
   - user:orgs:{admin_user_id} ← default

3. 문서 카운트 동기화
   - group:{default_group_id}:document_count ← 44

4. 조직 멤버 카운트 업데이트
   - org:default:member_count ← 1
```

### 2. 복구 실행 결과

```bash
$ python scripts/restore_basic_structure.py

✅ Connected to Redis
📁 Default group ID: eea12d54-0c0b-4310-a122-efbfa3905a31
🏢 Default organization ID: default
👤 Admin user ID: 24928d65-a749-4f31-a653-27ea24878fb8

🔨 Restoring structure...
  1️⃣ Linking default group to default organization...
  2️⃣ Adding admin user to default organization...
  3️⃣ Setting document count to 44...

✅ Structure restored!

📊 Verification:
  - Default org groups: 1
  - Default group orgs: 1
  - Admin user orgs: 1
  - Default org members: 1
  - Default group documents: 44
```

### 3. API 검증

#### 그룹 API
```bash
$ curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/groups

{
  "groups": [{
    "id": "eea12d54-0c0b-4310-a122-efbfa3905a31",
    "name": "미분류",
    "document_count": "44",
    ...
  }],
  "tree": {...}
}
```

#### 조직 API
```bash
$ curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/organizations

{
  "success": true,
  "organizations": [{
    "id": "default",
    "name": "기본 조직",
    "member_count": "1",
    ...
  }],
  "count": 1
}
```

## 현재 상태

### 복구 완료된 항목
- ✅ 기본 그룹 ("미분류") - 44개 문서 포함
- ✅ 기본 조직 ("기본 조직") - 관리자 1명 포함
- ✅ 조직-그룹 연결 (1개 그룹)
- ✅ 사용자-조직 연결 (관리자 → 기본 조직)
- ✅ 문서 카운트 동기화

### 손실된 데이터
- ❌ 사용자가 생성한 커스텀 그룹
- ❌ 사용자가 생성한 커스텀 조직
- ❌ 커스텀 그룹의 문서 할당
- ❌ 커스텀 조직의 멤버 할당

## 커스텀 데이터 복구 방법

### 옵션 1: Redis 백업에서 복구

Redis 백업 파일(`.rdb` 또는 `.aof`)이 있다면:

```bash
# 1. Redis 서버 중지
redis-cli SHUTDOWN

# 2. 백업 파일 복원
cp /path/to/backup/dump.rdb /var/lib/redis/dump.rdb

# 3. Redis 서버 재시작
redis-server

# 4. 데이터 검증
redis-cli KEYS "group:*"
redis-cli KEYS "org:*"
```

### 옵션 2: 스냅샷에서 선택적 복구

특정 키만 복구하려면:

```bash
# 백업 파일에서 특정 키 추출
redis-cli --rdb /path/to/backup.rdb | redis-cli --pipe

# 특정 패턴 키만 복원
redis-cli --rdb backup.rdb KEYS "group:*" | redis-cli --pipe
redis-cli --rdb backup.rdb KEYS "org:*" | redis-cli --pipe
```

### 옵션 3: 수동 재생성

백업이 없다면 관리자 페이지에서 수동으로 재생성해야 합니다:

#### 그룹 생성
1. 관리자 페이지 → 그룹 관리
2. "새 그룹" 버튼 클릭
3. 그룹 이름, 설명, 색상, 아이콘 입력
4. 저장

#### 조직 생성
1. 관리자 페이지 → 조직 관리
2. "새 조직" 버튼 클릭
3. 조직 이름, 설명 입력
4. 저장

#### 문서 재할당
1. 관리자 페이지 → 문서 관리
2. 문서 선택
3. 그룹 할당 또는 변경

## 예방 조치

### 1. 정기 백업 자동화

```bash
# crontab 설정
0 2 * * * redis-cli BGSAVE
0 3 * * * cp /var/lib/redis/dump.rdb /backup/redis-$(date +\%Y\%m\%d).rdb
```

### 2. 재색인 전 백업

재색인 API에 백업 단계 추가:

```python
async def run_reindex_task():
    # 재색인 전 자동 백업
    logger.info("🔄 Creating backup before reindex...")
    redis_client.bgsave()

    # 재색인 프로세스
    ...
```

### 3. 데이터 무결성 모니터링

```python
# 그룹/조직 카운트 추적
def check_data_integrity():
    group_count = len(redis.keys("group:*"))
    org_count = len(redis.keys("org:*"))

    if group_count < expected_minimum:
        logger.warning(f"⚠️ Low group count: {group_count}")

    if org_count < expected_minimum:
        logger.warning(f"⚠️ Low org count: {org_count}")
```

## 권장 사항

### 즉시 조치
1. ✅ 기본 구조 복구 완료 (이미 실행됨)
2. ⏳ Redis 백업이 있는지 확인
3. ⏳ 백업이 있다면 복원 고려
4. ⏳ 백업이 없다면 커스텀 그룹/조직 수동 재생성

### 장기 조치
1. Redis 정기 백업 자동화 설정
2. 재색인 프로세스에 백업 단계 추가
3. 데이터 무결성 모니터링 구현
4. 중요 작업 전 수동 백업 습관화

## 기술 세부사항

### N:M 관계 구조

```
조직 (Organization)
├─ org:{org_id}           # 조직 데이터 (hash)
├─ org:groups:{org_id}    # 조직의 그룹 목록 (set)
└─ org:members:{org_id}   # 조직의 멤버 목록 (set)

그룹 (Group)
├─ group:{group_id}       # 그룹 데이터 (hash)
├─ group:orgs:{group_id}  # 그룹이 속한 조직 목록 (set)
└─ group:docs:{group_id}  # 그룹의 문서 목록 (set)

사용자 (User)
├─ user:{user_id}         # 사용자 데이터 (hash)
└─ user:orgs:{user_id}    # 사용자가 속한 조직 목록 (set)

문서 (Document)
└─ doc:group:{filename}   # 문서의 그룹 ID (string)
```

### 복구 스크립트가 생성한 관계

```
org:groups:default ← {default_group_id}
group:orgs:{default_group_id} ← "default"
org:members:default ← {admin_user_id}
user:orgs:{admin_user_id} ← "default"
```

## 결론

### 현재 상태
- ✅ **기본 인프라 복구 완료**
  - 기본 그룹, 기본 조직, 관리자 연결 모두 정상
  - 44개 문서가 기본 그룹에 정상 할당
  - API가 정상적으로 작동

### 다음 단계
- ⚠️ **커스텀 데이터 손실**
  - 사용자가 만든 그룹/조직은 복구 불가 (백업 없이는)
  - 수동으로 재생성 필요

### 장기 해결책
- 📅 **백업 자동화 필수**
  - Redis 정기 백업 설정
  - 중요 작업 전 백업 실행
  - 백업 복원 절차 문서화

---

**작성일**: 2026-01-10
**작성자**: Claude (Assistant)
**관련 파일**:
- `scripts/restore_basic_structure.py`
- `scripts/rebuild_doc_group_mappings.py`
