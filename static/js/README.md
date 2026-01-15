# JavaScript 모듈 구조

## 📁 디렉토리 구조

```
static/js/
├── core/                      # 핵심 유틸리티
│   ├── modal-manager.js       # 모달 스택 관리 (ESC 키 처리)
│   └── utils.js               # 공통 유틸리티 함수
│
├── features/                  # 기능별 모듈
│   ├── chat.js                # 채팅 기능
│   ├── documents.js           # 문서 관리
│   ├── versions.js            # 버전 관리
│   ├── settings.js            # 설정 관리
│   ├── history.js             # 대화 기록
│   └── theme.js               # 테마 관리
│
└── main.js                    # 메인 엔트리 포인트
```

## 🎯 모듈 설명

### Core 모듈

#### `modal-manager.js`
- **목적**: 모달 스택 관리 및 ESC 키 처리
- **주요 기능**:
  - 모달 열기/닫기 스택 추적
  - ESC 키로 가장 최근 모달만 닫기
  - 여러 모달이 겹쳐 있을 때 순서대로 처리
- **사용법**:
  ```javascript
  // 모달 열기
  modalManager.push(modalElement, 'modalName');

  // 모달 닫기
  modalManager.pop(modalElement);

  // 최상위 모달 닫기
  modalManager.closeTopmost();
  ```

#### `utils.js`
- **목적**: 공통 유틸리티 함수
- **주요 기능**:
  - 입력 검증 (`validateInput`)
  - HTML 이스케이프 (`escapeHtml`)
  - 파일 크기 포맷 (`formatFileSize`)
  - 타임스탬프 포맷 (`formatTimestamp`)
  - Debounce/Throttle 함수
  - Toast 알림 표시

### Feature 모듈

#### `chat.js` - ChatManager
채팅 메시지 전송, 스트리밍 응답 처리, 대화 표시

**주요 메서드**:
- `sendMessage()` - 메시지 전송
- `clearChat()` - 채팅 초기화
- `checkStatus()` - 시스템 상태 확인

#### `documents.js` - DocumentManager
문서 업로드, 관리, 삭제

**주요 메서드**:
- `loadDocuments()` - 문서 목록 로드
- `uploadFile(file)` - 파일 업로드
- `deleteDocument(filename)` - 문서 삭제

#### `versions.js` - VersionManager
문서 버전 관리 및 비교

**주요 메서드**:
- `showVersionModal(filename)` - 버전 모달 표시
- `loadVersions(filename)` - 버전 목록 로드
- `createVersion(filename, comment)` - 새 버전 생성
- `compareVersions(filename, v1, v2)` - 버전 비교

#### `settings.js` - SettingsManager
애플리케이션 설정 관리

**주요 메서드**:
- `open()` - 설정 패널 열기
- `close()` - 설정 패널 닫기
- `loadAvailableModels()` - 사용 가능한 모델 로드

#### `history.js` - HistoryManager
대화 기록 및 세션 관리

**주요 메서드**:
- `loadConversations()` - 대화 목록 로드
- `createNewConversation()` - 새 대화 시작
- `loadConversation(sessionId)` - 대화 불러오기

#### `theme.js` - ThemeManager
다크/라이트 테마 전환

**주요 메서드**:
- `toggle()` - 테마 전환
- `setTheme(theme)` - 특정 테마 설정

## 🔄 마이그레이션 가이드

### 1단계: 스켈레톤 모듈 생성 ✅
현재 각 모듈의 기본 구조와 이벤트 리스너가 설정되어 있습니다.

### 2단계: 기존 코드 이전 (진행 중)
`script.js`의 기능을 각 모듈로 이전해야 합니다:

1. **Chat 기능** (`script.js` 라인 800-1500)
   - `sendMessage()` 함수
   - `streamResponse()` 함수
   - 메시지 렌더링 로직

2. **Document 기능** (`script.js` 라인 1550-1870)
   - 문서 업로드 로직
   - 문서 목록 표시
   - 문서 삭제 기능

3. **Version 기능** (`script.js` 라인 3718-4016)
   - 버전 생성/삭제
   - 버전 비교
   - 버전 복원

4. **Settings 기능** (`script.js` 라인 1879-2261)
   - 모델 선택
   - 캐시 통계
   - 설정 저장/로드

5. **History 기능** (`script.js` 라인 438-800)
   - 대화 저장/로드
   - 대화 목록 표시
   - 세션 관리

### 3단계: 테스트
각 모듈 이전 후 기능 테스트 필요:
- [ ] 채팅 전송
- [ ] 문서 업로드
- [ ] 버전 관리
- [ ] 설정 변경
- [ ] 대화 기록
- [ ] 테마 전환
- [ ] 모달 ESC 키 동작

### 4단계: 최적화
- 중복 코드 제거
- 모듈 간 의존성 최소화
- 이벤트 버스 패턴 적용 고려

## 🚀 사용 방법

### 개발 환경
```html
<!-- index.html에서 모듈 로드 -->
<script src="/static/js/core/modal-manager.js"></script>
<script src="/static/js/core/utils.js"></script>
<script src="/static/js/features/theme.js"></script>
<script src="/static/js/features/chat.js"></script>
<!-- ... 기타 모듈 ... -->
<script src="/static/js/main.js"></script>
```

### 모듈 사용 예시
```javascript
// main.js에서 초기화
const chatManager = new ChatManager();
const documentManager = new DocumentManager();

// 기능 사용
await chatManager.sendMessage();
await documentManager.loadDocuments();
```

## 📝 코딩 규칙

1. **클래스 기반 구조** - 각 모듈은 클래스로 구현
2. **명확한 책임** - 한 모듈은 한 가지 기능만 담당
3. **이벤트 기반 통신** - 모듈 간 직접 의존 최소화
4. **에러 핸들링** - 모든 비동기 함수에 try-catch
5. **주석 작성** - 복잡한 로직은 반드시 주석 추가

## 🐛 디버깅

개발 모드 활성화:
```javascript
// main.js에서
const DEBUG_MODE = true;

// 디버깅 정보 접근
console.log(window.app.chatManager);
console.log(window.app.modalManager);
```

## 📋 TODO

- [ ] `script.js`의 모든 기능을 각 모듈로 이전
- [ ] 각 모듈별 단위 테스트 작성
- [ ] 레거시 `script.js` 제거
- [ ] 빌드 시스템 추가 (번들링, 최소화)
- [ ] 타입스크립트 마이그레이션 검토

## 🔗 관련 파일

- `static/script.js` - 레거시 모놀리식 파일 (이전 예정)
- `static/index.html` - 모듈 로드 설정
- `static/auth.js` - 인증 관련 (별도 유지)
- `static/group-manager.js` - 그룹 관리 (별도 유지)
