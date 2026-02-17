#!/bin/bash
# Rate Limit 초기화 스크립트 (PostgreSQL)
#
# 사용법:
#   ./scripts/clear_rate_limit.sh            # 모든 rate limit 데이터 삭제
#   ./scripts/clear_rate_limit.sh <IP>       # 특정 IP의 rate limit만 삭제

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# .env에서 DATABASE_URL 읽기
if [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env"
fi

# PostgreSQL 컨테이너 감지
PG_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E "postgres" | head -1)

if [ -z "$PG_CONTAINER" ]; then
    echo "❌ PostgreSQL 컨테이너를 찾을 수 없습니다"
    echo "💡 docker-compose up -d 로 서비스를 시작하세요"
    exit 1
fi

if [ -z "$1" ]; then
    echo "🗑️  모든 rate limit 데이터 삭제 중..."
    COUNT=$(docker exec "$PG_CONTAINER" psql -U chatbot_user -d chatbot -t -c \
        "DELETE FROM ip_rate_limits; SELECT COUNT(*) FROM ip_rate_limits;" 2>/dev/null | tr -d ' ')
    echo "✅ rate limit 데이터가 초기화되었습니다."
else
    IP=$1
    echo "🗑️  IP $IP 의 rate limit 데이터 삭제 중..."
    docker exec "$PG_CONTAINER" psql -U chatbot_user -d chatbot -c \
        "DELETE FROM ip_rate_limits WHERE ip_address = '$IP';" 2>/dev/null
    echo "✅ IP $IP 의 rate limit 데이터를 삭제했습니다."
fi
