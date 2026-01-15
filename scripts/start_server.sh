#!/bin/bash
# 서버 시작 스크립트 - 로그를 보존하면서 서버 시작

cd "$(dirname "$0")/.."

# 기존 서버 종료
echo "Stopping existing server..."
pkill -f "uvicorn src.web_server:app" || true
sleep 2

# 로그 파일 설정 (append 모드)
echo "Starting server..."
echo "================================================" >> server.log
echo "Server started at $(date)" >> server.log
echo "================================================" >> server.log

# 서버 시작 (로그 append 모드)
nohup venv/bin/uvicorn src.web_server:app --host 0.0.0.0 --port 8000 --reload >> server.log 2>&1 &

sleep 3

# 서버 상태 확인
if pgrep -f "uvicorn src.web_server:app" > /dev/null; then
    echo "✅ Server started successfully (PID: $(pgrep -f 'uvicorn src.web_server:app'))"
    echo "📋 Logs: tail -f server.log"
else
    echo "❌ Server failed to start"
    exit 1
fi
