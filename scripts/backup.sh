#!/bin/bash

# ==============================================================================
# ATLEA 챗봇 시스템 - 데이터 백업 스크립트
# ==============================================================================
# 사용법: ./scripts/backup.sh [백업_디렉토리]
# 기본 백업 위치: ./backups/
# ==============================================================================

set -e

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 프로젝트 루트 디렉토리
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 백업 설정
BACKUP_BASE="${1:-$PROJECT_DIR/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE/$TIMESTAMP"
BACKUP_ARCHIVE="$BACKUP_BASE/backup_$TIMESTAMP.tar.gz"

echo -e "${CYAN}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        ATLEA 챗봇 시스템 백업 스크립트         ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════╝${NC}"
echo ""

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"
echo -e "${CYAN}[정보]${NC} 백업 디렉토리: $BACKUP_DIR"

# 1. Redis 데이터 백업
echo -e "${CYAN}[1/4]${NC} Redis 데이터 백업 중..."

# Redis 컨테이너 이름 자동 감지
REDIS_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E "redis" | grep -v "insight" | head -1)

if [ -n "$REDIS_CONTAINER" ]; then
    docker exec "$REDIS_CONTAINER" redis-cli BGSAVE > /dev/null 2>&1
    sleep 3
    if docker cp "$REDIS_CONTAINER":/data/dump.rdb "$BACKUP_DIR/redis_dump.rdb" 2>/dev/null; then
        echo -e "${GREEN}  ✅ Redis 데이터 백업 완료${NC}"
    else
        echo -e "${YELLOW}  ⚠️  Redis dump.rdb 복사 실패 (데이터가 없을 수 있음)${NC}"
    fi

    # AOF 파일도 백업 (존재하는 경우)
    docker cp "$REDIS_CONTAINER":/data/appendonly.aof "$BACKUP_DIR/appendonly.aof" 2>/dev/null || true
else
    echo -e "${YELLOW}  ⚠️  Redis 컨테이너를 찾을 수 없습니다${NC}"
fi

# 2. 문서 데이터 백업
echo -e "${CYAN}[2/4]${NC} 문서 데이터 백업 중..."

if [ -d "$PROJECT_DIR/data" ] && [ "$(ls -A $PROJECT_DIR/data 2>/dev/null)" ]; then
    cp -r "$PROJECT_DIR/data" "$BACKUP_DIR/data"
    FILE_COUNT=$(find "$BACKUP_DIR/data" -type f | wc -l | tr -d ' ')
    echo -e "${GREEN}  ✅ 문서 데이터 백업 완료 ($FILE_COUNT 파일)${NC}"
else
    mkdir -p "$BACKUP_DIR/data"
    echo -e "${YELLOW}  ⚠️  data 디렉토리가 비어있습니다${NC}"
fi

# 3. 환경 설정 백업
echo -e "${CYAN}[3/4]${NC} 환경 설정 백업 중..."

if [ -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env" "$BACKUP_DIR/.env"
    echo -e "${GREEN}  ✅ .env 파일 백업 완료${NC}"
else
    echo -e "${YELLOW}  ⚠️  .env 파일이 없습니다${NC}"
fi

# 4. 압축
echo -e "${CYAN}[4/4]${NC} 백업 파일 압축 중..."

tar czf "$BACKUP_ARCHIVE" -C "$BACKUP_BASE" "$TIMESTAMP"
rm -rf "$BACKUP_DIR"

# 백업 크기 계산
if [ "$(uname)" = "Darwin" ]; then
    BACKUP_SIZE=$(ls -lh "$BACKUP_ARCHIVE" | awk '{print $5}')
else
    BACKUP_SIZE=$(du -h "$BACKUP_ARCHIVE" | cut -f1)
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              백업 완료!                       ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}  백업 파일:${NC} $BACKUP_ARCHIVE"
echo -e "${CYAN}  파일 크기:${NC} $BACKUP_SIZE"
echo -e "${CYAN}  생성 시간:${NC} $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo -e "${CYAN}  복원 명령:${NC} ./scripts/restore.sh $BACKUP_ARCHIVE"
echo ""
