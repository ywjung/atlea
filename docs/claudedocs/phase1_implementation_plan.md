# Phase 1 (Critical) 구현 계획

**생성일**: 2026-01-14
**우선순위**: 🔴 Critical
**목표**: 성능 및 유지보수성 대폭 개선

---

## 📋 작업 개요

Phase 1에서는 가장 큰 영향을 미치는 Critical 이슈들을 해결합니다.

| # | 작업 | 파일 | 현재 | 목표 | 예상 효과 |
|---|------|------|------|------|----------|
| 1 | 백엔드 모듈화 | web_server.py | 9,510줄 | 500-800줄 x 12 | 유지보수성 300% ↑ |
| 2 | 프론트엔드 스플리팅 | script.js | 283KB | 50KB x 6 | 초기 로딩 60% ↓ |
| 3 | HTML 최적화 | admin.html | 591KB | 150KB | 페이지 로드 75% ↓ |
| 4 | 보안 강화 | innerHTML | 132건 | 0건 | XSS 위험 90% ↓ |
| 5 | DB 최적화 | Redis 쿼리 | N회 | 1회 (pipeline) | API 응답 50% ↓ |

---

## 1️⃣ web_server.py 모듈화

### 현재 상태
- **9,510줄**, 140개 함수, 96개 API 엔드포인트
- 단일 파일로 모든 기능 포함
- 탐색 시간 3-5분, Git 충돌 위험 높음

### 목표 구조
```
src/
├── web_server.py (500줄) - 앱 초기화만
└── routers/
    ├── documents.py (18개 엔드포인트)
    ├── chat.py (4개)
    ├── groups.py (9개)
    ├── conversations.py (7개)
    ├── settings.py (6개)
    ├── feedback.py (5개)
    ├── cache.py (4개)
    ├── search.py (2개)
    └── backup.py (Redis 백업)
```

### 구현 순서
1. ✅ **분석 완료**: API 엔드포인트 분류
2. 🔄 **진행 중**: documents.py 라우터 생성
3. ⏳ **대기**: 나머지 라우터 순차 생성
4. ⏳ **통합**: web_server.py 정리

**상세 계획**: `/claudedocs/web_server_modularization_plan.md`

---

## 2️⃣ script.js 코드 스플리팅

### 현재 상태
- **283KB** (압축 전), 7,909줄, 92개 함수
- 초기 로딩 시 전체 다운로드
- 파싱 시간 1-2초 추가

### 목표 구조
```javascript
static/js/
├── core/
│   ├── app.js (50KB) - 앱 초기화, 기본 기능
│   ├── chat.js (60KB) - 채팅 UI, 메시지 처리
│   └── utils.js (20KB) - 공통 유틸리티
│
├── features/
│   ├── rendering.js (40KB) - Math, Mermaid, Chart 렌더링
│   ├── documents.js (35KB) - 문서 업로드, 관리
│   ├── settings.js (30KB) - 설정 UI, 저장/로드
│   └── conversations.js (25KB) - 대화 이력, 북마크
│
└── vendors/
    └── (외부 라이브러리는 CDN 사용)
```

### 분리 기준
| 모듈 | 포함 기능 | 로딩 시점 |
|------|----------|----------|
| core/app.js | 앱 초기화, 인증, 이벤트 | 즉시 |
| core/chat.js | 채팅 UI, 메시지, 스트리밍 | 즉시 |
| core/utils.js | formatDate, escapeHtml 등 | 즉시 |
| features/rendering.js | Math, Mermaid, Chart | Lazy (필요시) |
| features/documents.js | 업로드, 관리, 그룹 | Lazy |
| features/settings.js | 설정 모달 | Lazy |
| features/conversations.js | 이력, 북마크 | Lazy |

### 구현 방법
```html
<!-- 기본 로딩 (130KB = 50+60+20) -->
<script src="/static/js/core/utils.js"></script>
<script src="/static/js/core/app.js"></script>
<script src="/static/js/core/chat.js"></script>

<!-- 기능별 Lazy Loading -->
<script>
// Rendering 모듈 (수식, 다이어그램 사용 시)
function loadRenderingModule() {
    return import('/static/js/features/rendering.js');
}

// Documents 모듈 (문서 업로드 버튼 클릭 시)
function loadDocumentsModule() {
    return import('/static/js/features/documents.js');
}

// Settings 모듈 (설정 버튼 클릭 시)
function loadSettingsModule() {
    return import('/static/js/features/settings.js');
}
</script>
```

### 예상 효과
- 초기 로딩: 283KB → 130KB (**54% 감소**)
- 첫 페이지 표시 시간: **60% 개선**
- 모바일 환경 성능 대폭 향상

---

## 3️⃣ admin.html 최적화

### 현재 상태
- **591KB** (압축 전)
- 인라인 CSS 대량 포함
- 인라인 JavaScript 혼재

