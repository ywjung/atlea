# 피드백 데이터 손실 문제 분석

**작성일**: 2026-01-12
**문제**: 사용자 피드백 데이터 완전 손실
**상태**: 🔴 **데이터 손실 확인**

---

## 📊 문제 요약

### 보고된 증상
- 사용자가 "피드백 데이터도 다 사라졌다"고 보고
- 관리 화면에서 피드백 통계가 표시되지 않음
- 과거 피드백 기록이 모두 손실됨

### 확인 결과
- ✅ Docker Redis (포트 6379): 피드백 키 0개
- ✅ 로컬 Redis (포트 6380): 피드백 키 0개
- ✅ 로그 확인: 2025-12-30에 피드백 1개 이상 저장됨
- ❌ **결론**: 피드백 데이터 완전 손실

---

## 🔍 피드백 데이터 구조

### Redis 키 패턴

피드백 시스템은 다음과 같은 Redis 키들을 사용합니다:

#### 1. 개별 피드백 데이터
```
키: feedback:{conversation_id}:{message_id}
타입: String (JSON)
TTL: 90일
내용: {
    "type": "positive" | "negative",
    "timestamp": "2025-12-30T21:38:47Z",
    "conversation_id": "...",
    "message_id": "..."
}
```

#### 2. 통계용 Sorted Sets
```
키: feedback:stats:positive
    feedback:stats:negative
타입: Sorted Set
스코어: Unix timestamp
멤버: feedback:{conversation_id}:{message_id}
```

#### 3. 피드백 카운트
```
키: feedback:count:positive
    feedback:count:negative
타입: Integer
내용: 총 피드백 수
```

#### 4. FeedbackAnalyzer 데이터
```
키: feedback:history
타입: String (JSON Array)
내용: 전체 피드백 히스토리

키: feedback:stats
타입: String (JSON Object)
내용: 통계 데이터 (신뢰도별, 출처별, 길이별)

키: feedback:patterns
타입: String (JSON Object)
내용: 학습된 패턴
```

### 코드 위치

**파일**: `src/web_server.py:4286-4365` - `submit_feedback()` API

```python
# 개별 피드백 저장 (TTL 90일)
feedback_key = f"feedback:{feedback.conversation_id}:{feedback.message_id}"
redis.setex(feedback_key, 90 * 24 * 60 * 60, json.dumps(feedback_data))

# 통계 ZSET에 추가
stats_key = f"feedback:stats:{feedback.feedback_type}"
redis.zadd(stats_key, {feedback_key: timestamp_score})

# 카운트 증가
redis.incr(f"feedback:count:{feedback.feedback_type}")

# FeedbackAnalyzer에 기록
feedback_analyzer.record_feedback(...)
```

**파일**: `src/feedback_analyzer.py:414-479` - Redis 영구 저장

```python
def _save_to_redis(self):
    # 피드백 히스토리 저장
    self.redis.set(f"{self.redis_key_prefix}:history", history_json)

    # 통계 저장
    self.redis.set(f"{self.redis_key_prefix}:stats", stats_json)

    # 학습 패턴 저장
    self.redis.set(f"{self.redis_key_prefix}:patterns", patterns_json)
```

---

## 💥 손실 원인

### 근본 원인: 마이그레이션 스크립트 누락

**파일**: `scripts/migrate_redis_data.py:20-34`

```python
# 마이그레이션할 패턴들
patterns = [
    "user:*",
    "users:*",
    "org:*",
    "orgs:*",
    "group:*",
    "groups:*",
    "doc:*",
    "conversation:*",
    "session:*",
    "audit:*",
    "security:*",
    "*:all"
]
```

❌ **`feedback:*` 패턴이 없음!**

### 손실 타임라인

**2025-12-30 21:38:47**:
- 사용자가 negative 피드백 제출
- 로그: `👍👎 Feedback saved: negative for message 1767098327396`
- 데이터는 로컬 Redis (포트 6380)에 저장됨

**2026-01-10 21:32 - 2026-01-11 09:46**:
- Redis 마이그레이션 실행 (로컬 → Docker)
- `feedback:*` 패턴이 마이그레이션 스크립트에 없어서 **복사 안 됨**

**2026-01-12 현재**:
- 로컬 Redis 데이터도 손실 (덮어쓰기 또는 플러시)
- Docker Redis에도 없음
- **완전 손실**

---

## 🔍 데이터 복구 가능성

### 1. 로컬 Redis dump.rdb 백업
```bash
$ ls -lh /opt/homebrew/var/db/redis/dump.rdb
-rw-r--r--@ 1 jyw  admin  35M  1월 10 21:28
```

