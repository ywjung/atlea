# 📚 문서 RAG 챗봇

다양한 형식의 문서를 기반으로 질의응답을 제공하는 AI 챗봇 시스템입니다.

## ✨ 주요 기능

### 🔍 문서 처리 및 검색
- **다중 형식 문서 처리**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX (9가지 형식 지원)
- **Java 문서 추출 서비스**: Apache POI + PDFBox 기반 고성능 텍스트 추출 (최대 50MB)
- **스마트 색인**: 파일 변경 감지 및 자동 재색인 (매번 임베딩하지 않음)
- **고속 벡터 검색**: Redis Vector DB + 연결 풀링으로 빠른 문서 검색 (동시 쿼리 5-10배 개선)
- **문서 그룹 관리**: 계층 구조 그룹으로 문서 조직화, 그룹별 OR 검색 지원
- **문서 관리**: 웹 UI에서 모든 형식의 문서 업로드, 삭제, 상태 확인, 그룹 할당
- **중복 방지**: MD5 해시 기반 중복 문서 업로드 차단
- **Python Fallback**: Java 서비스 미사용 시 Python HWP 추출 대체

### 🤖 AI 기능
- **지능형 질의응답**: Qwen LLM을 사용한 정확한 답변 생성
- **스트리밍 응답**: 실시간 답변 생성 및 진행 상황 표시
- **질문 자동완성**: 인덱스 기반 O(1) 검색으로 즉각 응답 (10배 성능 향상)
- **스마트 질문 생성**: 문서당 12개 한국어 질문 자동 생성 (백그라운드 처리)
- **답변 캐싱**: 유사 질문 자동 감지 및 캐시 응답 (95% 유사도 기반)
- **Apple GPU 최적화**: MLX 프레임워크로 Apple Silicon GPU 활용

### 🎨 사용자 인터페이스
- **모던 웹 UI**: 반응형 디자인 및 Markdown 렌더링 지원
- **다크 모드**: 라이트/다크 테마 자동/수동 전환
- **세션 관리**: 대화 히스토리 저장 및 복원
- **에러 처리**: 사용자 친화적 에러 메시지 및 복구 옵션
- **실시간 피드백**: 타이핑 인디케이터, 진행률 표시, 토큰 카운트
- **그룹 관리 UI**: 드래그 앤 드롭으로 문서 그룹 할당, 트리 뷰 탐색

### 🚀 프로덕션 기능
- **멀티 워커 서버**: CPU 코어 기반 자동 워커 설정 (최대 8개), 동시 요청 처리
- **비동기 처리**: asyncio.to_thread로 블로킹 작업 처리, 이벤트 루프 차단 방지
- **헬스 체크**: `/health` 엔드포인트로 Redis, 모델, 시스템 상태 모니터링
- **메트릭 수집**: `/metrics` Prometheus 호환 엔드포인트로 성능 지표 추적
- **프로덕션 로깅**: 구조화된 로깅, 로그 로테이션 (100MB, 7일 보관)
- **API 문서**: Swagger UI (`/docs`), ReDoc (`/redoc`) 자동 생성
- **보안 헤더**: CSP, XSS 방지, 프레임 보호, MIME 타입 스니핑 차단

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐
│   웹 브라우저    │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│  FastAPI 서버   │
│  (Python)       │◄─────┐
└────────┬────────┘      │
         │               │ REST API
    ┌────┴────┐          │
    │         │          │
    ▼         ▼          │
┌────────┐ ┌──────────┐  │
│ Qwen   │ │  Jina    │  │
│  LLM   │ │Embeddings│  │
│ (MLX)  │ │  (MPS)   │  │
└────────┘ └─────┬────┘  │
              │          │
              ▼          │
        ┌──────────┐     │
        │  Redis   │     │
        │Vector DB │     │
        │ (Docker) │     │
        └──────────┘     │
                         │
              ┌──────────┴─────────┐
              │ Java Document      │
              │ Extraction Service │
              │ (Spring Boot)      │
              │ - PDF (PDFBox)     │
              │ - Office (POI)     │
              │ - HWP/HWPX         │
              │ (Docker)           │
              └────────────────────┘
