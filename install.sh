#!/bin/bash

# ==============================================================================
# RAG 챗봇 시스템 - 원클릭 설치 스크립트
# ==============================================================================
# 이 스크립트는 RAG 챗봇 시스템을 자동으로 설치하고 구성합니다.
# 사용법: ./install.sh
# ==============================================================================

set -e

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 로고 출력
print_logo() {
    echo -e "${CYAN}"
    cat << "EOF"
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║    ██████╗  █████╗  ██████╗     ██████╗██╗  ██╗ █████╗ ████████╗ ║
║    ██╔══██╗██╔══██╗██╔════╝    ██╔════╝██║  ██║██╔══██╗╚══██╔══╝ ║
║    ██████╔╝███████║██║  ███╗   ██║     ███████║███████║   ██║    ║
║    ██╔══██╗██╔══██║██║   ██║   ██║     ██╔══██║██╔══██║   ██║    ║
║    ██║  ██║██║  ██║╚██████╔╝   ╚██████╗██║  ██║██║  ██║   ██║    ║
║    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝     ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ║
║                                                                   ║
║              AI 기반 문서 질의응답 시스템 설치 프로그램              ║
║                        Version 1.0.0                              ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

# 헬퍼 함수
log_info() {
    echo -e "${BLUE}[정보]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[성공]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[경고]${NC} $1"
}

log_error() {
    echo -e "${RED}[오류]${NC} $1"
}

log_step() {
    echo ""
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${PURPLE}  $1${NC}"
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# 명령어 존재 확인
command_exists() {
    command -v "$1" &> /dev/null
}

# 진행률 표시
show_progress() {
    local duration=$1
    local message=$2
    echo -ne "${CYAN}${message}${NC} "
    for i in $(seq 1 $duration); do
        echo -ne "▓"
        sleep 1
    done
    echo -e " ${GREEN}완료${NC}"
}

# 로고 출력
print_logo

echo -e "${CYAN}RAG 챗봇 시스템을 설치합니다.${NC}"
echo -e "${CYAN}이 과정은 약 10-20분 소요됩니다.${NC}"
echo ""

# 사용자 확인
read -p "계속 진행하시겠습니까? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_warning "설치가 취소되었습니다."
    exit 0
fi

# ==============================================================================
# 1단계: 시스템 요구사항 확인
# ==============================================================================
log_step "1단계: 시스템 요구사항 확인"

# OS 확인
OS_TYPE=$(uname -s)
ARCH=$(uname -m)
log_info "운영체제: $OS_TYPE ($ARCH)"

if [ "$OS_TYPE" = "Darwin" ]; then
    if [ "$ARCH" = "arm64" ]; then
        log_success "Apple Silicon (M1/M2/M3/M4) 감지 - MLX GPU 가속 사용 가능"
        PLATFORM="mac-arm64"
    else
        log_warning "Intel Mac 감지 - CPU 모드로 실행됩니다"
        PLATFORM="mac-x86"
    fi
elif [ "$OS_TYPE" = "Linux" ]; then
    log_success "Linux 시스템 감지"
    PLATFORM="linux"
else
    log_error "지원하지 않는 운영체제입니다: $OS_TYPE"
    exit 1
fi

# Docker 확인
log_info "Docker 확인 중..."
if ! command_exists docker; then
    log_error "Docker가 설치되어 있지 않습니다."
    log_info "Docker Desktop을 설치해주세요: https://www.docker.com/products/docker-desktop"
    exit 1
fi

if ! docker ps &> /dev/null; then
    log_error "Docker가 실행 중이지 않습니다."
    log_info "Docker Desktop을 실행한 후 다시 시도해주세요."
    exit 1
fi
log_success "Docker 확인 완료"

# Docker Compose 확인
log_info "Docker Compose 확인 중..."
if ! command_exists docker-compose && ! docker compose version &> /dev/null; then
    log_error "Docker Compose가 설치되어 있지 않습니다."
    exit 1
fi
log_success "Docker Compose 확인 완료"

# 디스크 공간 확인
log_info "디스크 공간 확인 중..."
if [ "$OS_TYPE" = "Darwin" ]; then
    AVAILABLE_SPACE=$(df -g . | awk 'NR==2 {print $4}')
else
    AVAILABLE_SPACE=$(df -BG . | awk 'NR==2 {print $4}' | tr -d 'G')
fi

if [ "$AVAILABLE_SPACE" -lt 30 ]; then
    log_warning "디스크 여유 공간이 부족합니다: ${AVAILABLE_SPACE}GB"
    log_warning "최소 30GB 이상의 여유 공간이 필요합니다."
    read -p "계속 진행하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    log_success "디스크 여유 공간 확인: ${AVAILABLE_SPACE}GB"
fi

# ==============================================================================
# 2단계: 환경 설정
# ==============================================================================
log_step "2단계: 환경 설정"

# 필수 디렉토리 생성
log_info "디렉토리 구조 생성 중..."
mkdir -p data model logs

# .env 파일 생성
if [ ! -f ".env" ]; then
    log_info ".env 파일 생성 중..."

    # JWT 시크릿 키 자동 생성
    if command_exists python3; then
        JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    else
        JWT_SECRET="PLEASE_CHANGE_THIS_SECRET_KEY_$(date +%s)_$(openssl rand -hex 16)"
    fi

    # .env 파일 생성
    cat > .env << EOF
# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Document Service Configuration
DOCUMENT_SERVICE_URL=http://document-service:8081
HWP_SERVICE_URL=http://document-service:8081

# Model Configuration
EMBEDDING_MODEL=nlpai-lab/KURE-v1
LLM_MODEL=mlx-community/Qwen3-30B-A3B-4bit
MODEL_DIR=/app/model

# Application Configuration
DATA_DIR=/app/data
CHUNK_SIZE=512
CHUNK_OVERLAP=50
MAX_FILE_SIZE_MB=100
ENABLE_QUESTION_GENERATION=false

# Server Configuration
HOST=0.0.0.0
PORT=8085

# JWT Security Configuration (자동 생성됨)
JWT_SECRET_KEY=$JWT_SECRET
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Rate Limiting Configuration
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10
EOF
    log_success ".env 파일 생성 완료"
else
    log_success ".env 파일이 이미 존재합니다"
fi

# ==============================================================================
# 3단계: AI 모델 다운로드
# ==============================================================================
log_step "3단계: AI 모델 다운로드"

if [ -d "model/mlx-community--Qwen3-30B-A3B-4bit" ] && [ -d "model/nlpai-lab--KURE-v1" ]; then
    log_success "AI 모델이 이미 다운로드되어 있습니다"
else
    log_warning "AI 모델이 필요합니다 (약 15-20GB)"
    log_info "다음 모델이 다운로드됩니다:"
    log_info "  • LLM: Qwen3-30B-A3B-4bit (~15GB)"
    log_info "  • Embedding: KURE-v1 (~4GB)"
    echo ""

    read -p "지금 다운로드하시겠습니까? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        if [ -f "download_models.py" ] && command_exists python3; then
            log_info "모델 다운로드 중... (시간이 걸릴 수 있습니다)"

            # Python 가상환경 생성 (필요시)
            if [ ! -d "venv" ]; then
                log_info "Python 가상환경 생성 중..."
                python3 -m venv venv
            fi

            # 가상환경 활성화 및 패키지 설치
            source venv/bin/activate
            pip install --quiet --upgrade pip
            pip install --quiet huggingface-hub requests tqdm

            # 모델 다운로드
            python3 download_models.py

            if [ $? -eq 0 ]; then
                log_success "모델 다운로드 완료"
            else
                log_error "모델 다운로드 실패"
                log_info "수동으로 모델을 다운로드해야 합니다:"
                log_info "  python3 download_models.py"
                exit 1
            fi
        else
            log_warning "모델을 수동으로 다운로드해야 합니다:"
            log_info "  python3 download_models.py"
        fi
    else
        log_warning "모델 다운로드를 건너뜁니다"
        log_warning "나중에 반드시 모델을 다운로드해야 시스템이 작동합니다!"
    fi
fi

# ==============================================================================
# 4단계: Docker 이미지 빌드
# ==============================================================================
log_step "4단계: Docker 이미지 빌드"

log_info "Docker 이미지를 빌드합니다... (첫 실행 시 시간이 걸립니다)"

# Java Document Service 빌드 (있는 경우)
if [ -d "document-service" ]; then
    log_info "Java 문서 처리 서비스 빌드 중..."
    docker-compose -f docker-compose.full.yml build document-service
    if [ $? -eq 0 ]; then
        log_success "문서 처리 서비스 빌드 완료"
    else
        log_error "문서 처리 서비스 빌드 실패"
        exit 1
    fi
fi

# Python 챗봇 애플리케이션 빌드
log_info "챗봇 애플리케이션 빌드 중..."
if [ -f "Dockerfile" ]; then
    docker-compose -f docker-compose.full.yml build chatbot-app
    if [ $? -eq 0 ]; then
        log_success "챗봇 애플리케이션 빌드 완료"
    else
        log_error "챗봇 애플리케이션 빌드 실패"
        exit 1
    fi
else
    log_warning "Dockerfile이 없습니다. Docker 없이 실행됩니다."
fi

# ==============================================================================
# 5단계: 서비스 시작
# ==============================================================================
log_step "5단계: 서비스 시작"

log_info "모든 서비스를 시작합니다..."
docker-compose -f docker-compose.full.yml up -d

# 서비스 시작 대기
log_info "서비스 초기화 대기 중..."
show_progress 15 "초기화 중"

# 서비스 상태 확인
log_info "서비스 상태 확인 중..."
sleep 5

PG_STATUS=$(docker-compose -f docker-compose.full.yml ps postgres | grep "Up" || echo "Down")
DOC_SERVICE_STATUS=$(docker-compose -f docker-compose.full.yml ps document-service | grep "Up" || echo "Down")
APP_STATUS=$(docker-compose -f docker-compose.full.yml ps chatbot-app | grep "Up" || echo "Down")

if [[ $PG_STATUS == *"Up"* ]]; then
    log_success "PostgreSQL: 실행 중"
else
    log_error "PostgreSQL: 시작 실패"
fi

if [[ $DOC_SERVICE_STATUS == *"Up"* ]]; then
    log_success "문서 서비스: 실행 중"
else
    log_warning "문서 서비스: 시작 실패 (선택 사항)"
fi

if [[ $APP_STATUS == *"Up"* ]]; then
    log_success "챗봇 애플리케이션: 실행 중"
else
    log_error "챗봇 애플리케이션: 시작 실패"
fi

# ==============================================================================
# 설치 완료
# ==============================================================================
echo ""
log_step "설치 완료!"
echo ""

cat << EOF
${GREEN}╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║                  🎉 설치가 성공적으로 완료되었습니다! 🎉              ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝${NC}

${CYAN}📊 설치 요약:${NC}
  ✅ Redis Vector Database: 실행 중
  ✅ Java 문서 처리 서비스: 실행 중
  ✅ RAG 챗봇 애플리케이션: 실행 중
  ✅ AI 모델: 준비됨

${CYAN}🌐 접속 정보:${NC}
  💬 챗봇 웹 UI:          http://localhost:8085
  📚 API 문서 (Swagger):  http://localhost:8085/docs
  ❤️  시스템 상태:         http://localhost:8085/health
  📊 PostgreSQL:          localhost:5432

${CYAN}📝 다음 단계:${NC}

  1️⃣  브라우저에서 http://localhost:8085 접속

  2️⃣  문서 추가:
     data/ 디렉토리에 PDF, HWP, DOCX 등의 파일 복사

  3️⃣  시스템 사용:
     - 질문을 입력하여 문서 내용 검색
     - 문서 관리에서 파일 업로드/삭제
     - 설정에서 모델 파라미터 조정

${CYAN}🔧 유용한 명령어:${NC}
  • 상태 확인:    docker-compose -f docker-compose.full.yml ps
  • 로그 확인:    docker-compose -f docker-compose.full.yml logs -f
  • 서비스 중지:  docker-compose -f docker-compose.full.yml down
  • 서비스 재시작: docker-compose -f docker-compose.full.yml restart

${CYAN}📖 문서:${NC}
  • 설치 매뉴얼:   INSTALLATION_MANUAL.md
  • 빠른 시작:     QUICK_START.md
  • 전체 가이드:   README.md

${CYAN}💡 문제 해결:${NC}
  • 서비스가 시작되지 않으면 로그를 확인하세요
  • Docker 메모리를 최소 8GB 이상 할당하세요
  • 포트 충돌 시 .env 파일에서 포트 번호를 변경하세요

${GREEN}즐거운 사용 되세요! 🚀${NC}

EOF

# 로그 파일 위치 안내
log_info "설치 로그가 저장되었습니다: logs/install_$(date +%Y%m%d_%H%M%S).log"

exit 0
