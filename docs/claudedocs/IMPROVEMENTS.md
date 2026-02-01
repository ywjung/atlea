# ATLEA 시스템 개선 계획

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

### Phase 4 - 보안 및 관리 기능 강화 (v2.3.0~v2.4.0, 완료)

- **2FA/TOTP 다중 인증**
  - pyotp 기반 RFC 6238 호환 TOTP 구현
  - Google Authenticator 호환 (6자리, 30초 주기)
  - QR 코드 생성 (Base64 인코딩)
  - 관리자 설정으로 전체 사용자 강제 적용 가능

- **조직(Organization) 관리**
  - 조직 CRUD 및 멤버 관리
  - 역할 기반 접근제어 (system_admin, org_admin, member)
  - 조직 단위 문서 격리 (멀티테넌트)
  - 조직별 설정 관리

- **Hybrid RAG (문서 + 웹 검색)**
  - 문서 기반 RAG에 실시간 웹 검색 통합
  - Tavily API 연동 지원
  - SearXNG 자체 호스팅 검색 엔진 지원
  - Crawl4AI 웹 페이지 콘텐츠 추출
  - 관리자 페이지에서 검색 프로바이더 설정

- **문서 버전 관리**
  - 동일 파일 재업로드 시 버전 자동 생성
  - 최대 10개 버전 유지 (설정 가능)
  - MD5 해시 기반 변경 감지
  - `data/versions/{filename}/` 구조로 저장
  - 타임스탬프 형식: `YYYYMMDDHHmmss`

- **Brute Force 방어**
  - 계정 잠금: 5회 실패 → 15분 잠금
  - IP 기반 차단: 10회 실패 → 30분 차단
  - Redis Sorted Set 기반 30분 윈도우 추적

- **관리자 대시보드 강화**
  - 모듈화된 관리 UI (CSS/JS 분리)
  - 사용자/문서/그룹/설정 통합 관리
  - 실시간 시스템 상태 모니터링
  - 테마 관리 (라이트/다크 모드)

### Phase 5 - 플랫폼 확장 (v2.5.0, 완료)

- **SearXNG + Crawl4AI 통합**
  - SearXNG 메타 검색 엔진 (포트 8888) - Google, Bing, DuckDuckGo 등 통합
  - Crawl4AI 웹 크롤러 (포트 11235) - 웹 페이지 콘텐츠 추출
  - Docker Compose 배포 (`docker-compose.searxng.yml`)
  - 관리자 페이지에서 프로바이더 전환 가능

- **TTS (Text-to-Speech) 음성 합성**
  - Edge TTS (Microsoft): 클라우드 기반, 24kHz, 10개 언어, MP3 출력
  - Qwen3 모델: 로컬 실행 (0.6B~1.7B), 음성 복제, WAV 출력
  - Redis 기반 설정 관리 (`config:tts`)
  - 8개 API 엔드포인트 (관리자/사용자)
  - 오디오 캐싱 (`cache/tts/audio/`)

- **CAPTCHA 시스템**
  - 자체 호스팅 이미지 기반 수학 문제
  - 280×80px, OCR 방지 (노이즈, 회전, 블러)
  - 5분 TTL, UUID 기반 식별
  - 로그인/회원가입 각각 활성화 설정

- **감사 로그 (Audit Log)**
  - 90일 보관 (설정 가능)
  - 17가지 액션 유형 추적 (인증, 문서, 그룹, 설정, 관리, 시스템)
  - 4단계 인덱싱 (사용자, 사용자명, 액션, 일별)
  - 일별 통계 (성공/실패율)

- **Ollama LLM 백엔드 지원**
  - Ollama 서버 연동 (기본 포트 11434)
  - 기본 모델: `alibayram/Qwen3-30B-A3B-Instruct-2507:latest`
  - OpenAI 호환 API 사용
  - 환경변수: `OLLAMA_BASE_URL`, `OLLAMA_LLM_MODEL`, `OLLAMA_EMBEDDING_MODEL`

- **멀티플랫폼 LLM 지원**
  - MLX (Apple Silicon), Transformers+CUDA (NVIDIA), Transformers+CPU, Ollama
  - 자동 플랫폼 감지 및 최적 백엔드 선택
  - `src/platform_utils.py` 기반 자동 구성

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

