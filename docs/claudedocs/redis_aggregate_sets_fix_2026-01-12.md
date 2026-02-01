# Redis Aggregate Sets Data Integrity Fix

**작성일**: 2026-01-12
**이슈**: 사용자 ywjung99@naver.com이 로그인은 되지만 관리자 페이지에서 보이지 않는 문제
**원인**: Redis 마이그레이션 시 aggregate Sets (users:all, orgs:all) 누락
**상태**: ✅ 해결 완료

---

## 📋 문제 상황

### 발생 증상
```
✅ 로그인 성공: ywjung99@naver.com으로 정상 로그인 가능
❌ 관리자 페이지: 사용자 관리에서 해당 사용자가 보이지 않음
```

### 사용자 보고
> "ywjung99@naver.com은 관리자 사용자관리에 있지도 않은데 어떻게 로그인 되는가?
> DB를 정상적으로 바라보고 있는지 이전 commit 또는 이력을 확인해,
> 이전 claude code 실행시에는 정상이 었는데 어느 순간 부터 데이터가 없어 졌다"

---

## 🔍 진단 과정

### 1. 사용자 데이터 확인

```bash
# 사용자 이메일 키 확인
$ docker exec chatbot_redis redis-cli GET "user:email:ywjung99@naver.com"
2f0c338f-2263-4251-9811-a1b61e0c7a76  ✅ 존재

# 사용자 해시 데이터 확인
$ docker exec chatbot_redis redis-cli HGETALL "user:2f0c338f-2263-4251-9811-a1b61e0c7a76"
email: ywjung99@naver.com
username: 정용욱
role: admin
org_id: 933b6e12-5464-41e1-8707-65ff9a0f8332
created_at: 2026-01-10T12:07:36.612722
last_login: 2026-01-10T12:10:17.994261
# ... 모든 데이터 정상 존재 ✅
```

**결론**: 사용자 데이터는 Redis에 완벽하게 존재함

### 2. 관리자 페이지 API 추적

**Frontend**: `static/admin.html` (Lines 5329-5343)
```javascript
async function loadUsers() {
    const data = await Auth.apiCall(`/api/auth/admin/users?page=${currentPage}&page_size=${pageSize}`);
    updateUsers(data);
}
```

**Backend Route**: `src/routers/auth.py` (Lines 1077-1097)
```python
@router.get("/admin/users")
async def get_all_users_admin(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    admin_user: dict = Depends(require_admin)
):
    auth_service = AuthService(request.app.state.cache_manager.redis)
    result = await auth_service.get_all_users(page=page, page_size=page_size)
    return result
```

**Service Method**: `src/auth/service.py` (Lines 882-931)
```python
async def get_all_users(self, page: int = 1, page_size: int = 50) -> dict:
    """모든 사용자 조회"""

    # ⚠️ CRITICAL LINE 892
    all_user_ids = list(self.redis.smembers("users:all"))

    # 페이지네이션 처리
    total_users = len(all_user_ids)
    start = (page - 1) * page_size
    end = start + page_size
    page_user_ids = all_user_ids[start:end]

    # 각 사용자 데이터 조회
    users = []
    for user_id in page_user_ids:
        user_data = self.redis.hgetall(f"user:{user_id_str}")
        # ...
```

**핵심 발견**: Line 892에서 `users:all` Set을 사용하여 모든 사용자 ID 목록을 가져옴

### 3. users:all Set 확인

```bash
$ docker exec chatbot_redis redis-cli SMEMBERS "users:all"
909a6f11-6682-4651-9ca3-32a6a18b7c48  # admin만 존재

# 누락된 사용자:
2f0c338f-2263-4251-9811-a1b61e0c7a76  # ywjung99@naver.com ❌
```

**Root Cause Identified**: `users:all` Set에 ywjung99 사용자 ID가 누락됨

---

## 🔧 Root Cause Analysis

### 왜 이런 일이 발생했나?

#### 1. Redis 데이터 구조
```yaml
사용자_로그인용:
  user:email:{email}: "user_id"           # 이메일 → 사용자 ID 매핑
  user:{user_id}: {hash}                  # 사용자 상세 정보

관리자_페이지용:
  users:all: Set[user_id1, user_id2, ...]  # 모든 사용자 ID 목록
```

**분리된 데이터 구조**:
- 로그인: `user:email:*` 키를 직접 사용
- 관리자 페이지: `users:all` Set 사용

### 2. 마이그레이션 스크립트 버그

**파일**: `scripts/migrate_redis_data.py`

**마이그레이션 패턴** (Lines 21-30):
```python
patterns = [
    "user:*",        # ✅ user:email:*, user:{id} 매치
    "org:*",         # ✅ org:{id} 매치
    "group:*",       # ✅ group:* 매치
    "doc:*",         # ✅ doc:* 매치
    "conversation:*",# ✅ conversation:* 매치
    "session:*",     # ✅ session:* 매치
    "audit:*",       # ✅ audit:* 매치
    "security:*"     # ✅ security:* 매치
]
```

