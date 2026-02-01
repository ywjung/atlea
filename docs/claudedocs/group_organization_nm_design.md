# 그룹-조직 N:M 관계 설계

## 개요

그룹을 여러 조직에서 공유할 수 있도록 1:1 관계를 N:M 관계로 변경합니다.

## 데이터 모델 변경

### 현재 (1:1)
```redis
# 그룹 데이터
group:{group_id} → {
    id: str,
    name: str,
    org_id: str,  # 단일 조직
    ...
}

# 조직의 그룹 인덱스
org:groups:{org_id} → SET(group_ids)
org:groups:root:{org_id} → SET(root_group_ids)
```

### 변경 후 (N:M)
```redis
# 그룹 데이터 - org_id 제거
group:{group_id} → {
    id: str,
    name: str,
    created_by_org: str,  # 최초 생성 조직 (optional, 추적용)
    ...
}

# 그룹이 속한 조직들 (NEW)
group:orgs:{group_id} → SET(org_ids)

# 조직의 그룹들 (기존 유지)
org:groups:{org_id} → SET(group_ids)
org:groups:root:{org_id} → SET(root_group_ids)
```

## API 변경

### 기존
- `POST /api/organizations/{org_id}/groups/{group_id}` - 그룹을 조직으로 **이동**
  - 그룹의 org_id를 변경
  - 기존 조직에서 제거, 새 조직에 추가

### 변경 후
- `POST /api/organizations/{org_id}/groups/{group_id}` - 그룹을 조직에 **추가**
  - `group:orgs:{group_id}`에 org_id 추가
  - `org:groups:{org_id}`에 group_id 추가
  - 기존 조직 관계 유지

- `DELETE /api/organizations/{org_id}/groups/{group_id}` - 조직에서 그룹 **제거** (NEW)
  - `group:orgs:{group_id}`에서 org_id 제거
  - `org:groups:{org_id}`에서 group_id 제거
  - 마지막 조직에서 제거 시 경고 또는 방지

## 권한 체크 변경

### 기존
```python
# 사용자의 조직 그룹만 조회
def get_all_groups(org_id):
    return groups where group.org_id == org_id
```

### 변경 후
```python
# 사용자의 조직에 할당된 그룹들 조회
def get_all_groups(org_id):
    group_ids = redis.smembers(f'org:groups:{org_id}')
    return [get_group(gid) for gid in group_ids]

# 그룹 접근 권한 체크
def can_access_group(user_org_id, group_id):
    group_orgs = redis.smembers(f'group:orgs:{group_id}')
    return user_org_id in group_orgs
```

## 마이그레이션 전략

### 단계 1: 데이터 변환
```python
for each group:
    org_id = group.get('org_id')
    if org_id:
        # 그룹-조직 관계 생성
        redis.sadd(f'group:orgs:{group_id}', org_id)
        # org_id 필드는 유지 (하위 호환성)
```

### 단계 2: 코드 업데이트
- GroupManager 메서드 수정
- 권한 체크 로직 변경
- API 엔드포인트 수정

### 단계 3: 검증
- 기존 기능 정상 작동 확인
- 새로운 중복 할당 기능 테스트

## 하위 호환성

기존 `org_id` 필드를 `created_by_org`로 rename하여 유지:
- 그룹을 최초 생성한 조직 추적
- 필요시 "소유" 조직 개념 유지

## 계층 구조 처리

**중요**: 부모-자식 그룹 관계가 있는 경우:
- **옵션 A**: 부모와 자식을 독립적으로 할당 (복잡도 낮음)
- **옵션 B**: 부모를 할당하면 자식도 자동 할당 (일관성 높음)

**선택**: 옵션 A - 각 그룹을 독립적으로 관리

## UI 변경

### 그룹 목록
```
현재: 그룹 이동 (이동 후 기존 조직에서 제거됨)
변경: 그룹 추가 (기존 조직 관계 유지)
     + 그룹 제거 버튼 추가
```

### 표시
```
그룹 카드에 공유 상태 표시:
- "📁 그룹명 (3개 조직에서 사용 중)"
```

## 주의사항

1. **마지막 조직 제거 방지**
   - 그룹이 최소 1개 조직에는 속해야 함
   - 또는 마지막 제거 시 그룹 자체를 삭제

2. **문서 접근 권한**
   - 그룹의 문서는 그룹이 속한 모든 조직의 사용자가 접근 가능

3. **검색 결과**
   - 사용자는 자신의 조직에 할당된 그룹의 문서만 검색

4. **그룹 수정 권한**
   - 시스템 관리자만 그룹 수정 가능
   - 또는 그룹이 속한 모든 조직의 관리자 허용

## 구현 순서

1. ✅ 설계 문서 작성
2. ⏳ GroupManager에 N:M 메서드 추가
3. ⏳ 마이그레이션 스크립트 작성
4. ⏳ API 엔드포인트 수정
5. ⏳ 권한 체크 로직 업데이트
6. ⏳ UI 수정 (추가/제거 버튼)
7. ⏳ 테스트 및 검증
