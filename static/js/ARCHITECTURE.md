# 아키텍처 문서

## 🏗️ 모듈 의존성 다이어그램

```
┌─────────────────────────────────────────────────────────┐
│                     index.html                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ├─── External Libraries
                     │    ├─── marked.js (Markdown 렌더링)
                     │    ├─── highlight.js (코드 하이라이팅)
                     │    └─── auth.js (인증)
                     │
                     ├─── Feature Utilities
                     │    ├─── utils.js
                     │    ├─── optimizations.js
                     │    ├─── session-manager.js
                     │    ├─── error-handler.js
                     │    ├─── streaming-visualizer.js
                     │    ├─── autocomplete.js
                     │    ├─── follow-up-questions.js
                     │    └─── group-manager.js
                     │
                     └─── New Modular Structure
                          │
                          ├─── 📁 js/core/
                          │    ├─── modal-manager.js
                          │    │    └─── 모달 스택 관리
                          │    │
                          │    └─── utils.js
                          │         └─── 공통 유틸리티
                          │
                          ├─── 📁 js/features/
                          │    ├─── theme.js
                          │    │    └─── ThemeManager
                          │    │         ├─── initTheme()
                          │    │         ├─── toggle()
                          │    │         └─── setTheme()
                          │    │
                          │    ├─── chat.js
                          │    │    └─── ChatManager
                          │    │         ├─── sendMessage()
                          │    │         ├─── clearChat()
                          │    │         └─── checkStatus()
                          │    │
                          │    ├─── documents.js
                          │    │    └─── DocumentManager
                          │    │         ├─── loadDocuments()
                          │    │         ├─── uploadFile()
                          │    │         └─── deleteDocument()
                          │    │
                          │    ├─── versions.js
                          │    │    └─── VersionManager
                          │    │         ├─── showVersionModal()
                          │    │         ├─── loadVersions()
                          │    │         ├─── createVersion()
                          │    │         └─── compareVersions()
                          │    │
                          │    ├─── settings.js
                          │    │    └─── SettingsManager
                          │    │         ├─── open()
                          │    │         ├─── close()
                          │    │         └─── loadAvailableModels()
                          │    │
                          │    └─── history.js
                          │         └─── HistoryManager
                          │              ├─── loadConversations()
                          │              ├─── createNewConversation()
                          │              └─── loadConversation()
                          │
                          └─── 📁 js/
                               └─── main.js
                                    └─── Application Entry Point
                                         ├─── init()
                                         ├─── setupGlobalEventListeners()
                                         └─── setupKeyboardShortcuts()
```

## 🔄 데이터 흐름

### 1. 애플리케이션 초기화
```
index.html 로드
    ↓
External Libraries 로드 (marked, highlight.js, auth.js)
    ↓
Feature Utilities 로드 (기존 모듈들)
    ↓
Core Modules 로드 (modal-manager, utils)
    ↓
Feature Modules 로드 (theme, chat, documents, etc.)
    ↓
main.js 실행
    ↓
init() 함수 실행
    ↓
각 Manager 인스턴스 생성
    ↓
이벤트 리스너 설정
    ↓
초기 데이터 로드
    ↓
애플리케이션 준비 완료
```

### 2. 사용자 인터랙션 흐름

#### 채팅 메시지 전송
```
사용자가 메시지 입력
    ↓
ChatManager.sendMessage() 호출
    ↓
Input 검증 (utils.validateInput)
    ↓
API 요청 (/api/chat)
    ↓
StreamingVisualizer로 응답 스트리밍
    ↓
Markdown 렌더링 (marked.js)
    ↓
코드 하이라이팅 (highlight.js)
    ↓
채팅 컨테이너에 추가
    ↓
HistoryManager에 세션 저장
```

#### 문서 업로드
```
사용자가 파일 선택
    ↓
DocumentManager.uploadFile() 호출
    ↓
파일 검증
    ↓
FormData 생성
    ↓
API 요청 (/api/upload)
    ↓
업로드 상태 표시
    ↓
문서 목록 새로고침
    ↓
VersionManager.createVersion() 호출 (자동 V1 생성)
```

#### 모달 관리
```
사용자가 모달 열기 버튼 클릭
    ↓
modalManager.push(element, name)
    ↓
모달 스택에 추가
    ↓
modal.classList.add('active')
    ↓
사용자가 ESC 키 누름
    ↓
modalManager.closeTopmost()
    ↓
스택에서 최상위 모달만 제거
    ↓
modal.classList.remove('active')
```

## 📦 모듈 간 통신

### 직접 의존성
- `main.js` → 모든 Manager 클래스
- 각 Manager → `modalManager` (전역)
- 각 Manager → `utils` 함수들

