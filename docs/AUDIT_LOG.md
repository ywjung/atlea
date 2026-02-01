# 감사 로그 (Audit Log) 사용 가이드

사용자 활동 기록 및 추적 시스템 사용 방법입니다.

## 📋 개요

감사 로그 시스템은 **모든 사용자 활동을 자동으로 기록**하여 보안, 규정 준수, 문제 해결을 지원합니다.

### 주요 기능

- ✅ **자동 추적**: 모든 API 요청 자동 기록
- ✅ **상세 정보**: 사용자, IP, 작업, 시간, 결과 저장
- ✅ **빠른 조회**: Redis 인덱싱으로 빠른 검색
- ✅ **통계 분석**: 일별/사용자별/작업별 통계
- ✅ **자동 정리**: 90일 자동 만료 (TTL)

## 🔍 추적되는 작업

### 인증
- 로그인/로그아웃
- 회원가입
- 비밀번호 변경
- 로그인 실패

### 문서 관리
- 문서 업로드
- 문서 삭제
- 문서 조회
- 문서 다운로드

### 채팅/질의
- 채팅 질문
- AI 응답

### 그룹 관리
- 그룹 생성/수정/삭제
- 문서 추가/제거

### 설정 및 관리
- 설정 조회/변경
- 사용자 관리
- 권한 변경
- 시스템 작업

## 📊 로그 데이터 구조

```json
{
  "log_id": "1703721234567:1234",
  "timestamp": 1703721234567,
  "datetime": "2025-12-27T18:30:45.123456",
  "action": "chat_query",
  "user_id": "user123",
  "username": "홍길동",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0...",
  "resource": "질문내용",
  "details": {
    "method": "POST",
    "path": "/api/chat",
    "status_code": 200,
    "duration_ms": 1234.56,
    "query_params": {}
  },
  "success": true,
  "error_message": null
}
```

## 🔌 API 사용법

### 1. 감사 로그 조회

**엔드포인트**: `GET /api/admin/audit/logs`

**권한**: 관리자 전용

**Query 파라미터**:
- `user_id`: 사용자 ID 필터
- `action`: 작업 유형 필터
- `start_date`: 시작 날짜 (YYYY-MM-DD)
- `end_date`: 종료 날짜 (YYYY-MM-DD)
- `limit`: 최대 반환 개수 (기본: 100)
- `offset`: 오프셋 (페이지네이션)

**예시**:

```bash
# 모든 로그 조회 (최근 100개)
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/logs"

# 특정 사용자의 로그
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/logs?user_id=user123&limit=50"

# 특정 작업 유형 필터
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/logs?action=login&limit=20"

# 날짜 범위 필터
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/logs?start_date=2025-12-01&end_date=2025-12-31"

# 페이지네이션
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/logs?limit=50&offset=100"
```

**응답**:

```json
{
  "logs": [
    {
      "log_id": "1703721234567:1234",
      "datetime": "2025-12-27T18:30:45",
      "action": "chat_query",
      "username": "홍길동",
      "success": true
    }
  ],
  "count": 50,
  "limit": 100,
  "offset": 0,
  "filters": {
    "user_id": null,
    "action": null,
    "start_date": null,
    "end_date": null
  }
}
```

### 2. 통계 조회

**엔드포인트**: `GET /api/admin/audit/stats`

**Query 파라미터**:
- `start_date`: 시작 날짜 (기본: 7일 전)
- `end_date`: 종료 날짜 (기본: 오늘)

**예시**:

```bash
# 최근 7일 통계
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/stats"

# 특정 기간 통계
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/stats?start_date=2025-12-01&end_date=2025-12-31"
```

**응답**:

```json
{
  "period": {
    "start": "2025-12-20",
    "end": "2025-12-27"
  },
  "summary": {
    "total_logs": 5432,
    "successful": 5234,
    "failed": 198,
    "success_rate": 96.35
  },
  "daily": {
    "2025-12-27": {
      "total": 823,
      "success": 810,
      "failed": 13,
      "action:login": 45,
      "action:chat_query": 567,
      "action:document_upload": 23
    }
  }
}
```

### 3. 사용자별 활동 조회

**엔드포인트**: `GET /api/admin/audit/user/{user_id}`

**Path 파라미터**:
- `user_id`: 사용자 ID

**Query 파라미터**:
- `limit`: 최대 반환 개수 (기본: 50)

**예시**:

```bash
# 사용자 활동 조회
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/user/user123?limit=100"
```

**응답**:

```json
{
  "user_id": "user123",
  "logs": [
    {
      "log_id": "1703721234567:1234",
      "datetime": "2025-12-27T18:30:45",
      "action": "chat_query",
      "ip_address": "192.168.1.100",
      "success": true
    }
  ],
  "count": 50
}
```

### 4. 작업 유형 목록

**엔드포인트**: `GET /api/admin/audit/actions`

**예시**:

