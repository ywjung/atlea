#!/bin/bash

# JavaScript 모듈 마이그레이션 스크립트
# 기존 script.js를 백업하고 새로운 모듈 구조로 전환합니다.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
STATIC_DIR="$PROJECT_ROOT/static"
BACKUP_DIR="$PROJECT_ROOT/backup"

echo "🚀 JavaScript 모듈 마이그레이션 시작..."

# 1. 백업 디렉토리 생성
echo "📦 백업 디렉토리 생성..."
mkdir -p "$BACKUP_DIR"

# 2. 기존 script.js 백업
if [ -f "$STATIC_DIR/script.js" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/script.js.$TIMESTAMP"
    echo "💾 script.js 백업: $BACKUP_FILE"
    cp "$STATIC_DIR/script.js" "$BACKUP_FILE"
else
    echo "⚠️  script.js 파일을 찾을 수 없습니다."
fi

# 3. 모듈 디렉토리 확인
echo "📁 모듈 디렉토리 확인..."
if [ ! -d "$STATIC_DIR/js/core" ]; then
    echo "❌ $STATIC_DIR/js/core 디렉토리가 없습니다."
    exit 1
fi

if [ ! -d "$STATIC_DIR/js/features" ]; then
    echo "❌ $STATIC_DIR/js/features 디렉토리가 없습니다."
    exit 1
fi

# 4. 필수 모듈 파일 확인
echo "✅ 필수 모듈 파일 확인..."
REQUIRED_FILES=(
    "js/core/modal-manager.js"
    "js/core/utils.js"
    "js/features/chat.js"
    "js/features/documents.js"
    "js/features/versions.js"
    "js/features/settings.js"
    "js/features/history.js"
    "js/features/theme.js"
    "js/main.js"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$STATIC_DIR/$file" ]; then
        echo "❌ $file 파일이 없습니다."
        exit 1
    fi
    echo "  ✓ $file"
done

# 5. index.html 백업
if [ -f "$STATIC_DIR/index.html" ]; then
    BACKUP_HTML="$BACKUP_DIR/index.html.$TIMESTAMP"
    echo "💾 index.html 백업: $BACKUP_HTML"
    cp "$STATIC_DIR/index.html" "$BACKUP_HTML"
fi

echo ""
echo "✅ 마이그레이션 준비 완료!"
echo ""
echo "📋 다음 단계:"
echo "  1. 브라우저에서 애플리케이션 테스트"
echo "  2. 모든 기능이 정상 작동하는지 확인"
echo "  3. 문제가 있으면 백업에서 복원: cp $BACKUP_FILE $STATIC_DIR/script.js"
echo ""
echo "📁 백업 위치: $BACKUP_DIR"
echo ""
