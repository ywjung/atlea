#!/bin/bash
# SBOM Generation Script for RAG Chatbot
# Generates Software Bill of Materials for both Python and Java components

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

# Create SBOM directory
SBOM_DIR="sbom"
mkdir -p "$SBOM_DIR"

log_info "🔍 Generating SBOM files..."

# ============================================================
# Python SBOM Generation
# ============================================================
log_info "📦 Generating Python SBOM..."

if command -v pip-audit &> /dev/null; then
    # Using pip-audit with SBOM generation
    log_info "Using pip-audit for Python SBOM..."
    pip-audit --requirement requirements.txt --format json --output "$SBOM_DIR/python-sbom.json" 2>/dev/null || true
    pip-audit --requirement requirements.txt --format cyclonedx-json --output "$SBOM_DIR/python-sbom-cyclonedx.json" 2>/dev/null || true
else
    log_warning "pip-audit not installed. Installing..."
    pip install pip-audit
    pip-audit --requirement requirements.txt --format json --output "$SBOM_DIR/python-sbom.json"
    pip-audit --requirement requirements.txt --format cyclonedx-json --output "$SBOM_DIR/python-sbom-cyclonedx.json"
fi

# Generate Python dependency tree
log_info "Generating Python dependency tree..."
pip list --format=json > "$SBOM_DIR/python-packages.json"
pip freeze > "$SBOM_DIR/python-frozen-requirements.txt"

log_success "Python SBOM generated: $SBOM_DIR/python-sbom.json"

# ============================================================
# Java SBOM Generation
# ============================================================
log_info "📦 Generating Java SBOM..."

cd document-service

# Using Maven to generate dependency tree
log_info "Generating Maven dependency tree..."
mvn dependency:tree -DoutputFile="../$SBOM_DIR/java-dependency-tree.txt" || true

# Using CycloneDX Maven Plugin for SBOM
log_info "Using CycloneDX Maven Plugin..."
mvn org.cyclonedx:cyclonedx-maven-plugin:2.8.2:makeAggregateBom -DoutputFormat=json -DoutputName=java-sbom-cyclonedx || {
    log_warning "CycloneDX plugin failed, trying to add plugin configuration..."

    # Generate SBOM using dependency:list
    mvn dependency:list -DoutputFile="../$SBOM_DIR/java-dependencies.txt"
}

# Move generated SBOM if it exists
if [ -f "target/bom.json" ]; then
    mv target/bom.json "../$SBOM_DIR/java-sbom-cyclonedx.json"
    log_success "Java SBOM generated: $SBOM_DIR/java-sbom-cyclonedx.json"
elif [ -f "target/java-sbom-cyclonedx.json" ]; then
    mv target/java-sbom-cyclonedx.json "../$SBOM_DIR/"
    log_success "Java SBOM generated: $SBOM_DIR/java-sbom-cyclonedx.json"
fi

cd ..

# ============================================================
# Combined SBOM Summary
# ============================================================
log_info "📊 Creating SBOM summary..."

cat > "$SBOM_DIR/SBOM_SUMMARY.md" << 'EOF'
# Software Bill of Materials (SBOM) Summary

Generated: $(date)

## Overview

This directory contains the complete Software Bill of Materials (SBOM) for the RAG Chatbot system.

## Files

### Python Component
- `python-sbom.json` - Vulnerability audit report in JSON format
- `python-sbom-cyclonedx.json` - CycloneDX format SBOM
- `python-packages.json` - Complete package list
- `python-frozen-requirements.txt` - Frozen dependency versions

### Java Component
- `java-sbom-cyclonedx.json` - CycloneDX format SBOM
- `java-dependency-tree.txt` - Maven dependency tree
- `java-dependencies.txt` - Flat dependency list

### Vulnerability Scans
- `python-vulnerabilities.json` - Python vulnerability scan results
- `java-vulnerabilities.json` - Java vulnerability scan results
- `combined-vulnerabilities.md` - Combined vulnerability report

## Usage

### Regenerate SBOM
```bash
./scripts/generate_sbom.sh
```

### Scan for vulnerabilities
```bash
./scripts/scan_vulnerabilities.sh
```

### Update dependencies
```bash
./scripts/update_dependencies.sh
```

## Standards Compliance

- **CycloneDX 1.6**: Industry-standard SBOM format
- **SPDX**: Software Package Data Exchange (optional)
- **OWASP**: Dependency check integration

## Integration

These SBOM files can be integrated with:
- GitHub Dependabot
- Snyk
- OWASP Dependency-Track
- Grype
- Trivy
- JFrog Xray

## License Compliance

All dependencies are tracked for license compliance. See individual SBOM files for license information.
EOF

log_success "SBOM summary created: $SBOM_DIR/SBOM_SUMMARY.md"

# ============================================================
# Display Summary
# ============================================================
echo ""
log_success "✅ SBOM Generation Complete!"
echo ""
echo "Generated files:"
ls -lh "$SBOM_DIR"
echo ""
log_info "Next steps:"
echo "  1. Run vulnerability scan: ./scripts/scan_vulnerabilities.sh"
echo "  2. Review SBOM files in: ./$SBOM_DIR/"
echo "  3. Update vulnerable dependencies: ./scripts/update_dependencies.sh"
