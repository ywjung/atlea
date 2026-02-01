# 프로덕션 배포 가이드

상용 서비스를 위한 프로덕션 환경 설정 및 배포 가이드입니다.

## 🔒 보안 설정

### 1. 환경 변수 설정

`.env.production.example`을 복사하여 `.env` 파일 생성:

```bash
cp .env.production.example .env
```

필수 환경 변수 설정:

```bash
# 보안 - 필수 변경!
SECRET_KEY=your-very-strong-secret-key-min-32-chars-here
JWT_SECRET_KEY=your-jwt-secret-key-here

# CORS - 실제 도메인으로 변경
CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com

# 환경 설정
ENV=production
DEBUG=false
REQUIRE_HTTPS=true

# Rate Limiting - 필요시 조정
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10

# Ollama LLM 백엔드 (선택 - Ollama 사용 시)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=alibayram/Qwen3-30B-A3B-Instruct-2507:latest

# 웹 검색 - Hybrid RAG (선택)
SEARXNG_URL=http://searxng:8888
CRAWL4AI_API_TOKEN=your-crawl4ai-token
TAVILY_API_KEY=your-tavily-api-key
```

> **참고**: 2FA 강제 적용, CAPTCHA, TTS, 감사 로그, Brute Force 방어 설정은 관리자 웹 UI 또는 Redis 설정 키로 관리됩니다. 프로덕션 배포 시 아래 보안 체크리스트를 참고하세요.

### 2. SECRET_KEY 생성

안전한 SECRET_KEY 생성:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. CORS 설정

프로덕션 환경에서는 **반드시 실제 도메인만** 허용:

```bash
# ❌ 개발용 (사용하지 마세요)
CORS_ORIGINS=http://localhost:3000,*

# ✅ 프로덕션용
CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
```

## 🚀 서버 시작

### 방법 1: 시작 스크립트 사용 (권장)

```bash
./scripts/start_production.sh
```

### 방법 2: 직접 실행

```bash
# 환경 변수 로드
source .env

# Uvicorn으로 서버 시작
uvicorn src.web_server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    --timeout-keep-alive 5 \
    --limit-concurrency 1000 \
    --no-access-log \
    --no-server-header
```

### 방법 3: systemd 서비스 (Linux)

`/etc/systemd/system/chatbot.service` 파일 생성:

```ini
[Unit]
Description=ATLEA Service
After=network.target redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/chatbot_redis
Environment="PATH=/path/to/venv/bin"
EnvironmentFile=/path/to/chatbot_redis/.env
ExecStart=/path/to/venv/bin/uvicorn src.web_server:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

서비스 활성화:

```bash
sudo systemctl enable chatbot
sudo systemctl start chatbot
sudo systemctl status chatbot
```

## 📊 모니터링

### 로그 확인

로그 파일 위치 설정 (`.env`):

```bash
LOG_FILE=/var/log/chatbot/app.log
LOG_LEVEL=info
LOG_ROTATION=100 MB
LOG_RETENTION=30 days
```

로그 조회:

```bash
# 실시간 로그
tail -f /var/log/chatbot/app.log

# 에러 로그만
grep ERROR /var/log/chatbot/app.log

# 최근 100줄
tail -100 /var/log/chatbot/app.log
```

### Rate Limit 모니터링

응답 헤더에서 확인:

```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 30
```

Rate limit 초과 시:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30

{
  "error": "Too Many Requests",
  "message": "Rate limit exceeded. Try again in 30 seconds.",
  "limit": 60,
  "reset": 30
}
```

## 🔧 성능 최적화

### Worker 수 조정

CPU 코어 수에 따라 조정:

```bash
# CPU 코어 수 확인
nproc

# Worker 수 = (2 x CPU 코어) + 1
WORKERS=4  # 2 코어인 경우
WORKERS=8  # 4 코어인 경우
```

### Redis 연결 풀

Redis 연결 수 조정 (`.env`):

```bash
REDIS_MAX_CONNECTIONS=50  # Worker당 10-15개 권장
```

### 타임아웃 설정

```bash
REQUEST_TIMEOUT=300        # 요청 타임아웃 (초)
KEEPALIVE_TIMEOUT=5        # Keep-alive 타임아웃 (초)
```

## 🛡️ 보안 체크리스트

프로덕션 배포 전 확인사항:

