# 📦 ATLEA 시스템 설치 패키지

## 패키지 내용물

이 패키지에는 ATLEA 시스템의 모든 구성 요소가 포함되어 있습니다.

### 📁 디렉토리 구조

```
chatbot_redis/
│
├── 📄 install.sh                    # 원클릭 설치 스크립트
├── 📄 INSTALLATION_MANUAL.md        # 상세 설치 매뉴얼
├── 📄 QUICK_START.md                # 빠른 시작 가이드
├── 📄 README.md                     # 프로젝트 전체 문서
│
├── 🐳 docker-compose.full.yml       # 완전 통합 Docker 설정
├── 🐳 docker-compose.yml            # 기본 Docker 설정
├── 🐳 Dockerfile                    # ATLEA 애플리케이션 이미지
│
├── ⚙️  .env.example                 # 환경 설정 템플릿
├── ⚙️  requirements.txt             # Python 패키지 의존성
│
├── 📂 src/                          # Python 소스 코드
├── 📂 static/                       # 웹 UI 파일
├── 📂 document-service/             # Java 문서 처리 서비스
├── 📂 data/                         # 문서 저장 디렉토리 (비어있음)
├── 📂 model/                        # AI 모델 저장 디렉토리 (설치 시 다운로드)
└── 📂 logs/                         # 로그 파일 디렉토리
```

---

## 🚀 빠른 설치 (3단계)

### 1️⃣ Docker Desktop 설치

