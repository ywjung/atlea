# 자동완성 기능 디버그 가이드

## 문제 확인 방법

### 1. 브라우저 개발자 도구에서 확인

1. **F12** 또는 **Ctrl+Shift+I** (Mac: Cmd+Option+I)를 눌러 개발자 도구 열기
2. **Console 탭** 확인
3. 다음 명령어를 입력하여 상태 확인:

```javascript
// 자동완성 인스턴스 확인
console.log('AutoComplete 인스턴스:', questionAutoComplete);

// 질문 목록 확인
if (questionAutoComplete) {
    console.log('설정:', questionAutoComplete.getConfig());
    console.log('질문 개수:', questionAutoComplete.suggestedQuestions.length);
    console.log('질문 목록:', questionAutoComplete.suggestedQuestions);
}
```

### 2. 질문 목록이 비어있는 경우

**원인**: 서버에서 질문 목록을 가져오지 못했거나 문서가 없음

**해결 방법**:
```bash
# 1. 백엔드 서버가 실행 중인지 확인
curl http://localhost:8085/api/suggested-questions

# 2. 응답 확인 (questions 배열이 있어야 함)
# 예상 응답:
# {
#   "questions": [
#     "이 문서의 주요 내용은 무엇인가요?",
#     "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
#     ...
#   ]
# }
```

### 3. 자동완성이 초기화되지 않은 경우

**증상**: `questionAutoComplete`가 `undefined`

**해결 방법**:
1. 페이지 새로고침 (**F5** 또는 **Ctrl+R**)
2. 브라우저 캐시 삭제 후 새로고침 (**Ctrl+Shift+R** / Mac: **Cmd+Shift+R**)

### 4. CSS 스타일이 적용되지 않은 경우

**증상**: 드롭다운이 보이지 않거나 위치가 이상함

**확인**:
```javascript
// 개발자 도구 Console에서
const dropdown = document.getElementById('autocompleteDropdown');
console.log('드롭다운 요소:', dropdown);
console.log('표시 상태:', dropdown ? dropdown.style.display : 'not found');
```

## 정상 작동 확인 방법

### 1. 입력창에 2글자 이상 입력
예: "문서", "주요", "내용"

### 2. 300ms 후 드롭다운 표시
- 입력 후 약 0.3초 대기 (디바운스)
- 일치하는 질문이 있으면 자동으로 표시

### 3. 키보드 네비게이션
- **↑/↓**: 항목 이동
- **Enter**: 선택
- **Esc**: 닫기

## 수동으로 자동완성 재초기화

브라우저 Console에서 다음 명령어 실행:

```javascript
// 1. 기존 인스턴스 제거
if (questionAutoComplete) {
    questionAutoComplete.destroy();
}

// 2. 질문 목록 다시 가져오기
fetch('/api/suggested-questions')
    .then(res => res.json())
    .then(data => {
        console.log('가져온 질문:', data.questions);

        // 3. 자동완성 재생성
        const userInput = document.getElementById('userInput');
        questionAutoComplete = new QuestionAutoComplete(userInput, data.questions);

        console.log('자동완성 재초기화 완료!');
    })
    .catch(err => console.error('에러:', err));
```

## 자동완성 설정 변경

```javascript
// 최소 입력 글자 수 변경 (기본값: 2)
questionAutoComplete.updateConfig({ minLength: 1 });

// 최대 결과 개수 변경 (기본값: 5)
questionAutoComplete.updateConfig({ maxResults: 10 });

// 디바운스 지연 시간 변경 (기본값: 300ms)
questionAutoComplete.updateConfig({ debounceDelay: 500 });
```

## 문제 해결 체크리스트

- [ ] 백엔드 서버 실행 중 (http://localhost:8085)
- [ ] `/api/suggested-questions` 엔드포인트 정상 응답
- [ ] 브라우저 Console에 에러 메시지 없음
- [ ] `questionAutoComplete` 객체 존재
- [ ] `suggestedQuestions` 배열에 질문 있음 (최소 1개 이상)
- [ ] 입력창 ID가 `userInput`으로 정확히 설정됨
- [ ] `autocomplete.js` 파일 로딩됨
- [ ] CSS 파일 `autocomplete-styles.css` 로딩됨

## 로그 확인

서버 로그에서 다음 메시지 확인:

```
SUCCESS | src.web_server:startup_event:194 - Generated 9 questions in pool
INFO | src.web_server:get_suggested_questions:989 - Returning 5 questions from pool of 9
```

로그에 경고가 있다면:
```
WARNING: Question pool is empty, using fallback questions
```
→ 문서를 업로드하고 서버를 재시작하세요.

**참고**: 서버는 `./run.sh` 스크립트로 실행됩니다. 기본 포트는 8085이며, .env 파일에서 변경 가능합니다.

## 테스트 예제

1. **입력**: "문서"
   - **기대 결과**: "문서의", "문서에서" 등을 포함한 질문 표시

2. **입력**: "주요"
   - **기대 결과**: "주요 내용", "주요 개념" 등을 포함한 질문 표시

3. **입력**: "무엇"
   - **기대 결과**: "무엇인가요"를 포함한 질문 표시
