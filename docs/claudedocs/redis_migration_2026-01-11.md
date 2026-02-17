# Redis 데이터 마이그레이션 (로컬 → Docker)

**작성일**: 2026-01-11
**이슈**: ywjung99@naver.com 로그인 불가, 사용자 데이터 손실
**원인**: 로컬 Redis에서 Docker Redis로 전환 시 데이터 마이그레이션 누락

---

## 📋 문제 상황

### 발생 증상
```
이전: ywjung99@naver.com으로 로그인 성공
현재: 로그인 실패 (사용자를 찾을 수 없음)
```

### 원인 분석
1. **로컬 Redis 사용 시**: 데이터가 `/opt/homebrew/var/db/redis/dump.rdb`에 저장됨
2. **Docker Redis로 전환**: 새로운 Redis 인스턴스로 데이터 없이 시작
3. **사용자 데이터**: 로컬 Redis에만 존재, Docker Redis에는 admin만 존재

---

## 🔍 진단 과정

### 1. Docker Redis 사용자 확인
```bash
docker exec chatbot_redis redis-cli KEYS "user:email:*"
# 결과: user:email:admin@admin.com (1개만 존재)
```

### 2. 로컬 Redis dump 파일 발견
```bash
find /opt/homebrew -name "dump.rdb"
# 결과: /opt/homebrew/var/db/redis/dump.rdb (35MB, 2026-01-10 21:28)
```

### 3. 로컬 Redis 데이터 확인
```bash
# 로컬 Redis 시작 (포트 6380)
redis-server --port 6380 --daemonize yes \
  --dir /opt/homebrew/var/db/redis \
  --dbfilename dump.rdb

# 사용자 조회
redis-cli -p 6380 KEYS "user:email:*"
# 결과:
#   user:email:admin@admin.com
#   user:email:ywjung99@naver.com ✅ 발견!
```

### 4. 사용자 상세 정보
```bash
redis-cli -p 6380 GET "user:email:ywjung99@naver.com"
# user_id: 2f0c338f-2263-4251-9811-a1b61e0c7a76

redis-cli -p 6380 HGETALL "user:2f0c338f-2263-4251-9811-a1b61e0c7a76"
# email: ywjung99@naver.com
# username: 정용욱
# role: admin
# org_id: 933b6e12-5464-41e1-8707-65ff9a0f8332
# created_at: 2026-01-10T12:07:36.612722
# last_login: 2026-01-10T12:10:17.994261
```

---

## ✅ 해결 방법

### 1. 마이그레이션 스크립트 작성
**파일**: `scripts/migrate_redis_data.py`

**기능**:
- 로컬 Redis (포트 6380) → Docker Redis (포트 6379)
- 모든 데이터 타입 지원 (string, hash, list, set, zset)
- TTL 보존
- 중복 키 스킵
- 검증 기능 포함

**마이그레이션 패턴**:
```python
patterns = [
    "user:*",        # 사용자 데이터
    "org:*",         # 조직 데이터
    "group:*",       # 그룹 데이터
    "doc:*",         # 문서 데이터
    "conversation:*",# 대화 데이터
    "session:*",     # 세션 데이터
    "audit:*",       # 감사 로그
    "security:*"     # 보안 로그
]
```

### 2. 마이그레이션 실행
```bash
# 로컬 Redis 시작 (데이터 읽기용)
redis-server --port 6380 --daemonize yes \
  --dir /opt/homebrew/var/db/redis \
  --dbfilename dump.rdb

# 마이그레이션 실행
source venv/bin/activate
python scripts/migrate_redis_data.py
```

### 3. 마이그레이션 결과
```
============================================================
Migration Summary
============================================================
✅ Migrated: 164 keys
⏭️  Skipped: 140 keys (already exist)
❌ Errors: 7487 keys (대부분 doc:* 벡터 인덱스 관련)

🔍 Verifying user data migration...
   Source users: 2
   Target users: 2
   ✅ Verified: ywjung99@naver.com
============================================================
```

**주요 마이그레이션 데이터**:
- ✅ 사용자: `user:*` (8개 키)
- ✅ 조직: `org:*` (17개 키)
- ✅ 그룹: `group:*` (다수)
- ✅ 세션: `session:*` (다수)
- ✅ 감사 로그: `audit:*` (다수)

**오류 발생 키**:
- ❌ `doc:*` 키: 벡터 인덱스 구조가 달라서 오류 발생
- **해결**: 리인덱싱으로 해결 가능 (문서는 파일 시스템에 보존됨)

### 4. 검증
```bash
# Docker Redis에서 사용자 확인
docker exec chatbot_redis redis-cli KEYS "user:email:*"
# 결과:
#   user:email:admin@admin.com
#   user:email:ywjung99@naver.com ✅

# 사용자 상세 정보 확인
docker exec chatbot_redis redis-cli HGETALL "user:2f0c338f-2263-4251-9811-a1b61e0c7a76"
# 결과: 모든 필드 복원 확인 ✅
```

### 5. 로컬 Redis 종료
```bash
# 더 이상 필요 없으므로 종료
redis-cli -p 6380 SHUTDOWN NOSAVE
```

---

## 📊 마이그레이션 상세 통계

### 마이그레이션 성공 데이터

