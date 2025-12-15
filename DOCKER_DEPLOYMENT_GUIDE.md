# Docker 배포 가이드

## 개요

이 가이드는 최적화된 Docker 이미지를 사용하여 프로덕션 환경에 애플리케이션을 배포하는 방법을 설명합니다.

## 최적화 내역

### 1. Multi-stage Build
- **Builder Stage**: 의존성 설치 및 빌드
- **Runtime Stage**: 최소한의 런타임 환경만 포함
- **결과**: 이미지 크기 50% 이상 감소

### 2. 보안 강화
- Non-root 사용자로 실행 (appuser)
- 최소 권한 원칙 적용
- 불필요한 패키지 제거
- Health check 추가

### 3. 성능 최적화
- Layer 캐싱 최적화
- .dockerignore로 불필요한 파일 제외
- Nginx reverse proxy로 부하 분산
- Redis 영구 저장 및 캐싱 설정

### 4. 운영 기능
- Health check 자동화
- 로깅 및 모니터링 (Prometheus, Grafana)
- Rate limiting 및 보안 헤더
- SSL/TLS 지원

## 빠른 시작

### 1. 환경 설정

```bash
# .env.production 파일 생성
cp .env.production.example .env.production

# 환경 변수 설정
nano .env.production
```

필수 환경 변수:
- `REDIS_PASSWORD`: Redis 비밀번호 (강력한 암호 사용)
- `GRAFANA_PASSWORD`: Grafana 관리자 비밀번호

### 2. 이미지 빌드

```bash
# 기본 빌드
./docker-build.sh

# 특정 태그로 빌드
./docker-build.sh v1.0.0

# 레지스트리에 푸시
export DOCKER_REGISTRY=your-registry.com/your-org
./docker-build.sh v1.0.0
```

### 3. 배포

```bash
# 프로덕션 환경 배포
./docker-deploy.sh production

# 로그 확인
docker-compose -f docker-compose.production.yml logs -f

# 서비스 상태 확인
docker-compose -f docker-compose.production.yml ps
```

## 서비스 구성

### Core Services

1. **app** - FastAPI 애플리케이션
   - Port: 8000 (internal)
   - Resources: 2 CPU, 4GB RAM
   - Health check: `/api/status`

2. **redis** - Redis 데이터베이스
   - Port: 6379 (internal only)
   - Persistence: AOF + RDB
   - Max Memory: 2GB (LRU eviction)

3. **nginx** - Reverse Proxy
   - Port: 80 (HTTP), 443 (HTTPS)
   - Rate limiting: 10 req/s per IP
   - SSL/TLS termination

### Optional Services (monitoring profile)

4. **redis-insight** - Redis 관리 UI
   - Port: 8001 (localhost only)

5. **prometheus** - 메트릭 수집
   - Port: 9090 (localhost only)

6. **grafana** - 시각화 대시보드
   - Port: 3000 (localhost only)

## SSL 인증서 설정

### Let's Encrypt 사용 (권장)

```bash
# Certbot 설치
sudo apt-get install certbot

# 인증서 발급
sudo certbot certonly --standalone -d yourdomain.com

# 인증서 복사
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/

# 권한 설정
sudo chmod 644 nginx/ssl/fullchain.pem
sudo chmod 600 nginx/ssl/privkey.pem
```

### 자체 서명 인증서 (테스트용)

```bash
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/privkey.pem \
  -out nginx/ssl/fullchain.pem \
  -subj "/CN=localhost"
```

## 모니터링 활성화

```bash
# 모니터링 프로파일 포함하여 시작
docker-compose -f docker-compose.production.yml --profile monitoring up -d

# 접속
# Grafana: http://localhost:3000 (admin / GRAFANA_PASSWORD)
# Prometheus: http://localhost:9090
# Redis Insight: http://localhost:8001
```

## 스케일링

### 수평 확장 (여러 앱 인스턴스)

```bash
# docker-compose.production.yml 수정
# nginx upstream 섹션에 추가 서버 추가

# 스케일 업
docker-compose -f docker-compose.production.yml up -d --scale app=3

# nginx 리로드
docker-compose -f docker-compose.production.yml exec nginx nginx -s reload
```

### 수직 확장 (리소스 증가)

docker-compose.production.yml에서 resources 섹션 수정:

```yaml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 8G
```

