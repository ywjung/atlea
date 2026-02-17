# 하이브리드 RAG 우선순위 프롬프트 관리 시스템

> **Note (v3.0)**: 이 문서에서 언급된 Redis 기반 관리는 PostgreSQL SystemConfig 테이블 기반으로 마이그레이션되었습니다. `src/config/prompts.py`에서 `config_get_sync()`를 통해 프롬프트를 조회합니다.

## 개요

하이브리드 검색 시 정보 소스(웹 검색 결과 vs 로컬 문서)의 우선순위를 동적으로 결정하는 프롬프트 관리 시스템입니다.

## 구현 날짜
- **날짜**: 2026-02-03
- **상태**: ✅ 완료

## 문제점 분석

### 기존 문제
- **증상**: "2026년 AI 기술 트렌드" 같은 최신 정보 요청 시, 웹 검색 결과를 가져왔음에도 "문서에 정보가 없습니다" 라고 응답
- **원인**: `hybrid_rag.py`의 `_build_hybrid_prompt()` 메서드가 항상 로컬 문서를 최우선으로 참조하도록 하드코딩되어 있음
- **영향**: 사용자가 최신 정보를 요청해도 제공되지 않아 하이브리드 검색의 효과가 없었음

### 해결 방법
1. **동적 우선순위 결정**: 쿼리 분석 결과(`needs_fresh_info`, `benefits_from_web`)에 따라 프롬프트 선택
2. **Redis 기반 관리**: 하드코딩된 프롬프트를 Redis로 이동하여 관리자가 수정 가능하도록 함
3. **관리자 UI 제공**: 웹 인터페이스에서 5가지 우선순위 프롬프트를 편집할 수 있는 UI 추가

## 아키텍처

### 프롬프트 종류 (5가지)

| 프롬프트 타입 | Redis Key | 사용 시점 | 설명 |
|--------------|-----------|----------|------|
| **웹 정보 우선** | `system:prompt:hybrid_web_priority` | `needs_fresh_info=True` OR `benefits_from_web=True` + 웹/로컬 둘 다 있음 | 최신 트렌드, 미래 전망 질문에 사용 |
| **균등 참조** | `system:prompt:hybrid_balanced` | 웹/로컬 둘 다 있으며 특별한 조건 없음 | 웹과 로컬을 동등하게 참조 |
| **웹만 사용** | `system:prompt:hybrid_web_only` | 웹 결과만 있음 | 웹 검색 결과만 참조 |
| **로컬만 사용** | `system:prompt:hybrid_local_only` | 로컬 문서만 있음 | 내부 문서만 참조 |
| **로컬 우선** | `system:prompt:hybrid_local_priority` | 로컬 문서가 있으며 특별한 조건 없음 | 로컬 최우선, 웹은 보조 |

### 우선순위 결정 로직

```python
# src/config/prompts.py: get_hybrid_rag_priority_prompt()

if needs_fresh or benefits_web:
    if has_web and has_local:
        return HYBRID_WEB_PRIORITY  # 최신 정보 필요 → 웹 우선
    elif has_web:
        return HYBRID_WEB_ONLY
    elif has_local:
        return HYBRID_LOCAL_ONLY
else:
    if has_local:
        return HYBRID_LOCAL_PRIORITY  # 일반적인 경우 → 로컬 우선
    elif has_web:
        return HYBRID_BALANCED
```

## 구현 내용

### 1. 백엔드 구현

#### src/config/prompts.py
- **새로운 Redis 키 추가** (lines 10-19):
  ```python
  PROMPT_KEY_HYBRID_WEB_PRIORITY = "system:prompt:hybrid_web_priority"
  PROMPT_KEY_HYBRID_BALANCED = "system:prompt:hybrid_balanced"
  PROMPT_KEY_HYBRID_WEB_ONLY = "system:prompt:hybrid_web_only"
  PROMPT_KEY_HYBRID_LOCAL_ONLY = "system:prompt:hybrid_local_only"
  PROMPT_KEY_HYBRID_LOCAL_PRIORITY = "system:prompt:hybrid_local_priority"
  ```

- **기본 프롬프트 정의** (lines 756-855):
  ```python
  DEFAULT_HYBRID_WEB_PRIORITY_PROMPT = "⭐ 최신 웹 정보 {web_count}개와 내부 문서 {local_count}개를 균등하게 참조하세요.\n..."
  DEFAULT_HYBRID_BALANCED_PROMPT = "⭐ 웹 정보 {web_count}개와 내부 문서 {local_count}개를 균등하게 참조하세요.\n"
  DEFAULT_HYBRID_WEB_ONLY_PROMPT = "⭐ 웹 정보 {web_count}개를 참조하여 답변하세요.\n"
  DEFAULT_HYBRID_LOCAL_ONLY_PROMPT = "내부 문서 {local_count}개를 참조하되, 정보가 부족하면 명확히 언급하세요.\n"
  DEFAULT_HYBRID_LOCAL_PRIORITY_PROMPT = "⭐ 내부 문서 {local_count}개 최우선 참조. 부분 정보라도 활용. 웹/공식 문서는 보충용.\n"
  ```

