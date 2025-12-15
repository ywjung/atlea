# 질문 자동완성 통합 가이드

## 개요
`autocomplete.js`와 `autocomplete-styles.css`가 생성되었으며, script.js에 통합이 필요합니다.

## 필요한 수정 사항

### 1. HTML에 파일 추가

**위치**: index.html의 `<head>` 섹션과 `<body>` 하단

```html
<!-- Head section에 CSS 추가 -->
<link rel="stylesheet" href="/static/autocomplete-styles.css">

<!-- Body 하단 script 섹션에 추가 (streaming-visualizer.js 다음) -->
<script src="/static/autocomplete.js"></script>
```

### 2. script.js에 AutoComplete 초기화 추가

**위치**: script.js 상단, StreamingVisualizer 초기화 다음

```javascript
// Streaming Visualizer
const streamingVisualizer = new StreamingVisualizer();

// ===== 여기에 추가 =====
// Question AutoComplete (초기에는 빈 배열로 시작)
let questionAutoComplete = null;

// fetchSuggestedQuestions 함수 후 초기화
async function initializeAutoComplete() {
    const questions = await fetchSuggestedQuestions();
    const userInput = document.getElementById('userInput');
    questionAutoComplete = new QuestionAutoComplete(userInput, questions);
}

// 페이지 로드 시 초기화
initializeAutoComplete();
```

### 3. fetchSuggestedQuestions 함수 수정

**위치**: script.js의 fetchSuggestedQuestions 함수

기존 함수를 수정하여 AutoComplete에 질문 목록을 업데이트하도록 합니다:

```javascript
async function fetchSuggestedQuestions() {
    try {
        const response = await fetch('/api/suggested-questions');
        if (!response.ok) {
            throw new Error('Failed to fetch suggested questions');
        }

        const data = await response.json();
        suggestedQuestions = data.questions || [];

        // ===== 추가: AutoComplete 업데이트 =====
        if (questionAutoComplete) {
            questionAutoComplete.updateSuggestions(suggestedQuestions);
        }

        return suggestedQuestions;
    } catch (error) {
        console.error('Error fetching suggested questions:', error);
        return [];
    }
}
```

### 4. 대화 초기화 시 AutoComplete 클리어 (선택사항)

**위치**: clearChat 함수 또는 새 대화 시작 시

```javascript
function clearChat() {
    // 기존 clearChat 로직...
    conversationHistory = [];
    chatContainer.innerHTML = '';

    // ===== 추가: AutoComplete 클리어 =====
    if (questionAutoComplete) {
        questionAutoComplete.clear();
    }

    // 추천 질문 다시 표시
    showSuggestedQuestions();
}
```

## 전체 통합 예시

```javascript
// ===== 1. 초기화 =====
const streamingVisualizer = new StreamingVisualizer();
let questionAutoComplete = null;

// ===== 2. AutoComplete 초기화 함수 =====
async function initializeAutoComplete() {
    const questions = await fetchSuggestedQuestions();
    const userInput = document.getElementById('userInput');
    questionAutoComplete = new QuestionAutoComplete(userInput, questions);
}

// ===== 3. 페이지 로드 시 초기화 =====
document.addEventListener('DOMContentLoaded', () => {
    initializeAutoComplete();
});

// ===== 4. fetchSuggestedQuestions에서 업데이트 =====
async function fetchSuggestedQuestions() {
    try {
        const response = await fetch('/api/suggested-questions');
        if (!response.ok) {
            throw new Error('Failed to fetch suggested questions');
        }

        const data = await response.json();
        suggestedQuestions = data.questions || [];

        // AutoComplete 업데이트
        if (questionAutoComplete) {
            questionAutoComplete.updateSuggestions(suggestedQuestions);
        }

        return suggestedQuestions;
    } catch (error) {
        console.error('Error fetching suggested questions:', error);
        return [];
    }
}

// ===== 5. 대화 초기화 시 클리어 =====
function clearChat() {
    conversationHistory = [];
    chatContainer.innerHTML = '';

    if (questionAutoComplete) {
        questionAutoComplete.clear();
    }

    showSuggestedQuestions();
}
```

## 주요 기능

### 1. 자동완성 활성화
- **최소 글자 수**: 2글자 이상 입력 시 활성화
- **최대 결과 수**: 5개까지 표시
- **디바운스 시간**: 300ms (입력 멈춘 후 검색)

### 2. 매칭 알고리즘
AutoComplete는 4단계 스코어링 시스템 사용:

1. **정확히 일치** (1000점): 입력과 완전 일치
2. **시작 일치** (500점): 질문이 입력으로 시작
3. **포함 일치** (300점): 질문이 입력을 포함
4. **단어 기반 퍼지 매칭** (단어당 100점): 단어 단위로 부분 일치

**예시**:
```javascript
입력: "PDF"
- "PDF에서 데이터 추출하는 방법" → 500점 (시작 일치)
- "어떻게 PDF 파일을 읽나요?" → 300점 (포함 일치)
- "문서 파일 처리" → 0점 (매칭 안됨)

입력: "파일 읽기"
- "PDF 파일 읽기 방법" → 200점 (단어 2개 매칭)
- "파일을 어떻게 읽나요?" → 200점 (단어 2개 매칭)
```

