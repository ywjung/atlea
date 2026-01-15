#!/bin/bash

# PDF RAG Chatbot Setup Script
# 다른 컴퓨터에서도 쉽게 설치할 수 있도록 개선된 스크립트

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" &> /dev/null
}

echo ""
echo "🚀 PDF RAG 챗봇 설치 시작..."
echo "================================"
echo ""

# ========================================
# 1. System Requirements Check
# ========================================
log_info "시스템 요구사항 확인 중..."

# Check OS
OS_TYPE=$(uname -s)
log_info "운영체제: $OS_TYPE"

# Check if Apple Silicon (for MLX optimization)
if [ "$OS_TYPE" = "Darwin" ]; then
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        log_success "Apple Silicon (M1/M2/M3) 감지 - MLX GPU 가속 사용 가능"
    else
        log_warning "Intel Mac 감지 - MLX은 Apple Silicon에서 최적화됩니다"
    fi
fi

# Check Python version
log_info "Python 버전 확인..."
if ! command_exists python3; then
    log_error "Python 3가 설치되어 있지 않습니다."
    log_info "설치 방법:"
    if [ "$OS_TYPE" = "Darwin" ]; then
        log_info "  brew install python3"
    else
        log_info "  https://www.python.org/downloads/"
    fi
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    log_error "Python 3.10 이상이 필요합니다. 현재 버전: $PYTHON_VERSION"
    exit 1
fi
log_success "Python $PYTHON_VERSION 발견"

# Check Docker
log_info "Docker 확인..."
if ! command_exists docker; then
    log_error "Docker가 설치되어 있지 않습니다."
    log_info "Docker Desktop 설치: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Check if Docker daemon is running
if ! docker ps &> /dev/null; then
    log_error "Docker가 실행 중이지 않습니다."
    log_info "Docker Desktop을 실행해주세요."
    exit 1
fi
log_success "Docker 발견 및 실행 중"

# Check Docker Compose
log_info "Docker Compose 확인..."
if ! command_exists docker-compose && ! docker compose version &> /dev/null; then
    log_error "Docker Compose가 설치되어 있지 않습니다."
    exit 1
fi
log_success "Docker Compose 발견"

# Check Java (for HWP service)
log_info "Java 확인..."
if ! command_exists java; then
    log_warning "Java가 설치되어 있지 않습니다."
    log_warning "HWP 파일 처리를 위해 Java 17+ 설치를 권장합니다."
    log_info "설치 방법:"
    if [ "$OS_TYPE" = "Darwin" ]; then
        log_info "  brew install openjdk@17"
    else
        log_info "  https://adoptium.net/"
    fi
    read -p "Java 없이 계속 진행하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    SKIP_HWP=true
else
    JAVA_VERSION=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2)
    log_success "Java $JAVA_VERSION 발견"
    SKIP_HWP=false
fi

# Check Maven (for HWP service)
if [ "$SKIP_HWP" = false ]; then
    log_info "Maven 확인..."
    if ! command_exists mvn; then
        log_warning "Maven이 설치되어 있지 않습니다."
        log_warning "HWP 서비스 빌드를 위해 Maven 설치를 권장합니다."
        log_info "설치 방법:"
        if [ "$OS_TYPE" = "Darwin" ]; then
            log_info "  brew install maven"
        else
            log_info "  https://maven.apache.org/download.cgi"
        fi
        read -p "Maven 없이 계속 진행하시겠습니까? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
        SKIP_HWP=true
    else
        MAVEN_VERSION=$(mvn -version | head -n 1 | cut -d' ' -f3)
        log_success "Maven $MAVEN_VERSION 발견"
    fi
fi

echo ""
log_success "시스템 요구사항 확인 완료"
echo ""

# ========================================
# 2. Python Environment Setup
# ========================================
log_info "Python 가상환경 설정 중..."

if [ ! -d "venv" ]; then
    log_info "가상환경 생성 중..."
    python3 -m venv venv
    log_success "가상환경 생성 완료"
else
    log_success "가상환경이 이미 존재합니다"
fi

# Activate virtual environment
log_info "가상환경 활성화..."
source venv/bin/activate

# Upgrade pip
log_info "pip 업그레이드..."
pip install --upgrade pip --quiet

# Install requirements
log_info "Python 패키지 설치 중... (시간이 걸릴 수 있습니다)"
pip install -r requirements.txt --quiet

log_success "Python 패키지 설치 완료"
echo ""

# ========================================
# 3. Configuration Files
# ========================================
log_info "설정 파일 확인 중..."

# Create .env file if not exists
if [ ! -f ".env" ]; then
    log_info ".env 파일 생성..."
    cp .env.example .env
    log_success ".env 파일이 생성되었습니다"
    log_warning "필요시 .env 파일을 수정해주세요 (Redis 비밀번호 등)"
else
    log_success ".env 파일이 이미 존재합니다"
fi

# Create necessary directories
log_info "필수 디렉토리 생성..."
mkdir -p data model logs

log_success "디렉토리 구조 확인 완료"
echo ""

# ========================================
# 4. Redis Setup
# ========================================
log_info "Redis 컨테이너 설정 중..."

# Check if redis is already running
if docker ps | grep -q "chatbot_redis"; then
    log_warning "Redis 컨테이너가 이미 실행 중입니다"
    read -p "Redis를 재시작하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Redis 중지 중..."
        docker-compose down
        log_info "Redis 시작 중..."
        docker-compose up -d
    fi
