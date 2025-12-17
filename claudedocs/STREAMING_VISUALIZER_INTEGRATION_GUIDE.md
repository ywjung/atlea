# 스트리밍 응답 시각화 통합 가이드

> **✅ 통합 완료 (Phase 2)** - 이 기능은 현재 시스템에 완전히 통합되어 정상 작동 중입니다.
> 이 문서는 통합 방법을 설명하는 참고 자료입니다.

## 개요
`streaming-visualizer.js`와 `streaming-styles.css`가 생성되었으며, script.js에 통합되어 있습니다.

## 필요한 수정 사항

### 1. HTML에 파일 추가

**위치**: index.html의 `<head>` 섹션과 `<body>` 하단

```html
<!-- Head section에 CSS 추가 -->
<link rel="stylesheet" href="/static/streaming-styles.css">

<!-- Body 하단 script 섹션에 추가 (error-handler.js 다음) -->
<script src="/static/streaming-visualizer.js"></script>
```

### 2. script.js 시작 부분에 StreamingVisualizer 초기화 추가

**위치**: script.js 상단, ErrorHandler 초기화 다음

```javascript
// Error Handler
const errorHandler = new ErrorHandler();

// ===== 여기에 추가 =====
// Streaming Visualizer
const streamingVisualizer = new StreamingVisualizer();
```

### 3. sendMessage 함수에 스트리밍 시각화 통합

**위치**: sendMessage 함수 내부, 스트리밍 응답 처리 부분

```javascript
async function sendMessage(stream = true) {
    const question = userInput.value.trim();
    if (!question || isLoading) return;

    try {
        isLoading = true;
        sendBtn.disabled = true;
        userInput.value = '';

        // Display user message
        appendMessage(question, 'user');
        hideSuggestedQuestions();

        // Add to history
        conversationHistory.push({
            role: 'user',
            content: question
        });

        // ===== 추가: 타이핑 인디케이터 표시 =====
        const typingIndicator = streamingVisualizer.showTypingIndicator(chatContainer);

        // Fetch streaming response
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                conversation_history: conversationHistory,
                stream: stream
            }),
            signal: currentAbortController.signal
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // ===== 추가: 스트리밍 시작 시 진행 인디케이터로 전환 =====
        streamingVisualizer.showStreamingProgress(chatContainer);

        // Create assistant message container
        const assistantMessageDiv = appendMessage('', 'assistant');
        const messageContent = assistantMessageDiv.querySelector('.message-content');

        let fullAnswer = '';
        let tokenCount = 0;

        // Read streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();

            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.substring(6);

                    if (data === '[DONE]') {
                        break;
                    }

                    try {
                        const parsed = JSON.parse(data);

                        if (parsed.content) {
                            fullAnswer += parsed.content;
                            tokenCount++;

                            // ===== 추가: 토큰 카운트 업데이트 =====
                            streamingVisualizer.updateTokenCount(tokenCount);

                            // Update message content
                            messageContent.innerHTML = marked.parse(fullAnswer);

                            // Highlight code blocks
                            messageContent.querySelectorAll('pre code').forEach((block) => {
                                hljs.highlightElement(block);
                            });

                            scrollToBottom();
                        }
                    } catch (e) {
                        console.error('Failed to parse chunk:', e);
                    }
                }
            }
        }

        // ===== 추가: 완료 표시 =====
        const elapsed = (Date.now() - streamingVisualizer.startTime) / 1000;
        streamingVisualizer.showCompletion(tokenCount, elapsed);

        // Add to history
        conversationHistory.push({
            role: 'assistant',
            content: fullAnswer
        });

        // Auto-save session
        sessionManager.autoSave(conversationHistory);

    } catch (error) {
        // ===== 추가: 오류 시 시각화 숨기기 =====
        streamingVisualizer.showError('응답 생성 중 오류가 발생했습니다.');

        const errorInfo = errorHandler.handleError(error, 'sendMessage');
        errorHandler.showErrorMessage(errorInfo, errorInfo.canRetry);
        console.error('Send message error:', error);
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        currentAbortController = null;
    }
}
```

### 4. 요청 취소 시 시각화 초기화

```javascript
// If using abort functionality
function cancelRequest() {
    if (currentAbortController) {
        currentAbortController.abort();
        streamingVisualizer.reset();
        currentAbortController = null;
    }
}
```

## 전체 통합 예시

```javascript
// ===== 1. 초기화 =====
const streamingVisualizer = new StreamingVisualizer();

// ===== 2. 메시지 전송 with 스트리밍 시각화 =====
async function sendMessage(stream = true) {
    const question = userInput.value.trim();
    if (!question || isLoading) return;

    try {
        isLoading = true;
        sendBtn.disabled = true;

        // Show typing indicator
        streamingVisualizer.showTypingIndicator(chatContainer);

        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                conversation_history: conversationHistory,
                stream: stream
            })
        });

        // Switch to streaming progress
        streamingVisualizer.showStreamingProgress(chatContainer);

        let fullAnswer = '';
        let tokenCount = 0;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            // ... parse chunks ...

            if (parsed.content) {
                fullAnswer += parsed.content;
                tokenCount++;

                // Update token count
                streamingVisualizer.updateTokenCount(tokenCount);

                // Update UI...
            }
        }

        // Show completion
        const elapsed = (Date.now() - streamingVisualizer.startTime) / 1000;
        streamingVisualizer.showCompletion(tokenCount, elapsed);

    } catch (error) {
        streamingVisualizer.showError('응답 생성 중 오류가 발생했습니다.');
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
    }
}
```