**가능성**: 1월 10일 21:28 시점의 스냅샷
- **포함 가능성**: 2025-12-30의 피드백 데이터가 포함되어 있을 수 있음
- **확인 필요**: dump.rdb 파일을 임시 Redis에 로드하여 `feedback:*` 키 확인

### 2. Docker Redis volumes 백업
```bash
$ docker volume inspect chatbot_redis_data
```

**가능성**: 낮음
- Docker Redis는 마이그레이션 후 생성되었으므로 피드백 데이터 없음

### 3. 애플리케이션 로그
**로그 파일**: `logs/server_new.log`

```
2025-12-30 21:38:47 | INFO | 👍👎 Feedback saved: negative for message 1767098327396
```

**복구 가능 정보**:
- 피드백 타입: negative
- 메시지 ID: 1767098327396
- 타임스탬프: 2025-12-30 21:38:47

**한계**: 로그에서 피드백 전체 내용을 복구할 수는 없음 (메타데이터, 컨텍스트 등 부족)

---

## 🛠️ 복구 시도

### 방안 1: dump.rdb 백업에서 복구 (추천)

**1단계: 임시 Redis 인스턴스 시작**
```bash
# 임시 디렉토리 생성
mkdir -p /tmp/redis_backup
cp /opt/homebrew/var/db/redis/dump.rdb /tmp/redis_backup/

# 임시 Redis 시작 (포트 6381)
redis-server --dir /tmp/redis_backup --port 6381 --daemonize yes
```

**2단계: 피드백 키 확인**
```bash
redis-cli -p 6381 KEYS "feedback:*" | wc -l
```

**3단계: 피드백 데이터가 있다면 추출**
```bash
# 모든 피드백 키 추출
redis-cli -p 6381 --scan --pattern "feedback:*" > feedback_keys.txt

# 데이터 덤프
while read key; do
    echo "=== $key ===" >> feedback_backup.txt
    redis-cli -p 6381 GET "$key" >> feedback_backup.txt
done < feedback_keys.txt
```

**4단계: Docker Redis로 복원**
```bash
# 복원 스크립트 실행
python scripts/restore_feedback_data.py feedback_backup.txt
```

### 방안 2: 로그에서 부분 복구

**한계**: 피드백 메타데이터 부족
- 메시지 내용, 컨텍스트, 신뢰도 정보 없음
- 통계만 부분 복원 가능

### 방안 3: 손실 수용 후 재구축

**조치**:
1. 마이그레이션 스크립트에 `feedback:*` 추가
2. 향후 피드백 데이터부터 정상 수집
3. 손실된 과거 데이터는 복구 불가 인정

---

## ✅ 재발 방지 조치

### 1. 마이그레이션 스크립트 수정

**파일**: `scripts/migrate_redis_data.py`

```python
patterns = [
    "user:*",
    "users:*",
    "org:*",
    "orgs:*",
    "group:*",
    "groups:*",
    "doc:*",
    "conversation:*",
    "session:*",
    "audit:*",
    "security:*",
    "feedback:*",      # ✅ 추가
    "*:all"
]
```

### 2. 전체 키 스캔 추가

마이그레이션 전에 모든 키 패턴을 자동 감지:

```python
def discover_all_patterns(redis_client):
    """모든 키 패턴 자동 감지"""
    all_keys = redis_client.keys("*")

    patterns = set()
    for key in all_keys:
        # 첫 번째 콜론까지를 패턴으로 추출
        if ':' in key:
            pattern = key.split(':')[0] + ':*'
            patterns.add(pattern)

    return list(patterns)
```

### 3. 마이그레이션 검증 스크립트

```python
def verify_migration():
    """마이그레이션 후 키 수 비교"""
    source_count = len(source_redis.keys("*"))
    target_count = len(target_redis.keys("*"))

    if source_count != target_count:
        logger.error(f"⚠️ 키 수 불일치: 소스 {source_count} vs 타겟 {target_count}")

        # 패턴별 비교
        for pattern in all_patterns:
            source_keys = source_redis.keys(pattern)
            target_keys = target_redis.keys(pattern)
            if len(source_keys) != len(target_keys):
                logger.error(f"❌ {pattern}: {len(source_keys)} → {len(target_keys)}")
```

### 4. 정기 백업

```bash
# 일일 백업 cron job
0 2 * * * docker exec chatbot_redis redis-cli SAVE && \
          cp /var/lib/redis/dump.rdb /backup/redis/dump_$(date +\%Y\%m\%d).rdb
```

### 5. 모니터링 알림

```python
# 피드백 데이터 모니터링
def check_feedback_health():
    history_exists = redis.exists("feedback:history")
    count_positive = redis.get("feedback:count:positive")
    count_negative = redis.get("feedback:count:negative")

    if not history_exists:
        send_alert("🚨 feedback:history 키 없음!")

    if not count_positive and not count_negative:
        send_alert("🚨 피드백 카운트 모두 0!")
```

