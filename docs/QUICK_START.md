# 🚀 ATLEA 빠른 시작 가이드

5분 안에 ATLEA를 실행해보세요!

---

## 📋 시작하기 전에

### 필수 요구사항

| 항목 | 요구사항 |
|------|----------|
| **메모리** | 최소 16GB RAM (32GB 권장) |
| **저장공간** | 50GB 여유 공간 |
| **소프트웨어** | Docker Desktop ([다운로드](https://www.docker.com/products/docker-desktop)) |
| **포트** | 8085, 5432, 8081 사용 가능 |

---

## ⚡ 3단계 설치

### 1️⃣ Docker 실행

Docker Desktop을 실행하고 다음을 확인하세요:
- ✅ Docker가 실행 중
- ✅ 메모리 8GB 이상 할당 (Settings → Resources → Memory)

### 2️⃣ 설치 스크립트 실행

```bash
# 터미널에서 프로젝트 디렉토리로 이동
cd /path/to/chatbot_redis

# 설치 스크립트 실행
./install.sh
```

설치가 자동으로 진행됩니다 (약 10-20분):
- ✅ 시스템 확인
- ✅ 환경 설정
- ✅ AI 모델 다운로드 (선택)
- ✅ 서비스 시작

### 3️⃣ 웹 브라우저 접속

```
http://localhost:8085
```

🎉 **설치 완료!** ATLEA가 실행되었습니다!

---

## 🎯 첫 번째 질문하기

### 1. 문서 업로드

#### 방법 A: 웹 UI 사용
1. "문서 관리" 버튼 클릭
2. 파일을 드래그 앤 드롭 또는 "파일 선택" 클릭
3. 업로드 완료 대기

#### 방법 B: 파일 복사
```bash
# data 폴더에 파일 복사
cp your-document.pdf ./data/
cp your-document.hwp ./data/

# 서비스 재시작 (자동 색인)
docker-compose -f docker-compose.full.yml restart chatbot-app
```

**지원 형식**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT

### 2. 질문하기

메인 화면에서 질문을 입력하세요:

```
"이 문서의 주요 내용을 요약해줘"
"계약 기간은 언제까지인가요?"
"제품 가격은 얼마인가요?"
```

**Enter** 키를 누르면 AI가 답변을 생성합니다!

### 3. 답변 확인

- 💬 답변이 실시간으로 생성되어 표시됩니다
- 📄 하단에 참고 문서가 표시됩니다
- 📋 "복사" 버튼으로 답변 복사 가능
- 🔄 "재생성" 버튼으로 다시 생성 가능

---

## 🔧 기본 조작 방법

### 문서 관리

```
1. 문서 관리 → 파일 선택/드래그 앤 드롭
2. 업로드 진행률 확인
3. 완료되면 자동으로 검색 가능
```

### 그룹 만들기

```
1. 그룹 관리 → 그룹 추가
2. 이름, 설명, 색상, 아이콘 입력
3. 문서를 그룹에 할당
```

### 설정 변경

```
1. 우측 상단 사용자 메뉴 → 설정
2. 검색/생성/UI 설정 조정
3. 저장
```

### 대화 기록

```
1. 좌측 사이드바 토글 (Ctrl+/)
2. 이전 대화 목록 확인
3. 클릭하여 대화 불러오기
4. 새 대화 시작 (Ctrl+N)
```

---

## 🛠️ 유용한 명령어

### 시스템 제어

```bash
# 서비스 시작
docker-compose -f docker-compose.full.yml up -d

# 서비스 중지
docker-compose -f docker-compose.full.yml down

# 서비스 재시작
docker-compose -f docker-compose.full.yml restart

# 상태 확인
docker-compose -f docker-compose.full.yml ps

# 로그 확인
docker-compose -f docker-compose.full.yml logs -f
```

### 시스템 상태 확인

```bash
# 헬스체크
curl http://localhost:8085/health

# API 문서
open http://localhost:8085/docs  # macOS
xdg-open http://localhost:8085/docs  # Linux
start http://localhost:8085/docs  # Windows
```

---

## ❓ 문제 해결

### 문제: Docker가 시작되지 않음

```bash
# Docker Desktop 실행 확인
docker ps

# 없으면 Docker Desktop 실행 후 재시도
```

### 문제: 포트가 이미 사용 중

```bash
# 포트 사용 확인
lsof -i :8085  # macOS/Linux
netstat -ano | findstr :8085  # Windows

# 다른 프로그램이 사용 중이면:
# 1. 해당 프로그램 종료
# 또는
# 2. .env 파일에서 포트 변경
PORT=8888
```

### 문제: 메모리 부족

```bash
# Docker 메모리 증가
# Docker Desktop → Settings → Resources → Memory → 16GB

# 또는 경량 모델 사용 (.env 수정)
LLM_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit
```

### 문제: 모델 다운로드 실패

```bash
# 수동으로 모델 다운로드
python3 download_models.py

# 모델 확인
ls -la model/
```

---

## 📚 접속 주소

| 서비스 | 주소 |
|--------|------|
| 💬 ATLEA 웹 UI | http://localhost:8085 |
| 📚 API 문서 (Swagger) | http://localhost:8085/docs |
| 📖 API 문서 (ReDoc) | http://localhost:8085/redoc |
| ❤️ 헬스체크 | http://localhost:8085/health |
| 🔍 DB 관리 | http://localhost:5432 (PostgreSQL) |

---

## ⌨️ 키보드 단축키

| 단축키 | 기능 |
|--------|------|
| `F1` | 도움말 |
| `Ctrl+N` | 새 대화 |
| `Ctrl+/` | 대화 목록 |
| `Ctrl+K` | 입력창 포커스 |
| `Esc` | 모달 닫기 |
| `Enter` | 질문 전송 |
| `Shift+Enter` | 줄바꿈 |

---

## 🎓 다음 단계

### 더 많은 기능 알아보기

1. **문서 그룹 관리**
   - 문서를 카테고리별로 분류
   - 그룹별 검색 필터링

2. **고급 검색**
   - 특정 문서만 검색
   - 그룹 필터 활용

3. **자동완성**
   - 2글자 입력 시 자동 제안
   - 화살표 키로 선택

4. **답변 재생성**
   - 만족스럽지 않은 답변 다시 생성
   - Temperature 조정으로 창의성 조절

### 보안 강화

```bash
# JWT 시크릿 키 변경 (프로덕션 필수!)
nano .env
# JWT_SECRET_KEY를 강력한 키로 변경

# 서비스 재시작
docker-compose -f docker-compose.full.yml restart
```

### 성능 최적화

```bash
# PostgreSQL 상태 확인
docker exec -it postgres psql -U atlea -c "SELECT pg_database_size('atlea');"

# 캐시 통계 확인
curl http://localhost:8085/api/admin/stats
```

---

## 📖 상세 문서

더 자세한 내용은 다음 문서를 참고하세요:

- **INSTALLATION_MANUAL.md**: 상세 설치 가이드
- **README.md**: 프로젝트 전체 문서
- **DEPLOYMENT_GUIDE.md**: 프로덕션 배포 가이드

---

## 💡 팁

### 💰 메모리 절약
```bash
# 경량 모델 사용
LLM_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit
```

### ⚡ 성능 향상
```bash
# Apple Silicon Mac에서 GPU 가속 자동 활성화
# NVIDIA GPU는 별도 설정 필요 (MULTIPLATFORM_SUPPORT.md 참고)
```

### 📦 백업
```bash
# 간단한 백업
tar -czf backup_$(date +%Y%m%d).tar.gz data/ .env

# 복원
tar -xzf backup_20260102.tar.gz
```

---

## 🆘 도움이 필요하세요?

1. **로그 확인**:
   ```bash
   docker-compose -f docker-compose.full.yml logs -f
   ```

2. **상태 확인**:
   ```bash
   docker-compose -f docker-compose.full.yml ps
   curl http://localhost:8085/health
   ```

3. **완전 재시작**:
   ```bash
   docker-compose -f docker-compose.full.yml down
   docker-compose -f docker-compose.full.yml up -d
   ```

4. **문서 참고**:
   - INSTALLATION_MANUAL.md: 문제 해결 섹션
   - README.md: FAQ 섹션

---

**🎉 이제 ATLEA를 사용할 준비가 완료되었습니다!**

질문이 있으시면 support@your-company.com으로 문의해주세요.

---

**마지막 업데이트**: 2026-01-02
**문서 버전**: 1.0.0
