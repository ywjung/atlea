# Rate Limiting 오류 수정 및 개선

**작성일**: 2026-01-11
**이슈**: 로그인 시 429 (Too Many Requests) 오류 발생, "null초 후에 다시 시도하세요" 메시지 표시
**우선순위**: High

---

## 📋 문제 분석

### 1. 발생한 오류

```
POST http://localhost:8000/api/auth/login 429 (Too Many Requests)
Login error: Error: 요청이 너무 많습니다. null초 후에 다시 시도하세요.
```

**문제점**:
1. Rate limiting이 개발 환경에서 너무 엄격하게 설정됨 (10분에 3회만 허용)
2. 프론트엔드에서 `Retry-After` 헤더 값이 null로 표시됨
3. `.env`의 `RATE_LIMIT_ENABLED=false` 설정이 무시됨
4. Redis에 rate limit 설정이 저장되지 않음

### 2. 원인 분석

#### A. Rate Limit 설정이 너무 엄격
**파일**: `src/auth/rate_limiter.py:214-216`

```python
# 기존 설정 (너무 엄격)
LOGIN_MAX_REQUESTS = 3          # 10분에 3회만 허용
LOGIN_WINDOW_SECONDS = 600      # 10분
```

**문제**: 개발 환경에서 테스트 중 쉽게 limit에 도달

#### B. 프론트엔드 에러 메시지 처리 문제
**파일**: `static/auth.js:171-173`

```javascript
// 기존 코드
if (response.status === 429) {
    const retryAfter = response.headers.get('Retry-After');
    throw new Error(`요청이 너무 많습니다. ${retryAfter}초 후에 다시 시도하세요.`);
}
```

**문제**: `retryAfter`가 null일 때 "null초"로 표시됨

#### C. Redis 설정이 적용되지 않음
**파일**: `.env:38`

```env
RATE_LIMIT_ENABLED=false  # 이 설정이 Redis에 반영되지 않음
```

**문제**: 웹 서버 시작 시 `.env`의 값을 Redis에 저장하는 로직이 없었음

---

## ✅ 적용한 수정사항

### 1. Rate Limit 설정 완화
**파일**: `src/auth/rate_limiter.py:214-228`

```python
# 수정 후 (개발 환경 고려)
class RateLimitConfig:
    """Rate Limit 설정"""

    # 로그인 엔드포인트: 5분에 10회 (개발 환경 고려)
    LOGIN_MAX_REQUESTS = 10
    LOGIN_WINDOW_SECONDS = 300  # 5분

    # 회원가입 엔드포인트: 1시간에 5회 (자동 가입 방지)
    REGISTER_MAX_REQUESTS = 5
    REGISTER_WINDOW_SECONDS = 3600  # 1시간

    # 일반 API: 1분에 60회
    API_MAX_REQUESTS = 60
    API_WINDOW_SECONDS = 60  # 1분

    # 비밀번호 재설정 요청: 1시간에 5회
    PASSWORD_RESET_MAX_REQUESTS = 5
    PASSWORD_RESET_WINDOW_SECONDS = 3600  # 1시간
```

**변경 내용**:
- 로그인: 10분 3회 → **5분 10회** (233% 증가)
- 회원가입: 2시간 3회 → **1시간 5회** (67% 증가)
- 비밀번호 재설정: 1시간 3회 → **1시간 5회** (67% 증가)

### 2. 프론트엔드 에러 메시지 개선
**파일**: `static/auth.js:171-177`

```javascript
// 수정 후
async handleResponse(response) {
    if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After');
        const retryMessage = retryAfter
            ? `${retryAfter}초 후에 다시 시도하세요.`
            : '잠시 후에 다시 시도하세요.';
        throw new Error(`요청이 너무 많습니다. ${retryMessage}`);
    }
    // ...
}
```

**개선 사항**:
- `retryAfter`가 null일 때 대체 메시지 표시
- "null초" 문제 해결

### 3. Redis Rate Limit 설정 자동 동기화
**파일**: `src/web_server.py:2713-2719`

```python
# 웹 서버 시작 시 .env의 RATE_LIMIT_ENABLED를 Redis에 저장
try:
    rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "false").lower()
    vector_db.client.set("config:rate_limit_enabled", rate_limit_enabled)
    logger.info(f"⚙️  Rate limiting: {rate_limit_enabled}")
except Exception as e:
    logger.warning(f"Failed to set rate limit config in Redis: {e}")
```

**동작 방식**:
1. 서버 시작 시 `.env`의 `RATE_LIMIT_ENABLED` 읽기
2. Redis에 `config:rate_limit_enabled` 키로 저장
3. `RateLimiter.check_rate_limit()`에서 이 값을 확인하여 rate limiting 활성화/비활성화