### 이벤트 기반 통신 (향후 개선)
```javascript
// 예: 문서 업로드 완료 시 다른 모듈에 알림
document.dispatchEvent(new CustomEvent('documentUploaded', {
    detail: { filename: 'example.pdf' }
}));

// 다른 모듈에서 수신
document.addEventListener('documentUploaded', (e) => {
    console.log('Document uploaded:', e.detail.filename);
});
```

## 🎨 클래스 다이어그램

### ModalManager
```
┌─────────────────────────────┐
│      ModalManager           │
├─────────────────────────────┤
│ - modalStack: Array         │
├─────────────────────────────┤
│ + push(element, name)       │
│ + pop(element)              │
│ + getTopmost()              │
│ + closeTopmost()            │
│ + hasOpenModals()           │
│ + closeAll()                │
│ - setupKeyboardShortcuts()  │
└─────────────────────────────┘
```

### ChatManager
```
┌─────────────────────────────┐
│       ChatManager           │
├─────────────────────────────┤
│ - isLoading: boolean        │
│ - conversationHistory: []   │
│ - currentAbortController    │
│ - lastUserQuestion: string  │
├─────────────────────────────┤
│ + sendMessage()             │
│ + clearChat()               │
│ + checkStatus()             │
│ - autoResize()              │
│ - updateSendButton()        │
│ - initElements()            │
│ - initEventListeners()      │
└─────────────────────────────┘
```

### DocumentManager
```
┌─────────────────────────────┐
│     DocumentManager         │
├─────────────────────────────┤
│ - docsModal: Element        │
│ - fileInput: Element        │
│ - docsList: Element         │
├─────────────────────────────┤
│ + loadDocuments()           │
│ + uploadFile(file)          │
│ + deleteDocument(filename)  │
│ - handleDragOver(e)         │
│ - handleDrop(e)             │
│ - handleFileSelect(e)       │
│ - showUploadStatus(msg)     │
└─────────────────────────────┘
```

## 🔐 보안 고려사항

### XSS 방지
- 모든 사용자 입력에 `validateInput()` 적용
- HTML 렌더링 시 `escapeHtml()` 사용
- CSP (Content Security Policy) 헤더 설정

### CSRF 방지
- 모든 API 요청에 JWT 토큰 포함 (Auth.js)
- CSRF 토큰 검증 (서버 측)

### 파일 업로드 보안
- 허용된 파일 확장자만 업로드
- 파일 크기 제한
- 바이러스 스캔 (서버 측)

## 🚀 성능 최적화

### 코드 스플리팅
현재는 모든 모듈이 초기 로드됩니다. 향후 개선:
```javascript
// 동적 임포트 사용
const AdminManager = await import('./features/admin.js');
```

### 레이지 로딩
```javascript
// 필요할 때만 모듈 로드
if (Auth.isAdmin()) {
    await import('./features/admin.js');
}
```

### 캐싱 전략
- Service Worker 사용
- LocalStorage/SessionStorage 활용
- HTTP 캐시 헤더 설정

## 📊 모니터링 및 디버깅

### 디버그 모드
```javascript
// main.js
const DEBUG_MODE = true;

// 콘솔에서 접근
window.app.chatManager
window.app.modalManager
window.app.documentManager
```

### 로깅
```javascript
// 각 Manager에서
console.group('ChatManager.sendMessage');
console.log('Input:', message);
console.log('Validation:', result);
console.groupEnd();
```

### 에러 추적
```javascript
// ErrorHandler 통합
try {
    await chatManager.sendMessage();
} catch (error) {
    errorHandler.handle(error, 'ChatManager.sendMessage');
}
```

## 🧪 테스트 전략

### 단위 테스트
```javascript
describe('ModalManager', () => {
    it('should push modal to stack', () => {
        const modal = document.createElement('div');
        modalManager.push(modal, 'test');
        expect(modalManager.modalStack.length).toBe(1);
    });
});
```

### 통합 테스트
```javascript
describe('Document Upload Flow', () => {
    it('should upload file and create version', async () => {
        const file = new File(['test'], 'test.pdf');
        await documentManager.uploadFile(file);
        // 버전 생성 확인
    });
});
```

## 📝 마이그레이션 체크리스트

### Phase 1: 인프라 ✅
- [x] 디렉토리 구조 생성
- [x] 모듈 스켈레톤 작성
- [x] index.html 업데이트
- [x] README 및 문서 작성

### Phase 2: 코드 이전 (진행 중)
- [ ] Chat 기능 이전
- [ ] Document 기능 이전
- [ ] Version 기능 이전
- [ ] Settings 기능 이전
- [ ] History 기능 이전
- [ ] Theme 기능 이전 ✅ (간단함)

### Phase 3: 테스트 및 최적화
- [ ] 기능 테스트
- [ ] 성능 테스트
- [ ] 크로스 브라우저 테스트
- [ ] 레거시 코드 제거

### Phase 4: 고도화
- [ ] TypeScript 마이그레이션
- [ ] 빌드 시스템 추가
- [ ] 번들 최적화
- [ ] 테스트 자동화
