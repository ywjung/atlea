# 관리자 페이지 보안 감사 결과

**작업 일자**: 2025-12-31
**대상**: 관리자 페이지 (admin.html) 메뉴 기능 API 엔드포인트
**목적**: 모든 관리자 기능이 관리자 권한으로 보호되는지 확인

## 📊 전체 요약

| 상태 | 개수 | 설명 |
|------|------|------|
| ✅ 관리자 권한 있음 | 17개 | 정상 작동 |
| ⚠️ 사용자 인증만 | 5개 | **관리자 권한 추가 필요** |
| ❌ 엔드포인트 없음 | 4개 | **URL 수정 또는 구현 필요** |

## ❌ 문제점

### 1. 사용자 인증만 있음 (관리자 권한 추가 필요) - 5개

이 엔드포인트들은 현재 **일반 사용자도 접근 가능**하지만, 관리자 페이지에서 사용되므로 **관리자 권한이 필요**합니다.

| API 엔드포인트 | 함수명 | 사용 메뉴 | 위험도 |
|---------------|--------|----------|--------|
| `/api/documents` | `list_documents` | 대시보드, 문서 관리 | 🟡 중 |
| `/api/documents/upload` | `upload_document` | 문서 관리 | 🟡 중 |
| `/api/groups` | `list_groups` | 그룹 관리 | 🟡 중 |
| `/api/reindex` | `reindex` | 재색인 | 🔴 높음 |
| `/api/reindex/progress` | `get_reindex_progress` | 재색인 | 🟡 중 |

**위험도 설명**:
- 🔴 **높음**: 시스템 전체에 영향을 미치는 작업 (재색인 등)
- 🟡 **중**: 데이터 조회/수정 권한 (일반 사용자에게 불필요)

### 2. 엔드포인트 없음 또는 URL 불일치 - 4개

admin.html에서 호출하지만 실제로 존재하지 않거나 URL이 다른 엔드포인트입니다.

| admin.html에서 호출하는 URL | 실제 상태 | 조치 필요 |
|---------------------------|-----------|---------|
| `/api/auth/admin/stats` | ❌ 존재하지 않음 | 엔드포인트 구현 또는 admin.html 수정 |
| `/api/auth/admin/security-logs` | ⚠️ 실제 URL: `/api/admin/security-logs` | **admin.html URL 수정** |
| `/api/auth/webhooks` | ❌ 존재하지 않음 | 엔드포인트 구현 또는 admin.html 수정 |

**주의**: `/api/admin/security-logs`는 존재하며 관리자 권한이 있습니다! admin.html만 잘못된 URL을 호출하고 있습니다.

## ✅ 정상 작동 중인 엔드포인트 (17개)

다음 엔드포인트들은 이미 관리자 권한으로 올바르게 보호되고 있습니다.

### 감사 및 로그
- ✅ `/api/admin/audit/logs` - 감사 로그 조회
- ✅ `/api/admin/audit/actions` - 감사 액션 목록
- ✅ `/api/admin/security-logs` - 보안 로그 조회 (admin.html에서 잘못된 URL 호출)

### 모델 및 설정
- ✅ `/api/admin/models/backend` - 모델 백엔드 정보
- ✅ `/api/admin/models/config` - 모델 설정
- ✅ `/api/admin/models/list` - 모델 목록
- ✅ `/api/admin/settings` - 관리자 설정
- ✅ `/api/admin/system-prompt` - 시스템 프롬프트
- ✅ `/api/settings` - 시스템 설정

### 백업
- ✅ `/api/redis/backup/list` - 백업 목록
- ✅ `/api/redis/backup/create` - 백업 생성
- ✅ `/api/redis/backup/restore` - 백업 복원
- ✅ `/api/redis/backup/delete` - 백업 삭제
- ✅ `/api/redis/backup/schedule` - 백업 스케줄

### 피드백 및 캐시
- ✅ `/api/admin/feedback/stats` - 피드백 통계
- ✅ `/api/cache/stats` - 캐시 통계
- ✅ `/api/cache/clear` - 캐시 삭제
- ✅ `/api/reindex/cancel` - 재색인 취소

## 🔧 권장 조치사항

### 우선순위 1: 관리자 권한 추가 (5개 엔드포인트)

다음 엔드포인트들에 `require_admin()` 호출 추가가 필요합니다:

