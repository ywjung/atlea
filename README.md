# ATLEA (Advanced Trusted Learning & Enterprise Assistant)

<div align="center">

**AI 기반 하이브리드 RAG 문서 질의응답 시스템**

로컬 문서 검색과 웹 검색을 결합한 엔터프라이즈급 AI 어시스턴트

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Java](https://img.shields.io/badge/Java-21-orange.svg)](https://openjdk.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-Stack-red.svg)](https://redis.io/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.5.0-brightgreen.svg)]()
[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-blueviolet?logo=anthropic)](https://claude.ai/claude-code)

[빠른 시작](#-빠른-시작) • [기능](#-주요-기능) • [API](#-api-레퍼런스) • [보안](#-보안) • [로드맵](#%EF%B8%8F-로드맵)

</div>

---

## 📖 목차

- [소개](#-소개)
- [주요 기능](#-주요-기능)
- [기술 스택](#-기술-스택)
- [시스템 요구사항](#-시스템-요구사항)
- [빠른 시작](#-빠른-시작)
- [사용 가이드](#-사용-가이드)
- [API 레퍼런스](#-api-레퍼런스)
- [프로젝트 구조](#-프로젝트-구조)
- [환경 설정](#-환경-설정)
- [배포 가이드](#-배포-가이드)
- [보안](#-보안)
- [문제 해결](#-문제-해결)
- [로드맵](#%EF%B8%8F-로드맵)
- [기여 가이드](#-기여-가이드)
- [라이선스](#-라이선스)
- [감사](#-감사)

---

## 🎯 소개

ATLEA는 **Retrieval-Augmented Generation (RAG)** 기술을 활용하여 다양한 형식의 문서에서 정보를 추출하고, 자연어 질문에 정확하게 답변하는 AI 시스템입니다. v2.5.0부터 SearXNG 웹 검색을 통합하여 로컬 문서와 웹 정보를 결합한 **하이브리드 RAG**를 지원합니다.

### 주요 사용 사례

- **기업 문서 관리**: 내부 정책, 매뉴얼, 보고서에서 신속한 정보 검색
- **연구 자료 분석**: 학술 논문, 기술 문서에서 필요한 정보 추출
- **멀티테넌트 지식 베이스**: 조직별 데이터 격리와 접근 제어
- **보안 문서 시스템**: JWT 인증, 2FA, 감사 로그를 갖춘 엔터프라이즈 환경

---

## ✨ 주요 기능

### 🔍 하이브리드 RAG

- **로컬 문서 검색**: Redis Vector DB 기반 시맨틱 검색
- **웹 검색 통합**: SearXNG 자체 호스팅 메타 검색 (Google, Bing, DuckDuckGo 등)
- **Crawl4AI 콘텐츠 추출**: 검색 스니펫을 전체 페이지 콘텐츠로 확장 (27-125배)
- **프로바이더 선택**: 관리자 페이지에서 Tavily/SearXNG 전환 가능

### 📄 문서 처리

- **11가지 문서 형식**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT
- **Java Document Service**: Apache POI + PDFBox 기반 고성능 텍스트 추출
- **자동 버전 관리**: MD5 해시 기반 중복 감지, 버전 추적 및 복원
- **ClamAV 바이러스 스캔**: 업로드 파일 실시간 악성코드 검사
- **Magic Bytes 검증**: 파일 확장자 위조 방지

### 🔐 인증 및 보안

- **JWT 인증**: Access Token (15분) + Refresh Token (7일), 자동 갱신
- **TOTP 2단계 인증**: Google Authenticator 호환, QR 코드 등록, 복구 코드
- **비밀번호 정책**: bcrypt 해싱, 복잡도 검증, 토큰 기반 재설정
- **브루트포스 방어**: 5회 실패 시 계정 잠금 (30분)
- **CSRF 보호**: 토큰 기반 CSRF 방어
- **CSP 헤더**: Content Security Policy로 XSS 차단
- **Rate Limiting**: Redis 기반 요청 속도 제한
- **PII 탐지**: 개인정보 자동 탐지 및 마스킹

### 🏢 조직 관리 (멀티테넌트)

- **조직별 데이터 격리**: 독립적인 문서 저장소 및 검색 권한
- **역할 기반 접근 제어**: 시스템 관리자 / 조직 관리자 / 일반 사용자
- **조직-그룹-문서 계층**: 체계적 권한 관리

### 🤖 AI 기능

- **Qwen3 30B LLM**: 4-bit 양자화, 한국어 최적화
- **KURE-v1 Embeddings**: 1024차원 한국어 특화 임베딩
- **MLX / CUDA / CPU**: 플랫폼별 자동 GPU 가속
- **스트리밍 응답**: WebSocket 기반 실시간 토큰 생성
- **답변 캐싱**: 95% 유사도 기준 자동 캐시
- **자동 질문 생성**: 문서당 12개 한국어 질문 자동 생성

### 🔊 TTS (Text-to-Speech)

- 답변 텍스트를 음성으로 변환

### 🎭 페르소나

- 다양한 AI 응답 스타일 설정

### 📊 관리자 대시보드

- **보안 대시보드**: 보안 이벤트 모니터링, 로그인 추적
- **감사 로그**: 사용자 활동 기록 및 추적
- **세션 관리**: 활성 세션 모니터링 및 강제 로그아웃
- **시스템 통계**: CPU, 메모리, 디스크, 모델 상태

### 🎨 사용자 인터페이스

- **반응형 디자인**: 모바일/태블릿/데스크톱 지원
- **다크 모드**: 라이트/다크 테마 자동/수동 전환
- **Markdown 렌더링**: 코드 블록, 테이블, 구문 강조
- **자동완성**: 2글자 입력 시 O(1) 검색, <5ms 응답
- **모달 스택 관리**: ESC 키로 중첩 모달 LIFO 제어
- **랜딩 페이지**: 프로젝트 소개 및 시작 안내

---

## 🛠️ 기술 스택

### Backend

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| **웹 프레임워크** | FastAPI + Uvicorn | REST API, WebSocket, ASGI |
| **인증** | JWT + TOTP + bcrypt | 토큰 인증, 2FA, 비밀번호 해싱 |
| **보안** | CSRF, CSP, Rate Limiting, ClamAV | 보안 미들웨어 스택 |
| **AI/ML** | MLX, Sentence Transformers, PyTorch | GPU 가속, 임베딩, LLM |
| **Vector DB** | Redis Stack (RediSearch, RedisJSON) | 벡터 검색, 캐시, 세션 |
| **문서 추출** | Spring Boot + Apache POI + PDFBox | Java 마이크로서비스 |
| **웹 검색** | SearXNG + Crawl4AI | 자체 호스팅 메타 검색 |

### Frontend

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| **핵심** | HTML5 / CSS3 / ES6 Modules | 웹 UI |
| **빌드** | Vite | 번들링 및 개발 서버 |
| **테스트** | Vitest + Playwright | 단위 테스트 + E2E 테스트 |
| **렌더링** | Marked.js + Highlight.js | Markdown + 구문 강조 |

### DevOps

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| **컨테이너** | Docker Compose | 5가지 구성 (기본, Full, GPU, Production, SearXNG) |
| **리버스 프록시** | Nginx | SSL, 로드 밸런싱 |
| **모니터링** | Prometheus + Grafana | 시스템 메트릭 |
| **보안 스캔** | CycloneDX SBOM + pip-audit | 취약점 분석 |

---

## 📋 시스템 요구사항

### 기본 구성 (Qwen3 30B)

| 항목 | 요구사항 |
|------|----------|
| **OS** | macOS 14+ (Apple Silicon) 또는 Linux (NVIDIA GPU) |
| **메모리** | 32GB RAM 이상 (24GB 최소) |
| **저장공간** | 50GB SSD |
| **GPU** | Apple M2 Pro/Max/Ultra 또는 NVIDIA 16GB+ VRAM |

### 필수 소프트웨어

- Python 3.10+
- Docker & Docker Compose
- Git

### 선택 소프트웨어

- Java 21 + Maven 3.9+ (Java Document Service 사용 시)
- Node.js 18+ (프론트엔드 테스트 시)

### 포트 요구사항

| 포트 | 서비스 | 용도 |
|------|--------|------|
| 8000 | FastAPI | 웹 UI, API |
| 6379 | Redis | Vector DB, Cache |
| 8080 | Java Service | 문서 추출 (선택) |
| 8888 | SearXNG | 웹 검색 (선택) |
| 8001 | RedisInsight | Redis 관리 (선택) |

---

## 🚀 빠른 시작

### 1단계: 저장소 클론

```bash
git clone https://github.com/ywjung/atlea.git
cd atlea
```

### 2단계: 자동 설치

```bash
chmod +x setup.sh
./setup.sh
```

설치 스크립트가 Python 가상환경, Redis, 환경 설정, AI 모델 다운로드를 자동으로 처리합니다.

### 3단계: 문서 추가

```bash
cp your_documents/*.pdf ./data/
cp your_documents/*.{hwp,hwpx,doc,docx,xls,xlsx,ppt,pptx,txt} ./data/
```

### 4단계: 서버 시작

```bash
# 자동 배포 (권장)
./deploy.sh

# 또는 수동 실행
./run.sh --background
```

### 5단계: 접속

브라우저에서 http://localhost:8000 접속

초기 관리자 계정은 `setup.sh` 또는 `scripts/setup_admin.py`로 생성합니다.

```bash
# 관리자 계정 생성
python scripts/setup_admin.py
```

**서비스 URL**:
| URL | 용도 |
|-----|------|
| http://localhost:8000 | 웹 UI (랜딩 페이지) |
| http://localhost:8000/static/login.html | 로그인 |
| http://localhost:8000/docs | Swagger API 문서 |
| http://localhost:8000/health | Health Check |
| http://localhost:8000/metrics | Prometheus 메트릭 |

<details>
<summary>수동 설치 (고급 사용자)</summary>

```bash
# 1. Python 환경
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Redis 시작
docker compose up -d redis

# 3. 환경 설정
cp .env.example .env
nano .env

# 4. Java Document Service (선택)
cd document-service && mvn clean package -DskipTests && cd ..
docker compose up -d document-service

# 5. 서버 시작
python -m src.web_server
```

</details>

---

## 📖 사용 가이드

### 기본 사용법

1. **로그인**: 이메일/비밀번호로 로그인 (2FA 설정 시 TOTP 코드 입력)
2. **질문 입력**: 채팅 입력 필드에 자연어 질문 입력 → Enter 전송
3. **자동완성**: 2글자 이상 입력 시 추천 질문 표시
4. **답변 확인**: 스트리밍으로 실시간 답변 생성, 참고 문서 출처 표시
5. **문서 관리**: 헤더의 "문서 관리" 버튼으로 업로드/삭제/그룹 관리

### 키보드 단축키

| 단축키 | 기능 |
|--------|------|
| `F1` | 도움말 모달 |
| `Ctrl+N` | 새 대화 |
| `Ctrl+/` | 사이드바 토글 |
| `Ctrl+K` | 입력 필드 포커스 |
| `Esc` | 최상위 모달 닫기 |

### 관리자 기능

관리자 대시보드(`/static/admin.html`)에서:
- 사용자 관리 (생성, 비활성화, 역할 변경)
- 조직 관리 (생성, 사용자 배정)
- 보안 이벤트 모니터링
- 시스템 설정 (웹 검색 프로바이더, TTS, 페르소나 등)

---

## 🔌 API 레퍼런스

전체 API 문서는 서버 실행 후 **Swagger UI** (`/docs`)에서 확인하세요.

### 인증

대부분의 엔드포인트는 JWT 인증이 필요합니다. `Authorization: Bearer <token>` 헤더를 포함하세요.

```bash
# 로그인하여 토큰 발급
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "your-password"}'

# 토큰 사용
curl http://localhost:8000/api/documents \
  -H "Authorization: Bearer <access_token>"
```

### 주요 엔드포인트

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `GET` | `/health` | - | 시스템 상태 확인 |
| `GET` | `/metrics` | - | Prometheus 메트릭 |
| **인증** |
| `POST` | `/api/auth/login` | - | 로그인 (JWT 발급) |
| `POST` | `/api/auth/register` | - | 회원가입 |
| `POST` | `/api/auth/refresh` | Token | 토큰 갱신 |
| `POST` | `/api/auth/logout` | Token | 로그아웃 |
| `POST` | `/api/auth/totp/setup` | Token | 2FA 설정 |
| **질의응답** |
| `POST` | `/api/query` | Token | 일반 질의응답 |
| `WS` | `/ws/chat` | Token | 스트리밍 질의응답 |
| **문서** |
| `GET` | `/api/documents` | Token | 문서 목록 |
| `POST` | `/api/documents/upload` | Token | 문서 업로드 |
| `DELETE` | `/api/documents/{filename}` | Token | 문서 삭제 |
| **그룹** |
| `GET` | `/api/groups` | Token | 그룹 목록 |
| `POST` | `/api/groups` | Token | 그룹 생성 |
| **세션** |
| `GET` | `/api/conversations` | Token | 대화 목록 |
| `DELETE` | `/api/conversations` | Token | 전체 대화 삭제 |
| **관리자** |
| `GET` | `/api/admin/users` | Admin | 사용자 목록 |
| `GET` | `/api/admin/stats` | Admin | 시스템 통계 |
| **조직** |
| `GET` | `/api/organizations` | Token | 조직 목록 |
| `POST` | `/api/organizations` | Admin | 조직 생성 |
| **TTS** |
| `POST` | `/api/tts` | Token | 텍스트→음성 변환 |
| **페르소나** |
| `GET` | `/api/persona` | Token | 페르소나 목록 |
| **감사** |
| `GET` | `/api/audit/logs` | Admin | 감사 로그 조회 |
| **보안** |
| `GET` | `/api/security/events` | Admin | 보안 이벤트 |
| **검색** |
| `POST` | `/api/search/web` | Token | 웹 검색 |

---

## 📁 프로젝트 구조

```
atlea/
├── src/                          # Python 소스 코드
│   ├── web_server.py             # FastAPI 메인 서버
│   ├── startup.py                # 서버 초기화
│   ├── routers/                  # API 라우터 (26개)
│   │   ├── auth.py               # 인증 API
│   │   ├── admin.py              # 관리자 API
│   │   ├── documents.py          # 문서 관리
│   │   ├── query.py              # 질의응답
│   │   ├── groups.py             # 그룹 관리
│   │   ├── organizations.py      # 조직 관리
│   │   ├── tts.py                # TTS
│   │   ├── persona.py            # 페르소나
│   │   ├── audit.py              # 감사 로그
│   │   ├── security.py           # 보안 이벤트
│   │   ├── search.py             # 웹 검색
│   │   ├── conversations.py      # 대화 관리
│   │   ├── feedback.py           # 피드백
│   │   ├── settings.py           # 설정
│   │   └── ...                   # 기타 라우터
│   ├── auth/                     # 인증 모듈 (16개)
│   │   ├── service.py            # 인증 서비스 로직
│   │   ├── middleware.py         # 인증 미들웨어
│   │   ├── totp.py               # TOTP 2FA
│   │   ├── password_policy.py    # 비밀번호 정책
│   │   ├── password_reset.py     # 비밀번호 재설정
│   │   ├── brute_force_protection.py  # 브루트포스 방어
│   │   ├── rate_limiter.py       # Rate Limiting
│   │   ├── token_blacklist.py    # 토큰 블랙리스트
│   │   ├── security_logger.py    # 보안 이벤트 로깅
│   │   ├── alert_system.py       # 보안 알림
│   │   └── ...                   # 기타 인증 모듈
│   ├── middleware/                # 미들웨어 (6개)
│   │   ├── csrf_protection.py    # CSRF 보호
│   │   ├── csp_nonce.py          # CSP 논스
│   │   ├── rate_limiter_redis.py # Redis Rate Limiter
│   │   ├── audit_middleware.py   # 감사 미들웨어
│   │   └── exception_handlers.py # 예외 처리
│   ├── services/                 # 비즈니스 서비스 (7개)
│   │   ├── tts_service.py        # TTS 서비스
│   │   ├── persona_service.py    # 페르소나 서비스
│   │   ├── question_generation.py # 질문 생성
│   │   ├── reindex_service.py    # 재색인 서비스
│   │   ├── scheduler_service.py  # 스케줄러
│   │   └── settings_service.py   # 설정 서비스
│   ├── utils/                    # 유틸리티 (7개)
│   │   ├── file_security.py      # 파일 보안 (ClamAV)
│   │   ├── pii_detector.py       # PII 탐지
│   │   ├── pagination.py         # 페이지네이션
│   │   ├── validation.py         # 입력 검증
│   │   └── ...                   # 기타 유틸리티
│   ├── audit/                    # 감사 로그
│   │   └── audit_logger.py
│   ├── config/                   # 설정
│   │   ├── settings.py           # 앱 설정
│   │   ├── production.py         # 프로덕션 설정
│   │   └── prompts.py            # 프롬프트 설정
│   ├── models/                   # 데이터 모델
│   │   └── persona.py
│   ├── hybrid_rag.py             # 하이브리드 RAG 파이프라인
│   ├── vector_db.py              # Redis Vector DB
│   ├── embeddings.py             # KURE-v1 임베딩
│   ├── llm.py                    # LLM 통합 (MLX/Ollama)
│   ├── document_processor.py     # 문서 처리
│   ├── document_version.py       # 문서 버전 관리
│   ├── cache_manager.py          # 답변 캐싱
│   ├── conversation_manager.py   # 대화 관리
│   ├── group_manager.py          # 그룹 관리
│   ├── organization_manager.py   # 조직 관리
│   └── ...                       # 기타 핵심 모듈
│
├── static/                       # 프론트엔드
│   ├── landing.html              # 랜딩 페이지
│   ├── login.html                # 로그인
│   ├── register.html             # 회원가입
│   ├── index.html                # 메인 채팅 UI
│   ├── profile.html              # 사용자 프로필
│   ├── admin.html                # 관리자 대시보드
│   ├── reset-password.html       # 비밀번호 재설정
│   ├── script.js                 # 메인 JavaScript
│   ├── auth.js                   # 인증 클라이언트
│   ├── session-manager.js        # 세션 관리
│   ├── admin/                    # 관리자 UI 모듈
│   ├── js/                       # ES6 모듈 구조
│   └── css/                      # 스타일시트
│
├── document-service/             # Java Document Service
│   ├── src/main/java/            # Spring Boot 소스
│   ├── Dockerfile
│   └── pom.xml
│
├── tests/                        # 테스트
│   ├── auth/                     # 인증 테스트
│   ├── unit/                     # 단위 테스트 (Vitest)
│   ├── e2e/                      # E2E 테스트 (Playwright)
│   └── integration/              # 통합 테스트
│
├── docs/                         # 문서
│   ├── DEPLOYMENT_GUIDE.md
│   ├── AUTHENTICATION.md
│   ├── CLAMAV_INTEGRATION.md
│   └── ...                       # 30+ 가이드 문서
│
├── scripts/                      # 운영 스크립트
│   ├── setup_admin.py            # 관리자 계정 생성
│   ├── migrate_to_organizations.py  # 조직 마이그레이션
│   ├── backup.sh / restore.sh    # 백업/복원
│   └── ...                       # 기타 스크립트
│
├── searxng/                      # SearXNG 설정
│   └── settings.yml
│
├── nginx/                        # Nginx 설정
│   └── nginx.conf
│
├── docker-compose.yml            # 기본 Docker 구성
├── docker-compose.full.yml       # 전체 서비스
├── docker-compose.gpu.yml        # GPU 지원
├── docker-compose.production.yml # 프로덕션
├── docker-compose.searxng.yml    # SearXNG 포함
├── deploy.sh                     # 배포 스크립트
├── setup.sh                      # 설치 스크립트
├── run.sh                        # 실행 스크립트
├── stop.sh                       # 종료 스크립트
├── vite.config.js                # Vite 설정
├── playwright.config.js          # Playwright 설정
├── requirements.txt              # Python 의존성
├── requirements-mac.txt          # macOS 의존성
├── requirements-linux.txt        # Linux 의존성
└── LICENSE                       # Apache License 2.0
```

---

## ⚙️ 환경 설정

### 주요 환경 변수 (`.env`)

```bash
# 서버
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=production

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_MAX_CONNECTIONS=50

# AI 모델
EMBEDDING_MODEL=nlpai-lab/KURE-v1
LLM_MODEL=mlx-community/Qwen3-30B-A3B-4bit
MODEL_DIR=./model

# 보안
SECRET_KEY=your-secret-key        # JWT 서명 키
CSRF_SECRET=your-csrf-secret      # CSRF 토큰 시크릿

# 문서 처리
DATA_DIR=./data
CHUNK_SIZE=512
MAX_FILE_SIZE_MB=100

# Java Document Service
DOCUMENT_SERVICE_URL=http://localhost:8080

# SearXNG (선택)
SEARXNG_URL=http://localhost:8888

# ClamAV (선택)
CLAMAV_ENABLED=true
```

전체 환경 변수 목록은 `.env.example`을 참조하세요.

---

## 🚢 배포 가이드

자세한 배포 가이드는 [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)를 참조하세요.

### 간단 배포

```bash
# 1. 환경 설정
cp .env.example .env && nano .env

# 2. 배포 스크립트 실행
./deploy.sh

# 3. SearXNG 웹 검색 추가 (선택)
docker compose -f docker-compose.searxng.yml up -d
```

### Docker Compose 구성

| 파일 | 용도 |
|------|------|
| `docker-compose.yml` | 기본 (Redis + Document Service) |
| `docker-compose.full.yml` | 전체 서비스 |
| `docker-compose.gpu.yml` | NVIDIA GPU 지원 |
| `docker-compose.production.yml` | 프로덕션 최적화 |
| `docker-compose.searxng.yml` | SearXNG 웹 검색 |

---

## 🛡️ 보안

### 구현된 보안 기능

- **JWT 인증**: Access/Refresh Token, 자동 갱신, 토큰 블랙리스트
- **TOTP 2FA**: Google Authenticator 호환
- **CSRF 보호**: 토큰 기반 방어
- **CSP 헤더**: XSS 공격 차단
- **Rate Limiting**: Redis 기반 요청 제한
- **브루트포스 방어**: 5회 실패 시 계정 잠금
- **ClamAV 바이러스 스캔**: 업로드 파일 검사
- **PII 탐지**: 개인정보 자동 탐지
- **Magic Bytes 검증**: 파일 확장자 위조 방지
- **SBOM**: CycloneDX 형식 소프트웨어 구성 목록
- **감사 로그**: 주요 보안 이벤트 기록
- **보안 헤더**: X-Frame-Options, X-Content-Type-Options 등

### 보안 체크리스트

- [x] JWT 인증 및 TOTP 2FA
- [x] CSRF 토큰 보호
- [x] CSP + 보안 헤더
- [x] Rate Limiting
- [x] 파일 업로드 검증 (Magic bytes, ClamAV)
- [x] PII 탐지
- [x] 감사 로그
- [ ] HTTPS (배포 환경에서 Nginx + Let's Encrypt 설정)
- [ ] Redis 비밀번호 설정 (프로덕션 권장)

자세한 내용은 [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md)와 [docs/CLAMAV_INTEGRATION.md](docs/CLAMAV_INTEGRATION.md)를 참조하세요.

---

## 🔧 문제 해결

### 일반적인 문제

#### Redis 연결 오류
```bash
docker compose restart redis
docker exec -it redis redis-cli ping
```

#### 모델 다운로드 실패
```bash
export HF_TOKEN=your_token_here
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nlpai-lab/KURE-v1')"
```

#### Java Service 시작 실패
```bash
java --version  # 21 이상 필요
cd document-service && mvn clean package -DskipTests
docker compose logs -f document-service
```

#### 메모리 부족
`.env`에서 경량 모델로 변경:
```bash
LLM_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit
```

### 로그 확인

```bash
tail -f logs/server.log              # Python 서버
docker compose logs -f               # Docker 전체
docker compose logs -f document-service  # Java 서비스
```

### 디버그 모드

```bash
ENVIRONMENT=development LOG_LEVEL=debug python -m src.web_server
```

---

## 🗺️ 로드맵

### ✅ 완료된 버전

#### v2.5.0 - SearXNG 웹 검색 통합
- ✅ SearXNG 자체 호스팅 메타 검색
- ✅ Crawl4AI 콘텐츠 추출 (27-125배 증가)
- ✅ 프로바이더 선택 (Tavily/SearXNG)
- ✅ `docker-compose.searxng.yml`

#### v2.4.0 - 인증 및 보안
- ✅ JWT 인증 (Access/Refresh Token)
- ✅ TOTP 2단계 인증
- ✅ 비밀번호 재설정
- ✅ 조직 기반 멀티테넌트
- ✅ CSRF 보호, CSP 헤더, Rate Limiting
- ✅ ClamAV 바이러스 스캔
- ✅ PII 탐지
- ✅ 감사 로그 및 보안 대시보드
- ✅ SBOM 및 취약점 스캔
- ✅ TTS (Text-to-Speech)
- ✅ 페르소나 시스템
- ✅ 랜딩 페이지
- ✅ 관리자 대시보드

#### v2.3.0 - 문서 버전 관리
- ✅ 자동 버전 추적 (MD5 해시)
- ✅ 버전 비교 및 복원
- ✅ 중복 파일 감지 UI

#### v2.1.0 - 프로덕션 최적화 및 그룹 관리
- ✅ 문서 그룹 시스템 (계층 구조, 그룹별 검색)
- ✅ Multi-worker 서버, Health check, Prometheus 메트릭
- ✅ Redis 연결 풀 최적화

#### v2.0.0 - 멀티 포맷 및 마이크로서비스
- ✅ 11가지 문서 형식 지원
- ✅ Java Document Service (Spring Boot)

#### v1.0.0 - 초기 릴리스
- ✅ PDF, HWP 지원, RAG 파이프라인, 웹 채팅 UI

### 📋 계획 중인 기능

#### 향후 버전
- [ ] **다중 언어 UI**: 영어, 일본어 등
- [ ] **이미지 OCR**: 이미지 내 텍스트 추출
- [ ] **실시간 협업**: 다중 사용자 동시 작업
- [ ] **웹훅 지원**: 이벤트 기반 알림
- [ ] **배치 처리 API**: 대량 문서 일괄 처리

---

## 🤝 기여 가이드

### 기여 방법

1. **이슈 생성** 또는 기존 이슈 선택
2. **저장소 포크**
3. **브랜치 생성**: `git checkout -b feature/amazing-feature`
4. **변경 사항 커밋**: `git commit -m 'feat: Add amazing feature'`
5. **Pull Request 생성**

### PR 체크리스트

- [ ] 코딩 컨벤션 준수
- [ ] 테스트 추가/수정
- [ ] 문서 업데이트
- [ ] CHANGELOG.md 업데이트

---

## 📄 라이선스

이 프로젝트는 **Apache License 2.0**으로 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

### 사용된 오픈소스

- [FastAPI](https://github.com/tiangolo/fastapi) - MIT License
- [Redis](https://github.com/redis/redis) - BSD 3-Clause License
- [MLX](https://github.com/ml-explore/mlx) - MIT License
- [Sentence Transformers](https://github.com/UKPLab/sentence-transformers) - Apache 2.0
- [Apache PDFBox](https://pdfbox.apache.org/) / [Apache POI](https://poi.apache.org/) - Apache 2.0
- [Spring Boot](https://spring.io/projects/spring-boot) - Apache 2.0
- [Qwen](https://github.com/QwenLM/Qwen) - Tongyi Qianwen License
- [SearXNG](https://github.com/searxng/searxng) - AGPL-3.0

---

## 🙏 감사

- **[nlpai-lab KURE](https://huggingface.co/nlpai-lab/KURE-v1)** - 한국어 특화 임베딩 모델
- **[Qwen Team](https://github.com/QwenLM/Qwen)** - 다국어 LLM
- **[MLX Team](https://github.com/ml-explore/mlx)** - Apple Silicon GPU 가속
- **[Redis Labs](https://redis.io/)** - 벡터 검색 기능
- **[FastAPI](https://fastapi.tiangolo.com/)** - 웹 프레임워크
- **[SearXNG](https://searxng.org/)** - 프라이버시 보호 메타 검색
- **Apache Software Foundation** - PDFBox, POI 문서 처리
- **Open Source Community** - 모든 기여자와 사용자분들께 감사드립니다

---

<div align="center">

**⭐ 이 프로젝트가 도움이 되었다면 Star를 눌러주세요! ⭐**

[맨 위로 이동](#atlea-advanced-trusted-learning--enterprise-assistant)

Made with ❤️ by @ZZang | Built with [Claude Code](https://claude.ai/claude-code)

</div>
