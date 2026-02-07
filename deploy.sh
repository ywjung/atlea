#!/bin/bash

# ==============================================================================
# ATLEA 챗봇 시스템 - 간편 배포 스크립트
# ==============================================================================
# 사용법:
#   ./deploy.sh dev          - 로컬 개발 (Redis + 부가서비스만, 앱은 직접 실행)
#   ./deploy.sh docker       - Docker 올인원 배포
#   ./deploy.sh production   - 프로덕션 배포 (SSL + Nginx)
#   ./deploy.sh gpu          - GPU 서버 배포
#   ./deploy.sh status       - 서비스 상태 확인
#   ./deploy.sh stop         - 서비스 중지
#   ./deploy.sh logs         - 로그 보기
# ==============================================================================

set -e

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 현재 사용 중인 compose 파일 감지
detect_compose_file() {
    if docker-compose -f docker-compose.production.yml ps 2>/dev/null | grep -q "Up"; then
        echo "docker-compose.production.yml"
    elif docker-compose -f docker-compose.gpu.yml ps 2>/dev/null | grep -q "Up"; then
        echo "docker-compose.gpu.yml"
    elif docker-compose -f docker-compose.full.yml ps 2>/dev/null | grep -q "Up"; then
        echo "docker-compose.full.yml"
    elif docker-compose -f docker-compose.yml ps 2>/dev/null | grep -q "Up"; then
        echo "docker-compose.yml"
    else
        echo ""
    fi
}

# .env 파일 확인 및 생성
ensure_env() {
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}[경고]${NC} .env 파일이 없습니다. .env.example에서 생성합니다."
        cp .env.example .env

        # JWT 시크릿 키 자동 생성
        if command -v python3 &> /dev/null; then
            JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
            if [ "$(uname)" = "Darwin" ]; then
                sed -i '' "s/CHANGE_THIS_TO_A_STRONG_RANDOM_SECRET_KEY_AT_LEAST_32_CHARS/$JWT_SECRET/" .env
            else
                sed -i "s/CHANGE_THIS_TO_A_STRONG_RANDOM_SECRET_KEY_AT_LEAST_32_CHARS/$JWT_SECRET/" .env
            fi
            echo -e "${GREEN}  ✅ JWT 시크릿 키 자동 생성 완료${NC}"
        else
            echo -e "${YELLOW}  ⚠️  python3이 없어 JWT 키를 자동 생성할 수 없습니다.${NC}"
            echo -e "${YELLOW}     .env 파일에서 JWT_SECRET_KEY를 수동으로 변경하세요.${NC}"
        fi
    fi
}

# 디렉토리 확인
ensure_dirs() {
    mkdir -p data model logs
}

print_header() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           ATLEA 챗봇 배포 스크립트             ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════╝${NC}"
    echo ""
}

print_urls() {
    local PORT=${PORT:-8000}
    if [ -f ".env" ]; then
        PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d= -f2 || echo "8000")
        PORT=${PORT:-8000}
    fi

    echo ""
    echo -e "${CYAN}  접속 정보:${NC}"
    echo -e "    웹 UI:       http://localhost:$PORT"
    echo -e "    소개 페이지:  http://localhost:$PORT/landing.html"
    echo -e "    API 문서:    http://localhost:$PORT/docs"
    echo -e "    상태 확인:   http://localhost:$PORT/health"
    echo -e "    RedisInsight: http://localhost:8001"
    echo ""
}

# === 명령어 처리 ===