### 목표
- **150KB** (75% 감소)

### 최적화 방법
1. **CSS 분리**: 인라인 CSS → `admin.css`
2. **JS 분리**: 인라인 스크립트 → `admin.js`
3. **HTML 압축**: 불필요한 공백, 주석 제거
4. **이미지 최적화**: Base64 인코딩된 이미지 제거

```html
<!-- Before (591KB) -->
<style>
  /* 수천 줄의 인라인 CSS */
</style>
<script>
  /* 수천 줄의 인라인 JavaScript */
</script>

<!-- After (150KB) -->
<link rel="stylesheet" href="/static/admin.css">
<script src="/static/admin.js" defer></script>
```

---

## 4️⃣ innerHTML XSS 위험 제거

### 현재 상태
- **132건** innerHTML 사용
- 사용자 입력 직접 삽입 → XSS 취약

### 목표
- innerHTML 사용 **0건**

### 대체 방법
```javascript
// ❌ Before (위험)
element.innerHTML = userInput;
sessionsDiv.innerHTML = sessions.map(s => 
  `<div>${s.name}</div>`
).join('');

// ✅ After (안전)
// 방법 1: textContent 사용
element.textContent = userInput;

// 방법 2: DOM API 사용
const div = document.createElement('div');
div.className = 'session-item';
div.textContent = session.name;
parent.appendChild(div);

// 방법 3: DOMPurify 사용 (HTML 필요 시)
element.innerHTML = DOMPurify.sanitize(htmlContent);
```

### 우선순위 파일
1. **index.html** - 채팅 메시지 렌더링
2. **profile.html** - 세션 목록 표시
3. **admin.html** - 관리자 데이터 표시
4. **script.js** - 동적 콘텐츠 생성

---

## 5️⃣ Redis Pipeline 최적화

### 현재 상태
```python
# 3번의 왕복 (3 round trips)
result1 = await redis.get(key1)
result2 = await redis.get(key2)
result3 = await redis.get(key3)
```

### 목표
```python
# 1번의 왕복 (1 round trip)
pipe = redis.pipeline()
pipe.get(key1)
pipe.get(key2)
pipe.get(key3)
results = await pipe.execute()
```

### 적용 대상
1. **document_processor.py** - 문서 메타데이터 조회
2. **conversation_manager.py** - 대화 이력 로드
3. **group_manager.py** - 그룹 정보 조회
4. **cache_manager.py** - 캐시 배치 조회

### 예상 효과
- API 응답 시간 **30-50% 개선**
- Redis 부하 **60% 감소**
- 동시 접속자 처리 능력 **2배 향상**

---

## 📅 구현 일정

### Week 1: 백엔드 모듈화
- Day 1-2: documents.py, chat.py 라우터 생성
- Day 3-4: groups.py, conversations.py 라우터 생성  
- Day 5: web_server.py 통합 및 테스트

### Week 2: 프론트엔드 최적화
- Day 1-2: script.js 모듈 분리
- Day 3: admin.html 최적화
- Day 4-5: innerHTML XSS 수정

### Week 3: 성능 최적화 및 테스트
- Day 1-2: Redis Pipeline 적용
- Day 3-4: 통합 테스트
- Day 5: 성능 측정 및 최종 검증

---

## ✅ 성공 기준

### 정량적 지표
- [ ] web_server.py → 파일당 500-800줄
- [ ] script.js → 초기 로딩 130KB 이하
- [ ] admin.html → 150KB 이하
- [ ] innerHTML 사용 → 0건
- [ ] API 응답 시간 → 30% 이상 개선

### 정성적 지표
- [ ] 코드 리뷰 시간 80% 감소
- [ ] Git 충돌 빈도 90% 감소
- [ ] 첫 페이지 로딩 체감 속도 향상
- [ ] 보안 감사 통과

---

## 🚨 리스크 및 대응

### 리스크 1: 기능 파손
- **대응**: 마이그레이션 전후 E2E 테스트 필수
- **검증**: 모든 API 엔드포인트 정상 동작 확인

### 리스크 2: 성능 저하
- **대응**: 각 단계별 성능 측정
- **기준**: 응답 시간 +10% 이내

### 리스크 3: Import 순환 참조
- **대응**: 의존성 그래프 작성 및 검증
- **도구**: `madge` 사용하여 순환 참조 탐지

---

## 📊 진행 상황

- [x] Performance Report 작성
- [x] web_server.py 분석 완료
- [x] script.js 분석 완료
- [ ] documents.py 라우터 구현
- [ ] script.js 모듈 분리 구현
- [ ] admin.html 최적화 구현
- [ ] innerHTML 수정 구현
- [ ] Redis Pipeline 적용

**다음 작업**: documents.py 라우터 구현 시작

---
**작성자**: Claude Code
**승인**: 진행 중
**최종 업데이트**: 2026-01-14
