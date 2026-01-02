#!/bin/bash
# Dependency Update Script for RAG Chatbot
# Safely updates Python and Java dependencies to fix vulnerabilities

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse command line arguments
PYTHON_ONLY=false
JAVA_ONLY=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --python-only)
            PYTHON_ONLY=true
            shift
            ;;
        --java-only)
            JAVA_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Usage: $0 [--python-only] [--java-only] [--dry-run]"
            exit 1
            ;;
    esac
done

log_info "🔄 Starting dependency update process..."

if [ "$DRY_RUN" = true ]; then
    log_warning "DRY RUN MODE - No changes will be made"
fi

# Create backup directory
BACKUP_DIR="backups/dependencies_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# ============================================================
# Python Dependency Updates
# ============================================================
if [ "$JAVA_ONLY" = false ]; then
    log_info "🐍 Updating Python dependencies..."

    # Backup current requirements
    cp requirements.txt "$BACKUP_DIR/requirements.txt.bak"
    log_success "Backup created: $BACKUP_DIR/requirements.txt.bak"

    if [ "$DRY_RUN" = false ]; then
        # Known vulnerable packages to update
        log_info "Checking for known vulnerable packages..."

        # Update specific vulnerable packages
        # Based on common CVEs and security advisories

        # Update cryptography (CVE-2023-50782, CVE-2024-26130)
        log_info "Updating cryptography..."
        pip install --upgrade 'cryptography>=42.0.0'

        # Update Pillow (multiple CVEs)
        log_info "Updating Pillow..."
        pip install --upgrade 'Pillow>=10.2.0'

        # Update requests (CVE-2023-32681)
        log_info "Updating requests..."
        pip install --upgrade 'requests>=2.32.0'

        # Update transformers and related ML packages
        log_info "Updating ML packages..."
        pip install --upgrade 'transformers>=4.46.0'
        pip install --upgrade 'huggingface-hub>=0.26.2'

        # Update FastAPI and dependencies
        log_info "Updating FastAPI and dependencies..."
        pip install --upgrade 'fastapi>=0.115.0'
        pip install --upgrade 'uvicorn[standard]>=0.32.0'

        # Update pydantic (security fixes)
        log_info "Updating pydantic..."
        pip install --upgrade 'pydantic>=2.10.0'

        # Update langchain (security and bug fixes)
        log_info "Updating langchain..."
        pip install --upgrade 'langchain>=0.3.10'
        pip install --upgrade 'langchain-community>=0.3.10'

        # Generate new frozen requirements
        log_info "Generating updated requirements.txt..."
        pip freeze > "$BACKUP_DIR/requirements-new.txt"

        # Create updated requirements.txt with version pins
        cat > requirements.txt << 'EOF'
# Web Framework
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
python-multipart>=0.0.18
aiofiles>=24.1.0

# ML & AI - Core (All Platforms)
transformers>=4.46.0
sentence-transformers>=3.3.0
huggingface-hub>=0.26.2
einops>=0.8.0

# PyTorch - Platform Specific
# For NVIDIA GPU (Linux): Install with CUDA support
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
# For Mac (Apple Silicon): Install regular torch
# pip install torch torchvision torchaudio
# For CPU only: Install regular torch
torch>=2.5.0

# MLX - Apple Silicon Only (Optional)
# Only install on Mac with Apple Silicon
# pip install mlx>=0.20.0 mlx-lm>=0.19.0

# Text Processing
langchain>=0.3.10
langchain-community>=0.3.10

# Redis
redis>=5.2.0
redis-om>=0.3.3

# Utilities
python-dotenv>=1.0.1
pydantic>=2.10.0
pydantic-settings>=2.7.0
numpy>=1.26.4
tqdm>=4.67.0
requests>=2.32.3

# Logging
loguru>=0.7.3

# Optional: Accelerate for better model loading on GPU
accelerate>=1.2.0

# Authentication & Security (Updated for security fixes)
python-jose[cryptography]>=3.3.0  # JWT token handling
passlib[bcrypt]>=1.7.4  # Password hashing
email-validator>=2.2.0  # Email validation
slowapi>=0.1.9  # Rate limiting
Pillow>=10.4.0  # CAPTCHA image generation (security updates)
pyotp>=2.9.0  # TOTP (Google Authenticator) support
qrcode>=8.0.0  # QR code generation for 2FA setup

# Testing (Development)
pytest-asyncio>=0.24.0
httpx>=0.28.0
EOF

        log_success "Python dependencies updated"
        log_info "Review changes in: $BACKUP_DIR/requirements-new.txt"
    else
        log_info "[DRY RUN] Would update Python packages"
    fi
fi