- **프롬프트 선택 함수** (lines 756-855):
  ```python
  def get_hybrid_rag_priority_prompt(
      redis_client,
      needs_fresh: bool = False,
      benefits_web: bool = False,
      has_web: bool = False,
      has_local: bool = False,
      web_count: int = 0,
      local_count: int = 0
  ) -> str:
      # Redis에서 프롬프트 가져오기 + 동적 선택 로직
  ```

#### src/hybrid_rag.py
- **Import 추가** (line 1):
  ```python
  from .config.prompts import get_hybrid_rag_priority_prompt
  ```

- **하드코딩된 로직 제거 및 함수 호출** (lines 1425-1442):
  ```python
  # OLD (17 lines of hardcoded logic)
  if needs_fresh or benefits_web:
      if web and local:
          prompt += f"⭐ 최신 웹 정보 {len(web)}개와 내부 문서 {len(local)}개를 균등하게 참조하세요.\n"
          # ...

  # NEW (9 lines with Redis-based selection)
  priority_prompt = get_hybrid_rag_priority_prompt(
      redis_client=self.cache.redis,
      needs_fresh=needs_fresh,
      benefits_web=benefits_web,
      has_web=bool(web),
      has_local=bool(local),
      web_count=len(web) if web else 0,
      local_count=len(local) if local else 0
  )
  if priority_prompt:
      prompt += priority_prompt
  ```

#### src/routers/prompts.py
- **Import 추가** (lines 18-35):
  ```python
  from ..config.prompts import (
      # ...existing...
      PROMPT_KEY_HYBRID_WEB_PRIORITY,
      PROMPT_KEY_HYBRID_BALANCED,
      # ... (5개 추가)
      DEFAULT_HYBRID_WEB_PRIORITY_PROMPT,
      # ... (5개 추가)
  )
  ```

- **Request 모델 업데이트** (lines 54-67):
  ```python
  class PromptsUpdateRequest(BaseModel):
      basic: Optional[str] = None
      hybrid: Optional[str] = None
      tools_only: Optional[str] = None
      hybrid_web_priority: Optional[str] = None  # NEW
      hybrid_balanced: Optional[str] = None      # NEW
      hybrid_web_only: Optional[str] = None      # NEW
      hybrid_local_only: Optional[str] = None    # NEW
      hybrid_local_priority: Optional[str] = None # NEW
  ```

- **GET /api/admin/prompts 엔드포인트 업데이트**: 5개 프롬프트 추가 반환
- **PUT /api/admin/prompts 엔드포인트 업데이트**: 5개 프롬프트 저장 지원

### 2. 프론트엔드 구현

#### static/admin.html

**새로운 UI 섹션 추가** (after line 3967):
- **카드 헤더**: "🎯 하이브리드 RAG 우선순위 프롬프트"
- **설명 패널**: 프롬프트의 목적과 자동 선택 방식 설명
- **5개 탭**:
  - 🌐 웹 정보 우선 (cyan)
  - ⚖️ 균등 참조 (green)
  - 🌍 웹만 사용 (blue)
  - 📁 로컬만 사용 (orange)
  - 📚 로컬 우선 (pink)
- **각 탭별 설명**: 사용 시점과 동작 설명
- **textarea 편집기**: 각 프롬프트 편집 (최대 2,000자)
- **버튼**: "💾 우선순위 프롬프트 저장", "🔄 다시 불러오기"

**JavaScript 함수 추가** (after line 10706):
```javascript
// 탭 전환
function switchPriorityPromptTab(type) { ... }

// 프롬프트 로드
async function loadPriorityPrompts() { ... }

// 프롬프트 저장
async function saveAllPriorityPrompts() { ... }
```

**초기화 훅 추가** (lines 8010, 15263):
```javascript
if (typeof loadPriorityPrompts === 'function') loadPriorityPrompts();
```

## API 엔드포인트

### GET /api/admin/prompts
**응답 (업데이트됨)**:
```json
{
  "success": true,
  "prompts": {
    "basic": "...",
    "hybrid": "...",
    "tools_only": "...",
    "hybrid_web_priority": "⭐ 최신 웹 정보...",
    "hybrid_balanced": "⭐ 웹 정보와 내부 문서를...",
    "hybrid_web_only": "⭐ 웹 정보를 참조...",
    "hybrid_local_only": "내부 문서를 참조...",
    "hybrid_local_priority": "⭐ 내부 문서 최우선..."
  }
}
```

### PUT /api/admin/prompts
**요청 (업데이트됨)**:
```json
{
  "basic": "...",
  "hybrid": "...",
  "tools_only": "...",
  "hybrid_web_priority": "새로운 웹 우선 프롬프트...",
  "hybrid_balanced": "...",
  "hybrid_web_only": "...",
  "hybrid_local_only": "...",
  "hybrid_local_priority": "..."
}
```