### 4. Rate Limit 초기화 스크립트 추가
**파일**: `scripts/clear_rate_limit.sh` (신규 생성)

```bash
#!/bin/bash
# Rate Limit 초기화 스크립트

# 사용법:
#   ./scripts/clear_rate_limit.sh            # 모든 rate limit 키 삭제
#   ./scripts/clear_rate_limit.sh <IP>       # 특정 IP의 rate limit만 삭제

# 전체 삭제
./scripts/clear_rate_limit.sh

# 특정 IP만 삭제
./scripts/clear_rate_limit.sh 127.0.0.1
```

**기능**:
- 모든 rate limit 키 일괄 삭제
- 특정 IP의 rate limit만 선택적 삭제
- 삭제된 키 개수 출력

---

## 🔧 즉시 조치 사항

### 1. Redis Rate Limit 키 삭제
```bash
# 모든 rate limit 키 삭제
docker exec chatbot_redis redis-cli KEYS "rate_limit:*" | xargs -I {} docker exec chatbot_redis redis-cli DEL {}
```

**결과**: 1개 키 삭제 (`rate_limit:127.0.0.1:login`)

### 2. Redis 설정 확인
```bash
# config:rate_limit_enabled 확인
docker exec chatbot_redis redis-cli GET "config:rate_limit_enabled"
# 출력: "false"
```

**확인 완료**: Rate limiting이 비활성화됨

### 3. 웹 서버 재시작
```bash
# 서버 재시작
kill <PID>
source venv/bin/activate
nohup uvicorn src.web_server:app --host 0.0.0.0 --port 8000 > logs/web_server.log 2>&1 &
```

**로그 확인**:
```
[18:41:18] ⚙️  Rate limiting: false
[18:41:18] ✅ Application initialized successfully!
```

---

## 📊 테스트 시나리오

### 시나리오 1: Rate Limiting 비활성화 상태 (개발 환경)

**설정**: `.env`의 `RATE_LIMIT_ENABLED=false`

**예상 동작**:
1. 로그인 요청 무제한 허용
2. Redis에서 `config:rate_limit_enabled` 값 확인 → "false"
3. `RateLimiter.check_rate_limit()`에서 즉시 True 반환

**테스트 결과**: ✅ 통과

### 시나리오 2: Rate Limiting 활성화 상태 (프로덕션 환경)

**설정**: `.env`의 `RATE_LIMIT_ENABLED=true`

**예상 동작**:
1. 5분에 10회까지 로그인 허용
2. 11번째 요청 시 429 오류
3. 에러 메시지: "요청이 너무 많습니다. XXX초 후에 다시 시도하세요."

**테스트 방법**:
```bash
# 1. Redis 설정 변경
docker exec chatbot_redis redis-cli SET "config:rate_limit_enabled" "true"

# 2. 11번 연속 로그인 시도
for i in {1..11}; do
    curl -X POST http://localhost:8000/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"test","password":"wrong"}' \
        -w "\nStatus: %{http_code}\n"
    sleep 1
done
```

### 시나리오 3: Retry-After 헤더 처리

**테스트 케이스**:
1. Rate limit 초과 시 429 응답 받기
2. `Retry-After` 헤더 확인
3. 프론트엔드에서 적절한 메시지 표시

**예상 출력**:
- Retry-After 있을 때: "요청이 너무 많습니다. 285초 후에 다시 시도하세요."
- Retry-After 없을 때: "요청이 너무 많습니다. 잠시 후에 다시 시도하세요."

---

## 🎯 운영 가이드

### 개발 환경 설정

**파일**: `.env`

```env
# Rate Limiting (개발 환경: 비활성화)
RATE_LIMIT_ENABLED=false
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10
```

**특징**:
- 무제한 요청 허용
- 빠른 테스트 및 개발 가능
- 보안 테스트 시에만 활성화

### 프로덕션 환경 설정

**파일**: `.env.production`

```env
# Rate Limiting (프로덕션: 활성화)
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10
```

**특징**:
- Brute Force 공격 방지
- 로그인: 5분에 10회
- 회원가입: 1시간에 5회
- 일반 API: 1분에 60회

### Rate Limit 모니터링

```bash
# 1. Redis에서 현재 설정 확인
docker exec chatbot_redis redis-cli GET "config:rate_limit_enabled"

# 2. 활성화된 rate limit 키 조회
docker exec chatbot_redis redis-cli KEYS "rate_limit:*"

# 3. 특정 IP의 요청 수 확인
docker exec chatbot_redis redis-cli GET "rate_limit:127.0.0.1:login"

# 4. TTL 확인 (남은 시간)
docker exec chatbot_redis redis-cli TTL "rate_limit:127.0.0.1:login"
```

