#!/bin/bash
# Production Server Startup Script
# 프로덕션 서버 시작 스크립트

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   프로덕션 서버 시작${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env 파일을 찾을 수 없습니다.${NC}"
    echo -e "${YELLOW}💡 .env.production.example을 복사하여 .env 파일을 만들어주세요:${NC}"
    echo -e "   cp .env.production.example .env"
    echo -e "   vi .env  # 설정 값 수정"
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

# Check Python version
echo -e "${BLUE}🔍 Python 버전 확인...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✅ Python $PYTHON_VERSION${NC}"
echo ""

# Set production environment
export ENV=production
export DEBUG=false

# Get configuration from .env
source .env

# Set defaults if not specified
WORKERS=${WORKERS:-4}
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
LOG_LEVEL=${LOG_LEVEL:-info}

echo -e "${BLUE}🚀 서버 설정:${NC}"
echo -e "   Environment: ${GREEN}production${NC}"
echo -e "   Host: ${HOST}"
echo -e "   Port: ${PORT}"
echo -e "   Workers: ${WORKERS}"
echo -e "   Log Level: ${LOG_LEVEL}"
echo -e "   CORS Origins: ${CORS_ORIGINS}"
echo -e "   Rate Limit: ${RATE_LIMIT_PER_MINUTE:-60}/min"
echo ""

# Check if SECRET_KEY is set
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "your-secret-key-here-min-32-chars" ]; then
    echo -e "${RED}❌ SECRET_KEY가 설정되지 않았습니다!${NC}"
    echo -e "${YELLOW}💡 .env 파일에서 SECRET_KEY를 설정해주세요${NC}"
    exit 1
fi

# Create log directory if specified
if [ -n "$LOG_FILE" ]; then
    LOG_DIR=$(dirname "$LOG_FILE")
    if [ ! -d "$LOG_DIR" ]; then
        echo -e "${BLUE}📁 로그 디렉토리 생성: $LOG_DIR${NC}"
        mkdir -p "$LOG_DIR"
    fi
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   서버 시작 중...${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Start server with uvicorn
uvicorn src.web_server:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL" \
    --timeout-keep-alive "${KEEPALIVE_TIMEOUT:-5}" \
    --limit-concurrency 1000 \
    --limit-max-requests 10000 \
    --no-access-log \
    --no-server-header \
    --no-date-header

# This will only execute if uvicorn exits
echo ""
echo -e "${YELLOW}⚠️  서버가 종료되었습니다${NC}"