**응답**:
```json
{
  "success": true,
  "message": "프롬프트 업데이트 완료: hybrid_web_priority, hybrid_balanced, ..."
}
```

## 사용 방법

### 관리자 UI에서 관리

1. **접속**: 관리자 페이지 → "⚙️ 설정" 탭 → "Prompts" 서브탭
2. **프롬프트 확인**:
   - 기존: "📝 시스템 프롬프트 관리" (3개)
   - 신규: "🎯 하이브리드 RAG 우선순위 프롬프트" (5개)
3. **편집**: 원하는 탭 선택 → textarea에서 프롬프트 수정
4. **저장**: "💾 우선순위 프롬프트 저장" 클릭
5. **초기화**: "🔄 다시 불러오기" 클릭 시 Redis에서 다시 로드

### Redis에서 직접 관리

```bash
# 웹 우선 프롬프트 조회
redis-cli GET "system:prompt:hybrid_web_priority"

# 웹 우선 프롬프트 수정
redis-cli SET "system:prompt:hybrid_web_priority" "⭐ 최신 웹 정보를 최우선으로 참조하세요..."

# 모든 우선순위 프롬프트 조회
redis-cli KEYS "system:prompt:hybrid_*"
```

## 테스트 시나리오

### 시나리오 1: 최신 정보 요청
**쿼리**: "2026년 AI 기술 트렌드는?"
- **분석 결과**: `needs_fresh_info=True`
- **선택된 프롬프트**: `HYBRID_WEB_PRIORITY`
- **기대 결과**: 웹 검색 결과를 우선 참조하여 최신 트렌드 응답

### 시나리오 2: 일반적인 내부 문서 질문
**쿼리**: "우리 회사의 휴가 정책은?"
- **분석 결과**: `needs_fresh_info=False`, `benefits_from_web=False`
- **선택된 프롬프트**: `HYBRID_LOCAL_PRIORITY`
- **기대 결과**: 로컬 문서를 최우선으로 참조

### 시나리오 3: 웹 검색만 필요한 경우
**쿼리**: "오늘 날씨는?"
- **분석 결과**: `needs_fresh_info=True`, 로컬 문서 없음
- **선택된 프롬프트**: `HYBRID_WEB_ONLY`
- **기대 결과**: 웹 검색 결과만 사용

## 성능 영향

- **Redis 조회 증가**: 프롬프트당 1회 Redis GET 호출 (캐싱 가능)
- **응답 시간**: 영향 없음 (프롬프트 선택 로직은 O(1))
- **유지보수성**: ⬆️ 향상 (하드코딩 제거, 관리자가 프롬프트 조정 가능)

## 향후 개선 사항

### Phase 1 (현재 완료)
- ✅ 5가지 우선순위 프롬프트 구현
- ✅ Redis 기반 관리 시스템
- ✅ 관리자 UI 제공

### Phase 2 (향후 고려)
- 📋 프롬프트 버전 관리 (변경 이력 추적)
- 📋 A/B 테스트 기능 (프롬프트 효과 비교)
- 📋 프롬프트 템플릿 라이브러리
- 📋 자동 최적화 (사용자 피드백 기반)
- 📋 멀티 언어 프롬프트 지원

## 파일 변경 요약

| 파일 | 변경 내용 | 라인 수 변화 |
|------|----------|-------------|
| `src/config/prompts.py` | 5개 Redis 키, 5개 기본값, 선택 함수 추가 | +110 |
| `src/hybrid_rag.py` | 하드코딩 제거, 함수 호출로 대체 | -17, +9 |
| `src/routers/prompts.py` | Import, 모델, GET/PUT 엔드포인트 업데이트 | +80 |
| `static/admin.html` | UI 섹션, JavaScript 함수, 초기화 훅 추가 | +200 |
| **총계** | | **+382** |

## 참고 자료

### 내부 문서
- `docs/FILE_UPLOAD_SECURITY.md` - Phase 2-3 파일 보안 (이전 작업)
- `docs/claudedocs/hybrid_search_fix_2026-02-03.md` - 하이브리드 검색 버그 수정 (이번 작업의 선행 버그 수정)

### 관련 코드
- `src/hybrid_rag.py:analyze_query()` - 쿼리 분석 로직
- `src/hybrid_rag.py:_build_hybrid_prompt()` - 프롬프트 생성 로직
- `src/config/prompts.py` - 프롬프트 설정 중앙 관리

## Changelog

### Version 2.3.0 (2026-02-03)
- ✅ 하이브리드 RAG 우선순위 프롬프트 시스템 구축
- ✅ Redis 기반 프롬프트 관리 구현
- ✅ 관리자 UI 추가 (5개 탭, 편집/저장 기능)
- ✅ 동적 프롬프트 선택 로직 구현
- ✅ API 엔드포인트 확장 (GET/PUT /api/admin/prompts)
- ✅ 문서화 및 테스트 시나리오 작성