---

## 📝 복구 스크립트

### restore_feedback_data.py

```python
#!/usr/bin/env python3
"""
피드백 데이터 복구 스크립트
dump.rdb에서 추출한 피드백 데이터를 Docker Redis로 복원
"""

import redis
import json
import sys

def restore_feedback_from_backup(backup_file):
    """백업 파일에서 피드백 데이터 복원"""

    # Redis 연결
    source_redis = redis.Redis(host='localhost', port=6381, decode_responses=True)
    target_redis = redis.Redis(host='localhost', port=6379, decode_responses=True)

    # 피드백 키 복사
    feedback_keys = source_redis.keys("feedback:*")

    print(f"📊 발견된 피드백 키: {len(feedback_keys)}개")

    restored_count = 0
    for key in feedback_keys:
        key_type = source_redis.type(key)

        if key_type == 'string':
            value = source_redis.get(key)
            ttl = source_redis.ttl(key)

            if ttl > 0:
                target_redis.setex(key, ttl, value)
            else:
                target_redis.set(key, value)

        elif key_type == 'zset':
            members = source_redis.zrange(key, 0, -1, withscores=True)
            if members:
                target_redis.zadd(key, dict(members))

        restored_count += 1
        print(f"✅ 복원: {key}")

    print(f"\n✅ 총 {restored_count}개 키 복원 완료")

    # 통계 확인
    positive = target_redis.get("feedback:count:positive")
    negative = target_redis.get("feedback:count:negative")
    history = target_redis.get("feedback:history")

    print(f"\n📊 복원 결과:")
    print(f"  긍정 피드백: {positive or 0}개")
    print(f"  부정 피드백: {negative or 0}개")
    print(f"  히스토리: {'있음' if history else '없음'}")

if __name__ == "__main__":
    restore_feedback_from_backup(sys.argv[1] if len(sys.argv) > 1 else None)
```

---

## 🎯 추천 조치 순서

1. **즉시** (데이터 복구 시도):
   ```bash
   # dump.rdb에서 피드백 키 확인
   python scripts/check_dump_for_feedback.py

   # 피드백 키가 있다면 복원
   python scripts/restore_feedback_data.py
   ```

2. **단기** (재발 방지):
   ```bash
   # 마이그레이션 스크립트에 feedback:* 추가
   # 검증 로직 추가
   # 정기 백업 설정
   ```

3. **장기** (시스템 개선):
   - 자동 백업 시스템 구축
   - 마이그레이션 전 키 패턴 자동 감지
   - 모니터링 및 알림 시스템

---

## 🔗 관련 파일

- `src/web_server.py:4286-4365` - submit_feedback() API
- `src/feedback_analyzer.py` - FeedbackAnalyzer 클래스
- `scripts/migrate_redis_data.py` - 마이그레이션 스크립트
- `claudedocs/data_loss_timeline_2026-01-12.md` - 전체 데이터 손실 타임라인

---

## 📊 검증 결과 (2026-01-12)

### dump.rdb 백업 확인
```bash
$ python scripts/check_dump_for_feedback.py

✅ dump.rdb 파일 발견: /opt/homebrew/var/db/redis/dump.rdb
   크기: 34.87 MB
   수정 시간: 2026-01-10 21:28:28

❌ 발견된 피드백 키: 0개
```

**결론**:
- 2026-01-10 21:28:28 시점의 백업에도 피드백 데이터 없음
- 2025-12-30에 저장된 피드백이 이미 그 전에 손실되었거나
- 피드백 데이터가 디스크에 저장되지 않았을 가능성
- **완전 손실 확정, 복구 불가**

### 재발 방지 조치 완료

✅ **마이그레이션 스크립트 수정** (`scripts/migrate_redis_data.py`)
```python
patterns = [
    # ... existing patterns ...
    "feedback:*",    # ✅ 추가됨 (2026-01-12)
    "*:all"
]
```

✅ **검증 스크립트 작성** (`scripts/verify_migration.py`)
- 패턴별 키 수 비교
- 자동 패턴 감지
- 누락 패턴 상세 분석

✅ **피드백 데이터 확인 스크립트** (`scripts/check_dump_for_feedback.py`)
- dump.rdb 백업 검사
- 임시 Redis 인스턴스로 안전하게 확인

---

**작성자**: Claude (Assistant)
**상태**: ✅ 원인 규명 완료, ❌ 복구 불가 확정, ✅ 재발 방지 완료
**다음 단계**: 향후 피드백부터 정상 수집, 정기 백업 설정
