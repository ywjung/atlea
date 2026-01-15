# 📘 RAG 챗봇 시스템 설치 매뉴얼

## 목차

1. [시스템 개요](#시스템-개요)
2. [시스템 요구사항](#시스템-요구사항)
3. [설치 준비](#설치-준비)
4. [설치 방법](#설치-방법)
   - [방법 1: 원클릭 자동 설치 (권장)](#방법-1-원클릭-자동-설치-권장)
   - [방법 2: 수동 설치](#방법-2-수동-설치)
5. [초기 설정](#초기-설정)
6. [시스템 시작 및 중지](#시스템-시작-및-중지)
7. [문제 해결](#문제-해결)
8. [운영 및 유지보수](#운영-및-유지보수)
9. [보안 설정](#보안-설정)
10. [성능 최적화](#성능-최적화)

---

## 시스템 개요

### RAG 챗봇이란?

RAG (Retrieval-Augmented Generation) 챗봇은 업로드된 문서에서 정보를 검색하고, AI를 활용하여 자연어로 질문에 답변하는 지능형 시스템입니다.

### 주요 기능

- **📄 다중 문서 형식 지원**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT (총 11가지)
- **🤖 고성능 AI 모델**: Qwen3 30B LLM + KURE-v1 한국어 특화 임베딩
- **🔍 의미 기반 검색**: 벡터 DB를 활용한 빠르고 정확한 문서 검색
- **💬 실시간 대화**: 스트리밍 방식의 자연스러운 답변 생성
- **📊 문서 그룹 관리**: 계층적 문서 분류 및 관리
- **🎨 직관적 웹 UI**: 반응형 디자인, 다크 모드 지원

### 시스템 구성 요소

```
┌─────────────────────────────────────┐
│     웹 브라우저 (사용자 인터페이스)      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   FastAPI 서버 (Python)             │
│   • RAG 파이프라인                  │
│   • AI 모델 관리                    │
│   • API 엔드포인트                  │
└──────────┬──────────┬───────────────┘
           │          │
           ▼          ▼
   ┌──────────┐  ┌──────────────┐
   │  Redis   │  │ Java 문서     │
   │ Vector DB│  │ 처리 서비스   │
   └──────────┘  └──────────────┘
```

---

## 시스템 요구사항

### 하드웨어 요구사항

#### 최소 사양
- **CPU**: 4코어 이상 (Intel/AMD/Apple Silicon)
- **메모리**: 16GB RAM
- **저장공간**: 50GB 여유 공간
- **네트워크**: 인터넷 연결 (모델 다운로드용)

#### 권장 사양
- **CPU**: 8코어 이상 (Apple M2 Pro/Max/Ultra 또는 Intel/AMD 고성능 CPU)
- **메모리**: 32GB RAM 이상
- **저장공간**: 100GB 이상 SSD
- **GPU**: Apple Silicon 또는 NVIDIA GPU (선택사항, 성능 향상)

### 소프트웨어 요구사항

#### 필수
- **Docker Desktop**: 최신 버전 ([다운로드](https://www.docker.com/products/docker-desktop))
- **운영체제**:
  - macOS 14 (Sonoma) 이상 (Apple Silicon 권장)
  - Windows 10/11 (WSL2 필요)
  - Linux (Ubuntu 20.04 이상)

#### 선택사항
- **Python 3.10+**: 모델 다운로드 및 관리 스크립트용
- **Java 21**: Java 문서 처리 서비스 빌드용 (Docker 사용 시 불필요)

### 네트워크 포트

다음 포트가 사용 가능해야 합니다:

| 포트 | 서비스 | 용도 |
|------|--------|------|
| 8000 | 챗봇 애플리케이션 | 웹 UI 및 API |
| 6379 | Redis | Vector DB |
| 8001 | RedisInsight | Redis 관리 UI (선택) |
| 8081 | 문서 처리 서비스 | 문서 텍스트 추출 |
| 8082 | 관리 포트 | 메트릭 및 헬스체크 |

---

## 설치 준비

### 1. Docker Desktop 설치

#### macOS
```bash
# Homebrew로 설치
brew install --cask docker

# 또는 공식 웹사이트에서 다운로드
# https://www.docker.com/products/docker-desktop
```

#### Windows
1. [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop) 다운로드
2. WSL2 활성화 (Windows 기능에서)
3. Docker Desktop 설치 및 실행

#### Linux (Ubuntu)
```bash
# Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Docker Desktop 설정

Docker Desktop 실행 후 설정:

1. **메모리 할당**: 최소 8GB, 권장 16GB
   - Docker Desktop → Settings → Resources → Memory

2. **디스크 용량**: 최소 50GB
   - Docker Desktop → Settings → Resources → Disk image size

3. **CPU 코어**: 최소 4코어
   - Docker Desktop → Settings → Resources → CPUs

### 3. 시스템 확인

설치 전 시스템 상태 확인:

```bash
# Docker 버전 확인
docker --version
docker-compose --version

# Docker 실행 확인
docker ps

# 디스크 공간 확인
df -h .

# 포트 사용 확인 (macOS/Linux)
lsof -i :8000
lsof -i :6379
lsof -i :8081

# 포트 사용 확인 (Windows PowerShell)
netstat -ano | findstr :8000
netstat -ano | findstr :6379
netstat -ano | findstr :8081
```

---

## 설치 방법

### 방법 1: 원클릭 자동 설치 (권장)

가장 간단하고 빠른 설치 방법입니다.

#### 1.1. 설치 파일 준비

```bash
# 설치 디렉토리로 이동
cd /path/to/chatbot_redis

# 설치 스크립트 실행 권한 부여 (macOS/Linux)
chmod +x install.sh
```

#### 1.2. 설치 실행

```bash
# 자동 설치 시작
./install.sh
```

설치 스크립트가 자동으로 수행하는 작업:

1. ✅ 시스템 요구사항 검증
2. ✅ 필수 디렉토리 생성
3. ✅ 환경 설정 파일 (.env) 생성
4. ✅ AI 모델 다운로드 (선택)
5. ✅ Docker 이미지 빌드
6. ✅ 서비스 시작

#### 1.3. 설치 확인

설치 완료 후 다음 URL에 접속하여 확인:

```
http://localhost:8000
```

정상적으로 챗봇 웹 UI가 표시되면 설치 성공입니다! 🎉

---

### 방법 2: 수동 설치

고급 사용자 또는 커스터마이징이 필요한 경우 수동으로 설치합니다.

#### 2.1. 저장소 준비

```bash
# 설치 디렉토리로 이동
cd /path/to/chatbot_redis

# 디렉토리 구조 확인
ls -la
```

#### 2.2. 환경 설정 파일 생성

```bash
# .env.example을 복사하여 .env 생성
cp .env.example .env

# .env 파일 편집
nano .env  # 또는 원하는 텍스트 편집기 사용
```

**필수 설정 항목**:

```bash
# JWT 시크릿 키 생성 (보안을 위해 반드시 변경!)
JWT_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')

# .env 파일에 추가
echo "JWT_SECRET_KEY=$JWT_SECRET_KEY" >> .env
```

#### 2.3. 필수 디렉토리 생성

```bash
mkdir -p data model logs
```

#### 2.4. AI 모델 다운로드

```bash
# Python 가상환경 생성 (선택사항)
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 모델 다운로드에 필요한 패키지 설치
pip install huggingface-hub requests tqdm

# 모델 다운로드 실행 (약 15-20GB, 시간 소요)
python3 download_models.py
```

**모델 다운로드 확인**:
```bash
ls -lh model/
# 다음 디렉토리가 있어야 함:
# - mlx-community--Qwen3-30B-A3B-4bit/
# - nlpai-lab--KURE-v1/
```

#### 2.5. Docker 이미지 빌드

```bash
# 완전 통합 Docker Compose로 빌드
docker-compose -f docker-compose.full.yml build

# 빌드 진행 상황 확인
docker images | grep rag_chatbot
```

#### 2.6. 서비스 시작

```bash
# 모든 서비스 시작
docker-compose -f docker-compose.full.yml up -d

# 서비스 상태 확인
docker-compose -f docker-compose.full.yml ps
```

#### 2.7. 설치 확인

```bash
# 헬스체크
curl http://localhost:8000/health

# 서비스 로그 확인
docker-compose -f docker-compose.full.yml logs -f
```

---

## 초기 설정

### 관리자 계정 생성

시스템 첫 실행 시 관리자 계정을 생성해야 합니다.

1. 웹 브라우저에서 `http://localhost:8000` 접속
2. "회원가입" 클릭
3. 관리자 정보 입력:
   - 이메일 주소
   - 사용자 이름
   - 비밀번호 (최소 8자, 영문+숫자+특수문자)
4. "가입" 클릭

> **참고**: 첫 번째로 가입한 사용자가 자동으로 시스템 관리자(system_admin)가 됩니다.

### 초기 문서 업로드

#### 방법 1: 웹 UI 사용

1. 로그인 후 "문서 관리" 클릭
2. "파일 선택" 또는 드래그 앤 드롭으로 파일 업로드
3. 지원 형식: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT
4. 업로드 완료 후 자동으로 색인화

#### 방법 2: 파일 시스템 직접 복사

```bash
# data 디렉토리에 문서 복사
cp /path/to/your/documents/*.pdf ./data/
cp /path/to/your/documents/*.hwp ./data/
cp /path/to/your/documents/*.docx ./data/

# 서비스 재시작하면 자동 색인
docker-compose -f docker-compose.full.yml restart chatbot-app
```

### 문서 그룹 설정 (선택사항)

문서를 체계적으로 관리하기 위한 그룹 생성:

1. "그룹 관리" 클릭
2. "그룹 추가" 클릭
3. 그룹 정보 입력:
   - 이름: 예) "기술 문서", "회사 규정"
   - 설명: 그룹에 대한 설명
   - 색상: 시각적 구분을 위한 색상
   - 아이콘: 이모지 선택
4. 저장

### 시스템 설정 확인

1. 우측 상단 사용자 메뉴 → "설정" 클릭
2. 다음 설정 확인 및 조정:
   - **검색 설정**: Top-K (기본 5)
   - **생성 설정**: Temperature (기본 0.7), Max Tokens (기본 2048)
   - **UI 설정**: 테마, 폰트 크기
   - **보안 설정**: 비밀번호 변경, 2FA 설정

---

## 시스템 시작 및 중지

### 서비스 시작

```bash
# 모든 서비스 시작 (백그라운드)
docker-compose -f docker-compose.full.yml up -d

# 또는 포그라운드로 실행 (로그 확인 가능)
docker-compose -f docker-compose.full.yml up
```

### 서비스 중지

```bash
# 모든 서비스 중지
docker-compose -f docker-compose.full.yml down

# 데이터 볼륨까지 삭제 (주의!)
docker-compose -f docker-compose.full.yml down -v
```

### 서비스 재시작

```bash
# 모든 서비스 재시작
docker-compose -f docker-compose.full.yml restart

# 특정 서비스만 재시작
docker-compose -f docker-compose.full.yml restart chatbot-app
```

### 서비스 상태 확인

```bash
# 실행 중인 컨테이너 확인
docker-compose -f docker-compose.full.yml ps

# 로그 확인
docker-compose -f docker-compose.full.yml logs -f

# 특정 서비스 로그만 확인
docker-compose -f docker-compose.full.yml logs -f chatbot-app
```

---

## 문제 해결

### 일반적인 문제

#### 문제 1: Docker 컨테이너가 시작되지 않음

**증상**:
```bash
docker-compose ps
# 상태가 "Exit" 또는 "Restarting"
```

**해결 방법**:
```bash
# 로그 확인
docker-compose -f docker-compose.full.yml logs

# 포트 충돌 확인
lsof -i :8000
lsof -i :6379

# 포트가 사용 중이면 .env 파일에서 포트 변경
nano .env
# PORT=8000 → PORT=8888로 변경

# 서비스 재시작
docker-compose -f docker-compose.full.yml down
docker-compose -f docker-compose.full.yml up -d
```

#### 문제 2: AI 모델 로드 실패

**증상**:
```
Model not found: model/mlx-community--Qwen3-30B-A3B-4bit
```

**해결 방법**:
```bash
# 모델 디렉토리 확인
ls -la model/

# 모델이 없으면 다운로드
python3 download_models.py

# 모델 경로 확인
ls -R model/
```

#### 문제 3: Redis 연결 오류

**증상**:
```
Failed to connect to Redis
```

**해결 방법**:
```bash
# Redis 컨테이너 상태 확인
docker ps | grep redis

# Redis가 실행 중이 아니면 시작
docker-compose -f docker-compose.full.yml up -d redis

# Redis 연결 테스트
docker exec -it rag_chatbot_redis redis-cli ping
# 응답: PONG
```

#### 문제 4: 문서 업로드 실패

**증상**:
```
File upload failed: Connection refused
```

**해결 방법**:
```bash
# Java 문서 서비스 상태 확인
docker-compose -f docker-compose.full.yml ps document-service

# 서비스 로그 확인
docker-compose -f docker-compose.full.yml logs document-service

# 서비스 재시작
docker-compose -f docker-compose.full.yml restart document-service
```

#### 문제 5: 메모리 부족

**증상**:
```
OutOfMemoryError 또는 Killed
```

**해결 방법**:
```bash
# Docker Desktop 메모리 증가
# Settings → Resources → Memory → 16GB 이상 할당

# 또는 경량 모델 사용
# .env 파일 수정
LLM_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit

# 서비스 재시작
docker-compose -f docker-compose.full.yml restart
```

### 로그 분석

#### 시스템 로그 위치

```bash
# 컨테이너 로그
docker-compose -f docker-compose.full.yml logs > system.log

# 애플리케이션 로그 (컨테이너 내부)
docker exec -it rag_chatbot_app ls -la /app/logs/

# 로그 파일 복사
docker cp rag_chatbot_app:/app/logs/app.log ./
```

#### 주요 로그 파일

| 파일 | 용도 |
|------|------|
| `logs/app.log` | 애플리케이션 로그 |
| `logs/error.log` | 에러 로그 |
| `logs/access.log` | API 접근 로그 |
| `docker-compose logs` | 컨테이너 로그 |

---

## 운영 및 유지보수

### 정기 백업

#### Redis 데이터 백업

```bash
# 수동 백업
docker exec rag_chatbot_redis redis-cli SAVE

# 백업 파일 위치 확인
docker exec rag_chatbot_redis ls -la /data/

# 백업 파일 복사
docker cp rag_chatbot_redis:/data/dump.rdb ./backups/redis_$(date +%Y%m%d).rdb
```

#### 문서 파일 백업

```bash
# data 디렉토리 백업
tar -czf backups/data_$(date +%Y%m%d).tar.gz data/

# 클라우드 스토리지로 업로드 (예: AWS S3)
aws s3 cp backups/data_$(date +%Y%m%d).tar.gz s3://my-bucket/backups/
```

#### 환경 설정 백업

```bash
# .env 파일 백업
cp .env backups/.env.$(date +%Y%m%d)
```

### 자동 백업 스크립트

```bash
#!/bin/bash
# backup.sh - 자동 백업 스크립트

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)

# 디렉토리 생성
mkdir -p $BACKUP_DIR

# Redis 백업
docker exec rag_chatbot_redis redis-cli SAVE
docker cp rag_chatbot_redis:/data/dump.rdb $BACKUP_DIR/redis_$DATE.rdb

# 문서 백업
tar -czf $BACKUP_DIR/data_$DATE.tar.gz data/

# 환경 설정 백업
cp .env $BACKUP_DIR/.env.$DATE

# 오래된 백업 삭제 (30일 이전)
find $BACKUP_DIR -name "*.rdb" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "백업 완료: $DATE"
```

**cron 설정** (매일 새벽 2시 자동 백업):
```bash
crontab -e
# 다음 줄 추가
0 2 * * * /path/to/chatbot_redis/backup.sh >> /path/to/chatbot_redis/logs/backup.log 2>&1
```

### 시스템 업데이트

#### 애플리케이션 업데이트

```bash
# 최신 버전 다운로드 (Git 사용 시)
git pull origin main

# Docker 이미지 재빌드
docker-compose -f docker-compose.full.yml build

# 서비스 재시작
docker-compose -f docker-compose.full.yml down
docker-compose -f docker-compose.full.yml up -d
```

#### Docker 이미지 업데이트

```bash
# 베이스 이미지 업데이트
docker-compose -f docker-compose.full.yml pull

# 재빌드 및 재시작
docker-compose -f docker-compose.full.yml up -d --build
```

### 모니터링

#### 시스템 상태 모니터링

```bash
# 헬스체크
curl http://localhost:8000/health | jq

# Prometheus 메트릭
curl http://localhost:8000/metrics
```

#### 리소스 사용량 모니터링

```bash
# 컨테이너 리소스 사용량
docker stats

# 디스크 사용량
docker system df

# 로그 크기 확인
du -sh logs/
```

### 성능 최적화 팁

1. **Redis 메모리 최적화**:
   ```bash
   # Redis 메모리 사용량 확인
   docker exec rag_chatbot_redis redis-cli INFO memory
   ```

2. **Docker 리소스 할당**:
   - CPU: 최소 4코어
   - 메모리: 최소 8GB, 권장 16GB
   - 디스크: SSD 권장

3. **AI 모델 최적화**:
   - 메모리 부족 시 경량 모델 사용
   - `.env`에서 `LLM_MODEL` 변경

---

## 보안 설정

### JWT 시크릿 키 변경

**매우 중요**: 프로덕션 환경에서는 반드시 JWT 시크릿 키를 변경해야 합니다!

```bash
# 강력한 시크릿 키 생성
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'

# .env 파일에서 JWT_SECRET_KEY 업데이트
nano .env
# JWT_SECRET_KEY=<생성된 키로 변경>

# 서비스 재시작
docker-compose -f docker-compose.full.yml restart chatbot-app
```

### HTTPS 설정 (프로덕션)

프로덕션 환경에서는 HTTPS를 사용해야 합니다.

#### Nginx 리버스 프록시 설정

```nginx
# /etc/nginx/sites-available/chatbot

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 지원
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

#### SSL 인증서 발급 (Let's Encrypt)

```bash
# Certbot 설치
sudo apt-get install certbot python3-certbot-nginx

# SSL 인증서 발급
sudo certbot --nginx -d your-domain.com
```

### 방화벽 설정

```bash
# UFW 방화벽 설정 (Ubuntu)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 데이터베이스 보안

```bash
# Redis 비밀번호 설정
# docker-compose.full.yml에 추가:
environment:
  - REDIS_PASSWORD=your-strong-password

# .env 파일에 비밀번호 추가
echo "REDIS_PASSWORD=your-strong-password" >> .env
```

---

## 성능 최적화

### 캐시 설정

시스템은 자동으로 다음을 캐싱합니다:
- **쿼리 임베딩**: LRU 캐시 1000개 항목
- **답변 캐싱**: 유사도 95% 이상 질문
- **Java 문서 추출**: Caffeine 캐시 500개 항목

### Redis 최적화

```bash
# Redis 설정 확인
docker exec rag_chatbot_redis redis-cli CONFIG GET maxmemory

# 최대 메모리 설정 (예: 4GB)
docker exec rag_chatbot_redis redis-cli CONFIG SET maxmemory 4gb
docker exec rag_chatbot_redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### 모델 선택 가이드

| 모델 | 메모리 | 성능 | 용도 |
|------|--------|------|------|
| Qwen3-30B-4bit | ~20GB | ⭐⭐⭐⭐⭐ | 프로덕션 (기본) |
| Qwen2.5-3B-4bit | ~2GB | ⭐⭐⭐ | 테스트, 개발 |
| Qwen2.5-1.5B-4bit | ~1.5GB | ⭐⭐ | 경량 환경 |

---

## 부록

### A. 디렉토리 구조

```
chatbot_redis/
├── data/                       # 업로드된 문서
├── model/                      # AI 모델
│   ├── mlx-community--Qwen3-30B-A3B-4bit/
│   └── nlpai-lab--KURE-v1/
├── logs/                       # 로그 파일
├── backups/                    # 백업 파일 (생성 필요)
├── src/                        # Python 소스 코드
├── static/                     # 웹 UI
├── document-service/           # Java 문서 서비스
├── docker-compose.full.yml     # Docker 설정
├── install.sh                  # 설치 스크립트
├── .env                        # 환경 설정
└── README.md                   # 프로젝트 문서
```

### B. 환경 변수 전체 목록

```bash
# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=                # 선택사항

# 문서 서비스
DOCUMENT_SERVICE_URL=http://document-service:8081
HWP_SERVICE_URL=http://document-service:8081

# AI 모델
EMBEDDING_MODEL=nlpai-lab/KURE-v1
LLM_MODEL=mlx-community/Qwen3-30B-A3B-4bit
MODEL_DIR=/app/model

# 애플리케이션
DATA_DIR=/app/data
CHUNK_SIZE=512
CHUNK_OVERLAP=50
MAX_FILE_SIZE_MB=100
ENABLE_QUESTION_GENERATION=false

# 서버
HOST=0.0.0.0
PORT=8000

# 보안
JWT_SECRET_KEY=<강력한 키로 변경 필수!>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# 성능
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10
```

### C. 유용한 명령어 모음

```bash
# 시스템 상태
docker-compose -f docker-compose.full.yml ps
curl http://localhost:8000/health

# 로그
docker-compose -f docker-compose.full.yml logs -f
docker-compose -f docker-compose.full.yml logs -f chatbot-app

# 재시작
docker-compose -f docker-compose.full.yml restart
docker-compose -f docker-compose.full.yml restart chatbot-app

# 정지/시작
docker-compose -f docker-compose.full.yml down
docker-compose -f docker-compose.full.yml up -d

# Redis 명령
docker exec -it rag_chatbot_redis redis-cli
docker exec rag_chatbot_redis redis-cli KEYS "*"

# 디스크 정리
docker system prune -a
docker volume prune
```

### D. 지원 및 문의

- **이메일**: support@your-company.com
- **기술 문서**: README.md, QUICK_START.md
- **GitHub Issues**: (해당되는 경우)

---

**마지막 업데이트**: 2026-01-02
**문서 버전**: 1.0.0
**제품 버전**: 1.0.0