### 현재 성능 (v2.5.0 기준)
- **서버 시작 시간**: ~14초 (95% 개선: 3-5분 → 14초) ✅
- **Suggested questions API**: 0.007s ✅
- **자동완성 검색**: <5ms (O(1) 조회) ✅
- **Redis 연결 풀**: 20개 동시 연결 (5-10배 개선) ✅
- **질문 응답 시간**: 2-5s (스트리밍)
- **세션 저장**: <100ms ✅
- **오류 복구율**: >95% (자동 재시도 3회) ✅
- **답변 캐싱**: 95% 유사도 기반 ✅
- **API 엔드포인트**: 168개 (18개 라우터) ✅
- **지원 문서 포맷**: 11가지 (PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, HTML) ✅
- **감사 로그 보관**: 90일 ✅
- **2FA 인증**: TOTP 6자리, 30초 주기 ✅

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
  - 모듈화된 관리자 UI (admin-core.css, admin-themes.css, admin-themes.js)

- **Backend**: FastAPI (Python 3.10+)
  - MLX (Apple Silicon GPU 가속)
  - Ollama (범용 LLM 서버)
  - Sentence Transformers (KURE-v1 - Korean Universal Representation Embeddings)
  - PyPDF (PDF 처리)
  - olefile (HWP 처리)
  - LangChain (텍스트 청킹)
  - pyotp (2FA/TOTP)
  - Edge TTS (음성 합성)
  - Pillow (CAPTCHA 이미지 생성)

- **Vector DB**: Redis Stack
  - RediSearch (벡터 검색)
  - Connection Pooling (20 연결)

- **웹 검색**: Hybrid RAG
  - Tavily API (클라우드)
  - SearXNG (자체 호스팅 메타 검색, 포트 8888)
  - Crawl4AI (웹 콘텐츠 추출, 포트 11235)

- **문서 처리**: Java Document Service (Spring Boot)
  - Apache POI (MS Office 형식)
  - HWP/HWPX 변환
  - Caffeine 캐시

- **LLM**: 멀티 백엔드
  - Qwen3-30B-A3B-4bit (MLX, Apple Silicon)
  - Ollama (범용, 기본 모델: alibayram/Qwen3-30B-A3B-Instruct-2507)
  - Transformers+CUDA (NVIDIA GPU)
  - Transformers+CPU (범용)

- **임베딩**: nlpai-lab/KURE-v1

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

### ✅ Phase 3 완료
1. ~~서버 관리 스크립트~~ ✅

### ✅ Phase 4 완료 (v2.3.0~v2.4.0)
1. ~~2FA/TOTP 다중 인증~~ ✅
2. ~~조직 관리~~ ✅
3. ~~Hybrid RAG (문서 + 웹 검색)~~ ✅
4. ~~문서 버전 관리~~ ✅
5. ~~Brute Force 방어~~ ✅
6. ~~관리자 대시보드 강화~~ ✅

### ✅ Phase 5 완료 (v2.5.0)
1. ~~SearXNG + Crawl4AI 통합~~ ✅
2. ~~TTS 음성 합성~~ ✅
3. ~~CAPTCHA 시스템~~ ✅
4. ~~감사 로그~~ ✅
5. ~~Ollama LLM 백엔드~~ ✅
6. ~~멀티플랫폼 지원~~ ✅

### 🚧 진행 중
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
- [x] 2FA/TOTP 활성화 및 인증 흐름
- [x] 조직 생성/멤버 관리/접근제어
- [x] 웹 검색 통합 (Tavily, SearXNG)
- [x] 문서 버전 관리 (업로드/복원)
- [x] CAPTCHA 생성/검증
- [x] 감사 로그 기록/조회
- [x] TTS 음성 합성 (Edge TTS)
- [x] Ollama 백엔드 연동
- [x] 멀티플랫폼 자동 감지

### 🚧 진행 중인 테스트
- [ ] 스트리밍 DOM 업데이트 CPU 프로파일링
- [ ] 긴 응답 (1000+ 토큰) 성능 테스트
- [ ] 60fps 유지 확인

---

## 7. 향후 고려사항

### 고급 기능
- ~~음성 입력/출력~~ ✅ (TTS 구현 완료, STT 미구현)
- ~~다국어 지원 (영어, 일본어 등)~~ ✅ (TTS 10개 언어 지원)
- PDF 요약 기능
- 질문 템플릿 제공
- 대화 내보내기 (PDF, Markdown)

### 관리 기능
- ~~사용량 통계 대시보드~~ ✅ (관리자 대시보드 구현)
- 사용자 피드백 수집
- A/B 테스팅 시스템
- 품질 모니터링

### 인프라
- CDN 도입
- 로드 밸런싱
- ~~캐싱 레이어~~ ✅ (답변 캐싱, TTS 캐싱 구현)
- 모니터링 & 알람