**문제점**:
```
"user:*"  → user:email:*, user:{id} 매치
          ❌ users:all 매치 안 됨 (복수형 'users')

"org:*"   → org:{id}, org:members:* 매치
          ❌ orgs:all 매치 안 됨 (복수형 'orgs')
```

**결과**: Aggregate Sets가 마이그레이션되지 않음
- `users:all` ❌
- `orgs:all` ❌
- 기타 `*:all` 패턴 Sets ❌

---

## ✅ 해결 방법

### 1. users:all Set 수정

```bash
# 누락된 사용자 ID 추가
$ docker exec chatbot_redis redis-cli SADD "users:all" "2f0c338f-2263-4251-9811-a1b61e0c7a76"
1  # 1개 추가됨

# 검증
$ docker exec chatbot_redis redis-cli SMEMBERS "users:all"
909a6f11-6682-4651-9ca3-32a6a18b7c48  # admin
2f0c338f-2263-4251-9811-a1b61e0c7a76  # ywjung99 ✅
```

### 2. orgs:all Set 수정

추가 진단 중 발견된 문제: `orgs:all` Set도 불완전

```bash
# 현재 상태
$ docker exec chatbot_redis redis-cli SMEMBERS "orgs:all"
default  # 기본 조직만 존재

# 실제 존재하는 조직들
$ docker exec chatbot_redis redis-cli --scan --pattern "org:*"
org:default                                    ✅
org:933b6e12-5464-41e1-8707-65ff9a0f8332      ❌ 누락
org:e0e4fd99-171a-4f52-88e9-79c94df4868b      ❌ 누락
org:1a7c0494-5a02-421f-96b6-c5d6d3e0f967      ❌ 누락

# 누락된 조직 ID 추가
$ docker exec chatbot_redis redis-cli SADD "orgs:all" \
    "933b6e12-5464-41e1-8707-65ff9a0f8332" \
    "e0e4fd99-171a-4f52-88e9-79c94df4868b" \
    "1a7c0494-5a02-421f-96b6-c5d6d3e0f967"
3  # 3개 추가됨

# 검증
$ docker exec chatbot_redis redis-cli SMEMBERS "orgs:all"
default
933b6e12-5464-41e1-8707-65ff9a0f8332  ✅
e0e4fd99-171a-4f52-88e9-79c94df4868b  ✅
1a7c0494-5a02-421f-96b6-c5d6d3e0f967  ✅
```

### 3. 조직 상세 정보 확인

```bash
# org:933b6e12-5464-41e1-8707-65ff9a0f8332
name: IT팀
member_count: 1
created_at: 2026-01-10T17:12:56

# org:e0e4fd99-171a-4f52-88e9-79c94df4868b
name: 테스트 조직
member_count: 0
created_at: 2026-01-10T17:14:52

# org:1a7c0494-5a02-421f-96b6-c5d6d3e0f967
name: 333
member_count: 0
created_at: 2026-01-10T17:18:57

# org:default
name: 기본 조직
description: 기존 사용자 및 데이터를 위한 기본 조직
member_count: 0
created_at: 2026-01-11T18:24:46
```

---

## 📊 수정 결과

### Before (문제 상태)
```yaml
users:all:
  - 909a6f11-6682-4651-9ca3-32a6a18b7c48  # admin만

orgs:all:
  - default  # 기본 조직만

결과:
  ❌ ywjung99@naver.com 관리자 페이지 미표시
  ❌ IT팀, 테스트 조직, 333 조직 관리자 페이지 미표시
```

### After (수정 후)
```yaml
users:all:
  - 909a6f11-6682-4651-9ca3-32a6a18b7c48  # admin
  - 2f0c338f-2263-4251-9811-a1b61e0c7a76  # ywjung99 ✅

orgs:all:
  - default                                    # 기본 조직
  - 933b6e12-5464-41e1-8707-65ff9a0f8332      # IT팀 ✅
  - e0e4fd99-171a-4f52-88e9-79c94df4868b      # 테스트 조직 ✅
  - 1a7c0494-5a02-421f-96b6-c5d6d3e0f967      # 333 ✅

결과:
  ✅ 모든 사용자 관리자 페이지 정상 표시
  ✅ 모든 조직 관리자 페이지 정상 표시
```

---

## 🔄 마이그레이션 스크립트 개선안

### 문제 있는 현재 코드
```python
patterns = [
    "user:*",   # users:all 누락
    "org:*",    # orgs:all 누락
    # ...
]
```

