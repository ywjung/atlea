# Compatibility Layer

호환성 레이어는 기존 레거시 코드와 새로운 ES6 모듈 간의 다리 역할을 합니다.

## 목적

기존 페이지가 `Auth` 객체를 사용하여 작성된 경우, 호환성 레이어를 통해 코드 변경 없이 새로운 모듈 시스템을 사용할 수 있습니다.

## 사용 방법

### 1. 호환성 브리지 로드

```html
<!-- 기존 방식 -->
<script src="/static/auth.js"></script>

<!-- 새로운 방식 (호환성 레이어 사용) -->
<script type="module">
    import '/static/js/compat/auth-bridge.js';
</script>
```

### 2. 기존 코드 그대로 사용

```javascript
// 기존 코드가 그대로 동작합니다
const user = Auth.getUser();
const isAuthenticated = Auth.isAuthenticated();

Auth.showSuccess('성공!');
Auth.showError('실패!');

await Auth.login(email, password);
await Auth.logout();
```

## 지원되는 메서드

### Session 관리
- `Auth.setTokens(accessToken, refreshToken)`
- `Auth.getAccessToken()`
- `Auth.getRefreshToken()`
- `Auth.clearTokens()`
- `Auth.setUser(user)`
- `Auth.getUser()`
- `Auth.clearUser()`
- `Auth.setSessionId(sessionId)`
- `Auth.getSessionId()`
- `Auth.clearSessionId()`
- `Auth.clearAuth()`

### 인증 상태
- `Auth.isAuthenticated()`
- `Auth.isAdmin()`
- `Auth.getUserRole()`
- `Auth.getUserId()`

### 리다이렉트
- `Auth.redirectToLogin(returnUrl)`
- `Auth.redirectToHome()`
- `Auth.requireAuth()`
- `Auth.requireAdmin()`

### 로그인/로그아웃
- `Auth.login(email, password, totpToken)`
- `Auth.logout()`
- `Auth.refreshToken()`
- `Auth.validateSession()`

### 회원가입
- `Auth.register(email, username, password, captchaId, captchaAnswer)`
- `Auth.generateCaptcha(context)`

### 비밀번호 관리
- `Auth.changePassword(oldPassword, newPassword)`
- `Auth.requestPasswordReset(email)`
- `Auth.confirmPasswordReset(token, newPassword)`

### UI 피드백
- `Auth.showError(message)`
- `Auth.showSuccess(message)`
- `Auth.showInfo(message)`
- `Auth.showWarning(message)`
- `Auth.hideError()` (호환성 유지, 실제로는 자동 숨김)
- `Auth.hideSuccess()` (호환성 유지, 실제로는 자동 숨김)

### API 호출
- `Auth.apiCall(endpoint, options)`
- `Auth.post(endpoint, data)`

### 유틸리티
- `Auth.isTokenExpired(token)`

## 내부 동작

호환성 브리지는 다음과 같이 동작합니다:

```javascript
// auth-bridge.js
import * as authSession from '../auth/session.js';
import * as authLogin from '../auth/login.js';
import { showToast } from '../ui/toast.js';

window.Auth = {
    // ES6 모듈 함수를 Auth 객체 메서드로 매핑
    isAuthenticated: authSession.isAuthenticated,
    login: authLogin.login,

    // UI 메서드는 새 UI 모듈로 매핑
    showError: (msg) => showToast(msg, 'error'),
    showSuccess: (msg) => showToast(msg, 'success'),
    // ...
};
```

## 마이그레이션 경로

### 단계 1: 호환성 레이어 적용 (현재)
```html
<script type="module">
    import '/static/js/compat/auth-bridge.js';
</script>
<script>
    // 기존 코드 그대로 사용
    Auth.showSuccess('작동합니다!');
</script>
```

### 단계 2: 점진적 모듈 전환
```html
<script type="module">
    import '/static/js/compat/auth-bridge.js';
    import { showToast } from '/static/js/index.js';

    // 새 코드는 직접 모듈 사용
    showToast('새로운 방식!', 'success');

    // 기존 코드는 계속 Auth 사용
    Auth.isAuthenticated();
</script>
```