```bash
# 사용 가능한 작업 유형 조회
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost:8000/api/admin/audit/actions"
```

**응답**:

```json
{
  "actions": [
    {"value": "login", "description": "Login"},
    {"value": "logout", "description": "Logout"},
    {"value": "chat_query", "description": "Chat Query"},
    {"value": "document_upload", "description": "Document Upload"}
  ]
}
```

## 🛠️ 프로그래밍 사용 예시

### Python

```python
import requests

# 관리자 로그인
response = requests.post("http://localhost:8000/api/auth/login", json={
    "username": "admin",
    "password": "admin_password"
})
token = response.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}

# 감사 로그 조회
response = requests.get(
    "http://localhost:8000/api/admin/audit/logs",
    headers=headers,
    params={
        "action": "login",
        "limit": 20
    }
)
logs = response.json()["logs"]

for log in logs:
    print(f"{log['datetime']} - {log['username']} - {log['action']} - {log['ip_address']}")

# 통계 조회
response = requests.get(
    "http://localhost:8000/api/admin/audit/stats",
    headers=headers
)
stats = response.json()
print(f"총 로그: {stats['summary']['total_logs']}")
print(f"성공률: {stats['summary']['success_rate']}%")
```

### JavaScript

```javascript
// 관리자 로그인
const loginResponse = await fetch('http://localhost:8000/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    username: 'admin',
    password: 'admin_password'
  })
});
const { access_token } = await loginResponse.json();

// 감사 로그 조회
const logsResponse = await fetch(
  'http://localhost:8000/api/admin/audit/logs?action=login&limit=20',
  {
    headers: { 'Authorization': `Bearer ${access_token}` }
  }
);
const { logs } = await logsResponse.json();

logs.forEach(log => {
  console.log(`${log.datetime} - ${log.username} - ${log.action} - ${log.ip_address}`);
});

// 통계 조회
const statsResponse = await fetch(
  'http://localhost:8000/api/admin/audit/stats',
  {
    headers: { 'Authorization': `Bearer ${access_token}` }
  }
);
const stats = await statsResponse.json();
console.log(`총 로그: ${stats.summary.total_logs}`);
console.log(`성공률: ${stats.summary.success_rate}%`);
```

## 📈 활용 사례

### 1. 보안 모니터링

```bash
# 로그인 실패 모니터링
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/admin/audit/logs?action=login_failed&limit=50"

# 특정 IP의 의심스러운 활동
# (IP 필터는 로그 조회 후 클라이언트에서 필터링)
```

### 2. 사용자 행동 분석

```bash
# 사용자의 활동 패턴 분석
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/admin/audit/user/user123?limit=200"

# 문서 업로드 활동 조회
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/admin/audit/logs?action=document_upload"
```

### 3. 규정 준수 보고서

```bash
# 월간 활동 보고서
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/admin/audit/stats?start_date=2025-12-01&end_date=2025-12-31"
```

### 4. 문제 해결

```bash
# 특정 시간대의 오류 조회
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/admin/audit/logs?start_date=2025-12-27&end_date=2025-12-27&limit=1000"
# 응답에서 success=false 항목 필터링
```

## ⚙️ 설정

감사 로그 시스템은 다음과 같이 설정됩니다:

**`src/web_server.py` (startup_event)**:

```python
audit_logger = AuditLogger(
    redis_client=cache_manager.redis,
    retention_days=90  # 보관 기간 (일)
)
```

**보관 기간 변경**:
- 기본값: 90일
- Redis TTL로 자동 만료
- 변경 시 `startup_event`의 `retention_days` 수정

## 🔒 보안 고려사항

1. **관리자 전용**: 모든 감사 로그 API는 관리자 권한 필요
2. **민감 정보 제외**: 비밀번호, 토큰 등은 로그에서 자동 제외
3. **IP 추적**: X-Forwarded-For 헤더 지원 (프록시 환경)
4. **자동 만료**: TTL로 오래된 로그 자동 삭제

## 📊 성능

- **저장소**: Redis (인메모리)
- **인덱싱**: 사용자별, 작업별, 일별
- **조회 속도**: O(log N) ~ O(N)
- **메모리 사용**: 로그당 ~1KB
- **예상 크기**: 1만 로그 ≈ 10MB

## 🆘 문제 해결

### 로그가 기록되지 않음

**확인**:
```bash
# AuditLogger 초기화 확인
grep "AuditLogger initialized" server.log
```

**해결**: 서버 재시작

### Redis 메모리 부족

**확인**:
```bash
redis-cli info memory
```

**해결**: retention_days 줄이거나 Redis 메모리 증설

### 조회가 느림

**원인**: 너무 많은 로그 조회

**해결**: limit 줄이거나 필터 사용

## 📝 참고

- 자세한 변경 이력: [CHANGELOG.md](CHANGELOG.md)
- API 문서: http://localhost:8000/docs (개발 모드)
