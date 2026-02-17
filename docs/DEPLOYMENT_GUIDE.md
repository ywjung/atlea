# ATLEA 배포 가이드

## 목차

1. [시스템 요구사항](#1-시스템-요구사항)
2. [배포 방식 비교](#2-배포-방식-비교)
3. [방법 1: 로컬 개발 환경](#3-방법-1-로컬-개발-환경)
4. [방법 2: Docker 올인원 배포](#4-방법-2-docker-올인원-배포)
5. [방법 3: 프로덕션 배포 (SSL + Nginx)](#5-방법-3-프로덕션-배포-ssl--nginx)
6. [방법 4: GPU 서버 배포 (NVIDIA)](#6-방법-4-gpu-서버-배포-nvidia)
7. [Ollama 설정](#7-ollama-설정)
8. [선택 구성요소](#8-선택-구성요소)
9. [환경 변수 설정](#9-환경-변수-설정)
10. [SSL 인증서 설정](#10-ssl-인증서-설정)
11. [백업 및 복원](#11-백업-및-복원)
12. [모니터링](#12-모니터링)
13. [업데이트 및 롤백](#13-업데이트-및-롤백)
14. [플랫폼별 특성](#14-플랫폼별-특성)
15. [문제 해결](#15-문제-해결)

---

## 1. 시스템 요구사항

### 최소 사양

| 항목 | 로컬 개발 | Docker 배포 | 프로덕션 |
|------|----------|------------|---------|
| CPU | 4코어 | 4코어 | 8코어 |
| RAM | 16GB | 16GB | 32GB |
| 디스크 | 30GB | 50GB | 100GB |
| OS | macOS 12+ / Linux | macOS / Linux | Linux |

### 필수 소프트웨어

| 소프트웨어 | 로컬 개발 | Docker 배포 | 버전 |
|-----------|----------|------------|------|
| Python 3.11+ | 필수 | - | 3.11 이상 |
| Docker | - | 필수 | 24.0 이상 |
| Docker Compose | - | 필수 | v2.20 이상 |
| PostgreSQL | 필수 | 자동 설치 | 17.x |
| Git | 필수 | 필수 | 2.x |
| Ollama | 필수 | 선택 | 최신 |

---

## 2. 배포 방식 비교

| 방식 | 난이도 | 용도 | 소요 시간 | 대상 |
|------|-------|------|----------|------|
| **로컬 개발** | 쉬움 | 개발/테스트 | 15분 | 개발자 |
| **Docker 올인원** | 쉬움 | 소규모 운영 | 20분 | 소규모 팀 |
| **프로덕션 (SSL)** | 보통 | 실제 서비스 | 30분 | 운영 서버 |
| **GPU 서버** | 보통 | 고성능 운영 | 30분 | NVIDIA GPU 보유 |

### Docker Compose 파일 용도

| 파일 | 용도 | 포함 서비스 |
|------|------|------------|
| `docker-compose.yml` | 부가 서비스 (로컬 개발용) | PostgreSQL + Document Service + ClamAV |
| `docker-compose.full.yml` | 올인원 배포 | PostgreSQL + Document Service + 챗봇 앱 |
| `docker-compose.production.yml` | 프로덕션 배포 | 전체 + Nginx SSL + 모니터링 |
| `docker-compose.gpu.yml` | GPU 서버 배포 | 전체 + NVIDIA GPU + 모니터링 |
| `docker-compose.searxng.yml` | 웹 검색 확장 | SearXNG + Crawl4AI |

---

## 3. 방법 1: 로컬 개발 환경

Docker 없이 직접 실행합니다. 개발 및 테스트에 적합합니다.

### 3-1. 소스 코드 받기

```bash
git clone <repository-url> atlea-chatbot
cd atlea-chatbot
```

### 3-2. Python 가상환경 설정

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3-3. 환경 설정

```bash
cp .env.example .env
```

`.env` 파일을 편집합니다:

```env
# 필수: JWT 보안 키 생성
# 아래 명령어 결과를 JWT_SECRET_KEY에 입력
# python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
JWT_SECRET_KEY=여기에_생성된_키_입력

# PostgreSQL (로컬 실행 시)
DATABASE_URL=postgresql+asyncpg://atlea:password@localhost:5432/atlea

# 서버 포트
PORT=8085

# 모델 설정 (RAM에 따라 선택)
# 20GB+ RAM → mlx-community/Qwen3-30B-A3B-4bit
# 4GB RAM   → mlx-community/Qwen2.5-3B-Instruct-4bit
LLM_MODEL=mlx-community/Qwen3-30B-A3B-4bit
```

### 3-4. Ollama 설치 및 모델 다운로드

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Ollama 서버 시작
ollama serve

# LLM 모델 다운로드 (별도 터미널에서)
ollama pull alibayram/Qwen3-30B-A3B-Instruct-2507:latest
```

### 3-5. PostgreSQL 및 부가 서비스 시작

```bash
docker-compose up -d
```

이 명령은 `docker-compose.yml`에 정의된 PostgreSQL, Document Service, ClamAV를 시작합니다.

Docker 없이 PostgreSQL만 사용하려면:

```bash
# macOS
brew install postgresql@17
brew services start postgresql@17

# Linux
sudo apt-get install postgresql-17
sudo systemctl start postgresql
```

### 3-6. 서버 실행

```bash
# 포그라운드 (로그가 터미널에 출력)
./run.sh

# 백그라운드 실행
./run.sh -b

# 서버 상태 확인
./run.sh status

# 서버 중지
./run.sh stop
```

### 3-7. 접속 확인

| 서비스 | URL | 설명 |
|--------|-----|------|
| 웹 UI | http://localhost:8085 | 챗봇 메인 화면 |
| 소개 페이지 | http://localhost:8085/landing.html | 제품 소개 |
| API 문서 | http://localhost:8085/docs | Swagger UI |
| 건강 상태 | http://localhost:8085/health | 서버 상태 |
| PostgreSQL | localhost:5432 | 데이터베이스 |

---

## 4. 방법 2: Docker 올인원 배포

모든 서비스를 Docker로 한번에 실행합니다. 가장 쉬운 방법입니다.

### 4-1. 원클릭 설치

```bash
git clone <repository-url> atlea-chatbot
cd atlea-chatbot
chmod +x install.sh
./install.sh
```

`install.sh`가 자동으로 처리하는 항목:
- 시스템 요구사항 확인 (Docker, 디스크 공간)
- `.env` 파일 생성 및 JWT 키 자동 생성
- AI 모델 다운로드 (선택)
- Docker 이미지 빌드
- 전체 서비스 시작

### 4-2. 수동 설치

원클릭 설치 대신 단계별로 실행할 수 있습니다:

```bash
# 1. 환경 설정
cp .env.example .env

# JWT 시크릿 키 생성 후 .env에 입력
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'

# 2. 디렉토리 생성
mkdir -p data model logs

# 3. Ollama 설치 및 모델 다운로드 (호스트에서)
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull alibayram/Qwen3-30B-A3B-Instruct-2507:latest

# 4. Docker 이미지 빌드 및 실행
docker-compose -f docker-compose.full.yml up -d

# 5. 상태 확인
docker-compose -f docker-compose.full.yml ps
```

### 4-3. 서비스 관리 명령어

```bash
# 전체 서비스 상태 확인
docker-compose -f docker-compose.full.yml ps

# 로그 확인 (실시간)
docker-compose -f docker-compose.full.yml logs -f

# 특정 서비스 로그
docker-compose -f docker-compose.full.yml logs -f chatbot-app

# 전체 서비스 중지
docker-compose -f docker-compose.full.yml down

# 전체 서비스 재시작
docker-compose -f docker-compose.full.yml restart

# 특정 서비스만 재시작
docker-compose -f docker-compose.full.yml restart chatbot-app
```

---

## 5. 방법 3: 프로덕션 배포 (SSL + Nginx)

실제 서비스 운영을 위한 배포입니다. SSL/TLS 암호화, 리버스 프록시, 리소스 제한, 모니터링이 포함됩니다.

### 5-1. 사전 준비

- 도메인 이름이 서버 IP를 가리키도록 DNS 설정
- SSL 인증서 준비 ([10. SSL 인증서 설정](#10-ssl-인증서-설정) 참조)

```bash
mkdir -p nginx/ssl
# 인증서 파일 배치:
# nginx/ssl/fullchain.pem  (인증서 + 체인)
# nginx/ssl/privkey.pem    (개인 키)
```

### 5-2. 환경 설정

```bash
cp .env.example .env
```

프로덕션용 `.env` 설정:

```env
# 보안 키 (반드시 변경!)
JWT_SECRET_KEY=여기에_python3으로_생성한_키

# PostgreSQL 비밀번호 설정
POSTGRES_PASSWORD=강력한_랜덤_비밀번호

# CORS 설정 (실제 도메인으로 변경)
CORS_ORIGINS=https://chatbot.example.com

# 로그 레벨
LOG_LEVEL=warning

# Ollama 연결 (호스트에서 실행 중인 경우)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### 5-3. Nginx 리버스 프록시 설정

`nginx/nginx.conf`에서 도메인 이름을 변경합니다:

```nginx
server_name chatbot.example.com;   # 실제 도메인으로 변경
```

Docker 없이 Nginx를 직접 설정하는 경우 (`/etc/nginx/sites-available/chatbot`):

```nginx
upstream chatbot {
    server 127.0.0.1:8085;
}

server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Rate limiting (추가 보호)
    limit_req_zone $binary_remote_addr zone=chatbot_limit:10m rate=10r/s;
    limit_req zone=chatbot_limit burst=20 nodelay;

    client_max_body_size 100M;

    location / {
        proxy_pass http://chatbot;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    location /static/ {
        alias /path/to/chatbot_redis/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 5-4. 서비스 시작

```bash
# 기본 실행
docker-compose -f docker-compose.production.yml up -d

# 모니터링 포함 실행 (Prometheus + Grafana)
docker-compose -f docker-compose.production.yml --profile monitoring up -d
```

### 5-5. 접속 확인

```bash
# HTTPS 접속 확인
curl -I https://chatbot.example.com

# 건강 상태 확인
curl https://chatbot.example.com/api/status
```

### 5-6. 방화벽 설정

```bash
# Ubuntu/Debian
sudo ufw allow 80/tcp     # HTTP → HTTPS 리다이렉트
sudo ufw allow 443/tcp    # HTTPS
sudo ufw deny 5432/tcp    # PostgreSQL 외부 접근 차단
sudo ufw deny 8081/tcp    # Document Service 외부 접근 차단
```

### 5-7. 프로덕션 보안 체크리스트

- [ ] `JWT_SECRET_KEY`를 강력한 랜덤 값으로 변경
- [ ] `POSTGRES_PASSWORD` 설정
- [ ] `CORS_ORIGINS`에 실제 도메인만 명시 (`*` 사용 금지)
- [ ] SSL 인증서 설치 및 자동 갱신 설정
- [ ] 방화벽으로 내부 포트 차단 (5432, 8081)
- [ ] `ADMIN_DEFAULT_PASSWORD` 강력한 비밀번호 설정
- [ ] `RATE_LIMIT_ENABLED=true` 확인
- [ ] Docker 메모리 제한 설정 확인
- [ ] 2FA 강제 적용 활성화 (`config:totp_enabled=true`)
- [ ] 로그인 CAPTCHA 활성화 (`config:captcha_login_enabled=true`)
- [ ] 회원가입 CAPTCHA 활성화 (`config:captcha_register_enabled=true`)
- [ ] 감사 로그 보관 기간 확인 (기본 90일)
- [ ] Brute Force 방어 설정 확인 (5회 실패 → 15분 잠금)

### 5-8. systemd 서비스 등록 (Linux)

Docker 없이 직접 실행하는 경우 systemd 서비스로 등록합니다.

**챗봇 서비스** (`/etc/systemd/system/chatbot.service`):

```ini
[Unit]
Description=ATLEA Service
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/chatbot_redis
Environment="PATH=/path/to/venv/bin"
EnvironmentFile=/path/to/chatbot_redis/.env
ExecStart=/path/to/venv/bin/uvicorn src.web_server:app --host 0.0.0.0 --port 8085 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**문서 처리 서비스** (`/etc/systemd/system/document-service.service`):

```ini
[Unit]
Description=ATLEA Document Processing Service (Java)
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/chatbot_redis/document-service
ExecStart=/usr/bin/java -jar build/libs/document-service.jar --server.port=8081
Restart=always
RestartSec=10
Environment=JAVA_OPTS=-Xmx2g

[Install]
WantedBy=multi-user.target
```

서비스 활성화:

```bash
sudo systemctl enable chatbot document-service
sudo systemctl start chatbot document-service
sudo systemctl status chatbot document-service
```

### 5-9. 성능 최적화

**Worker 수 조정** (CPU 코어 수에 따라):

```bash
nproc                    # CPU 코어 수 확인
# Worker 수 = (2 x CPU 코어) + 1
# 2코어 → 4 workers, 4코어 → 8 workers
```

**DB 연결 풀** (`.env`):

```bash
DB_POOL_SIZE=20  # Worker당 5-10개 권장
```

**타임아웃 설정** (`.env`):

```bash
REQUEST_TIMEOUT=300        # 요청 타임아웃 (초)
KEEPALIVE_TIMEOUT=5        # Keep-alive 타임아웃 (초)
```

---

## 6. 방법 4: GPU 서버 배포 (NVIDIA)

NVIDIA GPU가 있는 서버에서 빠른 LLM 추론을 위한 배포입니다.

### 6-1. NVIDIA Container Toolkit 설치

```bash
# NVIDIA 드라이버 확인
nvidia-smi

# NVIDIA Container Toolkit 설치 (Ubuntu/Debian)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 6-2. 환경 설정

```bash
cp .env.example .env
```

GPU 전용 `.env` 설정:

```env
# GPU용 LLM 모델
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct

# PostgreSQL 비밀번호
POSTGRES_PASSWORD=강력한_비밀번호

# JWT 키
JWT_SECRET_KEY=자동_생성_키
```

### 6-3. 서비스 시작

```bash
# 기본 실행
docker-compose -f docker-compose.gpu.yml up -d

# GPU 모니터링 포함 실행
docker-compose -f docker-compose.gpu.yml --profile monitoring up -d
```

### 6-4. GPU 모니터링

| 서비스 | URL | 설명 |
|--------|-----|------|
| NVIDIA Exporter | http://localhost:9400 | GPU 메트릭 |
| Prometheus | http://localhost:9090 | 메트릭 수집 |
| Grafana | http://localhost:3000 | 대시보드 |

---

## 7. Ollama 설정

Ollama는 LLM을 로컬에서 실행하기 위한 서버로, 모든 플랫폼에서 사용할 수 있습니다.

### 7-1. 설치

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Docker
docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama ollama/ollama
```

### 7-2. 모델 다운로드

```bash
# Ollama 서버 시작
ollama serve

# 기본 LLM 모델 (~20GB)
ollama pull alibayram/Qwen3-30B-A3B-Instruct-2507:latest

# 경량 모델 (~2GB, 메모리 부족 시)
ollama pull qwen2.5:3b

# 설치된 모델 확인
ollama list
```

### 7-3. 환경 변수

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=alibayram/Qwen3-30B-A3B-Instruct-2507:latest
```

### 7-4. Linux systemd 서비스 등록

```bash
# /etc/systemd/system/ollama.service
sudo tee /etc/systemd/system/ollama.service << 'EOF'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
Type=simple
User=ollama
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=10
Environment=OLLAMA_HOST=0.0.0.0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable ollama
sudo systemctl start ollama

# 상태 확인
curl http://localhost:11434/api/version
```

---

## 8. 선택 구성요소

### 8-1. 웹 검색 (SearXNG + Crawl4AI)

Hybrid RAG에서 웹 검색을 활성화하려면:

**옵션 A: SearXNG (자체 호스팅, 무료)**

```bash
docker-compose -f docker-compose.searxng.yml up -d
```

관리자 페이지(`/admin.html`) → Hybrid RAG 설정에서:
- 웹 검색 프로바이더: `SearXNG (자체 호스팅)` 선택
- SearXNG URL: `http://localhost:8888` 입력

**옵션 B: Tavily API (클라우드)**

```env
# .env에 추가 (https://tavily.com 에서 무료 키 발급)
TAVILY_API_KEY=tvly-xxxxxxxxxxxxx
```

### 8-2. ClamAV 바이러스 검사

`docker-compose.yml`에 포함되어 있으며 파일 업로드 시 자동으로 검사합니다.

```env
CLAMAV_HOST=localhost
CLAMAV_PORT=3310
```

> ClamAV는 시작 시 바이러스 정의 파일을 로드하므로 초기 구동에 3~5분이 소요됩니다.

---

## 9. 환경 변수 설정

### 필수 설정

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `JWT_SECRET_KEY` | JWT 토큰 서명 키 (32자 이상) | 없음 (반드시 설정) |
| `DATABASE_URL` | PostgreSQL 연결 URL | postgresql+asyncpg://... |
| `PORT` | 서버 포트 | 8085 |
| `LLM_MODEL` | LLM 모델 경로 | Qwen3-30B-A3B-4bit |
| `EMBEDDING_MODEL` | 임베딩 모델 경로 | nlpai-lab/KURE-v1 |

### 보안 설정

| 변수 | 설명 | 프로덕션 권장값 |
|------|------|----------------|
| `JWT_SECRET_KEY` | JWT 서명 키 | `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` |
| `POSTGRES_PASSWORD` | PostgreSQL 인증 | 반드시 설정 |
| `CORS_ORIGINS` | 허용 도메인 | 실제 도메인만 명시 |
| `RATE_LIMIT_ENABLED` | API 속도 제한 | true |
| `ADMIN_DEFAULT_PASSWORD` | 관리자 비밀번호 | 미설정 시 자동 생성 |

### 성능 설정

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `CHUNK_SIZE` | 문서 청크 크기 | 512 |
| `CHUNK_OVERLAP` | 청크 겹침 크기 | 50 |
| `MAX_FILE_SIZE_MB` | 최대 업로드 크기(MB) | 100 |
| `ENABLE_QUESTION_GENERATION` | 자동 질문 생성 | false |

---

## 10. SSL 인증서 설정

### 방법 A: Let's Encrypt (무료, 권장)

```bash
# 1. Certbot 설치
sudo apt install certbot

# 2. 인증서 발급 (서버가 중지된 상태에서)
sudo certbot certonly --standalone -d chatbot.example.com

# 3. 인증서 복사
mkdir -p nginx/ssl
sudo cp /etc/letsencrypt/live/chatbot.example.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/chatbot.example.com/privkey.pem nginx/ssl/
sudo chmod 644 nginx/ssl/fullchain.pem
sudo chmod 600 nginx/ssl/privkey.pem
```

자동 갱신 crontab:

```bash
sudo crontab -e
# 매월 1일 새벽 3시에 갱신
0 3 1 * * certbot renew --quiet && \
  cp /etc/letsencrypt/live/chatbot.example.com/fullchain.pem /path/to/atlea-chatbot/nginx/ssl/ && \
  cp /etc/letsencrypt/live/chatbot.example.com/privkey.pem /path/to/atlea-chatbot/nginx/ssl/ && \
  docker-compose -f docker-compose.production.yml restart nginx
```

### 방법 B: 자체 서명 인증서 (테스트용)

```bash
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/privkey.pem \
  -out nginx/ssl/fullchain.pem \
  -subj "/CN=localhost"
```

> 자체 서명 인증서는 브라우저에서 보안 경고가 표시됩니다. 테스트 목적으로만 사용하세요.

---

## 11. 백업 및 복원

### 수동 백업

```bash
# 백업 디렉토리 생성
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1. PostgreSQL 데이터 백업
docker exec postgres pg_dump -U atlea atlea > "$BACKUP_DIR/pg_dump.sql"

# 2. 업로드된 문서 백업
cp -r ./data "$BACKUP_DIR/data"

# 3. 환경 설정 백업
cp .env "$BACKUP_DIR/.env"

# 4. 압축
tar czf "$BACKUP_DIR.tar.gz" -C "$(dirname $BACKUP_DIR)" "$(basename $BACKUP_DIR)"
rm -rf "$BACKUP_DIR"
echo "백업 완료: $BACKUP_DIR.tar.gz"
```

### 복원

```bash
# 1. 압축 해제
RESTORE_DIR="./restore_tmp"
mkdir -p "$RESTORE_DIR"
tar xzf <백업파일.tar.gz> -C "$RESTORE_DIR"

# 2. 서비스 중지
docker-compose -f docker-compose.full.yml stop

# 3. 데이터 복원
cp -r "$RESTORE_DIR"/*/data/* ./data/
cp "$RESTORE_DIR"/*/.env ./.env

# 4. PostgreSQL 데이터 복원
docker-compose -f docker-compose.full.yml up -d postgres
sleep 5
docker exec -i postgres psql -U atlea atlea < "$RESTORE_DIR"/*/pg_dump.sql

# 5. 전체 서비스 시작
docker-compose -f docker-compose.full.yml up -d

# 6. 정리
rm -rf "$RESTORE_DIR"
```

### 자동 백업 (crontab)

```bash
# 매일 새벽 2시에 백업
0 2 * * * cd /path/to/atlea-chatbot && ./scripts/backup.sh

# 7일 이상 된 백업 자동 삭제
0 3 * * * find /path/to/atlea-chatbot/backups -name "*.tar.gz" -mtime +7 -delete
```

---

## 12. 모니터링

### 기본 상태 확인

```bash
# 서비스 상태
docker-compose -f docker-compose.full.yml ps

# 리소스 사용량
docker stats

# 애플리케이션 로그 (최근 100줄)
docker-compose -f docker-compose.full.yml logs -f chatbot-app --tail=100

# 건강 상태 API
curl http://localhost:8085/health
```

### Prometheus + Grafana (프로덕션)

```bash
docker-compose -f docker-compose.production.yml --profile monitoring up -d
```

| 서비스 | URL | 기본 계정 |
|--------|-----|----------|
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3000 | admin / admin |

---

## 13. 업데이트 및 롤백

### 업데이트 절차

```bash
# 1. 백업 (권장)
./scripts/backup.sh

# 2. 소스 코드 업데이트
git pull origin main

# 3. Docker 이미지 재빌드 및 재시작
docker-compose -f docker-compose.full.yml up -d --build

# 4. 확인
curl http://localhost:8085/health
```

### 롤백

```bash
# 1. 이전 버전 확인
git log --oneline -10

# 2. 이전 버전으로 체크아웃
git checkout <이전_커밋_해시>

# 3. 재빌드 및 재시작
docker-compose -f docker-compose.full.yml up -d --build
```

> 데이터는 Docker 볼륨에 저장되므로 이미지 재빌드 시에도 유지됩니다.

---

## 14. 플랫폼별 특성

### Apple Silicon (M1/M2/M3/M4)

- **MLX 프레임워크**로 GPU 가속 자동 지원
- Docker Desktop에서는 MLX를 사용할 수 없으므로 **네이티브 설치 권장**
- 통합 메모리 구조로 GPU/CPU 메모리 공유

### Linux + NVIDIA GPU

- **Transformers + CUDA** 또는 **Ollama + GPU**로 빠른 추론
- `docker-compose.gpu.yml`로 GPU 컨테이너 지원
- NVIDIA Container Toolkit 필수

### 성능 비교

| 플랫폼 | 백엔드 | 상대 속도 |
|--------|--------|----------|
| Mac M2 Max | MLX / Ollama | 1.5x |
| Mac M1 Pro | MLX / Ollama | 1.0x (기준) |
| RTX 4090 | CUDA / Ollama | 3-4x |
| RTX 3090 | CUDA / Ollama | 2-3x |
| CPU 16코어 | Ollama | 0.1-0.3x |

### 모델 호환성

| 플랫폼 | MLX 모델 | Ollama 모델 | Transformers 모델 |
|--------|---------|------------|------------------|
| macOS (Apple Silicon) | O | O | O |
| Linux (NVIDIA GPU) | X | O | O |
| Linux (CPU) | X | O | O (느림) |

---

## 15. 문제 해결

### 서비스가 시작되지 않음

```bash
# 로그 확인
docker-compose -f docker-compose.full.yml logs chatbot-app

# 주요 원인:
# 1. PostgreSQL 연결 실패 → PostgreSQL 먼저 시작 확인
# 2. 포트 충돌 → lsof -i :8085
# 3. 메모리 부족 → docker stats
```

### PostgreSQL 연결 실패

```bash
docker-compose -f docker-compose.full.yml exec postgres psql -U atlea -c "SELECT 1"
# 정상 응답이 와야 합니다
```

### 모델 로딩 실패

```bash
# Ollama 상태 확인
curl http://localhost:11434/api/version

# 모델 목록 확인
ollama list

# 모델 재다운로드
ollama pull alibayram/Qwen3-30B-A3B-Instruct-2507:latest
```

### 포트 충돌

```bash
# 사용 중인 포트 확인
lsof -i :8085
lsof -i :6379

# 해결: .env에서 PORT 값 변경
```

### Docker 메모리 부족

Docker Desktop 설정에서 메모리를 늘려주세요:
- 권장: 8GB 이상
- LLM 포함 시: 16GB 이상

### Ollama 연결 실패

```bash
# 서버 실행 확인
curl http://localhost:11434/api/version

# Docker에서 호스트 Ollama 접근 시
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Linux에서 Docker 호스트 접근 시
OLLAMA_BASE_URL=http://172.17.0.1:11434
```

### SSL 인증서 오류

```bash
# 인증서 파일 확인
ls -la nginx/ssl/

# 인증서 만료일 확인
openssl x509 -enddate -noout -in nginx/ssl/fullchain.pem

# 인증서 갱신
sudo certbot renew
```

---

## 포트 매핑 요약

| 포트 | 서비스 | 사용 환경 |
|------|--------|----------|
| 80 | Nginx HTTP | 프로덕션 |
| 443 | Nginx HTTPS | 프로덕션 |
| 8085 | 챗봇 웹 UI / API | 전체 |
| 5432 | PostgreSQL | 전체 (프로덕션: 외부 차단) |
| 8081 | Document Service | 전체 (프로덕션: 외부 차단) |
| 3310 | ClamAV | 전체 |
| 8888 | SearXNG | 선택 |
| 11235 | Crawl4AI | 선택 |
| 11434 | Ollama | 전체 |
| 9090 | Prometheus | 모니터링 |
| 3000 | Grafana | 모니터링 |
| 9400 | NVIDIA Exporter | GPU 모니터링 |
