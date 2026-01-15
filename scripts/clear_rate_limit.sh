#!/bin/bash
# Rate Limit 초기화 스크립트
#
# 사용법:
#   ./scripts/clear_rate_limit.sh            # 모든 rate limit 키 삭제
#   ./scripts/clear_rate_limit.sh <IP>       # 특정 IP의 rate limit만 삭제

REDIS_CONTAINER="chatbot_redis"

if [ -z "$1" ]; then
    echo "🗑️  모든 rate limit 키 삭제 중..."

    # 모든 rate_limit:* 키 조회
    KEYS=$(docker exec $REDIS_CONTAINER redis-cli KEYS "rate_limit:*")

    if [ -z "$KEYS" ]; then
        echo "✅ 삭제할 rate limit 키가 없습니다."
        exit 0
    fi

    # 각 키 삭제
    COUNT=0
    for KEY in $KEYS; do
        docker exec $REDIS_CONTAINER redis-cli DEL "$KEY" > /dev/null 2>&1
        ((COUNT++))
    done

    echo "✅ $COUNT 개의 rate limit 키를 삭제했습니다."
else
    IP=$1
    echo "🗑️  IP $IP 의 rate limit 키 삭제 중..."

    # 특정 IP의 키 조회
    PATTERN="rate_limit:${IP}:*"
    KEYS=$(docker exec $REDIS_CONTAINER redis-cli KEYS "$PATTERN")

    if [ -z "$KEYS" ]; then
        echo "✅ IP $IP 의 rate limit 키가 없습니다."
        exit 0
    fi

    # 각 키 삭제
    COUNT=0
    for KEY in $KEYS; do
        docker exec $REDIS_CONTAINER redis-cli DEL "$KEY" > /dev/null 2>&1
        ((COUNT++))
    done

    echo "✅ IP $IP 의 $COUNT 개 rate limit 키를 삭제했습니다."
fi
