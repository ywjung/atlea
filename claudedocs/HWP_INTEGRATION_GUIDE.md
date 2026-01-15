# HWP 파일 처리 통합 가이드

> **✅ 통합 완료 (Phase 2)** - HWP 파일 처리 기능이 현재 시스템에 완전히 통합되어 정상 작동 중입니다.
> 이 문서는 HWP 통합 방법 및 운영 가이드입니다.

PDF RAG 챗봇에 HWP(한글 문서) 파일 처리 기능이 통합되었습니다.

## 시스템 아키텍처

```
┌─────────────────────────┐
│   사용자 (웹 브라우저)    │
└────────┬────────────────┘
         │ HTTP
         ▼
┌─────────────────────────┐
│  FastAPI 서버 (Python)   │
│  - PDF 처리 (pypdf)      │
│  - HWP 처리 위임         │
└────────┬────────────────┘
         │
    ┌────┴────────────┐
    │                 │
    ▼                 ▼
┌──────────┐    ┌───────────────┐
│ PDF 처리  │    │ Java HWP Service│
│ (Python)  │    │ (Spring Boot)  │
└──────────┘    └────────┬────────┘
                         │
                         ▼
                    ┌─────────┐
                    │ hwplib  │
                    │ (한글 파싱)│
                    └─────────┘
```

## 주요 구성 요소

### 1. Java HWP Service (Spring Boot)

**위치**: `document-service/`

**기능**:
- HWP 파일에서 텍스트 추출
- RESTful API 제공
- hwplib 라이브러리 사용

**API 엔드포인트**:
- `GET /api/hwp/health` - 헬스 체크
- `POST /api/hwp/extract` - HWP 파일 업로드 및 텍스트 추출
- `POST /api/hwp/extract/base64` - Base64 인코딩된 HWP 파일 처리

**포트**: 8081

### 2. Python HWP Processor

**파일**: `src/hwp_processor.py`

**기능**:
- Java HWP Service API 호출
- Python과 Java 간 브릿지 역할
- 에러 처리 및 fallback 지원

### 3. Document Processor 통합

**파일**: `src/document_processor.py`

**기능**:
- PDF와 HWP 파일 통합 처리
- Java HWP Service 사용 우선
- Python fallback 지원 (제한적)

## 설치 및 실행

### 1. 필수 요구사항

- **Python** 3.10+
- **Java** 17+
- **Maven** 3.9+
- **Docker** (선택사항)

### 2. 설치

#### Option A: Docker Compose (권장)

```bash
# 모든 서비스 시작 (Redis + HWP Service)
docker-compose up -d

# 로그 확인
docker-compose logs -f document-service

# 상태 확인
docker-compose ps
```

#### Option B: 수동 설치

**Java HWP Service 빌드 및 실행:**

```bash
cd document-service

# Maven 빌드
mvn clean package

# 실행
java -jar target/document-service-1.0.0.jar

# 또는 Maven으로 직접 실행
mvn spring-boot:run
```

**Python 패키지 설치:**

```bash
# requirements.txt 업데이트됨 (requests 추가)
pip install -r requirements.txt
```

### 3. 환경 설정

`.env` 파일에 HWP Service URL 추가:

```bash
# HWP Service Configuration
HWP_SERVICE_URL=http://localhost:8081
```

### 4. 실행 확인

**HWP Service 헬스 체크:**

```bash
curl http://localhost:8081/api/hwp/health
# 응답: "HWP Service is running"
```

**Python 서버 로그 확인:**

```bash
# Python 서버 시작 시 다음과 같은 로그가 표시되어야 함:
# ✅ Java HWP service is available - using Java-based extraction
```

## 사용 방법

### 웹 UI에서 HWP 파일 업로드

1. 브라우저에서 http://localhost:8000 접속
2. "문서 관리" 버튼 클릭
3. PDF 또는 HWP 파일 드래그 앤 드롭 또는 클릭하여 선택
4. 파일이 자동으로 처리되고 색인됨

### Python 코드에서 직접 사용

