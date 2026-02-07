#!/bin/bash

# ==============================================================================
# ATLEA 챗봇 시스템 - 데이터 복원 스크립트
# ==============================================================================
# 사용법: ./scripts/restore.sh <백업파일.tar.gz>
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

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo -e "${RED}[오류]${NC} 백업 파일을 지정해주세요."
    echo ""
    echo "사용법: ./scripts/restore.sh <백업파일.tar.gz>"
    echo ""

    # 사용 가능한 백업 파일 표시
    if [ -d "$PROJECT_DIR/backups" ] && [ "$(ls -A $PROJECT_DIR/backups/*.tar.gz 2>/dev/null)" ]; then
        echo "사용 가능한 백업 파일:"
        ls -lhtr "$PROJECT_DIR/backups"/*.tar.gz 2>/dev/null | awk '{print "  " $NF " (" $5 ", " $6 " " $7 " " $8 ")"}'
    fi
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}[오류]${NC} 백업 파일을 찾을 수 없습니다: $BACKUP_FILE"
    exit 1
fi

echo -e "${CYAN}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        ATLEA 챗봇 시스템 복원 스크립트         ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}[경고]${NC} 이 작업은 현재 데이터를 백업 데이터로 덮어씁니다."
echo -e "${YELLOW}       현재 데이터를 먼저 백업하는 것을 권장합니다.${NC}"
echo ""
read -p "계속 진행하시겠습니까? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}[취소]${NC} 복원이 취소되었습니다."
    exit 0
fi

# 임시 디렉토리 생성
RESTORE_DIR=$(mktemp -d)
echo ""
echo -e "${CYAN}[1/5]${NC} 백업 파일 압축 해제 중..."
tar xzf "$BACKUP_FILE" -C "$RESTORE_DIR"

# 압축 해제된 디렉토리 찾기
EXTRACTED_DIR=$(find "$RESTORE_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)

if [ -z "$EXTRACTED_DIR" ]; then
    echo -e "${RED}[오류]${NC} 백업 파일 구조가 올바르지 않습니다."
    rm -rf "$RESTORE_DIR"
    exit 1
fi

# Docker Compose 파일 결정
COMPOSE_FILE="docker-compose.full.yml"
if [ ! -f "$PROJECT_DIR/$COMPOSE_FILE" ]; then
    COMPOSE_FILE="docker-compose.yml"
fi

# 2. 서비스 중지
echo -e "${CYAN}[2/5]${NC} 서비스 중지 중..."
cd "$PROJECT_DIR"
docker-compose -f "$COMPOSE_FILE" stop 2>/dev/null || true

# 3. 문서 데이터 복원
echo -e "${CYAN}[3/5]${NC} 문서 데이터 복원 중..."
if [ -d "$EXTRACTED_DIR/data" ]; then
    mkdir -p "$PROJECT_DIR/data"
    cp -r "$EXTRACTED_DIR/data/"* "$PROJECT_DIR/data/" 2>/dev/null || true
    echo -e "${GREEN}  ✅ 문서 데이터 복원 완료${NC}"
else
    echo -e "${YELLOW}  ⚠️  백업에 문서 데이터가 없습니다${NC}"
fi

# 4. 환경 설정 복원
echo -e "${CYAN}[4/5]${NC} 환경 설정 복원 중..."
if [ -f "$EXTRACTED_DIR/.env" ]; then
    cp "$EXTRACTED_DIR/.env" "$PROJECT_DIR/.env"
    echo -e "${GREEN}  ✅ .env 파일 복원 완료${NC}"
else
    echo -e "${YELLOW}  ⚠️  백업에 .env 파일이 없습니다${NC}"
fi

# 5. Redis 데이터 복원 및 서비스 재시작
echo -e "${CYAN}[5/5]${NC} Redis 데이터 복원 및 서비스 시작 중..."

# Redis 먼저 시작
docker-compose -f "$COMPOSE_FILE" up -d redis 2>/dev/null || true
sleep 5

if [ -f "$EXTRACTED_DIR/redis_dump.rdb" ]; then
    REDIS_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E "redis" | grep -v "insight" | head -1)
    if [ -n "$REDIS_CONTAINER" ]; then
        docker cp "$EXTRACTED_DIR/redis_dump.rdb" "$REDIS_CONTAINER":/data/dump.rdb
        docker-compose -f "$COMPOSE_FILE" restart redis
        sleep 3
        echo -e "${GREEN}  ✅ Redis 데이터 복원 완료${NC}"
    else
        echo -e "${YELLOW}  ⚠️  Redis 컨테이너를 찾을 수 없습니다${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠️  백업에 Redis 데이터가 없습니다${NC}"
fi

# 전체 서비스 시작
docker-compose -f "$COMPOSE_FILE" up -d

# 정리
rm -rf "$RESTORE_DIR"

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              복원 완료!                       ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}  복원 원본:${NC} $BACKUP_FILE"
echo -e "${CYAN}  완료 시간:${NC} $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo -e "${CYAN}  서비스 상태 확인:${NC} docker-compose -f $COMPOSE_FILE ps"
echo ""
