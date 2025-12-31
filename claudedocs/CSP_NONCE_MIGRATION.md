# CSP Nonce 기반 마이그레이션 가이드

## 개요

Content Security Policy (CSP)를 `'unsafe-inline'`에서 nonce 기반으로 마이그레이션하여 보안을 강화하는 가이드입니다.

## 현재 상태

현재 CSP 설정은 `'unsafe-inline'`을 사용하고 있습니다:

```python
"script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: https://cdn.jsdelivr.net"
"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
```

### 문제점:
- **XSS 취약점**: `'unsafe-inline'`은 모든 인라인 스크립트/스타일을 허용하여 XSS 공격에 취약
- **제한적 보호**: CSP의 주요 보안 이점을 제대로 활용하지 못함

## Nonce 기반 접근방식

### 작동 원리:
1. **서버**: 각 요청마다 고유한 nonce 생성
2. **템플릿**: nonce를 인라인 스크립트/스타일에 추가
3. **CSP**: 해당 nonce가 있는 스크립트/스타일만 실행 허용

```html
<!-- 요청마다 다른 nonce -->
<script nonce="rAnd0mN0nc3V4lu3">
  console.log('This is safe');
</script>
```

```http
Content-Security-Policy: script-src 'self' 'nonce-rAnd0mN0nc3V4lu3'
```

## 마이그레이션 단계

### Phase 1: 기반 구축 ✅ (완료)

1. **CSP Nonce Middleware 생성**
   ```python
   # src/middleware/csp_nonce.py
   class CSPNonceMiddleware(BaseHTTPMiddleware):
       ...
   ```

2. **SSRF 검증기 추가**
   ```python
   # src/security_validators.py
   class SSRFValidator:
       ...
   ```

### Phase 2: 점진적 적용 (진행 예정)

1. **미들웨어 활성화**

```python
# src/web_server.py
from .middleware.csp_nonce import CSPNonceMiddleware

app.add_middleware(CSPNonceMiddleware)
```

2. **HTML 템플릿 업데이트**

기존:
```html
<script>
  const data = JSON.parse('{{ data }}');
</script>
```

변경 후:
```html
<script nonce="{{ request.state.csp_nonce }}">
  const data = JSON.parse('{{ data }}');
</script>
```

3. **CSS 업데이트**

기존:
```html
<style>
  .custom { color: red; }
</style>
```

변경 후:
```html
<style nonce="{{ request.state.csp_nonce }}">
  .custom { color: red; }
</style>
```

### Phase 3: CSP 헤더 엄격화

```python
# 현재 보안 헤더 미들웨어 수정
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    # Nonce 가져오기
    nonce = getattr(request.state, 'csp_nonce', None)

    if nonce:
        # Nonce 기반 CSP 사용
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' 'unsafe-eval' blob: https://cdn.jsdelivr.net; "
            f"style-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
            "..."
        )
    else:
        # Fallback to 기존 CSP
        response.headers["Content-Security-Policy"] = "..."
```

## 파일별 마이그레이션 체크리스트

### HTML 파일:
- [ ] static/index.html
- [ ] static/admin.html
- [ ] static/login.html
- [ ] static/register.html
- [ ] static/profile.html
- [ ] static/reset-password.html

### JavaScript 파일:
대부분의 JavaScript는 외부 파일이므로 변경 불필요:
- ✅ static/script.js (외부 파일, nonce 불필요)
- ✅ static/admin.js (외부 파일, nonce 불필요)
- ✅ static/auth.js (외부 파일, nonce 불필요)

인라인 스크립트만 nonce 추가 필요:
- [ ] 인라인 `<script>` 태그 확인
- [ ] 인라인 이벤트 핸들러 제거 (onclick, onerror 등)

## 호환성 고려사항

### CDN 리소스:
- CDN 스크립트/스타일은 integrity 해시 사용 권장
- 또는 CSP에서 특정 CDN 도메인 허용

```python
"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com"
```

### 'unsafe-eval' 필요성:
- Marked.js, Highlight.js 등 일부 라이브러리는 `eval()` 사용
- 완전 제거 전에 대체 라이브러리 검토 필요

## 테스트 계획

### 1. 개발 환경에서 테스트
```bash
# Nonce 미들웨어 활성화
# 각 페이지 기능 테스트
# 브라우저 콘솔에서 CSP 오류 확인
```

### 2. CSP Report-Only 모드
프로덕션 배포 전:
```python
response.headers["Content-Security-Policy-Report-Only"] = csp_policy
```

### 3. 모니터링
- CSP 위반 리포트 수집
- 사용자 기능 장애 모니터링

## 롤백 계획

문제 발생 시:
1. **즉시 롤백**: 미들웨어 비활성화
2. **Fallback CSP**: 기존 'unsafe-inline' 정책으로 복구
3. **분석**: 실패한 리소스/기능 파악

## 보안 이점

Nonce 기반 CSP 적용 후:
- ✅ **XSS 공격 방어 강화**: 공격자 주입 스크립트 차단
- ✅ **데이터 유출 방지**: document.cookie 등 민감 정보 접근 차단
- ✅ **공격 표면 축소**: 허용된 nonce가 있는 스크립트만 실행

## 참고 자료

- [MDN - Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [CSP Evaluator](https://csp-evaluator.withgoogle.com/)
- [OWASP CSP Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
