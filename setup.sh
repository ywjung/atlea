#!/bin/bash

# PDF RAG Chatbot Setup Script

set -e

echo "🚀 PDF RAG 챗봇 설치 시작..."

# Check Python version
echo "📌 Python 버전 확인..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3가 설치되어 있지 않습니다."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python $PYTHON_VERSION 발견"

# Check Docker
echo "📌 Docker 확인..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker가 설치되어 있지 않습니다."
    echo "   Docker Desktop을 설치해주세요: https://www.docker.com/products/docker-desktop"
    exit 1
fi
echo "✅ Docker 발견"

# Check Docker Compose
echo "📌 Docker Compose 확인..."
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose가 설치되어 있지 않습니다."
    exit 1
fi
echo "✅ Docker Compose 발견"

# Create virtual environment
echo "📦 Python 가상환경 생성..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ 가상환경 생성 완료"
else
    echo "✅ 가상환경이 이미 존재합니다"
fi

# Activate virtual environment
echo "🔧 가상환경 활성화..."
source venv/bin/activate

# Upgrade pip
echo "📦 pip 업그레이드..."
pip install --upgrade pip

# Install requirements
echo "📦 패키지 설치 중..."
pip install -r requirements.txt

# Create .env file if not exists
if [ ! -f ".env" ]; then
    echo "📝 .env 파일 생성..."
    cp .env.example .env
    echo "✅ .env 파일이 생성되었습니다. 필요시 수정해주세요."
fi

# Create necessary directories
echo "📁 필수 디렉토리 확인..."
mkdir -p data model

# Start Redis
echo "🐳 Redis 컨테이너 시작..."
docker-compose up -d

# Wait for Redis
echo "⏳ Redis 준비 대기..."
sleep 5

# Check Redis
if docker-compose ps | grep -q "redis.*Up"; then
    echo "✅ Redis가 정상적으로 실행 중입니다"
else
    echo "❌ Redis 시작 실패"
    exit 1
fi

echo ""
echo "✨ 설치 완료!"
echo ""
echo "📚 다음 단계:"
echo "   1. PDF 파일을 ./data 디렉토리에 넣으세요"
echo "   2. ./run.sh 를 실행하여 서버를 시작하세요"
echo "   3. 브라우저에서 http://localhost:8000 을 여세요"
echo ""
echo "🔧 추가 명령어:"
echo "   - Redis 중지: docker-compose down"
echo "   - Redis 재시작: docker-compose restart"
echo "   - 로그 확인: docker-compose logs -f"
echo ""
