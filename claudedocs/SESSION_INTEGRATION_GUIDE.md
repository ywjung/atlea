# 세션 관리 통합 가이드

> **✅ 통합 완료 (Phase 2)** - 이 기능은 현재 시스템에 완전히 통합되어 정상 작동 중입니다.
> 이 문서는 통합 방법을 설명하는 참고 자료입니다.

## 개요
`session-manager.js`가 생성되었으며, script.js에 통합되어 있습니다.

## 필요한 수정 사항

### 1. script.js 시작 부분에 SessionManager 초기화 추가

**위치**: script.js 상단, State 선언 다음

```javascript
// State
let isLoading = false;
let conversationHistory = [];  // Store conversation history
let currentAbortController = null;
let lastUserQuestion = '';

// ===== 여기에 추가 =====
// Session Manager
const sessionManager = new SessionManager();
```

### 2. 페이지 로드 시 세션 복원

**위치**: `window.addEventListener('DOMContentLoaded', ...)` 또는 init 함수 내부

```javascript
// Load session on page load
document.addEventListener('DOMContentLoaded', function() {
    // 기존 초기화 코드...

    // 세션 복원 시도
    const savedHistory = sessionManager.loadSession();
    if (savedHistory && savedHistory.length > 0) {
        console.log('세션 복원:', saved History.length, '개 메시지');
        conversationHistory = savedHistory;
        rebuildChatUI();
    }
});
```

### 3. rebuildChatUI 함수 추가

```javascript
/**
 * Rebuild chat UI from conversation history
 */
function rebuildChatUI() {
    // Clear welcome message
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    // Rebuild messages from history
    conversationHistory.forEach(msg => {
        if (msg.role === 'user') {
            appendMessage(msg.content, 'user');
        } else if (msg.role === 'assistant') {
            appendMessage(msg.content, 'assistant');
        }
    });

    // Hide suggested questions if there are messages
    if (conversationHistory.length > 0) {
        hideSuggestedQuestions();
    }

    // Scroll to bottom
    scrollToBottom();
}
```

### 4. sendMessage 함수에 자동 저장 추가

**위치**: sendMessage 함수 내, conversationHistory에 추가한 직후

```javascript
async function sendMessage(stream = true) {
    const question = userInput.value.trim();
    if (!question || isLoading) return;

    // ... 기존 코드 ...

    // Add to history
    conversationHistory.push({
        role: 'user',
        content: question
    });

    // ===== 여기에 추가 =====
    // Auto-save session
    sessionManager.autoSave(conversationHistory);

    // ... 나머지 코드 ...
}
```

### 5. clearChat 함수 수정

```javascript
function clearChat() {
    if (confirm('대화 내용을 모두 삭제하시겠습니까?')) {
        clearHistory();

        // ===== 추가: 세션도 삭제 =====
        sessionManager.clearSession();

        // Clear chat UI and recreate suggested questions section
        chatContainer.innerHTML = `...`;

        // ... 나머지 코드 ...
    }
}
```

### 6. 응답 수신 후 저장 추가

**위치**: Assistant 응답을 conversationHistory에 추가한 직후

```javascript
// Add assistant response to history
conversationHistory.push({
    role: 'assistant',
    content: answer
});

// ===== 여기에 추가 =====
// Auto-save session
sessionManager.autoSave(conversationHistory);
```

## 전체 통합 예시

```javascript
// ===== 1. 초기화 =====
const sessionManager = new SessionManager();

// ===== 2. 페이지 로드 시 =====
document.addEventListener('DOMContentLoaded', function() {
    // 기존 초기화
    initializeApp();

    // 세션 복원
    const savedHistory = sessionManager.loadSession();
    if (savedHistory && savedHistory.length > 0) {
        console.log(`세션 복원: ${savedHistory.length}개 메시지`);
        conversationHistory = savedHistory;
        rebuildChatUI();
    } else {
        console.log('새 세션 시작');
    }
});

// ===== 3. UI 재구성 함수 =====
function rebuildChatUI() {
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) welcomeMsg.remove();

    conversationHistory.forEach(msg => {
        if (msg.role === 'user') {
            appendMessage(msg.content, 'user');
        } else if (msg.role === 'assistant') {
            appendMessage(msg.content, 'assistant');
        }
    });

    if (conversationHistory.length > 0) {
        hideSuggestedQuestions();
    }

    scrollToBottom();
}

// ===== 4. 메시지 전송 시 저장 =====
async function sendMessage(stream = true) {
    // ... 기존 코드 ...

    conversationHistory.push({ role: 'user', content: question });
    sessionManager.autoSave(conversationHistory); // 저장

    // ... 나머지 코드 ...
}

// ===== 5. 응답 수신 시 저장 =====
conversationHistory.push({ role: 'assistant', content: answer });
sessionManager.autoSave(conversationHistory); // 저장

// ===== 6. 대화 초기화 시 세션 삭제 =====
function clearChat() {
    if (confirm('대화 내용을 모두 삭제하시겠습니까?')) {
        clearHistory();
        sessionManager.clearSession(); // 세션 삭제
        // ... 나머지 코드 ...
    }
}
```

## 테스트 방법

### 1. 세션 저장 테스트
```javascript
// 콘솔에서
1. 질문 전송
2. localStorage.getItem('chatbot_session') 확인
3. JSON.parse 하여 내용 확인
```

### 2. 세션 복원 테스트
```javascript
1. 질문 여러 개 전송
2. F5 (새로고침)
3. 대화 내용이 복원되는지 확인
```

### 3. 만료 테스트
```javascript
// 콘솔에서
const session = JSON.parse(localStorage.getItem('chatbot_session'));
session.timestamp = Date.now() - (25 * 60 * 60 * 1000); // 25시간 전
localStorage.setItem('chatbot_session', JSON.stringify(session));
// 새로고침 - 만료되어 복원 안 됨
```

## 주의사항

1. **localStorage 용량**: 5MB 제한, 긴 대화는 용량 초과 가능
2. **보안**: 민감한 정보는 localStorage에 저장 지양
3. **브라우저 호환성**: 최신 브라우저만 지원
4. **프라이빗 모드**: 일부 브라우저에서 localStorage 비활성화됨

## 향후 개선

1. **압축**: LZ-String 등으로 대화 압축
2. **부분 저장**: 최근 N개 메시지만 저장
3. **IndexedDB**: 대용량 데이터 처리
4. **서버 동기화**: 계정 연동 시 서버에도 백업
