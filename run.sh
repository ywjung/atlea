#!/bin/bash

# PDF RAG Chatbot Run Script

set -e

echo "🚀 PDF RAG 챗봇 시작..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ 가상환경이 없습니다. 먼저 ./setup.sh 를 실행하세요."
    exit 1
fi

# Activate virtual environment
echo "🔧 가상환경 활성화..."
source venv/bin/activate

# Check if Redis is running
echo "🐳 Redis 상태 확인..."
if ! docker-compose ps | grep -q "redis.*Up"; then
    echo "📦 Redis 시작 중..."
    docker-compose up -d
    echo "⏳ Redis 준비 대기..."
    sleep 5
fi

if docker-compose ps | grep -q "redis.*Up"; then
    echo "✅ Redis가 실행 중입니다"
else
    echo "❌ Redis를 시작할 수 없습니다"
    exit 1
fi

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Get host and port from environment or use defaults
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

echo ""
echo "✨ 서버 시작 중..."
echo "📍 주소: http://localhost:$PORT"
echo "📊 RedisInsight: http://localhost:8001"
echo ""
echo "💡 Ctrl+C를 눌러 서버를 종료할 수 있습니다"
echo ""

# Run the application
python -m uvicorn src.web_server:app --host $HOST --port $PORT --reload
