#!/bin/bash
# Development Server Startup Script
# 개발 서버 시작 스크립트

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   개발 서버 시작${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ 가상 환경을 찾을 수 없습니다.${NC}"
    echo -e "${YELLOW}💡 가상 환경을 생성하세요:${NC}"
    echo -e "   python3 -m venv venv"
    echo -e "   source venv/bin/activate"
    echo -e "   pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo -e "${BLUE}🔧 가상 환경 활성화...${NC}"
source venv/bin/activate

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env 파일을 찾을 수 없습니다.${NC}"
    echo -e "${YELLOW}💡 .env.example을 복사하여 .env 파일을 만들어주세요:${NC}"
    echo -e "   cp .env.example .env"
    exit 1
fi

# Check if Redis is running
echo -e "${BLUE}🔍 Redis 연결 확인...${NC}"
REDIS_HOST=${REDIS_HOST:-localhost}
REDIS_PORT=${REDIS_PORT:-6379}

if ! nc -z "$REDIS_HOST" "$REDIS_PORT" 2>/dev/null; then
    echo -e "${RED}❌ Redis 서버에 연결할 수 없습니다 ($REDIS_HOST:$REDIS_PORT)${NC}"
    echo -e "${YELLOW}💡 Redis를 먼저 시작해주세요:${NC}"
    echo -e "   redis-server"
    exit 1
fi
echo -e "${GREEN}✅ Redis 연결 성공${NC}"
echo ""

# Load environment variables
source .env

# Set development defaults
export ENV=development
export DEBUG=true
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
LOG_LEVEL=${LOG_LEVEL:-debug}

echo -e "${BLUE}🚀 서버 설정:${NC}"
echo -e "   Environment: ${GREEN}development${NC}"
echo -e "   Host: ${HOST}"
echo -e "   Port: ${PORT}"
echo -e "   Debug: ${DEBUG}"
echo -e "   Log Level: ${LOG_LEVEL}"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   서버 시작 중...${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Start server with reload
uvicorn src.web_server:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    --log-level "$LOG_LEVEL"

# This will only execute if uvicorn exits
echo ""
echo -e "${YELLOW}⚠️  서버가 종료되었습니다${NC}"
