# web_server.py 모듈화 계획

**생성일**: 2026-01-14
**분석자**: Claude Code
**상태**: 📋 계획 수립 완료

---

## 📊 현재 상태 분석

### 파일 통계
- **총 라인 수**: 9,510줄
- **함수/클래스**: 140개
- **API 엔드포인트**: 96개
- **Import 문**: 222개

### API 엔드포인트 분포
| 카테고리 | 엔드포인트 수 | 비중 |
|---------|-------------|------|
| Admin | 27 | 28% |
| Documents | 18 | 19% |
| Groups | 9 | 9% |
| Conversations | 7 | 7% |
| Settings | 6 | 6% |
| System | 5 | 5% |
| Feedback | 5 | 5% |
| Query | 4 | 4% |
| Cache | 4 | 4% |
| User | 2 | 2% |
| Search | 2 | 2% |
| Quality | 2 | 2% |
| Conversion | 1 | 1% |
| **기타** (예외처리, 이벤트 등) | 4 | 4% |
| **총계** | **96** | **100%** |

### 주요 문제점
1. **유지보수 어려움**: 9,510줄을 탐색하는데 평균 3-5분 소요
2. **Git 충돌 위험**: 단일 파일 변경으로 머지 충돌 가능성 높음
3. **테스트 어려움**: 모듈별 단위 테스트 작성 불가
4. **메모리 사용량**: 전체 파일 로딩으로 메모리 낭비
5. **코드 재사용**: 관련 기능끼리 그룹화되지 않아 중복 코드 증가

---

## 🎯 모듈화 목표

### 정량적 목표
- 파일당 평균 **500-800줄** 유지
- 단일 파일 최대 **1,200줄** 이하
- 모듈별 **응집도 80% 이상**
- 모듈 간 **결합도 30% 이하**

### 정성적 목표
- 기능별 명확한 분리
- 독립적인 테스트 가능
- 재사용성 향상
- 팀 협업 효율성 증대

---

## 📁 제안 구조

### Phase 1: 라우터 분리 (Critical)

```
src/
├── web_server.py (약 500줄)
│   ├── 앱 초기화
│   ├── 미들웨어 설정
│   ├── 라우터 등록
│   ├── 예외 처리자
│   ├── 이벤트 핸들러 (startup/shutdown)
│   └── 헬스체크, Favicon 등 기본 엔드포인트
│
└── routers/
    ├── __init__.py
    ├── auth.py ✅ (이미 존재 - 인증/인가)
    ├── admin.py ✅ (이미 존재 - 관리자 기능)
    ├── organizations.py ✅ (이미 존재 - 조직 관리)
    │
    ├── documents.py (NEW - 18개 엔드포인트)
    │   ├── /api/reindex
    │   ├── /api/reindex/progress
    │   ├── /api/reindex/cancel
    │   ├── /api/documents/*
    │   └── /api/upload/*
    │
    ├── chat.py (NEW - 4개 엔드포인트)
    │   ├── /api/query
    │   ├── /api/query/stream
    │   ├── /api/chat/*
    │   └── WebSocket /ws/chat (if exists)
    │
    ├── groups.py (NEW - 9개 엔드포인트)
    │   ├── /api/groups/*
    │   ├── /api/user/groups
    │   └── 그룹 관련 CRUD
    │
    ├── conversations.py (NEW - 7개 엔드포인트)
    │   ├── /api/conversations/*
    │   ├── /api/conversation/history
    │   └── 대화 이력 관리
    │
    ├── settings.py (NEW - 6개 엔드포인트)
    │   ├── /api/user/preferences
    │   ├── /api/settings/*
    │   └── 시스템 설정
    │
    ├── feedback.py (NEW - 5개 엔드포인트)
    │   ├── /api/feedback
    │   ├── /api/feedback/analytics
    │   └── 피드백 분석
    │
    ├── cache.py (NEW - 4개 엔드포인트)
    │   ├── /api/cache/*
    │   └── 캐시 관리
    │
    ├── search.py (NEW - 2개 엔드포인트)
    │   ├── /api/web-search
    │   └── /api/docs-search
    │
    └── backup.py (NEW - Redis 백업 관련)
        ├── /api/redis/backup/create
        ├── /api/redis/backup/list
        ├── /api/redis/backup/restore
        ├── /api/redis/backup/download
        ├── /api/redis/backup/delete
        └── /api/redis/backup/schedule
```

### Phase 2: 서비스 레이어 분리 (High)

```
src/services/
├── __init__.py
├── document_service.py ✅ (이미 존재)
│
├── llm_service.py (NEW)
│   ├── LLM 초기화 및 관리
│   ├── 프롬프트 처리
│   └── 스트리밍 응답 처리
│
├── embedding_service.py (NEW)
│   ├── 임베딩 모델 관리
│   ├── 벡터 생성
│   └── 배치 처리
│
├── vector_search_service.py (NEW)
│   ├── 벡터 DB 쿼리
│   ├── 유사도 검색
│   └── 하이브리드 RAG
│
├── conversation_service.py (NEW)
│   ├── 대화 이력 관리
│   ├── 컨텍스트 유지
│   └── 세션 관리
│
└── cache_service.py (NEW)
    ├── Redis 캐시 관리
    ├── 캐시 무효화
    └── TTL 관리
```

### Phase 3: 유틸리티 정리 (Medium)

