# 오류 처리 통합 가이드

## 개요
`error-handler.js`와 `error-styles.css`가 생성되었으며, script.js에 통합이 필요합니다.

## 필요한 수정 사항

### 1. HTML에 파일 추가

**위치**: index.html의 `<head>` 섹션과 `<body>` 하단

```html
<!-- Head section에 CSS 추가 -->
<link rel="stylesheet" href="/static/error-styles.css">

<!-- Body 하단 script 섹션에 추가 (session-manager.js 다음) -->
<script src="/static/error-handler.js"></script>
```

### 2. script.js 시작 부분에 ErrorHandler 초기화 추가

**위치**: script.js 상단, SessionManager 초기화 다음

```javascript
// Session Manager
const sessionManager = new SessionManager();

// ===== 여기에 추가 =====
// Error Handler
const errorHandler = new ErrorHandler();

// Last request for retry functionality
let lastRequest = null;

// Global retry function
window.retryLastRequest = async function() {
    if (lastRequest) {
        const { question, stream } = lastRequest;
        await sendMessage(stream);
    }
};
```

### 3. sendMessage 함수에 오류 처리 통합

**위치**: sendMessage 함수 전체 수정

```javascript
async function sendMessage(stream = true) {
    const question = userInput.value.trim();
    if (!question || isLoading) return;

    // Save last request for retry
    lastRequest = { question, stream };

    try {
        // Create abort controller for cancellation
        currentAbortController = new AbortController();

        // Show loading with cancel button
        const loadingElement = errorHandler.showLoadingWithCancel(currentAbortController);

        isLoading = true;
        sendBtn.disabled = true;
        userInput.value = '';

        // ... 기존 UI 업데이트 코드 ...

        // Wrap fetch with retry and timeout
        const response = await errorHandler.withRetry(async () => {
            return await errorHandler.withTimeout(async () => {
                return await fetch('/api/chat/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        question: question,
                        conversation_history: conversationHistory,
                        stream: stream
                    }),
                    signal: currentAbortController.signal
                });
            });
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Remove loading indicator
        errorHandler.hideLoading();

        // ... 기존 스트리밍 처리 코드 ...

    } catch (error) {
        // Handle error with ErrorHandler
        const errorInfo = errorHandler.handleError(error, 'sendMessage');

        // Hide loading
        errorHandler.hideLoading();

        // Show error message with retry button if retryable
        errorHandler.showErrorMessage(errorInfo, errorInfo.canRetry);

        // Log error
        console.error('Send message error:', error);

    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        currentAbortController = null;
    }
}
```

### 4. 개별 API 호출에 오류 처리 추가

#### loadSuggestedQuestions 함수

```javascript
async function loadSuggestedQuestions() {
    try {
        const response = await errorHandler.withTimeout(async () => {
            return await fetch('/api/suggested-questions');
        }, 10000); // 10초 타임아웃

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        // ... 기존 질문 표시 코드 ...

    } catch (error) {
        const errorInfo = errorHandler.handleError(error, 'loadSuggestedQuestions');
        console.error('Failed to load suggested questions:', errorInfo.message);

        // 추천 질문 로딩 실패는 치명적이지 않으므로 조용히 실패
        // 필요시 작은 알림만 표시
    }
}
```

#### 파일 업로드 오류 처리

```javascript
uploadBtn.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file || file.type !== 'application/pdf') {
        errorHandler.showErrorMessage({
            type: 'client',
            message: 'PDF 파일만 업로드할 수 있습니다.',
            canRetry: false
        }, false);
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await errorHandler.withRetry(async () => {
            return await errorHandler.withTimeout(async () => {
                return await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
            }, 60000); // 60초 타임아웃 (파일 업로드)
        });

        if (!response.ok) {
            throw new Error(`Upload failed: ${response.status}`);
        }

        const result = await response.json();
        // ... 기존 성공 처리 코드 ...

    } catch (error) {
        const errorInfo = errorHandler.handleError(error, 'fileUpload');
        errorHandler.showErrorMessage(errorInfo, errorInfo.canRetry);
    }
});
```

## 전체 통합 예시

