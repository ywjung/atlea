# 챗봇 시스템 개선 계획

## 1. ✅ 완료된 개선사항
- Suggested questions API 성능 최적화 (5-10s → 0.007s)
- 대화 초기화 시 suggested questions 표시 문제 해결
- 한국어 질문만 필터링

## 2. 🚧 진행 중인 개선사항

### A. 세션 관리 강화 ⭐ 우선순위 1
**목표**: 브라우저 새로고침/종료 후에도 대화 내용 보존

**구현 방법**:
```javascript
// 세션 저장 (localStorage)
function saveSession() {
    const session = {
        history: conversationHistory,
        timestamp: Date.now(),
        version: '1.0'
    };
    localStorage.setItem('chatbot_session', JSON.stringify(session));
}

// 세션 복원
function loadSession() {
    const saved = localStorage.getItem('chatbot_session');
    if (saved) {
        const session = JSON.parse(saved);
        // 24시간 이내 세션만 복원
        if (Date.now() - session.timestamp < 24 * 60 * 60 * 1000) {
            conversationHistory = session.history;
            // UI 재구성
            rebuildChatUI();
        }
    }
}
```

**추가 기능**:
- 자동 저장 (메시지 전송 후)
- 세션 만료 시간 설정 (24시간)
- 세션 복원 확인 UI

---

### B. 오류 처리 개선 ⭐ 우선순위 2
**목표**: 네트워크 오류, 타임아웃 등 예외 상황에 대한 친절한 처리

**구현할 오류 유형**:
1. **네트워크 오류** (연결 실패)
   - 재시도 버튼 표시
   - 최대 3회 자동 재시도

2. **타임아웃** (응답 지연)
   - 진행 상태 표시
   - 취소 버튼 제공

3. **서버 오류** (500, 503 등)
   - 친절한 오류 메시지
   - 관리자 알림

**구현 예시**:
```javascript
async function sendMessageWithRetry(message, maxRetries = 3) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            return await sendMessage(message);
        } catch (error) {
            if (i === maxRetries - 1) {
                showErrorMessage({
                    type: 'network',
                    message: '연결에 실패했습니다. 인터넷 연결을 확인해주세요.',
                    actions: ['retry', 'cancel']
                });
                throw error;
            }
            await sleep(1000 * Math.pow(2, i)); // Exponential backoff
        }
    }
}
```

---

### C. 스트리밍 응답 시각화 ⭐ 우선순위 3
**목표**: 응답 생성 과정을 시각적으로 표시

**구현 방법**:
1. **타이핑 인디케이터**
   - 답변 생성 중 "..." 애니메이션
   - 예상 완료 시간 표시

2. **진행률 표시**
   ```html
   <div class="streaming-indicator">
       <div class="typing-dots">
           <span></span><span></span><span></span>
       </div>
       <span class="status-text">답변 생성 중...</span>
   </div>
   ```

3. **실시간 토큰 카운터**
   - 생성된 토큰 수 표시
   - 예상 완료까지 남은 시간

**CSS 애니메이션**:
```css
.typing-dots span {
    animation: blink 1.4s infinite;
}
.typing-dots span:nth-child(2) {
    animation-delay: 0.2s;
}
.typing-dots span:nth-child(3) {
    animation-delay: 0.4s;
}

@keyframes blink {
    0%, 80%, 100% { opacity: 0; }
    40% { opacity: 1; }
}
```

---

### D. 질문 자동완성 ⭐ 우선순위 4
**목표**: 사용자가 입력하는 동안 관련 질문 제안

**구현 방법**:
1. **입력 감지**
   ```javascript
   userInput.addEventListener('input', debounce(async (e) => {
       const query = e.target.value;
       if (query.length >= 2) {
           const suggestions = await getSuggestions(query);
           showAutocomplete(suggestions);
       }
   }, 300)); // 300ms debounce
   ```

2. **유사도 기반 검색**
   - 기존 suggested questions pool에서 검색
   - 문자열 유사도 계산 (Levenshtein distance)
   - 최대 5개 제안

3. **UI 구현**
   ```html
   <div class="autocomplete-dropdown" id="autocomplete">
       <div class="autocomplete-item">유사한 질문 1</div>
       <div class="autocomplete-item">유사한 질문 2</div>
       ...
   </div>
   ```

4. **키보드 네비게이션**
   - ↑/↓ : 항목 선택
   - Enter : 선택한 질문 입력
   - Esc : 닫기

---

## 3. 📊 성능 지표

### 현재 성능
- Suggested questions API: 0.007s ✅
- 질문 응답 시간: 2-5s (스트리밍)
- 세션 저장: 미구현 ❌
- 오류 재시도: 미구현 ❌

### 목표 성능
- 질문 응답 시간: 1-3s (최적화 후)
- 세션 저장: <100ms
- 오류 복구율: >95%
- 사용자 만족도: 4.5/5.0

---

## 4. 기술 스택

### 현재 사용 중
- Frontend: Vanilla JavaScript, HTML5, CSS3
- Backend: FastAPI (Python)
- Vector DB: Redis with vector search
- LLM: Qwen2.5-3B-Instruct (MLX)
- 임베딩: multilingual-e5-large-instruct

### 추가 라이브러리 (선택사항)
- 자동완성: Fuse.js (fuzzy search)
- 상태관리: (현재 vanilla JS로 충분)
- UI 애니메이션: CSS animations (라이브러리 불필요)

---

## 5. 구현 우선순위

1. **오류 처리 개선** (Week 1)
   - 재시도 로직
   - 친절한 오류 메시지
   - 타임아웃 처리

2. **세션 관리** (Week 1)
   - localStorage 저장/복원
   - 자동 저장
   - 세션 만료 처리

3. **스트리밍 시각화** (Week 2)
   - 타이핑 인디케이터
   - 진행률 표시

4. **질문 자동완성** (Week 2)
   - 입력 감지
   - 유사도 검색
   - UI 구현

---

## 6. 테스트 계획

### 오류 처리 테스트
- [ ] 네트워크 연결 끊김 시나리오
- [ ] 서버 다운 시나리오
- [ ] 느린 연결 시나리오 (3G)
- [ ] 타임아웃 시나리오

### 세션 관리 테스트
- [ ] 브라우저 새로고침 후 복원
- [ ] 24시간 후 만료 확인
- [ ] 여러 탭에서 동시 사용
- [ ] 세션 데이터 손상 시 처리

### 성능 테스트
- [ ] 100개 메시지 로드 시간
- [ ] localStorage 용량 제한 (5MB)
- [ ] 자동완성 응답 시간 (<100ms)

---

## 7. 향후 고려사항

### 고급 기능 (Phase 2)
- 음성 입력/출력
- 다국어 지원 (영어, 일본어 등)
- PDF 요약 기능
- 질문 템플릿 제공
- 대화 내보내기 (PDF, Markdown)

### 관리 기능
- 사용량 통계 대시보드
- 사용자 피드백 수집
- A/B 테스팅 시스템
- 품질 모니터링

### 인프라
- CDN 도입
- 로드 밸런싱
- 캐싱 레이어
- 모니터링 & 알람
