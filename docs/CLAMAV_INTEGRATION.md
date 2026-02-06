# ClamAV 바이러스 스캔 통합

## 개요

ClamAV를 Docker Compose로 구성하여 문서 업로드 시 실시간 바이러스 검사를 수행합니다.

## 구현 날짜
- **날짜**: 2026-02-03
- **상태**: ✅ 완료

## 아키텍처

### 컴포넌트

1. **ClamAV Docker Container**
   - 이미지: `clamav/clamav:latest`
   - 포트: 3310 (clamd daemon)
   - 자동 바이러스 정의 업데이트 (freshclam)

2. **Python Integration**
   - 라이브러리: `clamd>=1.0.2`
   - 모듈: `src/utils/file_security.py`
   - 비동기 스캔 지원

3. **Upload Security Pipeline**
   - 위치: `src/routers/documents.py`
   - 파일 저장 후 즉시 스캔
   - 위협 감지 시 파일 삭제 및 차단

### 데이터 흐름

```
파일 업로드 요청
    ↓
관리자 권한 확인
    ↓
파일명 검증 (Path Traversal 방어)
    ↓
확장자 화이트리스트 체크
    ↓
MIME 타입 검증
    ↓
악성 패턴 검사
    ↓
매직 바이트 검증
    ↓
디스크에 파일 저장
    ↓
🆕 ClamAV 바이러스 스캔 ← NEW
    ↓
├─ 바이러스 감지 → 파일 삭제 + HTTP 400 + 보안 로그
└─ 정상 → 중복 체크 → 인덱싱
```

## 설정

### 1. Docker Compose 설정

**파일**: `docker-compose.yml`

```yaml
services:
  clamav:
    image: clamav/clamav:latest
    platform: linux/amd64  # ARM64 support via x86 emulation (Apple Silicon)
    container_name: chatbot_clamav
    ports:
      - "3310:3310"  # ClamAV daemon port
    volumes:
      - clamav_data:/var/lib/clamav
    environment:
      - CLAMAV_NO_FRESHCLAM=false  # Enable automatic updates
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "/usr/local/bin/clamd", "--ping"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 120s  # Initial setup time

volumes:
  clamav_data:
    driver: local
```

**⚠️ ARM64/Apple Silicon 참고사항**:
- ClamAV 공식 이미지는 ARM64를 네이티브로 지원하지 않습니다
- `platform: linux/amd64` 설정으로 x86 에뮬레이션을 사용합니다
- 초기 시작 시간이 3-5분으로 증가할 수 있습니다
- 성능은 약간 느리지만 기능은 정상 작동합니다
- 프로덕션 환경(x86_64)에서는 `platform` 라인을 제거하세요

### 2. 환경 변수 설정

**파일**: `.env`

```bash
# ClamAV Configuration
CLAMAV_HOST=localhost
CLAMAV_PORT=3310
```

### 3. Python 의존성

**파일**: `requirements.txt`

```
clamd>=1.0.2  # ClamAV antivirus integration
```

## 사용 방법

### 1. ClamAV 컨테이너 시작

```bash
# ClamAV 컨테이너 시작
docker-compose up -d clamav

# 상태 확인 (2-3분 소요 - 바이러스 정의 다운로드)
docker-compose ps clamav

# 로그 확인
docker-compose logs -f clamav

# 초기화 완료 확인
docker exec chatbot_clamav /usr/local/bin/clamdscan --ping
```

**초기 시작 시간**: 2-3분
- 바이러스 정의 파일 다운로드 (~200MB)
- 메모리에 시그니처 로드
- `healthy` 상태가 되면 사용 가능

### 2. Python 라이브러리 설치

```bash
# 가상환경 활성화
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows

# clamd 설치
pip install clamd>=1.0.2
```

### 3. 애플리케이션 시작

```bash
# 환경 변수 설정 확인
cat .env | grep CLAMAV

# 서버 시작
./run.sh
```

### 4. 테스트

#### 정상 파일 업로드
```bash
# 정상 PDF 파일 업로드
curl -X POST http://localhost:8085/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.pdf"

# 예상 응답: 200 OK
# 로그: "✅ Virus scan completed - file is clean: test.pdf"
```

#### EICAR 테스트 파일 (바이러스 감지 테스트)
```bash
# EICAR 표준 테스트 파일 생성
echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > eicar.txt

# 업로드 시도
curl -X POST http://localhost:8085/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@eicar.txt"

# 예상 응답: 400 Bad Request
# {
#   "detail": "보안 위협이 감지되었습니다. 파일 업로드가 차단되었습니다. (위협: Win.Test.EICAR_HDB-1)"
# }

# 로그 확인
# "🚨 VIRUS DETECTED in 'eicar.txt': Win.Test.EICAR_HDB-1"
# "Security event: virus_detected"
```