```javascript
// ===== 1. 초기화 =====
const errorHandler = new ErrorHandler();
let lastRequest = null;

window.retryLastRequest = async function() {
    if (lastRequest) {
        await sendMessage(lastRequest.stream);
    }
};

// ===== 2. 메시지 전송 with 오류 처리 =====
async function sendMessage(stream = true) {
    const question = userInput.value.trim();
    if (!question || isLoading) return;

    lastRequest = { question, stream };

    try {
        currentAbortController = new AbortController();
        const loadingElement = errorHandler.showLoadingWithCancel(currentAbortController);

        isLoading = true;
        sendBtn.disabled = true;
        userInput.value = '';

        const response = await errorHandler.withRetry(async () => {
            return await errorHandler.withTimeout(async () => {
                return await fetch('/api/chat/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        question: question,
                        conversation_history: conversationHistory,
                        stream: stream
                    }),
                    signal: currentAbortController.signal
                });
            });
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        errorHandler.hideLoading();

        // Process streaming response...

    } catch (error) {
        const errorInfo = errorHandler.handleError(error, 'sendMessage');
        errorHandler.hideLoading();
        errorHandler.showErrorMessage(errorInfo, errorInfo.canRetry);
        console.error('Send message error:', error);
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        currentAbortController = null;
    }
}
```

## 오류 타입별 처리

### 네트워크 오류
- **증상**: "Failed to fetch", NetworkError
- **처리**: 자동 재시도 (최대 3회), 지수 백오프
- **메시지**: "네트워크 연결에 실패했습니다. 인터넷 연결을 확인해주세요."

### 타임아웃
- **증상**: 30초 이상 응답 없음
- **처리**: 자동 재시도, 진행 상황 표시
- **메시지**: "응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."

### 서버 오류 (5xx)
- **증상**: 500, 503 등
- **처리**: 자동 재시도 (백엔드 일시적 문제)
- **메시지**: "서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요."

### 클라이언트 오류 (4xx)
- **증상**: 400, 404 등
- **처리**: 재시도 없음 (사용자 입력 문제)
- **메시지**: "요청을 처리할 수 없습니다. 입력 내용을 확인해주세요."

### 요청 취소
- **증상**: AbortError
- **처리**: 조용히 종료
- **메시지**: "요청이 취소되었습니다."

## 테스트 방법

### 1. 네트워크 오류 시뮬레이션
```javascript
// Chrome DevTools > Network > Offline 설정
// 또는 콘솔에서
fetch('/api/chat/stream', { method: 'POST' }).catch(e => console.log(e));
```

### 2. 타임아웃 테스트
```javascript
// 백엔드에서 sleep 추가
import time
time.sleep(35)  # 30초 타임아웃 초과
```

### 3. 서버 오류 테스트
```javascript
// 백엔드에서 의도적으로 500 에러 발생
raise Exception("Test server error")
```

### 4. 재시도 로직 테스트
```javascript
// 콘솔에서 재시도 카운트 확인
console.log(errorHandler.getCurrentRetryCount());
```

### 5. UI 테스트
```javascript
// 오류 메시지 표시 테스트
errorHandler.showErrorMessage({
    type: 'network',
    message: '테스트 오류 메시지',
    canRetry: true
}, true);
```

## 설정 커스터마이징

### ErrorHandler 설정 변경

```javascript
// 재시도 횟수 변경
errorHandler.maxRetries = 5;

// 타임아웃 변경
errorHandler.timeout = 60000; // 60초

// 기본 지연 시간 변경
errorHandler.baseDelay = 2000; // 2초
```

### 특정 API 호출에 다른 설정 사용

```javascript
// 파일 업로드는 더 긴 타임아웃
await errorHandler.withTimeout(
    () => fetch('/api/upload', { method: 'POST', body: formData }),
    120000 // 2분
);

// 빠른 API는 재시도 없이
try {
    const response = await fetch('/api/quick-check');
} catch (error) {
    const errorInfo = errorHandler.handleError(error);
    console.log(errorInfo.message);
}
```

## 주의사항

1. **AbortController**: 모든 fetch 호출에 signal 연결 필요
2. **메모리 누수**: 타임아웃과 인터벌 정리 필수
3. **중복 재시도**: withRetry 중첩 호출 금지
4. **사용자 경험**: 과도한 재시도는 UX 저하
5. **로그**: 프로덕션에서는 콘솔 로그 제거 고려

## 향후 개선

1. **재시도 전략**: 지수 백오프 외 다른 전략 (선형, 고정)
2. **오류 추적**: Sentry 등 오류 모니터링 통합
3. **오프라인 모드**: Service Worker로 오프라인 대응
4. **재연결 감지**: 네트워크 복구 시 자동 재시도
5. **사용자 알림**: 토스트, 스낵바 등 다양한 알림 방식