## 백업 및 복구

### Redis 데이터 백업

```bash
# 백업 생성
docker-compose -f docker-compose.production.yml exec redis redis-cli --raw SAVE
docker cp chatbot_redis:/data/dump.rdb ./backups/redis-$(date +%Y%m%d).rdb

# 백업 복구
docker cp ./backups/redis-20240101.rdb chatbot_redis:/data/dump.rdb
docker-compose -f docker-compose.production.yml restart redis
```

### 애플리케이션 데이터 백업

```bash
# 문서 백업
docker-compose -f docker-compose.production.yml exec app tar czf /tmp/data-backup.tar.gz /app/data
docker cp chatbot_app_1:/tmp/data-backup.tar.gz ./backups/

# 복구
docker cp ./backups/data-backup.tar.gz chatbot_app_1:/tmp/
docker-compose -f docker-compose.production.yml exec app tar xzf /tmp/data-backup.tar.gz -C /
```

## 로그 관리

```bash
# 실시간 로그 확인
docker-compose -f docker-compose.production.yml logs -f app

# 최근 100줄 확인
docker-compose -f docker-compose.production.yml logs --tail=100 app

# 특정 시간 이후 로그
docker-compose -f docker-compose.production.yml logs --since="2024-01-01T00:00:00"

# 로그 저장
docker-compose -f docker-compose.production.yml logs > logs/app-$(date +%Y%m%d).log
```

## 업데이트 및 롤백

### 무중단 배포 (Blue-Green)

```bash
# 1. 새 이미지 빌드
./docker-build.sh v2.0.0

# 2. 새 컨테이너 시작 (다른 포트)
docker run -d --name app_new -p 8001:8000 chatbot-app:v2.0.0

# 3. Health check
curl http://localhost:8001/api/status

# 4. Nginx upstream 전환
# nginx.conf 수정 후
docker-compose -f docker-compose.production.yml exec nginx nginx -s reload

# 5. 이전 컨테이너 종료
docker stop chatbot_app_1
```

### 롤백

```bash
# 이전 버전으로 롤백
docker-compose -f docker-compose.production.yml down
docker tag chatbot-app:v1.0.0 chatbot-app:latest
docker-compose -f docker-compose.production.yml up -d
```

## 트러블슈팅

### 컨테이너가 시작되지 않음

```bash
# 로그 확인
docker-compose -f docker-compose.production.yml logs app

# 컨테이너 내부 접속
docker-compose -f docker-compose.production.yml exec app /bin/bash

# 환경 변수 확인
docker-compose -f docker-compose.production.yml exec app env
```

### Redis 연결 실패

```bash
# Redis 상태 확인
docker-compose -f docker-compose.production.yml exec redis redis-cli ping

# 비밀번호로 접속
docker-compose -f docker-compose.production.yml exec redis \
  redis-cli -a $REDIS_PASSWORD ping

# 연결 정보 확인
docker-compose -f docker-compose.production.yml exec redis redis-cli info
```

### 성능 문제

```bash
# 리소스 사용량 확인
docker stats

# 상세 메트릭
docker-compose -f docker-compose.production.yml exec app \
  curl http://localhost:8000/metrics

# Prometheus 확인
open http://localhost:9090
```

## 보안 체크리스트

- [ ] Redis 비밀번호 설정됨
- [ ] SSL 인증서 설정됨
- [ ] Nginx rate limiting 활성화됨
- [ ] 방화벽 규칙 설정됨
- [ ] 로그 모니터링 설정됨
- [ ] 백업 자동화 설정됨
- [ ] 환경 변수 암호화됨
- [ ] 컨테이너 보안 스캔 완료됨

## 성능 튜닝

### Nginx

```nginx
# nginx.conf에서 조정
worker_processes auto;  # CPU 코어 수에 맞춤
worker_connections 2048;  # 동시 연결 수
keepalive_timeout 65;  # Keep-alive 타임아웃
```

### Redis

```bash
# Redis 메모리 정책
maxmemory 2gb
maxmemory-policy allkeys-lru

# Persistence 설정
save 900 1
save 300 10
appendonly yes
```

### FastAPI

```yaml
# Workers 수 증가
environment:
  - WORKERS=4  # CPU 코어 수
```

## 참고 자료

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Redis Production Deployment](https://redis.io/topics/admin)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