## API 동작

### 정상 파일 업로드

**요청**:
```http
POST /api/documents/upload
Authorization: Bearer <admin_token>
Content-Type: multipart/form-data

file: document.pdf
```

**응답**: `200 OK`
```json
{
  "message": "파일 업로드 및 인덱싱 완료",
  "filename": "document.pdf",
  "version": 1,
  "chunk_count": 42,
  "indexed": true
}
```

**로그**:
```
INFO: 🔍 Scanning file with ClamAV: /path/to/document.pdf
INFO: ✅ File is clean: /path/to/document.pdf
INFO: ✅ Virus scan completed - file is clean: document.pdf
```

### 바이러스 감지 시

**요청**:
```http
POST /api/documents/upload
Authorization: Bearer <admin_token>
Content-Type: multipart/form-data

file: infected.pdf
```

**응답**: `400 Bad Request`
```json
{
  "detail": "보안 위협이 감지되었습니다. 파일 업로드가 차단되었습니다. (위협: Trojan.GenericKD.12345678)"
}
```

**로그**:
```
ERROR: 🚨 Virus detected in /path/to/infected.pdf: Trojan.GenericKD.12345678
ERROR: 🚨 VIRUS DETECTED in 'infected.pdf': Trojan.GenericKD.12345678
INFO: Security event logged: virus_detected
```

**보안 로그**:
```json
{
  "event_type": "virus_detected",
  "level": "critical",
  "user_id": "user_123",
  "username": "admin",
  "details": {
    "filename": "infected.pdf",
    "virus_name": "Trojan.GenericKD.12345678",
    "file_hash": "abc123...",
    "action": "file_deleted"
  },
  "timestamp": "2026-02-03T10:30:00Z"
}
```

### ClamAV 연결 실패 시

**동작**: 업로드 계속 진행 (Fail-Open)
- 비즈니스 연속성 우선
- 경고 로그 기록
- 보안팀 모니터링 필요

**로그**:
```
WARNING: ⚠️ ClamAV daemon not available at localhost:3310
WARNING: ⚠️ Continuing without virus scan due to connection error
```

**개선 방향**: 운영 환경에서는 Fail-Closed 정책 고려

## 모니터링

### ClamAV 헬스 체크

```bash
# Docker 헬스 상태
docker-compose ps clamav

# Clamd ping 테스트
docker exec chatbot_clamav /usr/local/bin/clamdscan --ping

# 바이러스 정의 버전 확인
docker exec chatbot_clamav /usr/local/bin/sigtool --info /var/lib/clamav/main.cvd
docker exec chatbot_clamav /usr/local/bin/sigtool --info /var/lib/clamav/daily.cvd

# 메모리 사용량 확인
docker stats chatbot_clamav
```

### 로그 모니터링

```bash
# ClamAV 로그
docker-compose logs -f clamav

# 애플리케이션 바이러스 스캔 로그
tail -f /tmp/chatbot_server.log | grep -E "virus|ClamAV|scan"

# 보안 이벤트 로그 (Redis)
redis-cli KEYS "audit:security:*" | head -20
redis-cli GET "audit:security:virus_detected:latest"
```

### 메트릭

- **스캔 성공률**: 정상 스캔 / 전체 업로드
- **바이러스 감지 건수**: 일일 감지 통계
- **평균 스캔 시간**: 파일 크기별 평균
- **ClamAV 가용성**: 업타임 모니터링

## 성능 특성

### 스캔 시간 (벤치마크)

| 파일 크기 | 평균 스캔 시간 | 비고 |
|----------|---------------|------|
| 1 MB | ~0.1초 | PDF, 문서 |
| 10 MB | ~0.5초 | 프레젠테이션 |
| 50 MB | ~2초 | 대용량 스프레드시트 |
| 100 MB | ~4초 | 최대 파일 크기 |

### 리소스 사용량

- **메모리**: 1-2 GB (바이러스 정의 로드)
- **CPU**: 스캔 시 1-2 코어 사용
- **디스크**: ~500 MB (바이러스 정의)
- **네트워크**: 매일 수십 MB (정의 업데이트)

### 병목 현상

- **대용량 파일**: 100MB+ 파일은 스캔 시간 증가
- **동시 업로드**: 여러 파일 동시 스캔 시 대기 발생
- **메모리 부족**: 시그니처 로드 실패 가능

**최적화 방안**:
- 파일 크기 제한 유지 (100MB)
- 업로드 대기열 구현
- ClamAV 수평 확장 (여러 인스턴스)

## 보안 고려사항

### 1. Fail-Open vs Fail-Closed