```
src/utils/
├── __init__.py
├── performance_utils.py ✅ (이미 존재)
│
├── response_utils.py (NEW)
│   ├── 응답 포맷팅
│   ├── 에러 메시지 생성
│   └── 공통 응답 헬퍼
│
├── validation_utils.py (NEW)
│   ├── 입력 검증
│   ├── 파일 검증
│   └── 보안 검증
│
└── redis_utils.py (NEW)
    ├── Redis 연결 헬퍼
    ├── Pipeline 유틸리티
    └── 키 관리
```

---

## 🔄 마이그레이션 전략

### Step 1: 백업 및 브랜치 생성
```bash
git checkout -b feature/modularize-web-server
cp src/web_server.py src/web_server.py.backup_$(date +%Y%m%d)
```

### Step 2: 라우터 파일 생성 (우선순위 순)
1. **documents.py** (18개 엔드포인트 - 가장 많음)
2. **chat.py** (4개 - 핵심 기능)
3. **groups.py** (9개)
4. **conversations.py** (7개)
5. **settings.py** (6개)
6. **feedback.py** (5개)
7. **cache.py** (4개)
8. **search.py** (2개)
9. **backup.py** (Redis 백업)

### Step 3: 각 라우터 작성 패턴
```python
# src/routers/documents.py 예시
from fastapi import APIRouter, Depends, HTTPException
from typing import List

router = APIRouter(prefix="/api", tags=["Documents"])

# 의존성 (web_server.py에서 이동)
async def get_current_user(...):
    # 인증 로직
    pass

# 엔드포인트
@router.post("/reindex")
async def reindex_documents(
    request: Request,
    current_user = Depends(get_current_user)
):
    # 기존 로직 이동
    pass

@router.get("/reindex/progress")
async def get_reindex_progress(...):
    pass
```

### Step 4: web_server.py 통합
```python
# src/web_server.py
from fastapi import FastAPI
from src.routers import documents, chat, groups, conversations

app = FastAPI()

# 라우터 등록
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(groups.router)
app.include_router(conversations.router)
# ...
```

### Step 5: 테스트 및 검증
```bash
# 1. Import 에러 체크
python -m py_compile src/web_server.py

# 2. 서버 시작 테스트
uvicorn src.web_server:app --reload

# 3. API 엔드포인트 테스트
curl http://localhost:8085/docs

# 4. 기능 테스트
pytest tests/
```

---

## 📝 체크리스트

### Phase 1: 라우터 분리
- [ ] documents.py 생성 (18개 엔드포인트)
- [ ] chat.py 생성 (4개 엔드포인트)
- [ ] groups.py 생성 (9개 엔드포인트)
- [ ] conversations.py 생성 (7개 엔드포인트)
- [ ] settings.py 생성 (6개 엔드포인트)
- [ ] feedback.py 생성 (5개 엔드포인트)
- [ ] cache.py 생성 (4개 엔드포인트)
- [ ] search.py 생성 (2개 엔드포인트)
- [ ] backup.py 생성 (Redis 백업)
- [ ] web_server.py 정리 (라우터 등록만)

### Phase 2: 서비스 분리
- [ ] llm_service.py 생성
- [ ] embedding_service.py 생성
- [ ] vector_search_service.py 생성
- [ ] conversation_service.py 생성
- [ ] cache_service.py 생성

### Phase 3: 유틸리티 정리
- [ ] response_utils.py 생성
- [ ] validation_utils.py 생성
- [ ] redis_utils.py 생성

### 테스트
- [ ] 모든 API 엔드포인트 동작 확인
- [ ] Import 에러 없음 확인
- [ ] 성능 테스트 (응답 시간 변화 없음)
- [ ] 메모리 사용량 확인

---

## 📊 예상 효과

### 정량적 효과
| 항목 | 이전 | 이후 | 개선율 |
|-----|------|------|--------|
| 파일당 평균 라인 수 | 9,510 | 500-800 | 91% |
| 코드 탐색 시간 | 3-5분 | 30초 | 80% |
| Git 충돌 빈도 | 높음 | 낮음 | 90% |
| 테스트 커버리지 | 30% | 70%+ | 133% |

### 정성적 효과
- ✅ **유지보수성**: 관련 코드가 한곳에 모여 있어 수정 용이
- ✅ **가독성**: 파일 크기 감소로 전체 구조 파악 용이
- ✅ **협업**: 모듈별 담당자 지정 가능, 충돌 감소
- ✅ **테스트**: 모듈별 독립 테스트 가능
- ✅ **재사용**: 서비스 레이어 분리로 다른 프로젝트 재사용 가능

---

## ⚠️ 주의사항

### 1. 의존성 관리
- 순환 참조 방지 (circular imports)
- 공통 의존성은 별도 모듈로 분리

### 2. 상태 관리
- `app.state`에 저장된 객체 접근 패턴 유지
- 싱글톤 객체 (cache_manager, security_logger 등) 처리

### 3. 테스트 커버리지
- 마이그레이션 전후 기능 동일성 보장
- 엔드투엔드 테스트 필수

### 4. 성능 영향
- Import 시간 증가 가능성 (미미함)
- 실제 응답 시간은 변화 없어야 함

---

## 🚀 다음 단계

1. **즉시 시작 가능**: documents.py 라우터 생성 (가장 많은 엔드포인트)
2. **우선순위 높음**: chat.py (핵심 기능)
3. **순차 진행**: 나머지 라우터 파일 생성

**승인 후 작업 시작 예정**

---
**작성자**: Claude Code
**검토 필요**: 프로젝트 담당자
**예상 소요 시간**: Phase 1 (3-4시간), Phase 2-3 (추가 2-3시간)
