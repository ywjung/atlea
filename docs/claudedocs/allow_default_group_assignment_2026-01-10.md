# 기본 그룹 할당 제한 제거 (2026-01-10)

## 문제 상황

사용자가 새로 만든 조직에 기본 그룹("미분류")을 할당하려고 하면 다음 오류가 발생했습니다:

```
POST http://localhost:8000/api/organizations/{org_id}/groups/{default_group_id} 400 (Bad Request)
Server error detail: 기본 그룹은 조직에 할당할 수 없습니다
```

### 오류 발생 위치

`src/group_manager.py:1067-1069`
```python
# Prevent adding default group to organizations
if group_id == self.get_default_group_id():
    raise ValueError("기본 그룹은 조직에 할당할 수 없습니다")
```

## 수정 내용

### 파일: `src/group_manager.py`

**변경 전**:
```python
# Validate group exists
group_key = f'group:{group_id}'
if not self.client.exists(group_key):
    raise ValueError("그룹이 존재하지 않습니다")

# Prevent adding default group to organizations
if group_id == self.get_default_group_id():
    raise ValueError("기본 그룹은 조직에 할당할 수 없습니다")

# Check if already assigned
if self.is_group_in_organization(group_id, org_id):
    logger.info(f"Group {group_id} is already in organization {org_id}")
    return True
```

**변경 후**:
```python
# Validate group exists
group_key = f'group:{group_id}'
if not self.client.exists(group_key):
    raise ValueError("그룹이 존재하지 않습니다")

# Check if already assigned
if self.is_group_in_organization(group_id, org_id):
    logger.info(f"Group {group_id} is already in organization {org_id}")
    return True
```

**Docstring 수정**:
```python
# 변경 전
Raises:
    ValueError: If group or organization doesn't exist, or group is default group

# 변경 후
Raises:
    ValueError: If group or organization doesn't exist
```

### 수정 사항 요약

1. ✅ 기본 그룹 할당 방지 코드 제거 (3줄 삭제)
2. ✅ Docstring 업데이트 (제한 설명 제거)

## 테스트 결과

### 1. 기본 그룹 할당 테스트

```bash
# 테스트 조직에 기본 그룹 할당
$ curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/organizations/e0e4fd99-171a-4f52-88e9-79c94df4868b/groups/eea12d54-0c0b-4310-a122-efbfa3905a31"

{
  "success": true,
  "message": "그룹 '미분류'이(가) '테스트 조직' 조직에 추가되었습니다 (총 2개 조직에서 공유 중)",
  "group_id": "eea12d54-0c0b-4310-a122-efbfa3905a31",
  "org_id": "e0e4fd99-171a-4f52-88e9-79c94df4868b",
  "total_organizations": 2
}
```

### 2. 할당 확인

```bash
$ curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/organizations/e0e4fd99-171a-4f52-88e9-79c94df4868b/groups"

{
  "success": true,
  "groups": [
    {
      "id": "eea12d54-0c0b-4310-a122-efbfa3905a31",
      "name": "미분류",
      "document_count": 42,
      "org_count": 2
    }
  ],
  "total": 1
}
```

### 3. Redis 검증

```bash
# 조직 → 그룹 관계
$ redis-cli SMEMBERS "org:groups:e0e4fd99-171a-4f52-88e9-79c94df4868b"
eea12d54-0c0b-4310-a122-efbfa3905a31

# 그룹 → 조직 관계
$ redis-cli SMEMBERS "group:orgs:eea12d54-0c0b-4310-a122-efbfa3905a31"
default
e0e4fd99-171a-4f52-88e9-79c94df4868b
```

## 제한 제거 이유

### 왜 기존에 제한이 있었나?

원래 설계에서는 기본 그룹("미분류")을 특별한 용도로만 사용하려고 했습니다:
- 조직에 할당되지 않은 문서들의 임시 보관 장소
- 시스템 레벨의 전역 그룹

### 왜 제한을 제거했나?

1. **유연성**: 사용자가 기본 그룹을 일반 그룹처럼 사용하고 싶을 수 있습니다.
2. **일관성**: 모든 그룹이 동일한 방식으로 작동하는 것이 더 직관적입니다.
3. **N:M 관계**: N:M 설계에서는 한 그룹이 여러 조직에 속할 수 있으므로 제한이 불필요합니다.
4. **사용자 요청**: 실제 사용 중에 제한이 불편함을 발견했습니다.

## 영향 분석

### ✅ 긍정적 영향

1. **사용자 경험 개선**: 모든 그룹을 동일하게 관리 가능
2. **유연성 향상**: 기본 그룹을 원하는 조직에 자유롭게 할당
3. **코드 단순화**: 불필요한 검증 로직 제거

### ⚠️ 주의사항

1. **기본 그룹 삭제**: 여전히 불가능 (시스템 필수 그룹)
2. **문서 할당**: 재색인 시 그룹이 없는 문서는 계속 기본 그룹으로 할당됨
3. **다중 조직**: 기본 그룹이 여러 조직에 공유될 수 있음

### 🔒 유지되는 제한

다음 제한은 여전히 유효합니다:

1. **그룹 삭제**: 기본 그룹은 삭제 불가
2. **이름 변경**: 기본 그룹 이름 변경 제한 (선택적)
3. **조직 필수**: 모든 조직은 최소 1개 이상의 그룹 필요 (기본 그룹 가능)

## 사용 시나리오

### 시나리오 1: 기본 조직만 사용

```
조직: "기본 조직"
그룹: "미분류" (기본 그룹)
→ 모든 문서가 기본 그룹에 저장됨
```

### 시나리오 2: 여러 조직이 기본 그룹 공유

```
조직 A: "개발팀"
조직 B: "마케팅팀"
→ 둘 다 "미분류" 그룹 공유 가능
→ 공통 문서를 "미분류"에 보관
```

### 시나리오 3: 각 조직이 별도 그룹 사용

```
조직 A: "개발팀"
  - 그룹: "개발", "테스트"

조직 B: "마케팅팀"
  - 그룹: "캠페인", "자료"

→ 기본 그룹은 사용하지 않음 (선택적)
```

## 업그레이드 가이드

### 기존 시스템에 적용

이 변경사항은 **하위 호환성이 있습니다**:

1. ✅ 기존 데이터 영향 없음
2. ✅ 기존 조직-그룹 관계 유지
3. ✅ API 동작 변경 없음 (제한만 제거)

### 적용 방법

```bash
# 1. 코드 업데이트
git pull

# 2. 서버 재시작
uvicorn src.web_server:app --reload

# 3. 검증 (선택)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/organizations/{org_id}/groups/{default_group_id}"
```

## 결론

### 변경 요약

- **제거**: 기본 그룹 할당 제한 (3줄 코드)
- **결과**: 기본 그룹을 일반 그룹처럼 사용 가능
- **영향**: 긍정적, 하위 호환성 유지

### 사용자 이점

1. ✅ 더 유연한 그룹 관리
2. ✅ 일관된 사용자 경험
3. ✅ 복잡한 조직 구조 지원

---

**작성일**: 2026-01-10
**작성자**: Claude (Assistant)
**관련 파일**: `src/group_manager.py`
**커밋 메시지**: `feat: Allow default group assignment to organizations`