else
    log_info "Redis 시작 중..."
    docker-compose up -d
fi

# Wait for Redis
log_info "Redis 준비 대기..."
sleep 5

# Check Redis
if docker ps | grep -q "chatbot_redis.*Up"; then
    log_success "Redis가 정상적으로 실행 중입니다"
else
    log_error "Redis 시작 실패"
    log_info "로그 확인: docker-compose logs redis"
    exit 1
fi

echo ""

# ========================================
# 5. HWP Service Setup (Optional)
# ========================================
if [ "$SKIP_HWP" = false ] && [ -d "document-service" ]; then
    log_info "HWP 서비스 설정 중..."

    read -p "HWP 파일 처리 서비스를 설치하시겠습니까? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        cd document-service

        log_info "Maven으로 HWP 서비스 빌드 중... (첫 실행 시 시간이 걸립니다)"
        if mvn clean package -DskipTests --quiet; then
            log_success "HWP 서비스 빌드 완료"
        else
            log_error "HWP 서비스 빌드 실패"
            log_warning "HWP 파일 처리는 사용할 수 없지만, PDF는 정상 작동합니다"
        fi

        cd ..
    fi
else
    if [ "$SKIP_HWP" = true ]; then
        log_warning "HWP 서비스를 건너뜁니다 (Java/Maven 미설치)"
    else
        log_warning "document-service 디렉토리를 찾을 수 없습니다"
    fi
    log_info "PDF 파일만 처리 가능합니다"
fi

echo ""

# ========================================
# 6. Model Setup
# ========================================
log_info "AI 모델 설정..."

if [ ! -d "model/mlx-community--Qwen3-30B-A3B-4bit" ] || [ ! -d "model/nlpai-lab--KURE-v1" ]; then
    log_warning "AI 모델이 설치되어 있지 않습니다"
    log_info ""
    log_info "모델 다운로드 방법:"
    log_info "  1. download_models.py 스크립트 사용 (자동):"
    log_info "     python3 download_models.py"
    log_info ""
    log_info "  2. 수동 다운로드:"
    log_info "     - LLM: mlx-community/Qwen3-30B-A3B-4bit"
    log_info "     - Embedding: nlpai-lab/KURE-v1"
    log_info "     model/ 디렉토리에 저장"
    log_info ""

    if [ -f "download_models.py" ]; then
        read -p "지금 모델을 다운로드하시겠습니까? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            log_info "모델 다운로드 중... (약 15-20GB, 시간이 걸릴 수 있습니다)"
            python3 download_models.py
        else
            log_warning "모델을 나중에 다운로드해야 서버를 실행할 수 있습니다"
        fi
    fi
else
    log_success "AI 모델이 이미 설치되어 있습니다"
fi

echo ""

# ========================================
# 7. Sample Data
# ========================================
log_info "샘플 데이터 확인..."

PDF_COUNT=$(find data -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')
HWP_COUNT=$(find data -name "*.hwp" 2>/dev/null | wc -l | tr -d ' ')

if [ "$PDF_COUNT" -eq 0 ] && [ "$HWP_COUNT" -eq 0 ]; then
    log_warning "data/ 디렉토리에 문서가 없습니다"
    log_info "PDF 또는 HWP 파일을 data/ 디렉토리에 추가하세요"
else
    log_success "문서 발견: PDF $PDF_COUNT개, HWP $HWP_COUNT개"
fi

echo ""

# ========================================
# 8. Final Summary
# ========================================
echo "================================"
log_success "설치 완료!"
echo "================================"
echo ""

echo "📊 설치 요약:"
echo "  • Python: $PYTHON_VERSION"
echo "  • Docker: 실행 중"
echo "  • Redis: 실행 중"
if [ "$SKIP_HWP" = false ]; then
    echo "  • HWP 서비스: 준비됨"
else
    echo "  • HWP 서비스: 비활성화 (PDF만 지원)"
fi
if [ -d "model/mlx-community--Qwen3-30B-A3B-4bit" ]; then
    echo "  • AI 모델: 설치됨"
else
    echo "  • AI 모델: 미설치 (다운로드 필요)"
fi
echo "  • 문서: PDF $PDF_COUNT개, HWP $HWP_COUNT개"
echo ""

echo "📚 다음 단계:"
echo ""
echo "1. 문서 추가:"
echo "   cp your-document.pdf ./data/"
echo ""
echo "2. 서버 시작:"
echo "   ./run.sh"
echo ""
echo "3. HWP 서비스 시작 (선택사항):"
echo "   cd document-service && mvn spring-boot:run"
echo ""
echo "4. 브라우저에서 접속:"
echo "   http://localhost:8000"
echo ""

echo "🔧 유용한 명령어:"
echo "  • Redis 중지:      docker-compose down"
echo "  • Redis 재시작:    docker-compose restart"
echo "  • Redis 로그:      docker-compose logs -f"
echo "  • 서버 중지:       ./stop.sh"
echo "  • 설정 파일:       .env"
echo ""

echo "📖 문서:"
echo "  • README.md:       프로젝트 개요"
echo "  • claudedocs/:     상세 기술 문서"
echo ""

log_success "설치가 완료되었습니다. 즐거운 개발 되세요! 🎉"
echo ""
