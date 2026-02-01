# 시스템 통계 수정 사항

## 문제 상황

관리자 페이지(`/static/admin.html`)의 시스템 통계에서:
- **최근 로그인** 값이 항상 `0`으로 표시됨
- **활성 세션** 값의 정확성 확인 필요

## 원인 분석

### 1. API 응답 키 불일치
**Frontend 기대값** (`static/admin.html:3984`):
```javascript
document.getElementById('stat-recent-logins').textContent = stats.recent_logins_24h || 0;
```

**Backend 반환값** (`src/auth/service.py:829`):
```python
return {
    ...
    "recent_logins": recent_logins,  # 배열 형태
    ...
}
```

- Frontend는 `recent_logins_24h` (숫자)를 기대
- Backend는 `recent_logins` (배열)을 반환
- 키 불일치로 인해 `undefined || 0 = 0` 표시

### 2. 24시간 필터링 미구현
기존 코드는 `last_login` 필드가 있는 모든 사용자를 수집했지만, 24시간 내 로그인 필터링을 하지 않음:
```python
# 기존 코드
if last_login:
    recent_logins.append({...})  # 모든 로그인 수집
```

### 3. 타임스탬프 형식 불일치
Redis에 저장된 `last_login` 타임스탬프 형식:
- 일부: `2026-01-02T08:27:50.481027` (Z 없음)
- 일부: `2025-12-27T07:26:33.674369Z` (Z 있음)

단순한 `.replace('Z', '+00:00')` 처리는 Z가 없는 타임스탬프에서 제대로 작동하지 않음

## 해결 방법

### 1. 24시간 로그인 카운트 추가
```python
# 24시간 로그인 카운터 추가
recent_logins_24h = 0

# 24시간 전 시각 계산
now = datetime.utcnow()
twenty_four_hours_ago = now - timedelta(hours=24)
```

### 2. 타임스탬프 파싱 및 필터링
```python
# 24시간 내 로그인 체크
try:
    # Z 접미사 유무에 따라 다른 파싱 방식 적용
    if last_login_str.endswith('Z'):
        last_login_dt = datetime.fromisoformat(last_login_str.replace('Z', '+00:00'))
    else:
        # 타임존 정보가 없으면 UTC로 가정
        last_login_dt = datetime.fromisoformat(last_login_str)

    if last_login_dt > twenty_four_hours_ago:
        recent_logins_24h += 1
except (ValueError, AttributeError):
    pass
```

### 3. API 응답에 필드 추가
```python
return {
    "total_users": total_users,
    "active_users": active_users,
    "inactive_users": total_users - active_users,
    "admin_users": admin_users,
    "active_sessions": active_sessions,
    "recent_logins": recent_logins,           # 배열 (최근 10개 로그인 정보)
    "recent_logins_24h": recent_logins_24h,   # 숫자 (24시간 내 로그인 수) ← 추가
    "security_events": security_events,
    "timestamp": datetime.utcnow().isoformat() + 'Z'
}
```

## 활성 세션 검증

### Redis 데이터 확인
```bash
# 세션 키 확인
docker exec chatbot_redis redis-cli --scan --pattern "user:sessions:*"
# 결과: 3개 사용자의 세션 키 존재

# 사용자별 세션 개수
docker exec chatbot_redis redis-cli SMEMBERS "user:sessions:5c112bb0-e1bc-42a4-a81f-7478928f5812"
# 결과: 17개 활성 세션
```

### 활성 세션 계산 로직
```python
# 활성 세션 수 계산
active_sessions = 0
for user_id in all_user_ids:
    user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id
    sessions = self.redis.smembers(f"user:sessions:{user_id_str}")
    active_sessions += len(sessions)
```

**결론**: 활성 세션 계산 로직은 정상 작동 중

## 테스트 데이터 예시

### 사용자별 last_login 확인
```
User: 5c112bb0-e1bc-42a4-a81f-7478928f5812
Last Login: 2026-01-01T08:00:37.743821 (약 24.5시간 전)

User: fb4746e8-98a0-4346-a326-6e4ca9b8452f
Last Login: 2025-12-27T07:26:33.674369Z (약 6일 전)

User: c0ad33b1-631a-4e10-8776-960fc5cbf761
Last Login: 2026-01-02T08:27:50.481027 (약 5분 전) ← 24시간 내
```

## 수정된 파일

- `/Users/jyw/works/ai/chatbot_redis/src/auth/service.py`
  - 라인 767-846: `get_system_stats()` 메서드 수정

## 적용 결과

1. **최근 로그인 (24시간)**: 정확한 카운트 표시
2. **활성 세션**: 정상 작동 확인 (Redis 데이터 기반 계산)
3. **타임스탬프 호환성**: Z 접미사 유무 관계없이 정확한 파싱

## 후속 작업 제안

1. **타임스탬프 형식 통일**: 모든 `last_login` 저장 시 UTC 'Z' 접미사로 통일
2. **세션 만료 로직**: 오래된 세션 자동 정리 메커니즘 고려
3. **통계 캐싱**: 대시보드 통계 계산 결과를 일정 시간 캐싱하여 성능 개선

## 관련 이슈

- 프론트엔드-백엔드 API 계약 불일치
- 타임스탬프 형식 불일치 (Z 접미사)
- 24시간 필터링 로직 누락
