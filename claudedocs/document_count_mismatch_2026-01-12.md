# 문서 개수 불일치 문제 분석

**작성일**: 2026-01-12
**문제**: 관리자 화면(44개) vs 사용자 화면(43개) 문서 개수 불일치
**상태**: 🔍 조사 중

---

## 📊 현재 상황

### 문서 개수
- **파일 시스템**: 44개 문서 ✅
- **Redis doc:group 매핑**: 44개 ✅
- **관리자 화면**: 44개 표시 ✅
- **사용자 화면(ywjung99)**: 43개 표시 ❌ (1개 누락)
- **청크 수**: 3,983개 (정확함)

### 그룹 분포
```
📊 그룹별 문서 분포:
  미분류 (eea12d54-0c0b-4310-a122-efbfa3905a31): 42개
  개발   (256496ee-8a0c-455b-8b16-97e7a102544f):  2개

총계: 44개 문서
```

---

## 🔍 발견 사항

### 1. 중복된 "미분류" 그룹

Redis에서 발견된 그룹:

```bash
$ docker exec chatbot_redis redis-cli --scan --pattern "group:*"

group:db509513-b431-4cb6-9237-9ac2b1a646fc  # 미분류 (0 docs) ⚠️
group:256496ee-8a0c-455b-8b16-97e7a102544f  # 개발 (2 docs)
group:eea12d54-0c0b-4310-a122-efbfa3905a31  # 미분류 (42 docs)
group:default  # String 타입 (그룹이 아님)
```

**문제점**:
- "미분류" 그룹이 2개 존재
- `db509513-b431-4cb6-9237-9ac2b1a646fc` 그룹은 0개 문서 (사용 안 함)
- `eea12d54-0c0b-4310-a122-efbfa3905a31` 그룹에 실제 42개 문서

### 2. 문서 필터링 로직

**파일**: `src/web_server.py:5029-5037`

```python
# Filter by organization: check if document's group belongs to user's org
doc_group_id = cache_manager.redis.get(f'doc:group:{pdf_file.name}')
if doc_group_id:
    doc_group_id = doc_group_id.decode('utf-8')
    # Skip documents not in user's organization groups
    if doc_group_id not in org_group_ids:
        continue
# If document has no group, skip it (documents without groups are not accessible)
else:
    continue
```

**로직**:
1. 문서의 그룹 ID 확인 (`doc:group:{filename}`)
2. 그룹 ID가 `org_group_ids`에 포함되어 있으면 표시
3. 그룹 ID가 없으면 스킵

### 3. 사용자 정보

**ywjung99@naver.com**:
```
user_id: 2f0c338f-2263-4251-9811-a1b61e0c7a76
role: admin
org_id: 933b6e12-5464-41e1-8707-65ff9a0f8332 (IT팀)
```

**admin 권한**:
- `is_admin = True`
- `get_all_groups()` 호출 시 모든 그룹 반환

### 4. get_all_groups() 분석

**파일**: `src/group_manager.py:886-896`

```python
else:
    # Get all groups (system admin)
    for key in self.client.scan_iter(match="group:*", count=100):
        key_str = key.decode('utf-8')

        # Skip non-group keys
        if (key_str.startswith('group:children:') or
            key_str.startswith('group:docs:') or
            key_str.startswith('group:orgs:') or
            key_str == 'group:default'):  # group:default 제외
            continue
```

**반환 그룹** (admin 사용자):
1. `group:db509513-b431-4cb6-9237-9ac2b1a646fc` (미분류, 0 docs)
2. `group:256496ee-8a0c-455b-8b16-97e7a102544f` (개발, 2 docs)
3. `group:eea12d54-0c0b-4310-a122-efbfa3905a31` (미분류, 42 docs)

**총 3개 그룹** → org_group_ids에 3개 ID 포함

---

## 🎯 가설

### 가설 1: org_group_ids에 모든 그룹 ID가 포함되지 않음

**검증 필요**:
- `get_all_groups()`가 실제로 3개 그룹을 반환하는지
- `org_group_ids` Set에 3개 ID가 모두 포함되는지

### 가설 2: 특정 문서의 doc:group 값이 잘못됨

**검증 필요**:
- 어떤 문서가 43개에 포함되고 1개가 빠졌는지
- 빠진 문서의 `doc:group` 값이 무엇인지

### 가설 3: chunk_count = 0인 문서가 필터링됨

**코드**: `src/web_server.py:5080`
```python
"indexed": chunk_count > 0
```

**검증 필요**:
- 모든 44개 문서의 chunk_count 확인
- chunk_count = 0인 문서가 있는지

---

## 🔬 추가 조사 필요

### 1. 실제 API 응답 확인
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/documents
```

**확인 사항**:
- `total_count`가 43인지
- 어떤 문서가 목록에 포함되는지
- 어떤 문서가 누락되었는지

### 2. 그룹별 문서 필터링 테스트

```python
# 각 그룹 ID에 속한 문서 수 확인
for group_id in org_group_ids:
    docs = [f for f in files if redis.get(f"doc:group:{f}") == group_id]
    print(f"{group_id}: {len(docs)}개")
```

### 3. 로그 확인

```bash
tail -f logs/web_server.log | grep "list_documents"
```

**확인 사항**:
- `org_group_ids`에 포함된 그룹 ID
- 필터링된 문서 수

---

## 💡 해결 방안 (추정)

### 방안 1: 중복된 미분류 그룹 제거

```bash
# db509513-b431-4cb6-9237-9ac2b1a646fc 그룹 삭제 (0 docs)
docker exec chatbot_redis redis-cli DEL "group:db509513-b431-4cb6-9237-9ac2b1a646fc"

# org:groups:* Set에서 제거
docker exec chatbot_redis redis-cli SREM "org:groups:default" "db509513-b431-4cb6-9237-9ac2b1a646fc"
```

### 방안 2: 모든 문서의 그룹 매핑 검증

```bash
python scripts/check_document_groups.py
```

**결과**: 모든 44개 문서 매핑 정상 ✅

### 방안 3: 사용자별 문서 목록 API 직접 호출

실제 API를 호출하여 어떤 문서가 빠졌는지 확인

---

## 📝 다음 단계

1. [ ] API 직접 호출하여 실제 반환되는 문서 목록 확인
2. [ ] 어떤 문서가 43개에 포함되고 1개가 빠졌는지 식별
3. [ ] 빠진 문서의 `doc:group` 값 확인
4. [ ] `get_all_groups()`의 실제 반환값 로깅
5. [ ] 중복된 "미분류" 그룹 정리
6. [ ] 문제 해결 후 검증

---

## 🔗 관련 코드

- `src/web_server.py:4965-5095` - list_documents API
- `src/web_server.py:5029-5037` - 문서 필터링 로직
- `src/group_manager.py:866-896` - get_all_groups 메서드

---

**작성자**: Claude (Assistant)
**상태**: 조사 중, 추가 정보 필요