**macOS / Windows / Linux**:
- [Docker Desktop 다운로드](https://www.docker.com/products/docker-desktop)
- 설치 후 실행
- 메모리 8GB 이상 할당 (Settings → Resources → Memory)

### 2️⃣ 설치 스크립트 실행

```bash
# 터미널에서 패키지 디렉토리로 이동
cd /path/to/chatbot_redis

# 설치 스크립트 실행
chmod +x install.sh  # macOS/Linux에서 실행 권한 부여
./install.sh
```

### 3️⃣ 웹 브라우저 접속

```
http://localhost:8000
```

**🎉 설치 완료!** 이제 사용하실 수 있습니다!

---

## 📚 문서 가이드

### 빠르게 시작하고 싶으신가요?

👉 **QUICK_START.md** 읽어보세요 (5분 소요)

### 상세한 설치 과정이 필요하신가요?

👉 **INSTALLATION_MANUAL.md** 참고하세요

### 전체 기능과 사용법을 알고 싶으신가요?

👉 **README.md** 전체 문서 확인하세요

---

## ⚙️ 시스템 요구사항

### 최소 사양
- **CPU**: 4코어 이상
- **메모리**: 16GB RAM
- **저장공간**: 50GB 여유 공간
- **운영체제**: macOS 14+ / Windows 10+ / Linux (Ubuntu 20.04+)

### 권장 사양
- **CPU**: 8코어 이상 (Apple M2/M3 또는 고성능 Intel/AMD)
- **메모리**: 32GB RAM
- **저장공간**: 100GB SSD
- **GPU**: Apple Silicon 또는 NVIDIA GPU (선택)

---

## 🎯 주요 기능

### 📄 다중 문서 형식 지원
- PDF, HWP, HWPX
- DOC, DOCX
- XLS, XLSX
- PPT, PPTX
- TXT

### 🤖 고성능 AI
- **LLM**: Qwen3 30B (4-bit 양자화)
- **임베딩**: KURE-v1 (한국어 특화)
- **GPU 가속**: Apple Silicon, NVIDIA CUDA 지원

### 🔍 스마트 검색
- 벡터 기반 의미 검색
- 문서 그룹 관리
- 필터링 검색
- 자동완성

### 💬 자연스러운 대화
- 실시간 스트리밍 답변
- 출처 표시
- 대화 기록
- 답변 재생성

### 🎨 현대적인 UI
- 반응형 디자인
- 다크 모드
- Markdown 지원
- 직관적인 인터페이스

---

## 🔐 보안 기능

- **인증 시스템**: JWT 토큰 기반
- **2FA 지원**: Google Authenticator
- **역할 기반 권한**: 시스템 관리자, 조직 관리자, 사용자
- **조직 격리**: 멀티테넌트 아키텍처
- **Rate Limiting**: API 요청 제한
- **보안 헤더**: CSP, X-Frame-Options 등

---

## 📊 성능 최적화

### 캐싱 시스템
- **쿼리 캐시**: LRU 1000개 항목
- **답변 캐시**: 95% 유사도 자동 캐시
- **문서 추출 캐시**: Caffeine 500개 항목

### 멀티 워커
- CPU 코어 기반 자동 스케일링
- 비동기 처리
- 워커 재활용

### 최적화 기능
- Redis 연결 풀링 (50개)
- HTTP 압축
- 배치 임베딩
- 증분 색인

---

## 🛠️ 설치 후 첫 단계

### 1. 관리자 계정 생성

브라우저에서 http://localhost:8000 접속 후:
1. "회원가입" 클릭
2. 정보 입력
3. 가입 완료 (첫 사용자가 자동으로 관리자가 됩니다)

### 2. 문서 업로드

- 웹 UI에서 "문서 관리" → 파일 업로드
- 또는 `data/` 디렉토리에 파일 복사 후 서비스 재시작

### 3. 첫 질문하기

메인 화면에서 질문 입력:
```
"이 문서의 주요 내용은 무엇인가요?"
```

---

## 💡 유용한 명령어

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

### 시스템 상태

```bash
# 헬스체크
curl http://localhost:8000/health

# 메트릭
curl http://localhost:8000/metrics
```

---

## 🔧 문제 해결

### Docker가 시작되지 않음
```bash
# Docker Desktop 실행 확인
docker ps

# 재시작
docker-compose -f docker-compose.full.yml restart
```

### 포트 충돌
```bash
# 사용 중인 포트 확인
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# .env에서 포트 변경
PORT=8888
```

### 메모리 부족
```bash
# Docker 메모리 증가: Settings → Resources → Memory → 16GB
# 또는 경량 모델 사용
LLM_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit
```

더 많은 문제 해결 방법은 **INSTALLATION_MANUAL.md**의 "문제 해결" 섹션을 참고하세요.

---

## 📞 지원

### 기술 지원
- **이메일**: support@your-company.com
- **전화**: 1234-5678 (평일 09:00-18:00)

### 문서
- **설치 매뉴얼**: INSTALLATION_MANUAL.md
- **빠른 시작**: QUICK_START.md
- **전체 가이드**: README.md
- **배포 가이드**: DEPLOYMENT_GUIDE.md

### 추가 리소스
- **API 문서**: http://localhost:8000/docs
- **GitHub**: (해당하는 경우)
- **웹사이트**: https://your-company.com

---

## 📝 라이선스

이 소프트웨어는 상용 라이선스로 제공됩니다.

- **단일 서버 라이선스**: 1대의 서버에서 사용
- **기업 라이선스**: 무제한 서버에서 사용
- **소스 코드**: 라이선스에 포함되지 않음

자세한 라이선스 조건은 LICENSE 파일을 참고하세요.

---

## 🎓 교육 및 컨설팅

### 교육 프로그램
- 관리자 교육 (4시간)
- 사용자 교육 (2시간)
- 기술 교육 (개발자 대상, 8시간)

### 컨설팅 서비스
- 시스템 최적화
- 커스터마이징
- 온프레미스 배포 지원

문의: sales@your-company.com

---

## 🔄 업데이트 정책

### 마이너 업데이트 (무료)
- 버그 수정
- 성능 개선
- 보안 패치

### 메이저 업데이트 (유료)
- 새로운 기능
- 아키텍처 개선
- AI 모델 업그레이드

### 업데이트 방법
```bash
# 최신 버전 다운로드 (제공받은 링크에서)
# 백업 수행
./backup.sh

# 업데이트 설치
./update.sh
```

---

## ✅ 설치 체크리스트

설치를 시작하기 전에 확인하세요:

- [ ] Docker Desktop 설치됨
- [ ] Docker Desktop 실행 중
- [ ] 메모리 8GB 이상 할당
- [ ] 디스크 여유 공간 50GB 이상
- [ ] 포트 8000, 6379, 8081 사용 가능
- [ ] 인터넷 연결 (모델 다운로드용)

설치 완료 후 확인하세요:

- [ ] http://localhost:8000 접속 가능
- [ ] 관리자 계정 생성됨
- [ ] 샘플 문서 업로드됨
- [ ] 첫 질문 성공적으로 처리됨
- [ ] 시스템 상태 정상 (http://localhost:8000/health)

---

## 📅 버전 정보

- **패키지 버전**: 1.0.0
- **출시일**: 2026-01-02
- **포함 소프트웨어**:
  - ATLEA 애플리케이션 v1.0.0
  - Java 문서 서비스 v1.0.0
  - Redis Stack 7.x
  - Qwen3 30B 4-bit
  - KURE-v1 임베딩 모델

---

**🎉 ATLEA를 선택해 주셔서 감사합니다!**

설치 및 사용 중 궁금한 점이 있으시면 언제든지 문의해 주세요.

**즐거운 사용 되세요! 🚀**

---

**마지막 업데이트**: 2026-01-02
**문서 버전**: 1.0.0
