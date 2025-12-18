#!/bin/bash

# PDF RAG Chatbot Run Script
# Usage:
#   ./run.sh              - Run in foreground (default)
#   ./run.sh --background - Run in background
#   ./run.sh -b           - Run in background (short form)
#   ./run.sh stop         - Stop background process
#   ./run.sh status       - Check if running

set -e

PID_FILE=".server.pid"
LOG_FILE="server.log"

# Function to check if server is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

# Function to stop server
stop_server() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "🛑 서버 종료 중... (PID: $PID)"
        kill "$PID"
        rm -f "$PID_FILE"
        echo "✅ 서버가 종료되었습니다"
    else
        echo "ℹ️  실행 중인 서버가 없습니다"
    fi
}

# Function to show status
show_status() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "✅ 서버가 실행 중입니다 (PID: $PID)"
        echo "📍 주소: http://localhost:${PORT:-8000}"
        echo "📊 RedisInsight: http://localhost:8001"
        echo "📝 로그: tail -f $LOG_FILE"
    else
        echo "❌ 서버가 실행 중이지 않습니다"
    fi
}

# Parse command line arguments
BACKGROUND=false
COMMAND=""

if [ $# -gt 0 ]; then
    case "$1" in
        --background|-b)
            BACKGROUND=true
            ;;
        stop)
            COMMAND="stop"
            ;;
        status)
            COMMAND="status"
            ;;
        *)
            echo "❌ 알 수 없는 옵션: $1"
            echo "사용법: $0 [--background|-b|stop|status]"
            exit 1
            ;;
    esac
fi

# Handle stop command
if [ "$COMMAND" = "stop" ]; then
    stop_server
    exit 0
fi

# Handle status command
if [ "$COMMAND" = "status" ]; then
    show_status
    exit 0
fi

# Check if already running
if is_running; then
    echo "⚠️  서버가 이미 실행 중입니다"
    show_status
    exit 1
fi

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

# Run in background or foreground
if [ "$BACKGROUND" = true ]; then
    echo "🌙 백그라운드 모드로 실행합니다"
    echo "📝 로그 파일: $LOG_FILE"
    echo "💡 서버 종료: ./run.sh stop"
    echo "💡 서버 상태: ./run.sh status"
    echo "💡 로그 확인: tail -f $LOG_FILE"
    echo ""

    # Run in background with nohup
    nohup python -m uvicorn src.web_server:app --host $HOST --port $PORT --reload > "$LOG_FILE" 2>&1 &

    # Save PID
    echo $! > "$PID_FILE"

    # Wait a bit and check if started successfully
    sleep 2
    if is_running; then
        echo "✅ 서버가 백그라운드에서 시작되었습니다 (PID: $(cat $PID_FILE))"
    else
        echo "❌ 서버 시작에 실패했습니다. 로그를 확인하세요: cat $LOG_FILE"
        exit 1
    fi
else
    echo "💡 Ctrl+C를 눌러 서버를 종료할 수 있습니다"
    echo ""

    # Run in foreground
    python -m uvicorn src.web_server:app --host $HOST --port $PORT --reload
fi