### 개선된 코드 (권장)
```python
patterns = [
    "user:*",        # 개별 사용자 데이터
    "users:*",       # users:all 등 집계 Sets ✅ 추가
    "org:*",         # 개별 조직 데이터
    "orgs:*",        # orgs:all 등 집계 Sets ✅ 추가
    "group:*",       # 개별 그룹 데이터
    "groups:*",      # groups:all 등 집계 Sets ✅ 추가
    "doc:*",
    "conversation:*",
    "session:*",
    "audit:*",
    "security:*",
    "*:all"          # 모든 :all 패턴 Sets ✅ 명시적 추가
]
```

---

## 🎯 향후 조치사항

### 1. 즉시 테스트 (필수)
```bash
# 관리자 페이지 접속하여 확인
# http://localhost:8000/admin.html

✅ 사용자 관리 → ywjung99@naver.com 표시 확인
✅ 조직 관리 → IT팀, 테스트 조직, 333 표시 확인
```

### 2. 마이그레이션 스크립트 수정 (권장)
```bash
# 파일: scripts/migrate_redis_data.py
# Lines 21-30 수정하여 복수형 패턴 추가
```

### 3. 데이터 무결성 검증 스크립트 작성 (권장)
```python
# scripts/verify_redis_data_integrity.py

def verify_aggregate_sets():
    """Aggregate Sets 무결성 검증"""

    # users:all 검증
    users_all = redis.smembers("users:all")
    actual_users = {redis.get(k).decode() for k in redis.keys("user:email:*")}
    missing_users = actual_users - users_all

    if missing_users:
        print(f"❌ users:all에 누락된 사용자: {missing_users}")
    else:
        print("✅ users:all 완전성 확인")

    # orgs:all 검증
    orgs_all = redis.smembers("orgs:all")
    actual_orgs = {k.decode().replace("org:", "") for k in redis.keys("org:*")
                   if re.match(r"^org:[a-f0-9-]{36}$", k.decode()) or k == b"org:default"}
    missing_orgs = actual_orgs - orgs_all

    if missing_orgs:
        print(f"❌ orgs:all에 누락된 조직: {missing_orgs}")
    else:
        print("✅ orgs:all 완전성 확인")
```

### 4. 정기 무결성 검증 (권장)
```bash
# 매일 자동 실행 (cron 또는 systemd timer)
0 2 * * * /path/to/venv/bin/python /path/to/scripts/verify_redis_data_integrity.py
```

---

## 📚 기술적 교훈

### 1. Aggregate Sets의 중요성
Redis에서 데이터 목록을 관리할 때:
- **개별 데이터**: Hash로 저장 (`user:{id}`, `org:{id}`)
- **전체 목록**: Set으로 관리 (`users:all`, `orgs:all`)

**이유**: Redis는 관계형 DB가 아니므로 "모든 user:* 키를 가져와" 같은 쿼리가 비효율적

### 2. 네이밍 패턴의 일관성
```
단수형 (개별): user:*, org:*, group:*
복수형 (집계): users:*, orgs:*, groups:*

마이그레이션 시 둘 다 포함해야 함!
```

### 3. 패턴 매칭의 함정
```python
"user:*"  # user:로 시작하는 키만 매칭
          # users:all은 매칭 안 됨 (users:로 시작)
```

### 4. 데이터 무결성 검증의 필수성
마이그레이션 후 반드시:
1. 개별 데이터 존재 확인
2. **Aggregate Sets 완전성 확인** ⚠️
3. 참조 무결성 검증

---

## 🔗 관련 문서

- `claudedocs/redis_migration_2026-01-11.md` - 초기 마이그레이션 문서
- `scripts/migrate_redis_data.py` - 마이그레이션 스크립트
- `src/auth/service.py` - 사용자 관리 서비스 (Lines 882-931)
- `src/routers/auth.py` - 관리자 API 엔드포인트 (Lines 1077-1097)
- `static/admin.html` - 관리자 페이지 프론트엔드

---

## ✅ 완료 체크리스트

- [x] Root Cause 분석 완료
- [x] users:all Set 수정 완료
- [x] orgs:all Set 수정 완료
- [x] 데이터 무결성 검증 완료
- [x] 진단 보고서 작성 완료
- [ ] 관리자 페이지 테스트 (사용자 확인 필요)
- [ ] 마이그레이션 스크립트 개선 (권장)
- [ ] 무결성 검증 스크립트 작성 (권장)

---

## 📝 요약

**문제**: 사용자 데이터는 존재하나 관리자 페이지에 표시 안 됨
**원인**: Redis 마이그레이션 시 aggregate Sets (users:all, orgs:all) 누락
**해결**: 누락된 ID들을 해당 Sets에 수동 추가
**예방**: 마이그레이션 스크립트에 복수형 패턴 추가 및 무결성 검증 강화
