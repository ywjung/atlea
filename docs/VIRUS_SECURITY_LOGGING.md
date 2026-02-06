# 바이러스 검사 보안 로깅 구현

## 개요

모든 바이러스 검사 활동이 보안 로그에 자동으로 기록되어 관리자 페이지의 보안 이벤트 섹션에서 확인할 수 있습니다.

## 구현된 이벤트 타입

### 1. 업로드 시 바이러스 발견 (CRITICAL)
```python
event_type: "virus_detected"
level: "critical"
details: {
    "filename": "malicious.exe",
    "virus_name": "Trojan.Generic",
    "file_hash": "abc123...",
    "action": "file_deleted"
}
```
- **위치**: `src/routers/documents.py:1284-1296`
- **발생 시점**: 파일 업로드 중 바이러스 감지
- **조치**: 파일 즉시 삭제, 업로드 차단

### 2. 업로드 시 안전한 파일 (INFO)
```python
event_type: "virus_scan_clean"
level: "info"
details: {
    "filename": "document.pdf",
    "file_hash": "def456...",
    "scan_result": "clean",
    "scanner": "ClamAV"
}
```
- **위치**: `src/routers/documents.py:1305-1316`
- **발생 시점**: 파일 업로드 중 안전 확인
- **조치**: 업로드 계속 진행

### 3. 업로드 시 스캔 실패 (WARNING)
```python
event_type: "virus_scan_failed"
level: "warning"
details: {
    "filename": "large_file.zip",
    "file_hash": "ghi789...",
    "error": "Connection timeout",
    "action": "upload_continued"
}
```
- **위치**: `src/routers/documents.py:1326-1341`
- **발생 시점**: ClamAV 스캔 실패
- **조치**: 업로드 계속하되 경고 로그

### 4. 수동 스캔 시 바이러스 발견 (CRITICAL)
```python
event_type: "manual_virus_detected"
level: "critical"
details: {
    "filename": "suspicious.doc",
    "virus_name": "Macro.Virus",
    "scan_type": "manual",
    "action": "detected_not_deleted"
}
```
- **위치**: `src/routers/documents.py:1633-1647`
- **발생 시점**: 관리자 수동 스캔 중 바이러스 감지
- **조치**: 감지만 하고 파일 유지 (관리자 판단 필요)

### 5. 수동 스캔 시 안전한 파일 (INFO)
```python
event_type: "manual_virus_scan_clean"
level: "info"
details: {
    "filename": "report.hwp",
    "scan_result": "clean",
    "scan_type": "manual",
    "scanner": "ClamAV"
}
```
- **위치**: `src/routers/documents.py:1670-1683`
- **발생 시점**: 관리자 수동 스캔 완료
- **조치**: 안전 확인 기록

### 6. 수동 스캔 실패 (WARNING)
```python
event_type: "manual_virus_scan_failed"
level: "warning"
details: {
    "filename": "test.pdf",
    "error": "ClamAV not responding",
    "scan_type": "manual"
}
```
- **위치**: `src/routers/documents.py:1699-1713`
- **발생 시점**: 수동 스캔 실패
- **조치**: 실패 기록 및 사용자 알림

## 관리자 페이지에서 확인하기

### 접근 경로
1. http://localhost:8085/admin.html 접속
2. [보안] 탭 클릭
3. [보안 이벤트] 섹션 확인

### 이벤트 레벨별 표시

#### 🚨 CRITICAL (빨간색)
- `virus_detected`: 업로드 중 바이러스 발견
- `manual_virus_detected`: 수동 스캔 바이러스 발견

#### ⚠️ WARNING (노란색)
- `virus_scan_failed`: 업로드 스캔 실패
- `manual_virus_scan_failed`: 수동 스캔 실패

#### ℹ️ INFO (파란색)
- `virus_scan_clean`: 업로드 안전 파일
- `manual_virus_scan_clean`: 수동 스캔 안전 파일

## 보안 감사 추적 (Audit Trail)

### 추적 가능한 정보
- ✅ **누가**: 사용자 ID 및 이름
- ✅ **언제**: 정확한 타임스탬프
- ✅ **무엇을**: 파일명 및 해시
- ✅ **결과**: 안전/감염/실패
- ✅ **조치**: 삭제/계속/경고

### 활용 사례

#### 1. 보안 사고 조사
```
시나리오: 바이러스 파일이 업로드 시도됨
추적 정보:
  - 시도자: testuser (ID: user123)
  - 시간: 2026-02-04 07:30:15
  - 파일: malicious.exe
  - 바이러스: Trojan.Generic
  - 조치: 파일 삭제, 업로드 차단
  - 결과: 시스템 보호됨 ✅
```

#### 2. 컴플라이언스 감사
```
질문: "모든 업로드된 파일이 바이러스 검사를 거쳤는가?"
확인: 보안 로그에서 virus_scan_clean 이벤트 조회
  - 2026-02-04: 45개 파일 스캔 완료
  - 모두 안전 확인됨
  - 감사 통과 ✅
```

#### 3. 시스템 모니터링
```
알림: virus_scan_failed 이벤트 증가
조사: ClamAV 서비스 상태 확인
조치: ClamAV 재시작 또는 설정 점검
```

## 코드 위치

### 업로드 엔드포인트
```
파일: src/routers/documents.py
라인: 1263-1350 (바이러스 스캔 및 로깅)
```

### 수동 스캔 엔드포인트
```
파일: src/routers/documents.py
라인: 1580-1725 (수동 스캔 및 로깅)
```

### SecurityLogger
```
파일: src/auth/security_logger.py
기능: Redis 기반 보안 이벤트 로깅
```

## 테스트 방법

### 1. 안전한 파일 업로드
```bash
# 관리자 페이지에서 PDF 파일 업로드
# 보안 로그 확인:
# - virus_scan_clean 이벤트 생성됨
# - level: info
# - 파일명, 해시, 사용자 정보 기록됨
```

### 2. EICAR 테스트 파일
```bash
# EICAR 테스트 파일 업로드 시도
# 보안 로그 확인:
# - virus_detected 이벤트 생성됨
# - level: critical
# - 바이러스명: Eicar-Signature
# - action: file_deleted
# - 업로드 차단됨 ✅
```

### 3. 수동 스캔
```bash
# 관리자 페이지 > 업로드된 문서 > 미검사 파일 클릭
# 보안 로그 확인:
# - manual_virus_scan_clean 또는 manual_virus_detected
# - scan_type: manual
# - 관리자 작업 기록됨
```

## 데이터 보관

- **저장 위치**: Redis
- **키 패턴**: `security:event:{event_type}:{timestamp}`
- **보관 기간**: 90일 (설정 가능)
- **검색**: event_type, level, username, timestamp로 필터링

## 보안 고려사항

1. **민감 정보 보호**
   - 파일 내용은 로그에 저장하지 않음
   - 파일 해시만 기록하여 추적 가능

2. **로그 무결성**
   - Redis에 직접 저장
   - 변조 방지를 위한 타임스탬프 포함

3. **접근 제어**
   - 관리자만 보안 로그 조회 가능
   - 일반 사용자는 접근 불가

4. **로그 분석**
   - 이상 패턴 감지 가능
   - 반복적인 바이러스 업로드 시도 추적

## 요약

✅ **6가지 이벤트 타입** 모두 구현됨
✅ **자동 로깅** - 별도 설정 불필요
✅ **관리자 페이지** 에서 즉시 확인 가능
✅ **보안 감사** 완벽 지원
✅ **컴플라이언스** 요구사항 충족