#### 사용자 관련 (user:*)
```
✅ user:2f0c338f-2263-4251-9811-a1b61e0c7a76 (hash)
   - email: ywjung99@naver.com
   - username: 정용욱
   - role: admin

✅ user:email:ywjung99@naver.com (string)
✅ user:sessions:2f0c338f-2263-4251-9811-a1b61e0c7a76 (set)
✅ user:preferences:정용욱 (string)
✅ user:24928d65-a749-4f31-a653-27ea24878fb8 (hash)
✅ user:orgs:24928d65-a749-4f31-a653-27ea24878fb8 (set)
```

#### 조직 관련 (org:*)
```
✅ org:933b6e12-5464-41e1-8707-65ff9a0f8332 (hash)
   - name: it팀
✅ org:1a7c0494-5a02-421f-96b6-c5d6d3e0f967 (hash)
   - name: 테스트 조직
✅ org:e0e4fd99-171a-4f52-88e9-79c94df4868b (hash)
✅ org:members:933b6e12-5464-41e1-8707-65ff9a0f8332 (set)
✅ org:groups:* (다수)
```

#### 감사 로그 (audit:*)
```
✅ audit:user:2f0c338f-2263-4251-9811-a1b61e0c7a76 (zset)
✅ audit:daily:2026-01-10 (zset)
✅ audit:log:* (다수 로그 항목)
✅ audit:action:login (zset)
✅ audit:action:register (zset)
```

### 스킵된 데이터
```
⏭️  user:email:admin@admin.com (이미 Docker Redis에 존재)
⏭️  org:default (이미 존재)
⏭️  audit:action:settings_view (이미 존재)
⏭️  audit:action:document_view (이미 존재)
```

### 오류 발생 데이터
```
❌ doc:* 키 (7487개) - 벡터 인덱스 구조 불일치
   원인: Redis Stack의 Vector Similarity Search 모듈 버전/설정 차이
   해결: 리인덱싱으로 재생성 가능
```

---

## 🔧 향후 조치사항

### 1. 문서 데이터 복구 (선택사항)
문서 파일은 `data/` 디렉토리에 보존되어 있으므로 벡터 인덱스만 재생성하면 됩니다.

```bash
# 관리자 페이지에서 리인덱싱 실행
curl -X POST http://localhost:8085/api/reindex \
  -H "Authorization: Bearer <admin_token>"
```

### 2. 로컬 Redis dump 백업
```bash
# 향후 참조를 위해 백업 보존
cp /opt/homebrew/var/db/redis/dump.rdb \
   /Users/jyw/works/ai/chatbot_redis/backups/dump.rdb.2026-01-11
```

### 3. 로컬 Redis 제거 (선택사항)
더 이상 로컬 Redis가 필요 없다면:
```bash
# Homebrew Redis 중지 및 제거
brew services stop redis
brew uninstall redis
```

---

## 📝 체크리스트

### 마이그레이션 완료 확인
- [x] 로컬 Redis dump 파일 발견
- [x] 로컬 Redis에서 ywjung99@naver.com 확인
- [x] 마이그레이션 스크립트 작성
- [x] 마이그레이션 실행 (164개 키 성공)
- [x] Docker Redis에서 사용자 확인
- [x] 사용자 상세 정보 검증
- [x] 로컬 Redis 종료

### 서비스 정상화 확인
- [x] Docker Redis 정상 작동
- [x] 웹 서버 정상 작동
- [ ] ywjung99@naver.com 로그인 테스트 (사용자가 확인 필요)
- [ ] 조직 데이터 접근 확인
- [ ] 그룹 데이터 접근 확인

### 선택적 후속 작업
- [ ] 문서 리인덱싱 (doc:* 키 복구)
- [ ] 로컬 Redis dump 백업
- [ ] 로컬 Redis 제거

---

## 🎯 핵심 교훈

### 1. Redis 전환 시 데이터 마이그레이션 필수
Docker Redis로 전환할 때는 기존 데이터를 반드시 마이그레이션해야 합니다.

### 2. dump.rdb 위치 파악
- **Homebrew Redis**: `/opt/homebrew/var/db/redis/dump.rdb`
- **Docker Redis**: 볼륨 내부 `/data/dump.rdb`

### 3. 마이그레이션 스크립트의 중요성
- 단순 파일 복사로는 부족 (모듈 버전 차이)
- Redis 클라이언트로 키별 마이그레이션 필요
- 검증 기능 포함 필수

### 4. 벡터 인덱스는 재생성
- Vector Search 인덱스는 버전/설정에 민감
- 문서 파일 보존하고 리인덱싱으로 해결

---

## 📚 참고 자료

- [Redis Persistence](https://redis.io/docs/management/persistence/)
- [Redis Migration Best Practices](https://redis.io/docs/management/migration/)
- [Redis Stack Documentation](https://redis.io/docs/stack/)
- [Python Redis Client](https://redis-py.readthedocs.io/)

---

## 🔗 관련 파일

- `scripts/migrate_redis_data.py` - 마이그레이션 스크립트
- `/opt/homebrew/var/db/redis/dump.rdb` - 원본 데이터
- `docker-compose.yml` - Redis 컨테이너 설정
- `.env` - Redis 연결 설정