## 시각화 상태

### 1. 타이핑 인디케이터 (초기 대기)
- **표시 시점**: 요청 전송 직후
- **애니메이션**: 점 3개 튕기는 애니메이션
- **메시지**: "답변 생성 중..."

### 2. 스트리밍 진행 표시
- **표시 시점**: 첫 토큰 수신 시
- **표시 내용**:
  - 생성된 토큰 수
  - 경과 시간 (실시간 업데이트)
  - 진행률 바 (예상 완료율)
- **업데이트**: 토큰 수신할 때마다

### 3. 완료 표시
- **표시 시점**: 스트리밍 완료 시
- **표시 내용**:
  - 최종 토큰 수
  - 총 소요 시간
  - 진행률 100% (녹색)
- **자동 제거**: 1.5초 후

### 4. 오류 표시
- **표시 시점**: 오류 발생 시
- **표시 내용**: 오류 메시지
- **자동 제거**: 3초 후

## 커스터마이징

### 예상 토큰 수 조정

```javascript
// streaming-visualizer.js 내부
updateProgressBar() {
    // 기본값: 350 토큰
    const avgTokens = 350;

    // 조정 예시: 더 긴 응답 예상
    const avgTokens = 500;

    const progress = Math.min((this.tokenCount / avgTokens) * 100, 95);
    progressBar.style.width = `${progress}%`;
}
```

### 업데이트 주기 변경

```javascript
// 기본: 100ms마다 업데이트
startStatsUpdate() {
    this.updateInterval = setInterval(() => {
        // Update elapsed time
    }, 100);
}

// 더 빠르게: 50ms
startStatsUpdate() {
    this.updateInterval = setInterval(() => {
        // Update elapsed time
    }, 50);
}
```

### 완료 표시 시간 변경

```javascript
// 기본: 1.5초 후 제거
showCompletion(finalTokenCount, totalTime) {
    // ... completion logic ...

    setTimeout(() => {
        this.hide();
    }, 1500); // 여기를 조정
}
```

## 통계 정보 활용

```javascript
// 현재 통계 가져오기
const stats = streamingVisualizer.getStats();
console.log('토큰 수:', stats.tokenCount);
console.log('경과 시간:', stats.elapsedTime);
console.log('초당 토큰:', stats.tokensPerSecond);
```

## 접근성 고려사항

1. **애니메이션 감소 모드**: `prefers-reduced-motion` 지원
2. **고대비 모드**: `prefers-contrast` 지원
3. **다크 모드**: `prefers-color-scheme` 지원
4. **화면 읽기**: ARIA 레이블 추가 권장

```javascript
// ARIA 레이블 추가 예시
const indicator = document.createElement('div');
indicator.setAttribute('role', 'status');
indicator.setAttribute('aria-live', 'polite');
indicator.setAttribute('aria-label', '답변 생성 중');
```

## 성능 최적화

### 1. 토큰 카운트 업데이트 최적화

```javascript
// 매 토큰마다 업데이트하지 않고 배치 처리
let updateCounter = 0;
if (parsed.content) {
    fullAnswer += parsed.content;
    tokenCount++;
    updateCounter++;

    // 10개 토큰마다만 UI 업데이트
    if (updateCounter % 10 === 0) {
        streamingVisualizer.updateTokenCount(tokenCount);
    }
}

// 마지막에 최종 업데이트
streamingVisualizer.updateTokenCount(tokenCount);
```

### 2. 메모리 관리

```javascript
// 스트리밍 완료 또는 오류 시 반드시 cleanup
finally {
    streamingVisualizer.reset();
    isLoading = false;
    sendBtn.disabled = false;
}
```

## 테스트 방법

### 1. 타이핑 인디케이터 테스트

```javascript
// 콘솔에서
const visualizer = new StreamingVisualizer();
visualizer.showTypingIndicator(document.body);
```

### 2. 스트리밍 시뮬레이션

```javascript
// 콘솔에서
const visualizer = new StreamingVisualizer();
visualizer.showStreamingProgress(document.body);

let count = 0;
const interval = setInterval(() => {
    count += 10;
    visualizer.updateTokenCount(count);

    if (count >= 200) {
        clearInterval(interval);
        visualizer.showCompletion(200, 5.2);
    }
}, 100);
```

### 3. 오류 표시 테스트

```javascript
// 콘솔에서
visualizer.showError('테스트 오류 메시지');
```

## 주의사항

1. **타이머 정리**: 컴포넌트 언마운트 시 `stopStatsUpdate()` 반드시 호출
2. **중복 인디케이터**: 동시에 여러 인디케이터 표시되지 않도록 관리
3. **메모리 누수**: 긴 대화 시 DOM 요소 정리 확인
4. **모바일 성능**: 애니메이션 과다 사용 주의

## 향후 개선

1. **예상 완료 시간**: 실시간 토큰 생성 속도 기반 예측
2. **토큰 속도 그래프**: 시간별 토큰 생성 속도 시각화
3. **사용자 설정**: 시각화 on/off 토글
4. **커스텀 테마**: 사용자 정의 색상 테마 지원
