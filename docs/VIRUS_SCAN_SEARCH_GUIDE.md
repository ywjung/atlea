# 바이러스 검사 보안 로그 검색 가이드

## 이벤트 유형 (Event Type) 전체 목록

### 🚨 바이러스 발견 (CRITICAL)
```
virus_detected
  - 파일 업로드 중 바이러스 발견
  - 파일 자동 삭제
  - 업로드 차단

manual_virus_detected
  - 관리자 수동 스캔 중 바이러스 발견
  - 파일은 유지 (관리자 판단 필요)
```

### ✅ 안전한 파일 (INFO)
```
virus_scan_clean
  - 파일 업로드 중 안전 확인
  - 업로드 계속 진행

manual_virus_scan_clean
  - 관리자 수동 스캔 중 안전 확인
```

### ⚠️ 스캔 실패 (WARNING)
```
virus_scan_failed
  - 파일 업로드 중 스캔 실패
  - ClamAV 오류
  - 업로드는 계속되나 경고

manual_virus_scan_failed
  - 관리자 수동 스캔 실패
  - ClamAV 연결 문제 등
```

## 검색 패턴

### 포괄적 검색
| 검색어 | 결과 |
|--------|------|
| `virus` | 모든 바이러스 관련 이벤트 |
| `manual` | 모든 수동 스캔 이벤트 |
| `scan` | 모든 스캔 이벤트 |

### 구체적 검색
| 검색어 | 결과 |
|--------|------|
| `virus_detected` | 업로드 시 바이러스 발견만 |
| `virus_scan_clean` | 업로드 시 안전 파일만 |
| `manual_virus_detected` | 수동 스캔 바이러스 발견만 |
| `manual_virus_scan_clean` | 수동 스캔 안전 파일만 |

### 레벨 필터 조합
```
레벨: CRITICAL + 검색어: virus
→ 모든 바이러스 발견 이벤트 (긴급)

레벨: WARNING + 검색어: virus
→ 모든 스캔 실패 이벤트

레벨: INFO + 검색어: virus
→ 모든 안전 확인 이벤트
```

## 실전 활용 시나리오

### 1. 보안 감사
**목적**: 최근 바이러스 침입 시도 확인

```
검색어: virus_detected
레벨: CRITICAL
기간: 최근 30일

결과 분석:
- 발견된 바이러스 종류
- 시도한 사용자
- 발생 빈도
```

### 2. 시스템 모니터링
**목적**: ClamAV 정상 작동 확인

```
검색어: virus_scan_failed
레벨: WARNING
기간: 최근 24시간

결과:
- 실패 건수가 많으면 → ClamAV 점검 필요
- 실패 건수가 없으면 → 정상 작동
```

### 3. 사용자 활동 추적
**목적**: 특정 사용자의 파일 업로드 이력

```
검색어: virus_scan_clean
사용자: testuser
기간: 전체

결과:
- 업로드한 파일 목록
- 모두 안전하게 스캔됨
```

### 4. 관리자 작업 감사
**목적**: 관리자 수동 스캔 이력

```
검색어: manual_virus
기간: 최근 7일

결과:
- 어떤 관리자가
- 어떤 파일을
- 언제 스캔했는지
```

## 빠른 참조표

| 상황 | 검색어 | 레벨 |
|------|--------|------|
| 긴급: 바이러스 발견 확인 | `virus_detected` | CRITICAL |
| 일상: 오늘 업로드 파일 | `virus_scan_clean` | INFO |
| 문제: ClamAV 오류 확인 | `virus_scan_failed` | WARNING |
| 감사: 관리자 작업 이력 | `manual_virus` | 전체 |
| 전체: 모든 스캔 활동 | `virus` | 전체 |

## 검색 팁

1. **부분 검색 활용**
   - `virus`로 검색하면 `virus_detected`, `virus_scan_clean` 등 모두 검색
   - `manual`로 검색하면 모든 수동 스캔 검색

2. **레벨 필터 활용**
   - CRITICAL: 즉시 대응 필요한 긴급 이벤트
   - WARNING: 모니터링 필요한 경고 이벤트
   - INFO: 정상 작동 확인용 정보 이벤트

3. **기간 필터 활용**
   - 최근 24시간: 실시간 모니터링
   - 최근 7일: 주간 리포트
   - 최근 30일: 월간 감사
   - 전체: 전체 이력 조회

4. **사용자 필터 활용**
   - 특정 사용자의 활동만 추적
   - 의심스러운 활동 패턴 분석

## 알림 설정 권장사항

### 높은 우선순위
- `virus_detected`: 즉시 알림 (SMS/이메일)
- `manual_virus_detected`: 관리자 알림

### 중간 우선순위
- `virus_scan_failed`: 일일 요약 알림
- 실패 건수 > 10건/일: 긴급 알림

### 낮은 우선순위
- `virus_scan_clean`: 로그만 기록
- `manual_virus_scan_clean`: 로그만 기록

## 데이터 보존

- **보관 기간**: 90일
- **저장 위치**: Redis
- **백업**: 정기적인 Redis 백업 권장
- **아카이빙**: 장기 보관 필요 시 외부 로그 시스템 연동 권장
