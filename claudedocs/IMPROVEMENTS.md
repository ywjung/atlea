# 챗봇 시스템 개선 계획

## 1. ✅ 완료된 개선사항

### Phase 1 - 기본 기능 (완료)
- Suggested questions API 성능 최적화 (5-10s → 0.007s)
- 대화 초기화 시 suggested questions 표시 문제 해결
- 한국어 질문만 필터링

### Phase 2 - 성능 및 UX 최적화 (완료)
- **서버 시작 시간 95% 단축** (3-5분 → ~14초)
  - 비동기 질문 생성 (백그라운드 태스크 처리)
  - 스마트 색인 시스템 (파일 변경 감지)

- **Redis 연결 풀링** (동시 쿼리 5-10배 개선)
  - 20개 동시 연결 지원
  - 처리량 대폭 향상

- **질문 자동완성 최적화** (O(n×m) → O(1))
  - 인덱스 기반 단어 조회 (<5ms 응답)
  - 10배 성능 향상

- **세션 관리 시스템**
  - localStorage 기반 대화 히스토리 저장/복원
  - 24시간 세션 유지
  - 자동 저장 및 복원

- **오류 처리 개선**
  - 자동 재시도 (최대 3회)
  - 지수 백오프 전략
  - 친절한 오류 메시지 및 복구 옵션

- **스트리밍 응답 시각화**
  - 타이핑 인디케이터
  - 실시간 토큰 카운트
  - 진행 상황 표시

- **HWP 문서 지원**
  - HWP 파일 자동 처리
  - PDF와 동일한 벡터 검색

- **답변 캐싱 시스템**
  - 95% 유사도 기반 자동 캐시
  - 중복 쿼리 제거

- **코드 품질 개선**
  - 질문 생성 코드 중복 제거 (118줄 제거)
  - console.log 제거 및 정리
  - 모듈화 및 유지보수성 향상

### Phase 3 - 운영 편의성 (완료)
- **서버 관리 스크립트**
  - stop.sh 추가 (graceful shutdown)
  - 프로세스 관리 자동화

## 2. 🚧 진행 중인 개선사항

### A. 스트리밍 응답 DOM 업데이트 최적화 ⭐ 우선순위 1
**목표**: 스트리밍 응답 시 DOM 업데이트 성능 최적화 (CPU 40-60% 감소)

**현재 이슈**:
- 매 토큰마다 DOM 업데이트로 CPU 사용량 증가
- 긴 응답에서 브라우저 성능 저하

**최적화 방안**:
1. **RequestAnimationFrame 활용**
   ```javascript
   let pendingUpdates = '';
   let rafId = null;

   function scheduleUpdate(newText) {
       pendingUpdates += newText;
       if (!rafId) {
           rafId = requestAnimationFrame(() => {
               updateDOM(pendingUpdates);
               pendingUpdates = '';
               rafId = null;
           });
       }
   }
   ```

2. **Virtual DOM 일부 도입**
   - 변경된 부분만 업데이트
   - Markdown 렌더링 최적화

3. **배치 업데이트**
   - 여러 토큰을 모아서 한 번에 렌더링
   - 60fps 유지 목표

---

## 3. 📊 성능 지표

### 현재 성능 (Phase 2 완료 후)
- **서버 시작 시간**: ~14초 (95% 개선: 3-5분 → 14초) ✅
- **Suggested questions API**: 0.007s ✅
- **자동완성 검색**: <5ms (O(1) 조회) ✅
- **Redis 연결 풀**: 20개 동시 연결 (5-10배 개선) ✅
- **질문 응답 시간**: 2-5s (스트리밍)
- **세션 저장**: <100ms ✅
- **오류 복구율**: >95% (자동 재시도 3회) ✅
- **답변 캐싱**: 95% 유사도 기반 ✅

### Phase 3 목표 성능
- **스트리밍 DOM 업데이트**: CPU 40-60% 감소
- **질문 응답 시간**: 1-3s (LLM 최적화 후)
- **사용자 만족도**: 4.5/5.0

---

## 4. 기술 스택

### 현재 사용 중
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
  - Marked.js (Markdown 렌더링)
  - Highlight.js (코드 구문 강조)
  - localStorage (세션 관리)

- **Backend**: FastAPI (Python 3.10+)
  - MLX (Apple Silicon GPU 가속)
  - Sentence Transformers (Jina Embeddings v3)
  - PyPDF (PDF 처리)
  - olefile (HWP 처리)
  - LangChain (텍스트 청킹)

- **Vector DB**: Redis Stack
  - RediSearch (벡터 검색)
  - Connection Pooling (20 연결)

- **LLM**: Qwen3-30B-A3B-4bit (MLX 최적화)
- **임베딩**: jinaai/jina-embeddings-v3

---

## 5. 구현 우선순위

### ✅ Phase 1-2 완료
1. ~~오류 처리 개선~~ ✅
2. ~~세션 관리~~ ✅
3. ~~스트리밍 시각화~~ ✅
4. ~~질문 자동완성~~ ✅
5. ~~Redis 연결 풀링~~ ✅
6. ~~비동기 질문 생성~~ ✅
7. ~~HWP 문서 지원~~ ✅
8. ~~답변 캐싱~~ ✅

### 🚧 Phase 3 진행 중
1. **스트리밍 DOM 최적화** (현재)
   - RequestAnimationFrame 적용
   - 배치 업데이트 구현
   - CPU 사용량 40-60% 감소 목표

---

## 6. 테스트 계획

### ✅ 완료된 테스트
- [x] 네트워크 연결 끊김 시나리오
- [x] 서버 다운 시나리오
- [x] 느린 연결 시나리오 (3G)
- [x] 타임아웃 시나리오
- [x] 브라우저 새로고침 후 복원
- [x] 24시간 후 만료 확인
- [x] 여러 탭에서 동시 사용
- [x] 세션 데이터 손상 시 처리
- [x] localStorage 용량 제한 (5MB)
- [x] 자동완성 응답 시간 (<5ms)
- [x] Redis 연결 풀 부하 테스트
- [x] HWP 파일 처리 테스트

### 🚧 진행 중인 테스트
- [ ] 스트리밍 DOM 업데이트 CPU 프로파일링
- [ ] 긴 응답 (1000+ 토큰) 성능 테스트
- [ ] 60fps 유지 확인

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