```

## 🛠️ 기술 스택

### Backend (Python)
- **Python 3.10+**: 메인 프로그래밍 언어
- **FastAPI**: 웹 서버 프레임워크
- **MLX**: Apple Silicon GPU 가속 (Qwen LLM)
- **Sentence Transformers**: Jina Embeddings v3
- **requests**: HTTP 클라이언트 (연결 풀링)
- **LangChain**: 텍스트 청킹

### Backend (Java)
- **Java 21**: Document Extraction Service
- **Spring Boot 3.5**: REST API 프레임워크
- **Apache PDFBox 3.0**: PDF 텍스트 추출
- **Apache POI 5.3**: Office 문서 처리 (DOC, DOCX, XLS, XLSX, PPT, PPTX)
- **hwplib**: HWP 파일 처리
- **Caffeine Cache**: 고성능 LRU 캐싱 (100개 항목, 1시간)
- **Micrometer**: 성능 메트릭 수집

### Database
- **Redis Stack**: Vector DB with RediSearch (50 연결 풀, 프로덕션 최적화)
- **Docker**: 컨테이너화 (Redis, Java Service)

### Frontend
- **HTML/CSS/JavaScript**: 웹 인터페이스
- **Marked.js**: Markdown 렌더링
- **Highlight.js**: 코드 구문 강조

## 📋 시스템 요구사항

- **OS**: macOS (Apple Silicon 권장)
- **Python**: 3.10 이상
- **Docker**: Docker Desktop
- **메모리**: 최소 8GB RAM (16GB 권장)
- **저장공간**: 모델 다운로드를 위한 10GB 이상

## 🚀 빠른 시작

### 1. 설치

#### 자동 설치 (권장)

개선된 설치 스크립트로 모든 환경에서 쉽게 설치할 수 있습니다:

```bash
# 저장소 이동
cd chatbot_redis

# 설치 스크립트 실행
./setup.sh
```

#### 설치 스크립트 주요 기능

**✅ 자동 시스템 요구사항 확인**
- Python 3.10+ 버전 검증
- Docker 및 Docker Compose 확인
- Docker 데몬 실행 상태 확인
- Apple Silicon (M1/M2/M3) 감지 및 MLX 최적화 안내
- Java 17+ 및 Maven 확인 (HWP 처리용, 선택사항)

**🎨 사용자 친화적 인터페이스**
- 컬러 코드 로그 출력 (정보, 성공, 경고, 에러)
- 단계별 진행 상황 표시
- 명확한 에러 메시지 및 해결 방법 제시

**🔧 자동 환경 구성**
- Python 가상환경 자동 생성
- 필요한 패키지 자동 설치
- Redis 컨테이너 자동 시작
- `.env` 환경 설정 파일 생성
- 필수 디렉토리 구조 생성 (data, model, logs)

**💬 대화형 설치**
- HWP 파일 처리 서비스 설치 선택 (Java 필요)
- AI 모델 자동 다운로드 옵션 (~15-20GB)
- Redis 재시작 옵션 (기존 컨테이너가 있는 경우)

**📊 설치 완료 요약**
- 설치된 구성 요소 상태 표시
- 다음 단계 안내 (문서 추가, 서버 시작)
- 유용한 명령어 참고 자료

#### 수동 설치

자동 설치가 실패하거나 커스터마이징이 필요한 경우:

```bash
# 1. Python 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 2. 패키지 설치
pip install -r requirements.txt

# 3. Redis 시작
docker-compose up -d

# 4. 환경 설정 파일 생성
cp .env.example .env

