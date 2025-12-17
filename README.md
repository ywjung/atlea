# 📚 PDF RAG 챗봇

PDF 문서를 기반으로 질의응답을 제공하는 AI 챗봇 시스템입니다.

## ✨ 주요 기능

### 🔍 문서 처리 및 검색
- **PDF/HWP 문서 자동 처리**: data 폴더의 모든 PDF 및 HWP 파일을 자동으로 처리하고 벡터 DB에 저장
- **스마트 색인**: 파일 변경 감지 및 자동 재색인 (매번 임베딩하지 않음)
- **고속 벡터 검색**: Redis Vector DB + 연결 풀링으로 빠른 문서 검색 (동시 쿼리 5-10배 개선)
- **문서 관리**: 웹 UI에서 PDF/HWP 업로드, 삭제, 상태 확인
- **중복 방지**: MD5 해시 기반 중복 문서 업로드 차단

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

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐
│   웹 브라우저    │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│  FastAPI 서버   │
│  (Python)       │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌──────────┐
│ Qwen   │ │  Jina    │
│  LLM   │ │Embeddings│
│ (MLX)  │ │  (MPS)   │
└────────┘ └─────┬────┘
              │
              ▼
        ┌──────────┐
        │  Redis   │
        │Vector DB │
        │ (Docker) │
        └──────────┘
```

## 🛠️ 기술 스택

### Backend
- **Python 3.10+**: 메인 프로그래밍 언어
- **FastAPI**: 웹 서버 프레임워크
- **MLX**: Apple Silicon GPU 가속 (Qwen LLM)
- **Sentence Transformers**: Jina Embeddings v3
- **PyPDF**: PDF 문서 처리
- **olefile**: HWP 문서 처리
- **LangChain**: 텍스트 청킹

### Database
- **Redis Stack**: Vector DB with RediSearch (20 연결 풀)
- **Docker**: Redis 컨테이너화

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
# data 디렉토리에 PDF/HWP 파일 복사
cp your_documents/*.pdf ./data/
cp your_documents/*.hwp ./data/
```

### 3. 서버 관리

```bash
# 서버 시작
./run.sh

# 서버 중지
./stop.sh

# 서버 재시작
./stop.sh && ./run.sh
```

서버가 시작되면:
- 웹 UI: http://localhost:8000
- RedisInsight: http://localhost:8001 (Redis 관리 도구)
- 서버 준비 시간: ~14초 (질문 생성은 백그라운드 처리)

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
- 헤더의 "문서 관리" 버튼으로 PDF 관리 모달 열기
- **PDF 업로드**: 드래그 앤 드롭 또는 클릭하여 파일 선택
- **문서 삭제**: 각 문서의 삭제 버튼 클릭
- **문서 새로고침**: 문서 목록 갱신
- 업로드된 모든 문서 목록 및 상태 확인

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
# Redis 설정
REDIS_HOST=localhost
REDIS_PORT=6379

# 모델 설정
EMBEDDING_MODEL=jinaai/jina-embeddings-v3
LLM_MODEL=mlx-community/Qwen3-30B-A3B-4bit
MODEL_DIR=./model

# 문서 처리 설정
DATA_DIR=./data
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# 서버 설정
HOST=0.0.0.0
PORT=8000
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
│   └── autocomplete-styles.css
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

### 벡터 검색 최적화

- **Redis 연결 풀링**: 20개 동시 연결로 처리량 5-10배 향상
- **Redis Vector 인덱스**: 코사인 유사도 기반 고속 검색
- **답변 캐싱**: 95% 유사도 기반 자동 캐시 응답 (중복 쿼리 제거)

### 서버 시작 최적화

- **비동기 질문 생성**: 백그라운드 태스크로 처리 (시작 시간 95% 단축)
- **스마트 색인**: 파일 변경 감지로 불필요한 재처리 방지
- **서버 준비 시간**: ~14초 (질문 생성은 백그라운드에서 진행)

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