case "${1:-help}" in

    dev)
        print_header
        echo -e "${BLUE}[모드]${NC} 로컬 개발 환경"
        ensure_env
        ensure_dirs

        echo -e "${CYAN}[1/2]${NC} 부가 서비스 시작 (Redis, Document Service, ClamAV)..."
        docker-compose up -d

        echo -e "${CYAN}[2/2]${NC} 서비스 시작 대기 중..."
        sleep 5

        echo ""
        echo -e "${GREEN}  ✅ 부가 서비스가 시작되었습니다${NC}"
        echo ""
        echo -e "${CYAN}  앱 서버 실행:${NC}"
        echo -e "    ./run.sh          (포그라운드)"
        echo -e "    ./run.sh -b       (백그라운드)"
        print_urls
        ;;

    docker)
        print_header
        echo -e "${BLUE}[모드]${NC} Docker 올인원 배포"
        ensure_env
        ensure_dirs

        echo -e "${CYAN}[1/3]${NC} Docker 이미지 빌드 중..."
        docker-compose -f docker-compose.full.yml build

        echo -e "${CYAN}[2/3]${NC} 서비스 시작 중..."
        docker-compose -f docker-compose.full.yml up -d

        echo -e "${CYAN}[3/3]${NC} 서비스 시작 대기 중..."
        sleep 10

        echo ""
        echo -e "${GREEN}  ✅ 전체 서비스가 시작되었습니다${NC}"
        docker-compose -f docker-compose.full.yml ps
        print_urls
        ;;

    production|prod)
        print_header
        echo -e "${BLUE}[모드]${NC} 프로덕션 배포 (SSL + Nginx)"
        ensure_env
        ensure_dirs

        # SSL 인증서 확인
        if [ ! -f "nginx/ssl/fullchain.pem" ] || [ ! -f "nginx/ssl/privkey.pem" ]; then
            echo -e "${RED}[오류]${NC} SSL 인증서가 없습니다."
            echo ""
            echo "  다음 파일이 필요합니다:"
            echo "    nginx/ssl/fullchain.pem"
            echo "    nginx/ssl/privkey.pem"
            echo ""
            echo "  Let's Encrypt 인증서 발급:"
            echo "    sudo certbot certonly --standalone -d your-domain.com"
            echo "    cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/"
            echo "    cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/"
            echo ""
            echo "  테스트용 자체 서명 인증서:"
            echo "    mkdir -p nginx/ssl"
            echo "    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \\"
            echo "      -keyout nginx/ssl/privkey.pem -out nginx/ssl/fullchain.pem \\"
            echo "      -subj '/CN=localhost'"
            exit 1
        fi

        echo -e "${CYAN}[1/3]${NC} Docker 이미지 빌드 중..."
        docker-compose -f docker-compose.production.yml build

        echo -e "${CYAN}[2/3]${NC} 서비스 시작 중..."
        docker-compose -f docker-compose.production.yml up -d

        echo -e "${CYAN}[3/3]${NC} 서비스 시작 대기 중..."
        sleep 15

        echo ""
        echo -e "${GREEN}  ✅ 프로덕션 서비스가 시작되었습니다${NC}"
        docker-compose -f docker-compose.production.yml ps
        echo ""
        echo -e "${CYAN}  HTTPS 접속: https://your-domain.com${NC}"
        echo ""
        ;;

    gpu)
        print_header
        echo -e "${BLUE}[모드]${NC} GPU 서버 배포 (NVIDIA)"
        ensure_env
        ensure_dirs

        # NVIDIA 드라이버 확인
        if ! command -v nvidia-smi &> /dev/null; then
            echo -e "${RED}[오류]${NC} NVIDIA 드라이버가 설치되어 있지 않습니다."
            echo "  nvidia-smi 명령이 실행되어야 합니다."
            exit 1
        fi

        echo -e "${CYAN}[1/3]${NC} Docker 이미지 빌드 중 (GPU 버전)..."
        docker-compose -f docker-compose.gpu.yml build

        echo -e "${CYAN}[2/3]${NC} 서비스 시작 중..."
        docker-compose -f docker-compose.gpu.yml up -d

        echo -e "${CYAN}[3/3]${NC} 서비스 시작 대기 중..."
        sleep 15

        echo ""
        echo -e "${GREEN}  ✅ GPU 서비스가 시작되었습니다${NC}"
        docker-compose -f docker-compose.gpu.yml ps
        print_urls
        ;;

    status)
        print_header
        COMPOSE_FILE=$(detect_compose_file)
        if [ -n "$COMPOSE_FILE" ]; then
            echo -e "${CYAN}  활성 배포:${NC} $COMPOSE_FILE"
            echo ""
            docker-compose -f "$COMPOSE_FILE" ps
            echo ""
            echo -e "${CYAN}  리소스 사용량:${NC}"
            docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | head -10
        else
            echo -e "${YELLOW}  실행 중인 서비스가 없습니다${NC}"

            # run.sh로 실행 중인지 확인
            if [ -f ".server.pid" ]; then
                PID=$(cat .server.pid)
                if ps -p "$PID" > /dev/null 2>&1; then
                    echo -e "${GREEN}  ✅ 로컬 서버 실행 중 (PID: $PID)${NC}"
                fi
            fi
        fi
        ;;

    stop)
        print_header
        COMPOSE_FILE=$(detect_compose_file)
        if [ -n "$COMPOSE_FILE" ]; then
            echo -e "${CYAN}[정보]${NC} $COMPOSE_FILE 서비스 중지 중..."
            docker-compose -f "$COMPOSE_FILE" down
            echo -e "${GREEN}  ✅ 서비스가 중지되었습니다${NC}"
        else
            echo -e "${YELLOW}  실행 중인 Docker 서비스가 없습니다${NC}"
        fi

        # run.sh로 실행 중인 경우도 중지
        if [ -f ".server.pid" ]; then
            PID=$(cat .server.pid)
            if ps -p "$PID" > /dev/null 2>&1; then
                echo -e "${CYAN}[정보]${NC} 로컬 서버 중지 중 (PID: $PID)..."
                kill "$PID"
                rm -f .server.pid
                echo -e "${GREEN}  ✅ 로컬 서버가 중지되었습니다${NC}"
            fi
        fi
        ;;

    logs)
        COMPOSE_FILE=$(detect_compose_file)
        if [ -n "$COMPOSE_FILE" ]; then
            SERVICE="${2:-}"
            if [ -n "$SERVICE" ]; then
                docker-compose -f "$COMPOSE_FILE" logs -f --tail=100 "$SERVICE"
            else
                docker-compose -f "$COMPOSE_FILE" logs -f --tail=100
            fi
        else
            echo -e "${YELLOW}  실행 중인 Docker 서비스가 없습니다${NC}"
            if [ -f "logs/server.log" ]; then
                echo -e "${CYAN}  로컬 서버 로그:${NC}"
                tail -f logs/server.log
            fi
        fi
        ;;

    help|--help|-h|*)
        print_header
        echo "사용법: ./deploy.sh <명령>"
        echo ""
        echo -e "${CYAN}배포 명령:${NC}"
        echo "  dev          로컬 개발 환경 (부가서비스만, 앱은 ./run.sh로)"
        echo "  docker       Docker 올인원 배포"
        echo "  production   프로덕션 배포 (SSL + Nginx)"
        echo "  gpu          GPU 서버 배포 (NVIDIA)"
        echo ""
        echo -e "${CYAN}관리 명령:${NC}"
        echo "  status       서비스 상태 확인"
        echo "  stop         서비스 중지"
        echo "  logs         로그 보기 (logs [서비스명])"
        echo ""
        echo -e "${CYAN}예시:${NC}"
        echo "  ./deploy.sh dev            # 개발 환경 시작"
        echo "  ./deploy.sh docker         # Docker로 전체 실행"
        echo "  ./deploy.sh logs chatbot-app  # 챗봇 앱 로그"
        echo "  ./deploy.sh stop           # 전체 중지"
        echo ""
        echo -e "${CYAN}백업/복원:${NC}"
        echo "  ./scripts/backup.sh        # 데이터 백업"
        echo "  ./scripts/restore.sh <파일>  # 데이터 복원"
        echo ""
        echo -e "${CYAN}자세한 안내:${NC} docs/DEPLOYMENT_GUIDE.md"
        echo ""
        ;;
esac