### 3. 키보드 네비게이션
- **ArrowDown**: 다음 항목 선택
- **ArrowUp**: 이전 항목 선택
- **Enter**: 선택된 항목으로 입력 필드 채우기
- **Escape**: 드롭다운 닫기

### 4. 마우스 인터랙션
- **클릭**: 항목 선택
- **마우스 오버**: 항목 하이라이트

## 커스터마이징

### 최소 글자 수 변경

```javascript
// 3글자부터 활성화
questionAutoComplete.updateConfig({
    minLength: 3
});
```

### 최대 결과 수 변경

```javascript
// 10개까지 표시
questionAutoComplete.updateConfig({
    maxResults: 10
});
```

### 디바운스 시간 변경

```javascript
// 500ms로 변경 (느린 타이핑에 적합)
questionAutoComplete.updateConfig({
    debounceDelay: 500
});
```

### 모든 설정 한번에 변경

```javascript
questionAutoComplete.updateConfig({
    minLength: 1,
    maxResults: 8,
    debounceDelay: 200
});
```

## 현재 설정 확인

```javascript
const config = questionAutoComplete.getConfig();
console.log('현재 설정:', config);
// {
//   minLength: 2,
//   maxResults: 5,
//   debounceDelay: 300,
//   questionsCount: 50
// }
```

## API 메서드

### updateSuggestions(questions)
질문 목록 업데이트

```javascript
const newQuestions = ['질문1', '질문2', '질문3'];
questionAutoComplete.updateSuggestions(newQuestions);
```

### clear()
AutoComplete 상태 초기화 (드롭다운 닫기, 타이머 클리어)

```javascript
questionAutoComplete.clear();
```

### destroy()
AutoComplete 완전히 제거 (DOM 요소 삭제, 이벤트 리스너 제거)

```javascript
questionAutoComplete.destroy();
questionAutoComplete = null;
```

### getConfig()
현재 설정 가져오기

```javascript
const config = questionAutoComplete.getConfig();
```

### updateConfig(config)
설정 업데이트

```javascript
questionAutoComplete.updateConfig({
    minLength: 3,
    maxResults: 10
});
```

## 테스트 방법

### 1. 기본 동작 테스트

```javascript
// 콘솔에서
const testQuestions = [
    'PDF 파일을 어떻게 읽나요?',
    'PDF에서 텍스트 추출하는 방법',
    '문서 처리 방법',
    '데이터 분석 기법',
    'RAG 시스템 구축 방법'
];

const userInput = document.getElementById('userInput');
const autocomplete = new QuestionAutoComplete(userInput, testQuestions);

// 입력 필드에 "PDF" 입력하여 자동완성 확인
```

### 2. 키보드 네비게이션 테스트

1. 입력 필드에 텍스트 입력
2. 드롭다운이 표시되면 ArrowDown/ArrowUp 키로 이동
3. Enter로 선택 확인
4. Escape로 드롭다운 닫기 확인

### 3. 동적 업데이트 테스트

```javascript
// 콘솔에서
setTimeout(() => {
    const newQuestions = ['새로운 질문1', '새로운 질문2'];
    autocomplete.updateSuggestions(newQuestions);
    console.log('질문 목록 업데이트됨');
}, 5000);
```

## 스타일 커스터마이징

### 드롭다운 최대 높이 변경

```css
/* autocomplete-styles.css */
.autocomplete-dropdown {
    max-height: 400px; /* 기본 300px에서 변경 */
}
```

### 항목 폰트 크기 변경

```css
.autocomplete-item {
    font-size: 15px; /* 기본 14px에서 변경 */
}
```

### 선택된 항목 색상 변경

```css
.autocomplete-item.selected {
    background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
    border-left-color: #1890ff;
}
```

## 접근성 고려사항

1. **키보드 네비게이션**: 완전한 키보드 지원
2. **고대비 모드**: `prefers-contrast: high` 지원
3. **다크 모드**: `prefers-color-scheme: dark` 지원
4. **애니메이션 감소**: `prefers-reduced-motion: reduce` 지원
5. **포커스 표시**: `:focus-visible` 아웃라인 제공

## 주의사항

1. **초기화 순서**: fetchSuggestedQuestions가 완료된 후 AutoComplete 초기화
2. **메모리 관리**: destroy() 메서드로 완전히 제거 가능
3. **이벤트 충돌**: 입력 필드의 다른 이벤트 리스너와 충돌 가능성 확인
4. **모바일 성능**: 대량의 질문(>100개)에서는 성능 모니터링 필요

## 향후 개선 사항

1. **하이라이팅**: 매칭된 텍스트 부분 하이라이트 표시
2. **카테고리**: 질문을 카테고리별로 그룹화
3. **최근 검색**: 최근 선택한 질문 기억
4. **인기도 기반 정렬**: 자주 선택된 질문 우선 표시
5. **음성 입력 지원**: Web Speech API 통합
6. **다국어 지원**: 한국어/영어 동시 매칭
