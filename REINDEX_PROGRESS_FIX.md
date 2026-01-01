# 재색인 진행 상태 관리 개선 사항

## 문제점

재색인 작업이 실패하거나 오류가 발생했을 때, Redis의 `reindex:progress` 상태가 "오류 발생" 상태로 남아있어 프론트엔드가 무한히 폴링을 계속하는 문제가 있었습니다.

**증상:**
- 콘솔에 반복적으로 "Response data: {in_progress: true, step: '오류 발생', progress: 0, ...}" 메시지
- `/api/reindex/progress` 엔드포인트에 대한 지속적인 폴링
- 수동으로 Redis 키를 삭제하지 않는 한 해결되지 않음

## 해결 방법

### 1. TTL 기반 자동 만료 (핵심 개선)

모든 재색인 진행 상태 업데이트에 **1시간 TTL(Time To Live)**을 설정하여 자동으로 만료되도록 구현했습니다.

**헬퍼 함수 추가** (`src/web_server.py:3315-3345`):

```python
def set_reindex_progress(redis_client, step: str, progress: str = "0",
                        current_item: str = "", total_items: str = "0",
                        start_time: str = None, ttl: int = 3600):
    """
    재색인 진행 상태 설정 (자동 만료 포함)

    Args:
        redis_client: Redis 클라이언트
        step: 진행 단계
        progress: 진행률 (0-100)
        current_item: 현재 처리 중인 항목
        total_items: 전체 항목 수
        start_time: 시작 시간 (선택사항)
        ttl: 자동 만료 시간 (초, 기본 1시간)
    """
    mapping = {
        "step": step,
        "progress": progress,
        "current_item": current_item,
        "total_items": total_items
    }
    if start_time:
        mapping["start_time"] = start_time

    redis_client.hset("reindex:progress", mapping=mapping)
    # 자동 만료 설정 (1시간 후 자동 삭제)
    redis_client.expire("reindex:progress", ttl)


def clear_reindex_progress(redis_client):
    """재색인 진행 상태 초기화"""
    redis_client.delete("reindex:progress")
```

### 2. 일관된 진행 상태 관리

**기존 방식 (14개 인스턴스):**
```python
vector_db.client.hset("reindex:progress", mapping={
    "step": "...",
    "progress": "...",
    "current_item": "...",
    "total_items": "..."
})
# TTL 설정 없음 - 영구히 남음!
```

**개선된 방식:**
```python
set_reindex_progress(
    vector_db.client,
    step="...",
    progress="...",
    current_item="...",
    total_items="..."
)
# 자동으로 1시간 TTL 설정됨
```

**변경된 위치:**
- `index_pdfs()` 함수: 9개 인스턴스
- `reindex_with_zero_downtime()` 함수: 4개 인스턴스
- `/api/reindex/cancel` 엔드포인트: 1개 인스턴스

### 3. 관리자용 수동 초기화 API

긴급 상황에서 관리자가 수동으로 진행 상태를 초기화할 수 있는 API 추가:

**엔드포인트:** `DELETE /api/reindex/progress`

```python
@app.delete("/api/reindex/progress", tags=["Documents"])
async def clear_reindex_progress_api(
    request: Request,
    user: dict = Depends(require_admin)
):
    """
    재색인 진행 상태 초기화 (관리자 전용)

    에러 상태에 갇힌 진행 상태를 수동으로 초기화합니다.
    정상적인 경우 TTL에 의해 자동으로 만료되지만,
    필요시 관리자가 수동으로 초기화할 수 있습니다.
    """
    clear_reindex_progress(vector_db.client)
    return {"success": True, "message": "진행 상태가 초기화되었습니다"}
```

**사용 방법:**
```bash
# 관리자 권한으로 호출
curl -X DELETE http://localhost:8000/api/reindex/progress \
  -H "Authorization: Bearer <admin_token>"
```

## 효과

### 자동 복구
- **1시간 후** 자동으로 진행 상태가 삭제되어 무한 폴링 문제 해결
- 서버 재시작이나 수동 개입 없이 자동으로 정상 상태로 복구

### 일관성
- 모든 진행 상태 업데이트가 동일한 방식으로 처리됨
- TTL이 누락될 위험 제거

### 관리 편의성
- 긴급 상황 시 관리자가 즉시 초기화 가능
- 명확한 로깅으로 문제 추적 용이

## 추가 고려사항

### TTL 시간 조정
기본값은 1시간(3600초)이지만, 필요시 함수 호출 시 조정 가능:

```python
# 30분으로 설정
set_reindex_progress(
    vector_db.client,
    step="처리 중",
    progress="50",
    ttl=1800  # 30분
)
```

### 프론트엔드 개선 권장사항
추가적인 안정성을 위해 프론트엔드에서도 개선 가능:

1. **폴링 타임아웃 설정**: 일정 시간(예: 10분) 후 자동 중지
2. **에러 감지**: "오류 발생" 상태 감지 시 폴링 중지
3. **재시도 제한**: 동일 에러 반복 시 폴링 중지

## 변경 파일

- `src/web_server.py`:
  - 헬퍼 함수 추가 (라인 3311-3345)
  - 14개 인스턴스 업데이트
  - 새 API 엔드포인트 추가 (라인 3511-3538)

## 테스트 방법

1. **정상 케이스**: 재색인 완료 시 "완료" 상태로 정상 종료
2. **에러 케이스**: 재색인 실패 시 1시간 후 자동 삭제 확인
3. **수동 초기화**: DELETE API 호출하여 즉시 삭제 확인

```bash
# Redis에서 TTL 확인
redis-cli TTL reindex:progress
# 결과: 3600 (초) 또는 그 이하

# 수동 초기화 테스트
curl -X DELETE http://localhost:8000/api/reindex/progress \
  -H "Authorization: Bearer <token>"
```

## 결론

이제 재색인 진행 상태가 영구히 남아 있는 문제가 근본적으로 해결되었습니다:

✅ **자동 만료**: 1시간 TTL로 자동 정리
✅ **일관성**: 모든 업데이트에 TTL 자동 적용
✅ **관리 편의성**: 관리자용 수동 초기화 API
✅ **로깅**: 명확한 로그로 문제 추적 가능

사용자는 더 이상 Redis를 직접 조작하거나 서버를 재시작할 필요가 없습니다.