# 5. 필수 디렉토리 생성
mkdir -p data model logs
```

### 2. 문서 파일 추가

```bash
# data 디렉토리에 문서 파일 복사 (9가지 형식 지원)
cp your_documents/*.pdf ./data/
cp your_documents/*.hwp ./data/
cp your_documents/*.hwpx ./data/
cp your_documents/*.{doc,docx} ./data/
cp your_documents/*.{xls,xlsx} ./data/
cp your_documents/*.{ppt,pptx} ./data/
```

**지원 형식**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX

### 3. 서버 관리

#### Foreground 모드 (기본)
```bash
# 서버 시작 (터미널에서 실행, Ctrl+C로 종료)
./run.sh

# 별도 터미널에서 서버 중지
./stop.sh
```

#### Background 모드 (권장)
```bash
# 백그라운드에서 서버 시작
./run.sh --background
# 또는 단축형
./run.sh -b

# 서버 상태 확인
./run.sh status

# 로그 실시간 확인
tail -f server.log

# 서버 중지
./run.sh stop

# 서버 재시작
./run.sh stop && ./run.sh --background
```

**Background 모드 장점**:
- 터미널 종료해도 서버 계속 실행
- 로그 파일(`server.log`)로 출력 저장
- PID 파일로 프로세스 자동 관리
- 쉬운 상태 확인 및 제어

서버가 시작되면:
- **웹 UI**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs (API 문서)
- **ReDoc**: http://localhost:8000/redoc (대체 API 문서)
- **Health Check**: http://localhost:8000/health (시스템 상태)
- **Metrics**: http://localhost:8000/metrics (Prometheus 메트릭)
- **RedisInsight**: http://localhost:8001 (Redis 관리 도구)
- **서버 준비 시간**: ~1초 (Fast Startup 모드, 96% 개선)

## 📝 사용 방법

### 기본 사용

1. 브라우저에서 http://localhost:8000 접속
2. 문서가 자동으로 로딩될 때까지 대기
3. 질문 입력 후 전송 버튼 클릭 (또는 Enter 키)
4. AI의 답변 확인 (Markdown 형식, 실시간 스트리밍)

### 🎨 UI 기능

#### 질문 자동완성
- 입력 필드에 2글자 이상 입력 시 자동완성 제안
- **인덱스 기반 검색**: O(1) 단어 조회로 즉각 응답 (<5ms)
- 키보드 화살표(↑/↓)로 항목 선택
- Enter 키로 선택된 질문 입력
- 접두사 매칭 및 점수 기반 순위 정렬

#### 다크 모드
- 헤더의 테마 버튼(🌙/☀️)으로 테마 전환
- 자동 모드: 시스템 설정에 따라 자동 전환
- 수동 모드: 사용자가 직접 선택한 테마 유지

#### 문서 관리
- 헤더의 "문서 관리" 버튼으로 문서 관리 모달 열기
- **문서 업로드**: 드래그 앤 드롭 또는 클릭하여 파일 선택 (9가지 형식 지원)
- **문서 삭제**: 각 문서의 삭제 버튼 클릭
- **문서 새로고침**: 문서 목록 갱신
- **그룹 할당**: 문서를 그룹에 배치하여 조직화
- 업로드된 모든 문서 목록 및 상태 확인

#### 문서 그룹 관리
- **그룹 생성**: "그룹 관리" 버튼으로 계층 구조 그룹 생성
- **그룹 편집**: 이름, 설명, 색상, 아이콘 커스터마이징
- **문서 할당**: 드래그 앤 드롭 또는 배치 할당으로 문서 그룹 지정
- **그룹별 검색**: 특정 그룹의 문서만 검색 (OR 검색 지원)
- **트리 뷰**: 계층 구조로 그룹 및 문서 탐색

#### 세션 관리
- **대화 저장**: 대화 내용이 자동으로 로컬 저장
- **세션 복원**: 페이지 새로고침 시 이전 대화 자동 복원
- **대화 초기화**: "대화 초기화" 버튼으로 새 대화 시작

#### 에러 처리
- 네트워크 오류, 서버 오류 발생 시 친절한 에러 메시지 표시
- "다시 시도" 버튼으로 즉시 재시도 가능
- 자동 복구 시도 및 상태 피드백

### 🧠 스마트 색인 시스템

시스템은 **자동으로 PDF/HWP 파일 변경을 감지**하여 필요한 경우에만 재색인합니다:

#### 첫 실행
- `./data` 폴더의 모든 PDF 및 HWP 파일 처리
- 임베딩 생성 및 Vector DB 저장
- 파일 메타데이터 저장 (MD5 해시, 크기, 수정 시간)

#### 재실행 시
시스템이 자동으로 다음을 확인:

✅ **변경 없음** → 기존 인덱스 사용 (빠른 시작!)
```
No document changes detected. Using existing index (150 documents)
```

⚠️ **변경 감지** → 자동 재색인
```
Document changes detected:
  • New files (2): new_document.pdf, policy_update.hwp
  • Modified files (1): old_document.pdf
  • Deleted files (1): removed.hwp
Reindexing required...
```

#### 변경 감지 방식
- **새 파일**: 추가된 PDF/HWP 파일
- **수정된 파일**: 내용이 변경된 문서 (MD5 해시 비교)
- **삭제된 파일**: 제거된 PDF/HWP 파일

#### 메타데이터 저장 위치
- **로컬**: `./data/.document_metadata.json` (파일 해시 및 메타데이터)
- **Redis**: `index:state` 키 (색인 상태 및 통계)

### 고급 기능

#### 강제 재색인

변경 여부와 관계없이 모든 문서를 재색인:

```bash
# 웹 UI에서 "문서 재색인" 버튼 클릭
# 또는 API 호출:
curl -X POST http://localhost:8000/api/reindex
```

이 명령은:
1. 기존 인덱스 삭제
2. 메타데이터 초기화
3. 모든 PDF/HWP 재처리
4. 새 인덱스 생성

#### 상태 확인

시스템 상태 및 변경 사항 확인:

```bash
curl http://localhost:8000/api/status
```

응답 예시:
```json
{
  "status": "ready",
  "document_count": 150,
  "embedding_model": "jinaai/jina-embeddings-v3",
  "llm_model": "mlx-community/Qwen3-30B-A3B-4bit",
  "index_state": {
    "indexed_at": "2025-12-08T10:30:00",
    "total_chunks": 150,
    "total_files": 5
  },
  "changes": {
    "needs_reindex": false,
    "total_changes": 0
  }
}
```

#### 문서 파일 추가/수정/삭제

1. **새 문서 추가**: `./data` 폴더에 PDF/HWP 파일 복사 후 서버 재시작
2. **문서 수정**: 파일 수정 후 서버 재시작
3. **문서 삭제**: 파일 삭제 후 서버 재시작

시스템이 자동으로 변경을 감지하고 필요한 경우 재색인합니다.

#### 대화 초기화

웹 UI에서 "대화 초기화" 버튼 클릭

## ⚙️ 환경 설정

`.env` 파일에서 설정을 변경할 수 있습니다:

```bash
# 서버 기본 설정
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=production  # production 또는 development

# Redis 설정
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_MAX_CONNECTIONS=50  # 연결 풀 크기 (기본: 50)
REDIS_SOCKET_TIMEOUT=5    # 타임아웃 (초)
REDIS_SOCKET_KEEPALIVE=true  # TCP keepalive 활성화

# 캐시 설정
CACHE_SIMILARITY_THRESHOLD=0.95  # 유사도 임계값 (0-1)
CACHE_TTL=3600  # 캐시 TTL (초, 기본: 1시간)

# 모델 설정
EMBEDDING_MODEL=jinaai/jina-embeddings-v3
LLM_MODEL=mlx-community/Qwen3-30B-A3B-4bit
MODEL_DIR=./model

# 문서 처리 설정
DATA_DIR=./data
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# 파일 업로드 제한
MAX_FILE_SIZE_MB=100  # 파일 최대 크기 (MB)

# 성능 최적화 설정
ENABLE_QUESTION_GENERATION=false  # 시작 시 자동 질문 생성

# Uvicorn 서버 설정
TIMEOUT_KEEP_ALIVE=65  # Keep-alive 타임아웃 (초)
TIMEOUT_GRACEFUL_SHUTDOWN=30  # 종료 대기 시간 (초)
LIMIT_CONCURRENCY=1000  # 최대 동시 연결 수
LIMIT_MAX_REQUESTS=10000  # 워커 재시작 전 최대 요청 수

# 로깅 설정
LOG_LEVEL=info  # debug, info, warning, error
LOG_FILE=/tmp/chatbot_production.log  # 로그 파일 경로
ACCESS_LOG=false  # 액세스 로그 활성화 (true/false)
```

## 📂 프로젝트 구조

```
chatbot_redis/
├── data/                    # PDF/HWP 문서 폴더
├── model/                   # 다운로드된 AI 모델
├── src/                     # 소스 코드
│   ├── __init__.py
│   ├── embeddings.py       # Jina embeddings
│   ├── pdf_processor.py    # PDF 처리
│   ├── hwp_processor.py    # HWP 처리
│   ├── document_processor.py # 통합 문서 처리
│   ├── document_tracker.py # 문서 변경 감지
│   ├── vector_db.py        # Redis vector DB
│   ├── cache_manager.py    # 답변 캐싱
│   ├── group_manager.py    # 문서 그룹 관리
│   ├── llm.py              # Qwen LLM
│   ├── model_manager.py    # 모델 관리
│   └── web_server.py       # FastAPI 서버
├── static/                  # 웹 UI
│   ├── index.html
│   ├── style.css
│   ├── script.js
│   ├── error-handler.js     # 에러 처리 모듈
│   ├── error-styles.css
│   ├── session-manager.js   # 세션 관리
│   ├── streaming-visualizer.js  # 스트리밍 시각화
│   ├── streaming-styles.css
│   ├── follow-up-questions.js   # 후속 질문
│   ├── follow-up-styles.css
│   ├── autocomplete.js      # 질문 자동완성
│   ├── autocomplete-styles.css
│   ├── group-manager.js     # 그룹 관리
│   └── group-styles.css
├── docker-compose.yml       # Redis 설정
├── requirements.txt         # Python 패키지
├── .env.example            # 환경 변수 템플릿
├── setup.sh                # 설치 스크립트
├── run.sh                  # 실행 스크립트
├── stop.sh                 # 종료 스크립트
└── README.md               # 이 파일
```

## 🔧 문제 해결

### Redis 연결 오류

```bash
# Redis 재시작
docker-compose restart

# Redis 로그 확인
docker-compose logs -f redis
```

### 모델 다운로드 실패

모델이 자동으로 다운로드되지 않으면:

```bash
# model 디렉토리 확인
ls -la model/

# 수동으로 재시도하려면 서버 재시작
./run.sh
```

### 파일 업로드 실패 (파일 크기 초과)

파일이 너무 큰 경우 (기본 제한: 100MB):

```bash
# .env 파일에서 제한 변경 (예: 200MB)
MAX_FILE_SIZE_MB=200
```

**권장 크기**:
- 일반 문서: 50MB 이하
- 대용량 문서: 100-200MB
- 초대형 문서 (500MB+): 메모리 부족 및 타임아웃 위험

**대용량 파일 처리 팁**:
1. 파일을 여러 개로 분할
2. 이미지가 많은 경우 이미지 제거 후 업로드
3. 필요한 부분만 추출하여 별도 PDF로 저장

### 메모리 부족

`.env` 파일에서 더 작은 모델 사용:

```bash
LLM_MODEL=mlx-community/Qwen2.5-1.5B-Instruct-4bit
```

### Apple GPU 미사용

MLX가 자동으로 Apple GPU를 사용합니다. CPU만 사용되는 경우:

```bash
# MLX 설치 확인
pip list | grep mlx

# 재설치
pip install --upgrade mlx mlx-lm
```

## 🛑 서버 종료

```bash
# 서버 종료 (Ctrl+C)

# Redis 중지
docker-compose down

# Redis 데이터 삭제 (선택사항)
docker-compose down -v
```

## 📊 성능 최적화

### Apple Silicon 최적화

- MLX 프레임워크가 자동으로 Metal GPU 사용
- Sentence Transformers가 MPS (Metal Performance Shaders) 사용
- 메모리 효율적인 4-bit 양자화 모델 사용

### Python 최적화 (2025-12-21)

#### HTTP 연결 풀링
- **DocumentService**: 10-20 연결 풀, 자동 재시도 3회
- **HWPProcessor**: 5-10 연결 풀, 자동 재시도 2회
- 성능 향상: 단일 문서 10-15%, 다중 문서 25-35%

#### 코드 최적화
- **HWP Fallback 개선**: 2단계 폴백 (HWPProcessor → Python 직접 파싱)
- **불필요한 코드 제거**: pdf_service.py 삭제 (-118 줄)
- **메모리 효율**: 연결 재사용으로 리소스 절약

### Java Document Service 최적화 (2025-12-21)

#### JVM 메모리 관리
```
-Xms512m                    # 초기 힙 512MB
-Xmx2048m                   # 최대 힙 2GB
-XX:+UseG1GC                # G1 가비지 컬렉터
-XX:MaxGCPauseMillis=200    # 최대 GC 일시정지 200ms
-XX:+UseStringDeduplication # 문자열 중복 제거
```

#### Caffeine 캐싱
- **LRU 캐시**: 최대 100개 항목, 1시간 만료
- **캐시 히트**: 동일 문서 재처리 시 99% 빠름 (즉시 응답)
- **메모리 최적화**: 자동 만료 및 크기 제한

#### 비동기 처리
- **스레드 풀**: 4-16 스레드로 대량 문서 병렬 처리
- **대기 큐**: 100개 작업 버퍼링
- **성능**: 대량 처리 시 2-3배 향상

#### Tomcat 서버 최적화
- **워커 스레드**: 최대 200개 동시 요청 처리
- **HTTP 압축**: JSON 응답 30-50% 크기 감소
- **연결 관리**: 최대 10,000 동시 연결 지원

#### 성능 메트릭
- **시작 시간**: 1.26초 (37% 개선)
- **메모리 사용**: 367-401MB (동적 할당)
- **CPU 사용**: 유휴 시 0.3-0.5%

### 벡터 검색 최적화

- **Redis 연결 풀링**: 50개 동시 연결로 처리량 5-10배 향상 (프로덕션 최적화)
- **Redis Vector 인덱스**: 코사인 유사도 기반 고속 검색
- **답변 캐싱**: 95% 유사도 기반 자동 캐시 응답 (중복 쿼리 제거)
- **Connection Health Check**: 30초 간격 연결 상태 확인 및 자동 복구

### 프로덕션 서버 최적화 (2025-12-23)

#### 멀티 워커 아키텍처
- **자동 워커 설정**: `(CPU 코어 * 2) + 1`, 최소 4개, 최대 8개
- **비동기 처리**: asyncio.to_thread()로 블로킹 작업(임베딩, LLM) 처리
- **동시 요청 처리**: 이벤트 루프 차단 없이 여러 요청 병렬 처리
- **워커 재활용**: 10,000 요청마다 워커 자동 재시작 (메모리 누수 방지)

#### 모니터링 및 관찰성
```
/health      - 시스템 헬스 체크 (Redis, 모델, CPU, 메모리, 디스크)
/metrics     - Prometheus 메트릭 (캐시 히트율, Redis 연결, 시스템 리소스)
/docs        - Swagger UI (인터랙티브 API 문서)
/redoc       - ReDoc (읽기 전용 API 문서)
```

#### 로깅 시스템
- **구조화된 로깅**: 타임스탬프, 레벨, 소스 위치 포함
- **로그 로테이션**: 100MB마다 회전, 7일 보관, 자동 압축 (zip)
- **환경별 설정**: Production (INFO), Development (DEBUG)
- **파일 로깅**: `/tmp/chatbot_production.log` (설정 가능)

#### 타임아웃 및 제한
- **Keep-alive**: 65초 (브라우저 타임아웃 방지)
- **Graceful Shutdown**: 30초 (요청 완료 대기 후 종료)
- **동시 연결 제한**: 1,000개 (DoS 방지)
- **연결 대기 큐**: 2,048개 (백로그)

#### 보안 강화
- **CSP 헤더**: XSS 공격 차단, Swagger UI는 허용 목록 방식
- **보안 헤더**: X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
- **서버 정보 숨김**: 버전 정보 노출 차단
- **프록시 지원**: X-Forwarded-* 헤더 처리 (로드 밸런서 호환)

### 서버 시작 최적화 (Fast Startup Mode)

#### ⚡ Lazy Loading 전략
- **LLM 지연 로딩**: LLM은 첫 질문 요청 시에만 로드 (시작 시 수십 초 절약)
- **선택적 질문 생성**: 기본적으로 비활성화 (`ENABLE_QUESTION_GENERATION=false`)
- **필수 구성요소만 로드**: Embedding 모델 + Redis만 시작 시 초기화

#### 📊 시작 시간 비교
| 모드 | 시작 시간 | LLM 로딩 | 질문 생성 |
|------|----------|---------|----------|
| **Fast (기본)** | ~1초 | 첫 요청 시 | 비활성화 |
| Legacy | ~30초+ | 시작 시 | 백그라운드 |

#### 🚀 시작 과정
```bash
🚀 Starting application initialization (fast mode)...
📚 Loading embedding model...          (0.5초)
🔌 Connecting to Redis...              (즉시)
💾 Initializing cache manager...       (즉시)
⚡ LLM will load on first use         (건너뜀!)
✅ Application initialized! (총 ~1초)
💡 First chat request will load LLM automatically
```

#### 💬 첫 질문 시
- LLM 자동 로드: 10-15초 (한 번만)
- 이후 모든 질문: 즉시 응답 (LLM 이미 로드됨)

#### 📝 질문 생성 활성화 (선택사항)
```bash
# .env 파일에 추가
ENABLE_QUESTION_GENERATION=true
```
- 시작 시 모든 문서에 대해 한국어 질문 생성
- 백그라운드에서 처리되므로 서버는 즉시 사용 가능
- 생성된 질문은 자동완성에 사용

#### 🎯 권장 사항
- **개발 환경**: Fast 모드 (기본) - 빠른 재시작
- **프로덕션**: 질문 생성 활성화 - 더 나은 자동완성 경험

#### 기타 최적화
- **스마트 색인**: 파일 변경 감지로 불필요한 재처리 방지
- **서버 준비 시간**: ~1초 (이전 대비 96% 단축)

### 프론트엔드 최적화

- **자동완성 인덱스**: O(1) 단어 조회로 검색 속도 10배 향상 (<5ms 응답)
- **세션 관리**: localStorage 기반 대화 히스토리 자동 저장/복원
- **에러 처리**: 자동 재시도 및 지수 백오프 전략

## 🤝 기여

이슈나 개선 사항이 있으면 자유롭게 제안해주세요!

## 📄 라이선스

MIT License

## 🙏 감사

- [Jina AI](https://jina.ai/) - Embeddings 모델
- [Qwen](https://github.com/QwenLM/Qwen) - LLM 모델
- [MLX](https://github.com/ml-explore/mlx) - Apple GPU 가속
- [Redis](https://redis.io/) - Vector Database
- [FastAPI](https://fastapi.tiangolo.com/) - Web Framework
