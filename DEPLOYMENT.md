# 프로덕션 배포 가이드

## 📋 배포 전 체크리스트

### 1. 환경 설정

```bash
# 1. 프로덕션 환경 파일 복사
cp .env.production .env

# 2. 비밀키 생성
python3 scripts/generate_secrets.py

# 3. 생성된 키를 .env 파일에 복사
# JWT_SECRET_KEY와 SECRET_KEY를 변경
nano .env
```

### 2. 필수 변경 항목

**.env 파일에서 반드시 변경해야 할 항목:**

```bash
# 1. 비밀키 (절대 dev-secret-key 사용 금지!)
JWT_SECRET_KEY=<generate_secrets.py 출력값>
SECRET_KEY=<generate_secrets.py 출력값>

# 2. CORS 도메인
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# 3. 로그 파일 경로 (선택사항)
LOG_FILE=/var/log/chatbot/server.log
```

### 3. 보안 설정 확인

**.env 파일 확인:**
```bash
ENV=production                    # ✅ production으로 설정
DEBUG=false                       # ✅ false로 설정
RATE_LIMIT_ENABLED=true          # ✅ true로 설정
PASSWORD_MIN_LENGTH=12           # ✅ 12자 이상
MAX_LOGIN_ATTEMPTS=3             # ✅ 3회로 제한
```

### 4. 디렉토리 준비

```bash
# 로그 디렉토리 생성
sudo mkdir -p /var/log/chatbot
sudo chown $USER:$USER /var/log/chatbot

# 데이터 디렉토리 권한 설정
chmod 750 ./data
```

### 5. 서버 시작

```bash
# 개발 모드
python3 -m src.web_server

# 또는 nohup으로 백그라운드 실행
nohup python3 -m src.web_server > /var/log/chatbot/stdout.log 2>&1 &
```

## 🔒 보안 강화 설정

### Rate Limiting 효과

**개발 환경 (.env):**
```bash
RATE_LIMIT_ENABLED=false  # 테스트 편의성
```

**프로덕션 (.env.production):**
```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60   # 분당 60회 요청 제한
RATE_LIMIT_BURST=10        # 버스트 10회 허용
```

### 브라우저 캐싱

**개발 환경:**
- JavaScript/CSS: 캐시 비활성화
- 코드 변경 즉시 반영

**프로덕션:**
- JavaScript/CSS: 1년 캐시
- HTML: 1시간 캐시

### 로그 레벨

**개발:**
```bash
LOG_LEVEL=INFO  # 상세 로그
```

**프로덕션:**
```bash
LOG_LEVEL=WARNING  # 경고/에러만
```

## 🚀 배포 시나리오

### A. 로컬 프로덕션 테스트

```bash
# 1. 프로덕션 설정 복사
cp .env.production .env.prod.test

# 2. 비밀키 생성 및 설정
python3 scripts/generate_secrets.py
# 출력값을 .env.prod.test에 복사

# 3. 테스트 서버 실행
ENV_FILE=.env.prod.test python3 -m src.web_server

# 4. 테스트
curl http://localhost:8000/health
```

### B. 프로덕션 서버 배포

```bash
# 1. 코드 배포
git pull origin main

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경 설정
cp .env.production .env
python3 scripts/generate_secrets.py
# 비밀키 및 도메인 설정

# 4. 서버 재시작
pkill -f "python.*web_server"
nohup python3 -m src.web_server > /var/log/chatbot/stdout.log 2>&1 &
```

## 📊 모니터링

### 로그 확인

```bash
# 실시간 로그
tail -f /var/log/chatbot/server.log

# 에러만 확인
grep "ERROR" /var/log/chatbot/server.log

# 보안 이벤트 확인
grep "SECURITY_EVENT" /var/log/chatbot/server.log
```

### 성능 모니터링

```bash
# Health check
curl http://localhost:8000/health

# Redis 상태
redis-cli INFO

# 프로세스 확인
ps aux | grep web_server
```

## ⚠️ 주의사항

1. **비밀키는 절대 Git에 커밋하지 마세요**
   ```bash
   # .gitignore에 포함 확인
   .env
   .env.production
   .env.*.local
   ```

2. **dev-secret-key를 프로덕션에서 사용하지 마세요**
   - 보안 취약점 발생
   - 반드시 generate_secrets.py로 생성

3. **CORS 도메인을 정확히 설정하세요**
   - localhost는 프로덕션에서 제거
   - 실제 도메인만 허용

4. **로그 파일을 주기적으로 정리하세요**
   ```bash
   # logrotate 설정 권장
   sudo nano /etc/logrotate.d/chatbot
   ```

## 🔄 업데이트 절차

```bash
# 1. 백업
cp .env .env.backup

# 2. 코드 업데이트
git pull origin main

# 3. 의존성 확인
pip install -r requirements.txt

# 4. 서버 재시작
pkill -f "python.*web_server"
nohup python3 -m src.web_server > /var/log/chatbot/stdout.log 2>&1 &

# 5. 헬스 체크
curl http://localhost:8000/health
```
