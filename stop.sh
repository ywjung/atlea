#!/bin/bash

echo "🛑 PDF RAG 챗봇 중지 중..."

# Find and kill the server process
PID=$(ps aux | grep "[u]vicorn src.web_server:app" | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "❌ 실행 중인 서버를 찾을 수 없습니다."
    exit 0
fi

echo "📍 서버 프로세스 발견: PID $PID"
echo "⏳ 서버 종료 중..."

# Send SIGTERM for graceful shutdown
kill $PID

# Wait up to 5 seconds for graceful shutdown
for i in {1..5}; do
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "✅ 서버가 정상적으로 종료되었습니다."
        exit 0
    fi
    sleep 1
done

# If still running, force kill
if ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  강제 종료 중..."
    kill -9 $PID
    sleep 1

    if ps -p $PID > /dev/null 2>&1; then
        echo "❌ 서버 종료 실패. 수동으로 종료해주세요: kill -9 $PID"
        exit 1
    else
        echo "✅ 서버가 강제 종료되었습니다."
    fi
fi