### 단계 3: 완전 전환 (목표)
```html
<script type="module">
    import {
        isAuthenticated,
        login,
        showToast
    } from '/static/js/index.js';

    // 모든 코드가 직접 모듈 사용
    if (isAuthenticated()) {
        showToast('인증됨', 'success');
    }
</script>
```

## 예제

### 로그인 페이지
```html
<!DOCTYPE html>
<html>
<head>
    <title>로그인</title>
</head>
<body>
    <form id="loginForm">
        <input type="email" id="email">
        <input type="password" id="password">
        <button type="submit">로그인</button>
    </form>

    <!-- 호환성 브리지 로드 -->
    <script type="module">
        import '/static/js/compat/auth-bridge.js';

        // 기존 코드 그대로 작동
        document.getElementById('loginForm')
            .addEventListener('submit', async (e) => {
                e.preventDefault();

                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;

                try {
                    await Auth.login(email, password);
                    Auth.showSuccess('로그인 성공!');
                    Auth.redirectToHome();
                } catch (error) {
                    Auth.showError('로그인 실패: ' + error.message);
                }
            });
    </script>
</body>
</html>
```

## 주의사항

### 1. script type="module" 필수
호환성 브리지는 ES6 모듈이므로 `type="module"` 속성이 필요합니다.

```html
<!-- ❌ 작동 안 함 -->
<script src="/static/js/compat/auth-bridge.js"></script>

<!-- ✅ 작동함 -->
<script type="module">
    import '/static/js/compat/auth-bridge.js';
</script>
```

### 2. 모듈 스코프
ES6 모듈은 자체 스코프를 가지므로, 전역 함수를 사용하려면 `window`에 할당해야 합니다.

```html
<script type="module">
    import '/static/js/compat/auth-bridge.js';

    // ❌ 전역에 자동으로 노출되지 않음
    function myFunction() { }

    // ✅ 전역에 명시적으로 노출
    window.myFunction = function() { };
</script>
```

### 3. 인라인 이벤트 핸들러
인라인 이벤트 핸들러에서 Auth 사용 시 window.Auth로 접근:

```html
<!-- ✅ 작동함 -->
<button onclick="window.Auth.logout()">로그아웃</button>

<!-- 더 나은 방법: addEventListener 사용 -->
<button id="logoutBtn">로그아웃</button>
<script type="module">
    import '/static/js/compat/auth-bridge.js';
    document.getElementById('logoutBtn')
        .addEventListener('click', () => Auth.logout());
</script>
```

## 성능 고려사항

### 장점
- ✅ 기존 코드 변경 최소화
- ✅ 점진적 마이그레이션 가능
- ✅ 새 모듈의 이점 활용 (코드 분할, 트리 쉐이킹)

### 단점
- ⚠️ 약간의 오버헤드 (래핑 레이어)
- ⚠️ 전역 Auth 객체 사용 (모듈의 이점 일부 상실)

### 권장사항
호환성 레이어는 **임시 솔루션**입니다. 가능한 빨리 직접 ES6 모듈 import로 전환하는 것이 좋습니다.

## 테스트

호환성 레이어 테스트 페이지: `/static/example-compat-bridge.html`

이 페이지에서 모든 Auth 메서드가 정상 작동하는지 확인할 수 있습니다.

## 문제 해결

### Auth is not defined
호환성 브리지가 로드되지 않았습니다. `import` 문을 확인하세요.

### Cannot use import statement outside a module
`<script>` 태그에 `type="module"` 속성을 추가하세요.

### CORS errors
로컬 파일로 열면 CORS 에러가 발생할 수 있습니다. 웹 서버를 통해 접근하세요.

## 추가 리소스

- [ES6 모듈 가이드](../README.md)
- [통합 전략](../../../docs/claudedocs/phase2-next-steps.md)
- [모듈 사용 예제](../example-modular.html)