- [ ] `SECRET_KEY` 변경 완료
- [ ] `DEBUG=false` 설정
- [ ] CORS origins를 실제 도메인으로 제한
- [ ] Rate limiting 활성화 (`RATE_LIMIT_ENABLED=true`)
- [ ] HTTPS 사용 (`REQUIRE_HTTPS=true`)
- [ ] Redis 비밀번호 설정
- [ ] 로그 파일 권한 확인
- [ ] 방화벽 설정 (필요한 포트만 개방)
- [ ] API 문서 비활성화 확인 (프로덕션에서는 /docs 자동 비활성화됨)
- [ ] 2FA 강제 적용 활성화 (`config:totp_enabled=true`)
- [ ] 로그인 CAPTCHA 활성화 (`config:captcha_login_enabled=true`)
- [ ] 회원가입 CAPTCHA 활성화 (`config:captcha_register_enabled=true`)
- [ ] 감사 로그 보관 기간 확인 (기본 90일)
- [ ] Brute Force 방어 설정 확인 (5회 실패 → 15분 잠금)

## 🔍 트러블슈팅

### 환경 변수 검증 실패

```bash
❌ Configuration validation failed:
  - SECRET_KEY must be set in production
```

**해결**: `.env` 파일에서 `SECRET_KEY` 설정

### Rate Limit 초과

```bash
⚠️  Rate limit exceeded for 192.168.1.1 on /api/chat (reset in 30s)
```

**해결**:
1. `RATE_LIMIT_PER_MINUTE` 값 증가
2. 클라이언트에서 요청 속도 제한
3. IP별 제한이 필요한 경우 Nginx에서 추가 제어

### Redis 연결 실패

```bash
❌ Redis 서버에 연결할 수 없습니다 (localhost:6379)
```

**해결**:
```bash
# Redis 시작
redis-server

# Redis 상태 확인
redis-cli ping  # PONG 응답 확인
```

### 로그 파일 권한 오류

```bash
❌ Permission denied: '/var/log/chatbot/app.log'
```

**해결**:
```bash
# 로그 디렉토리 생성 및 권한 설정
sudo mkdir -p /var/log/chatbot
sudo chown $USER:$USER /var/log/chatbot
```

## 🌐 리버스 프록시 (Nginx)

Nginx 설정 예시 (`/etc/nginx/sites-available/chatbot`):

```nginx
upstream chatbot {
    server 127.0.0.1:8000;
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

    # 보안 헤더 (이미 FastAPI에서 설정되어 있음)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Rate limiting (추가 보호)
    limit_req_zone $binary_remote_addr zone=chatbot_limit:10m rate=10r/s;
    limit_req zone=chatbot_limit burst=20 nodelay;

    # 파일 업로드 크기
    client_max_body_size 100M;

    location / {
        proxy_pass http://chatbot;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 타임아웃
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # 정적 파일 캐싱 (선택사항)
    location /static/ {
        alias /path/to/chatbot_redis/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

## 📦 Docker 배포 (선택사항)

`Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드
COPY . .

# 환경 변수
ENV ENV=production
ENV DEBUG=false

EXPOSE 8000

CMD ["uvicorn", "src.web_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

`docker-compose.yml`:

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - chatbot_network

  chatbot:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENV=production
      - DEBUG=false
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - SECRET_KEY=${SECRET_KEY}
      - CORS_ORIGINS=${CORS_ORIGINS}
    volumes:
      - ./data:/app/data
      - ./model:/app/model
      - chatbot_logs:/var/log/chatbot
    depends_on:
      - redis
    networks:
      - chatbot_network

volumes:
  redis_data:
  chatbot_logs:

networks:
  chatbot_network:
```

실행:

```bash
docker-compose up -d
```

### SearXNG + Crawl4AI (웹 검색 기능)

Hybrid RAG 웹 검색 기능을 사용하려면 SearXNG와 Crawl4AI 서비스를 추가로 실행합니다:

```bash
# SearXNG + Crawl4AI 시작
docker compose -f docker-compose.searxng.yml up -d

# 상태 확인
docker ps | grep -E "searxng|crawl4ai"

# 헬스체크
curl http://localhost:8888/healthz      # SearXNG
curl http://localhost:11235/health      # Crawl4AI
```

관리자 페이지에서 웹 검색 프로바이더를 `SearXNG (자체 호스팅)`으로 설정하고 URL을 `http://searxng:8888`로 입력하세요.

### document-service (Java) systemd 서비스

Java 문서 처리 서비스를 Docker 없이 직접 실행하는 경우:

```ini
# /etc/systemd/system/document-service.service
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

```bash
sudo systemctl enable document-service
sudo systemctl start document-service
```

## 📝 변경 이력

자세한 변경 이력은 [CHANGELOG.md](CHANGELOG.md)를 참조하세요.

## 🆘 지원

문제가 발생하면 다음을 확인하세요:

1. 로그 파일 확인
2. 환경 변수 설정 확인
3. Redis 연결 상태 확인
4. 방화벽 및 포트 개방 확인