```python
# 1. /api/documents (GET)
@app.get("/api/documents", tags=["Documents"])
async def list_documents(
    request: Request,  # 추가
    current_user: dict = Depends(get_current_active_user)
):
    # 함수 시작 부분에 추가:
    require_admin(request, redis_client)
    # ...

# 2. /api/documents/upload (POST)
@app.post("/api/documents/upload", tags=["Documents"])
async def upload_document(
    request: Request,  # 추가
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user)
):
    # 함수 시작 부분에 추가:
    redis_client = request.app.state.cache_manager.redis
    require_admin(request, redis_client)
    # ...

# 3. /api/groups (GET, POST, ...)
@app.get("/api/groups", tags=["Groups"])
async def list_groups(
    request: Request,  # 추가
    current_user: dict = Depends(get_current_active_user)
):
    # 함수 시작 부분에 추가:
    redis_client = request.app.state.cache_manager.redis
    require_admin(request, redis_client)
    # ...

# 4. /api/reindex (POST)
@app.post("/api/reindex", tags=["Documents"])
async def reindex(
    request: Request,  # 추가
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user)
):
    # 함수 시작 부분에 추가:
    redis_client = request.app.state.cache_manager.redis
    require_admin(request, redis_client)
    # ...

# 5. /api/reindex/progress (GET)
@app.get("/api/reindex/progress", tags=["Documents"])
async def get_reindex_progress(
    request: Request,  # 추가
    current_user: dict = Depends(get_current_active_user)
):
    # 함수 시작 부분에 추가:
    redis_client = request.app.state.cache_manager.redis
    require_admin(request, redis_client)
    # ...
```

### 우선순위 2: admin.html URL 수정

**보안 로그 URL 수정** (1곳):

```javascript
// Before
const url = '/api/auth/admin/security-logs';

// After
const url = '/api/admin/security-logs';
```

**파일 위치**: `static/admin.html` 라인 ~3430

### 우선순위 3: 누락된 엔드포인트 처리

다음 엔드포인트들은 admin.html에서 호출하지만 존재하지 않습니다:

1. **`/api/auth/admin/stats`** - 사용자 통계
   - **옵션 A**: 엔드포인트 구현
   - **옵션 B**: admin.html에서 해당 기능 제거 또는 다른 엔드포인트 사용

2. **`/api/auth/webhooks`** - 웹훅 관리
   - **옵션 A**: 엔드포인트 구현
   - **옵션 B**: admin.html에서 웹훅 메뉴 제거

## 📝 메뉴별 상세 분석

### 📊 대시보드
- ❌ `/api/auth/admin/stats` - 존재하지 않음
- ⚠️ `/api/documents` - 사용자 인증만
- ✅ `/api/cache/stats` - 관리자 권한 있음
- ✅ `/api/admin/feedback/stats` - 관리자 권한 있음

### 👥 사용자 관리
- ❌ `/api/auth/admin/stats` - 존재하지 않음

### 📄 문서 관리
- ⚠️ `/api/documents` - 사용자 인증만
- ⚠️ `/api/documents/upload` - 사용자 인증만

### 📁 그룹 관리
- ⚠️ `/api/groups` - 사용자 인증만

### 🔐 보안 로그
- ⚠️ `/api/auth/admin/security-logs` - URL 불일치 (실제: `/api/admin/security-logs`)

### 📋 감사 로그
- ✅ `/api/admin/audit/logs` - 관리자 권한 있음
- ✅ `/api/admin/audit/actions` - 관리자 권한 있음

### 🔔 웹훅
- ❌ `/api/auth/webhooks` - 존재하지 않음

### 🤖 모델 설정
- ✅ `/api/admin/models/backend` - 관리자 권한 있음
- ✅ `/api/admin/models/config` - 관리자 권한 있음
- ✅ `/api/admin/models/list` - 관리자 권한 있음

### ⚙️ 시스템 설정
- ✅ `/api/admin/settings` - 관리자 권한 있음
- ✅ `/api/admin/system-prompt` - 관리자 권한 있음
- ✅ `/api/settings` - 관리자 권한 있음

### 💾 백업
- ✅ `/api/redis/backup/list` - 관리자 권한 있음
- ✅ `/api/redis/backup/create` - 관리자 권한 있음
- ✅ `/api/redis/backup/restore` - 관리자 권한 있음
- ✅ `/api/redis/backup/delete` - 관리자 권한 있음
- ✅ `/api/redis/backup/schedule` - 관리자 권한 있음

### 🔄 재색인
- ⚠️ `/api/reindex` - 사용자 인증만
- ⚠️ `/api/reindex/progress` - 사용자 인증만
- ✅ `/api/reindex/cancel` - 관리자 권한 있음

### 💾 캐시
- ✅ `/api/cache/stats` - 관리자 권한 있음
- ✅ `/api/cache/clear` - 관리자 권한 있음

## 🔒 보안 영향 평가

### 현재 상태 (수정 전)
- ⚠️ **일반 사용자가 재색인을 시작할 수 있음** - 시스템 성능에 영향
- ⚠️ 일반 사용자가 모든 문서 목록을 볼 수 있음
- ⚠️ 일반 사용자가 문서를 업로드할 수 있음
- ⚠️ 일반 사용자가 그룹 정보를 볼 수 있음

### 수정 후 예상 상태
- ✅ 관리자만 재색인 제어 가능
- ✅ 관리자만 전체 문서 목록 조회 가능
- ✅ 관리자만 문서 업로드 가능
- ✅ 관리자만 그룹 관리 가능

## 검증 스크립트

이 감사는 다음 스크립트를 사용하여 수행되었습니다:
- `scripts/verify_admin_endpoints.py` - 관리자 페이지 API 엔드포인트 권한 검증

수정 후 동일한 스크립트로 재검증 권장합니다.