```python
from src.hwp_processor import HWPProcessor

# HWP Processor 초기화
hwp_processor = HWPProcessor()

# HWP 파일에서 텍스트 추출
text = hwp_processor.extract_text_from_file("./data/document.hwp")

if text:
    print(f"추출된 텍스트 길이: {len(text)} 문자")
    print(text[:500])  # 처음 500자 출력
```

### API 직접 호출

```bash
# 파일 업로드 방식
curl -X POST http://localhost:8081/api/hwp/extract \
  -F "file=@document.hwp"

# Base64 인코딩 방식
base64 document.hwp > encoded.txt
curl -X POST http://localhost:8081/api/hwp/extract/base64 \
  -H "Content-Type: application/json" \
  -d '{
    "fileContent": "'$(cat encoded.txt)'",
    "filename": "document.hwp"
  }'
```

## 트러블슈팅

### HWP Service가 시작되지 않음

**증상**: Python 로그에 "Java HWP service not available" 표시

**해결책**:
```bash
# HWP Service 상태 확인
curl http://localhost:8081/api/hwp/health

# 포트 사용 확인
lsof -i :8081

# Docker로 실행 중이라면
docker-compose logs document-service

# 수동 실행으로 에러 확인
cd document-service
mvn spring-boot:run
```

### HWP 텍스트 추출 실패

**증상**: "HWP extraction failed" 에러

**확인 사항**:
1. HWP 파일이 유효한지 확인 (*.hwp 확장자)
2. 파일 크기가 50MB 이하인지 확인
3. HWP 파일이 암호화되지 않았는지 확인

**Fallback 동작**:
- Java 추출 실패 시 자동으로 Python fallback 사용
- Python fallback은 제한적이므로 Java 서비스 사용 권장

### Maven 빌드 실패

**증상**: hwplib 라이브러리 다운로드 실패

**해결책**:
```bash
# Maven 캐시 클리어
mvn clean

# 의존성 강제 재다운로드
mvn dependency:purge-local-repository
mvn clean install
```

### Docker 빌드 실패

**증상**: document-service 컨테이너 빌드 오류

**해결책**:
```bash
# 캐시 없이 재빌드
docker-compose build --no-cache document-service

# 개별 빌드 및 로그 확인
cd document-service
docker build -t document-service:latest .
```

## 성능 최적화

### Java Service 메모리 설정

`docker-compose.yml`에서 Java 메모리 조정:

```yaml
document-service:
  environment:
    - JAVA_OPTS=-Xmx1024m -Xms512m  # 1GB 최대, 512MB 초기
```

### 동시 요청 처리

HWP Service는 Spring Boot의 기본 스레드 풀 사용:
- 기본 최대 스레드: 200
- 필요 시 `application.yml`에서 조정 가능

### 캐싱

- Python에서 동일 파일 재처리 방지
- Redis를 활용한 처리 결과 캐싱 가능 (추후 구현)

## 개발 가이드

### Java Service 수정

```bash
cd document-service

# 코드 수정 후 재빌드
mvn clean package

# 테스트 실행
mvn test

# 개발 모드로 실행 (hot reload)
mvn spring-boot:run
```

### Python Client 수정

`src/hwp_processor.py`를 수정하여 HWP 처리 로직 변경 가능

### 새로운 엔드포인트 추가

1. Java: `document-service/src/main/java/com/chatbot/hwp/controller/HwpController.java`
2. Python: `src/hwp_processor.py`에 새 메서드 추가

## 기술 스택

### Java Service
- Spring Boot 3.2.0
- hwplib 1.1.5
- Maven 3.9
- Java 17

### Python Integration
- requests 2.31.0+
- FastAPI
- 기존 PDF 처리 라이브러리들

## 라이선스

- hwplib: LGPL-3.0
- Spring Boot: Apache License 2.0
- Python 코드: 프로젝트 라이선스 따름

## 참고 자료

- [hwplib GitHub](https://github.com/neolord0/hwplib)
- [Spring Boot Documentation](https://spring.io/projects/spring-boot)
- 프로젝트 README.md
