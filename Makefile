# ==============================================================================
# ATLEA 챗봇 시스템 - Makefile
# ==============================================================================
# 사용법: make [타겟]
# 전체 명령 목록: make help
# ==============================================================================

.DEFAULT_GOAL := help

# 색상 코드
CYAN   := \033[0;36m
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RESET  := \033[0m

# 설정
COMPOSE_FULL := docker-compose -f docker-compose.full.yml
COMPOSE_PROD := docker-compose -f docker-compose.production.yml
COMPOSE_GPU  := docker-compose -f docker-compose.gpu.yml
COMPOSE_SRXNG := docker-compose -f docker-compose.searxng.yml

# .env 에서 포트 로드 (기본값 8000)
-include .env
APP_PORT ?= 8000

# ==============================================================================
# 모든 .PHONY 선언
# ==============================================================================
.PHONY: help setup dev run run-bg run-stop run-status \
        up production gpu down restart \
        status logs logs-app health \
        backup restore build clean \
        test test-unit test-e2e lint \
        searxng-up searxng-down \
        install dist

# ==============================================================================
# 도움말
# ==============================================================================

help: ## 사용 가능한 명령 목록 표시
	@echo ""
	@echo "$(CYAN)ATLEA 챗봇 시스템 - 명령어$(RESET)"
	@echo "$(CYAN)======================================$(RESET)"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(firstword $(MAKEFILE_LIST)) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ==============================================================================
# 개발
# ==============================================================================

setup: ## 초기 환경 설정
	@./setup.sh

dev: ## 개발 환경 시작 (Redis + 부가서비스)
	@./deploy.sh dev

run: ## 로컬 앱 서버 포그라운드 실행
	@./run.sh

run-bg: ## 로컬 앱 서버 백그라운드 실행
	@./run.sh -b

run-stop: ## 로컬 앱 서버 중지
	@./run.sh stop

run-status: ## 로컬 앱 서버 상태 확인
	@./run.sh status

# ==============================================================================
# Docker 배포
# ==============================================================================

up: ## Docker 올인원 시작
	@./deploy.sh docker

production: ## 프로덕션 배포 (SSL + Nginx)
	@./deploy.sh production

gpu: ## GPU 서버 배포
	@./deploy.sh gpu

down: ## 서비스 중지
	@./deploy.sh stop

restart: down up ## 서비스 재시작 (중지 후 시작)

# ==============================================================================
# 모니터링
# ==============================================================================

status: ## 서비스 상태 확인
	@./deploy.sh status

logs: ## 전체 로그 보기
	@./deploy.sh logs

logs-app: ## 앱 로그만 보기
	@./deploy.sh logs chatbot-app

health: ## 헬스체크 엔드포인트 호출
	@curl -sf http://localhost:$(APP_PORT)/health | python3 -m json.tool 2>/dev/null || \
		curl -sf http://localhost:$(APP_PORT)/health || \
		echo "$(YELLOW)서비스가 응답하지 않습니다 (port $(APP_PORT))$(RESET)"

# ==============================================================================
# 유지보수
# ==============================================================================

backup: ## 데이터 백업
	@./scripts/backup.sh

restore: ## 데이터 복원 (사용법: make restore BACKUP=파일경로)
	@if [ -z "$(BACKUP)" ]; then \
		echo "$(YELLOW)사용법: make restore BACKUP=백업파일경로$(RESET)"; \
		exit 1; \
	fi
	@./scripts/restore.sh $(BACKUP)

build: ## Docker 이미지 빌드
	$(COMPOSE_FULL) build

clean: ## Docker 볼륨/이미지 정리
	$(COMPOSE_FULL) down -v --rmi local 2>/dev/null || true
	$(COMPOSE_PROD) down -v --rmi local 2>/dev/null || true
	$(COMPOSE_GPU) down -v --rmi local 2>/dev/null || true

# ==============================================================================
# 테스트
# ==============================================================================

test: ## 전체 테스트 실행
	pytest

test-unit: ## 단위 테스트만 실행
	pytest tests/unit/

test-e2e: ## E2E 테스트 실행
	npx playwright test

lint: ## 코드 린트
	ruff check src/

# ==============================================================================
# SearXNG (웹 검색)
# ==============================================================================

searxng-up: ## SearXNG + Crawl4AI 시작
	$(COMPOSE_SRXNG) up -d

searxng-down: ## SearXNG 중지
	$(COMPOSE_SRXNG) down

# ==============================================================================
# 패키지
# ==============================================================================

install: ## pip editable 설치
	pip install -e .

dist: ## 배포용 패키지 빌드
	python -m build