**현재 구현**: Fail-Open (ClamAV 실패 시 업로드 허용)
- **장점**: 비즈니스 연속성
- **단점**: 보안 위험 증가

**프로덕션 권장**: Fail-Closed (ClamAV 실패 시 업로드 차단)
```python
# src/utils/file_security.py에서 수정
if not cd.ping():
    raise ConnectionError("ClamAV not available - blocking upload")
```

### 2. 바이러스 정의 업데이트

- **자동 업데이트**: freshclam (매일 1회)
- **수동 업데이트**: `docker exec chatbot_clamav freshclam`
- **업데이트 확인**: 로그에서 "Database updated" 확인

### 3. 제로데이 위협

- ClamAV는 시그니처 기반 탐지
- 신종 악성코드는 탐지 불가능
- **추가 방어층 필요**:
  - 파일 샌드박싱
  - 휴리스틱 분석
  - 행동 기반 탐지

### 4. 우회 공격

- **압축 파일**: ZIP, RAR 내부 파일 검사 제한
- **암호화**: 암호화된 압축 파일 검사 불가
- **대응**: 압축 파일 업로드 제한 또는 추가 검증

## 트러블슈팅

### 1. ClamAV 컨테이너 시작 실패

**증상**:
```
Error: Container is unhealthy
```

**원인**: 바이러스 정의 다운로드 실패

**해결**:
```bash
# 로그 확인
docker-compose logs clamav

# 수동 업데이트 시도
docker exec chatbot_clamav freshclam

# 컨테이너 재시작
docker-compose restart clamav
```

### 2. Python 연결 오류

**증상**:
```
WARNING: ⚠️ ClamAV daemon not available at localhost:3310
```

**원인**:
- ClamAV 컨테이너 미실행
- 포트 바인딩 오류
- 방화벽 차단

**해결**:
```bash
# ClamAV 상태 확인
docker-compose ps clamav

# 포트 리스닝 확인
netstat -an | grep 3310
lsof -i :3310

# 환경 변수 확인
echo $CLAMAV_HOST
echo $CLAMAV_PORT

# Telnet 테스트
telnet localhost 3310
```

### 3. 스캔 타임아웃

**증상**:
```
ERROR: ClamAV scan failed: Timeout
```

**원인**: 대용량 파일 또는 ClamAV 과부하

**해결**:
```python
# src/utils/file_security.py에서 타임아웃 증가
await scan_with_antivirus(
    file_path=str(file_path),
    timeout=60  # 기본 30초 → 60초
)
```

### 4. 메모리 부족

**증상**:
```
ERROR: ClamAV daemon out of memory
```

**원인**: 시그니처 로드 실패

**해결**:
```yaml
# docker-compose.yml에서 메모리 제한 증가
services:
  clamav:
    mem_limit: 3g  # 기본 2GB → 3GB
    memswap_limit: 3g
```

## 향후 개선 사항

### Phase 1 (완료)
- ✅ Docker Compose ClamAV 통합
- ✅ Python clamd 클라이언트 구현
- ✅ 업로드 파이프라인 통합
- ✅ 보안 로깅 구현

### Phase 2 (계획)
- 📋 스캔 결과 대시보드
- 📋 바이러스 통계 및 리포트
- 📋 격리된 파일 관리 (Quarantine)
- 📋 사용자 알림 시스템

### Phase 3 (고려)
- 📋 ClamAV 클러스터링 (고가용성)
- 📋 VirusTotal API 통합 (다중 엔진)
- 📋 파일 샌드박싱 (동적 분석)
- 📋 ML 기반 악성코드 탐지

## 참고 자료

### 공식 문서
- [ClamAV Documentation](https://docs.clamav.net/)
- [ClamAV Docker Hub](https://hub.docker.com/r/clamav/clamav)
- [Python clamd Library](https://pypi.org/project/clamd/)

### 보안 기준
- [OWASP - Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload)
- [NIST SP 800-83: Guide to Malware Incident Prevention](https://csrc.nist.gov/publications/detail/sp/800-83/rev-1/final)

### 관련 문서
- `docs/FILE_UPLOAD_SECURITY.md` - 파일 업로드 보안 (Phase 2-3)
- `docker-compose.yml` - ClamAV 서비스 정의
- `src/utils/file_security.py` - 보안 검증 모듈
- `src/routers/documents.py` - 업로드 엔드포인트

## Changelog

### Version 2.4.0 (2026-02-03)
- ✅ ClamAV Docker Compose 통합
- ✅ 실시간 바이러스 스캔 구현
- ✅ 바이러스 감지 시 자동 파일 삭제
- ✅ 보안 이벤트 로깅 시스템
- ✅ 환경 변수 기반 설정
- ✅ 헬스 체크 및 모니터링
- ✅ 문서화 및 테스트 가이드