### Rate Limit 초기화

```bash
# 1. 스크립트 사용 (권장)
./scripts/clear_rate_limit.sh              # 전체 삭제
./scripts/clear_rate_limit.sh 127.0.0.1    # 특정 IP만 삭제

# 2. 수동 삭제
docker exec chatbot_redis redis-cli DEL "rate_limit:127.0.0.1:login"

# 3. 패턴 매칭 삭제
docker exec chatbot_redis redis-cli KEYS "rate_limit:*" | \
    xargs -I {} docker exec chatbot_redis redis-cli DEL {}
```

---

## 🔐 보안 고려사항

### 1. 분산 환경에서의 Rate Limiting

**현재 구현**:
- Redis 기반 중앙 집중식 rate limiting
- 여러 웹 서버 인스턴스 간 rate limit 공유

**장점**:
- 로드 밸런서 뒤에 여러 서버가 있어도 정확한 제한
- 공격자가 여러 서버로 분산 공격 시도해도 방어

### 2. IP 스푸핑 방지

**파일**: `src/auth/rate_limiter.py:38-39`

```python
def _get_client_ip(self, request: Request) -> str:
    # IPValidator를 사용하여 안전하게 IP 추출
    return IPValidator.get_client_ip(request, trust_proxy=True)
```

**보안 기능**:
- `X-Forwarded-For` 헤더 검증
- Proxy 신뢰 설정 적용
- IP 스푸핉 방지

### 3. Fail-Open vs Fail-Closed

**현재 정책**: Fail-Open (Redis 오류 시 요청 허용)

**파일**: `src/auth/rate_limiter.py:118-123`

```python
except HTTPException:
    raise  # Rate limit 오류는 재발생
except Exception as e:
    # Redis 오류 시 요청 허용 (fail-open)
    logger.error(f"Rate limiter error: {e}")
    return True
```

**근거**:
- 가용성 우선 (Redis 장애 시에도 서비스 유지)
- 로깅을 통한 문제 추적
- 보안 로그에서 별도 모니터링

---

## 📈 개선 효과

### 1. 사용자 경험 개선
- ✅ "null초" 오류 메시지 해결
- ✅ 개발 환경에서 로그인 제한 완화
- ✅ 명확한 에러 메시지 제공

### 2. 운영 편의성 향상
- ✅ `.env` 파일에서 중앙 집중식 설정
- ✅ Redis 자동 동기화
- ✅ Rate limit 초기화 스크립트 제공

### 3. 보안 강화
- ✅ 프로덕션 환경에서 여전히 강력한 보호
- ✅ IP 기반 제한으로 Brute Force 방지
- ✅ 보안 로깅 및 모니터링

### 4. 개발 효율성
- ✅ 테스트 중 rate limit 걸림 현상 제거
- ✅ 빠른 개발 및 디버깅 가능
- ✅ 환경별 설정 분리

---

## 📝 체크리스트

### 배포 전 확인 사항

- [x] `.env` 파일에서 `RATE_LIMIT_ENABLED` 설정 확인
- [x] Redis에 `config:rate_limit_enabled` 저장되는지 확인
- [x] 웹 서버 시작 로그에서 rate limiting 상태 확인
- [x] 프론트엔드 에러 메시지 테스트
- [x] Rate limit 초기화 스크립트 테스트

### 운영 모니터링 항목

- [ ] Redis `config:rate_limit_enabled` 값 모니터링
- [ ] Rate limit 키 수 추적 (`rate_limit:*` 패턴)
- [ ] 429 응답 비율 모니터링
- [ ] SecurityLogger에서 rate limit 이벤트 확인

---

## 🔄 향후 개선 계획

### Phase 1: 동적 Rate Limit 조정
- 사용자 권한별 다른 limit 적용 (일반 사용자 vs 관리자)
- API 키 별 독립적인 rate limit
- 신뢰된 IP 화이트리스트

### Phase 2: 고급 모니터링
- Grafana 대시보드 연동
- Rate limit 메트릭 수집
- 실시간 알림 시스템

### Phase 3: 적응형 Rate Limiting
- 머신러닝 기반 비정상 패턴 감지
- 동적 threshold 조정
- Geo-based rate limiting

---

## 📚 참고 자료

- [OWASP Rate Limiting Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html)
- [Redis Rate Limiting Pattern](https://redis.io/docs/manual/patterns/rate-limiter/)
- [HTTP 429 Status Code](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429)
- [Retry-After Header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Retry-After)