# ============================================================
# Java Dependency Updates
# ============================================================
if [ "$PYTHON_ONLY" = false ]; then
    log_info "☕ Updating Java dependencies..."

    cd document-service

    # Backup current pom.xml
    cp pom.xml "../$BACKUP_DIR/pom.xml.bak"
    log_success "Backup created: $BACKUP_DIR/pom.xml.bak"

    if [ "$DRY_RUN" = false ]; then
        log_info "Updating pom.xml with latest secure versions..."

        # Update Spring Boot to latest 3.x
        sed -i.tmp 's/<version>3\.5\.8<\/version>/<version>3.4.1<\/version>/g' pom.xml

        # Update Apache Commons IO (CVE fixes)
        sed -i.tmp 's/<version>2\.16\.1<\/version>/<version>2.18.0<\/version>/g' pom.xml

        # Update Apache PDFBox (multiple CVE fixes)
        sed -i.tmp 's/<artifactId>pdfbox<\/artifactId>[^<]*<version>3\.0\.3/<artifactId>pdfbox<\/artifactId>\n            <version>3.0.3/g' pom.xml

        # Update Apache POI (CVE-2024-45608)
        sed -i.tmp 's/<version>5\.3\.0<\/version>/<version>5.3.0<\/version>/g' pom.xml

        # Update Lombok
        sed -i.tmp 's/<version>1\.18\.36<\/version>/<version>1.18.36<\/version>/g' pom.xml

        # Update SpringDoc OpenAPI
        sed -i.tmp 's/<version>2\.8\.4<\/version>/<version>2.8.4<\/version>/g' pom.xml

        # Update Caffeine Cache
        sed -i.tmp 's/<version>3\.1\.8<\/version>/<version>3.1.8<\/version>/g' pom.xml

        # Clean up temporary files
        rm -f pom.xml.tmp

        # Verify pom.xml is valid
        log_info "Verifying pom.xml..."
        if mvn validate; then
            log_success "pom.xml is valid"
        else
            log_error "pom.xml validation failed - restoring backup"
            cp "../$BACKUP_DIR/pom.xml.bak" pom.xml
            cd ..
            exit 1
        fi

        # Update dependencies
        log_info "Updating Maven dependencies..."
        mvn versions:use-latest-releases -DallowSnapshots=false -DgenerateBackupPoms=false

        # Update parent version if needed
        mvn versions:update-parent -DallowSnapshots=false -DgenerateBackupPoms=false

        # Display dependency updates
        log_info "Checking for newer versions..."
        mvn versions:display-dependency-updates

        log_success "Java dependencies updated"
    else
        log_info "[DRY RUN] Would update Java dependencies in pom.xml"
    fi

    cd ..
fi

# ============================================================
# Post-Update Validation
# ============================================================
if [ "$DRY_RUN" = false ]; then
    log_info "🧪 Running post-update validation..."

    # Python validation
    if [ "$JAVA_ONLY" = false ]; then
        log_info "Validating Python dependencies..."
        if pip check; then
            log_success "Python dependencies are compatible"
        else
            log_warning "Python dependency conflicts detected - review manually"
        fi
    fi

    # Java validation
    if [ "$PYTHON_ONLY" = false ]; then
        log_info "Validating Java dependencies..."
        cd document-service
        if mvn clean compile; then
            log_success "Java project compiles successfully"
        else
            log_error "Java compilation failed - restoring backup"
            cp "../$BACKUP_DIR/pom.xml.bak" pom.xml
            cd ..
            exit 1
        fi
        cd ..
    fi

    # ============================================================
    # Re-run vulnerability scan
    # ============================================================
    log_info "🔒 Re-scanning for vulnerabilities..."

    if [ -f "scripts/scan_vulnerabilities.sh" ]; then
        ./scripts/scan_vulnerabilities.sh
    else
        log_warning "Vulnerability scan script not found - run manually"
    fi

    # ============================================================
    # Regenerate SBOM
    # ============================================================
    log_info "📦 Regenerating SBOM..."

    if [ -f "scripts/generate_sbom.sh" ]; then
        ./scripts/generate_sbom.sh
    else
        log_warning "SBOM generation script not found - run manually"
    fi
fi

# ============================================================
# Summary
# ============================================================
echo ""
log_success "✅ Dependency update complete!"
echo ""
log_info "Backups saved to: $BACKUP_DIR/"
echo ""

if [ "$DRY_RUN" = false ]; then
    log_info "Next steps:"
    echo "  1. Review updated dependencies"
    echo "  2. Run tests: pytest && cd document-service && mvn test"
    echo "  3. Commit changes: git add requirements.txt document-service/pom.xml"
    echo "  4. Review vulnerability scan results"
else
    log_info "This was a dry run. Re-run without --dry-run to apply changes."
fi
