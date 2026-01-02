#!/bin/bash
# Vulnerability Scanning Script for RAG Chatbot
# Scans both Python and Java dependencies for known security vulnerabilities

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

# Create directories
SBOM_DIR="sbom"
SCAN_DIR="$SBOM_DIR/scans"
mkdir -p "$SCAN_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

log_info "🔒 Starting vulnerability scan..."

# ============================================================
# Python Vulnerability Scanning
# ============================================================
log_info "🐍 Scanning Python dependencies..."

PYTHON_VULNS_FOUND=0

# Method 1: pip-audit (recommended)
if command -v pip-audit &> /dev/null; then
    log_info "Using pip-audit..."

    if pip-audit --requirement requirements.txt --format json --output "$SCAN_DIR/python-vulnerabilities-$TIMESTAMP.json"; then
        log_success "pip-audit scan completed (no vulnerabilities)"
    else
        PYTHON_VULNS_FOUND=$?
        log_warning "Vulnerabilities found in Python dependencies"
    fi

    # Generate human-readable report
    pip-audit --requirement requirements.txt > "$SCAN_DIR/python-vulnerabilities-$TIMESTAMP.txt" || true
else
    log_warning "pip-audit not installed. Installing..."
    pip install pip-audit
    pip-audit --requirement requirements.txt --format json --output "$SCAN_DIR/python-vulnerabilities-$TIMESTAMP.json" || PYTHON_VULNS_FOUND=$?
fi

# Method 2: safety (alternative)
if command -v safety &> /dev/null; then
    log_info "Using safety check..."
    safety check --file requirements.txt --json > "$SCAN_DIR/python-safety-$TIMESTAMP.json" 2>&1 || true
    safety check --file requirements.txt > "$SCAN_DIR/python-safety-$TIMESTAMP.txt" 2>&1 || true
fi

# Create symlinks to latest scans
ln -sf "python-vulnerabilities-$TIMESTAMP.json" "$SCAN_DIR/python-vulnerabilities-latest.json"
ln -sf "python-vulnerabilities-$TIMESTAMP.txt" "$SCAN_DIR/python-vulnerabilities-latest.txt"

# ============================================================
# Java Vulnerability Scanning
# ============================================================
log_info "☕ Scanning Java dependencies..."

JAVA_VULNS_FOUND=0

cd document-service

# Method 1: OWASP Dependency-Check Maven Plugin
log_info "Using OWASP Dependency-Check..."

if mvn org.owasp:dependency-check-maven:11.1.1:check \
    -DfailBuildOnCVSS=0 \
    -Dformat=JSON \
    -DoutputDirectory="../$SCAN_DIR" \
    -DdataDirectory=./owasp-data; then
    log_success "OWASP Dependency-Check scan completed"
else
    JAVA_VULNS_FOUND=$?
    log_warning "Vulnerabilities found in Java dependencies"
fi

# Generate HTML report as well
mvn org.owasp:dependency-check-maven:11.1.1:check \
    -DfailBuildOnCVSS=0 \
    -Dformat=HTML \
    -DoutputDirectory="../$SCAN_DIR" \
    -DdataDirectory=./owasp-data \
    2>/dev/null || true

cd ..

# Rename generated reports
if [ -f "$SCAN_DIR/dependency-check-report.json" ]; then
    mv "$SCAN_DIR/dependency-check-report.json" "$SCAN_DIR/java-vulnerabilities-$TIMESTAMP.json"
    ln -sf "java-vulnerabilities-$TIMESTAMP.json" "$SCAN_DIR/java-vulnerabilities-latest.json"
fi

if [ -f "$SCAN_DIR/dependency-check-report.html" ]; then
    mv "$SCAN_DIR/dependency-check-report.html" "$SCAN_DIR/java-vulnerabilities-$TIMESTAMP.html"
    ln -sf "java-vulnerabilities-$TIMESTAMP.html" "$SCAN_DIR/java-vulnerabilities-latest.html"
fi

# ============================================================
# Combined Vulnerability Report
# ============================================================
log_info "📊 Generating combined vulnerability report..."

cat > "$SCAN_DIR/VULNERABILITY_REPORT_$TIMESTAMP.md" << EOF
# Vulnerability Scan Report

**Generated**: $(date)
**Scan ID**: $TIMESTAMP

## Summary

### Python Dependencies
- Scan Tool: pip-audit, safety
- Results: See \`python-vulnerabilities-latest.txt\`

### Java Dependencies
- Scan Tool: OWASP Dependency-Check
- Results: See \`java-vulnerabilities-latest.html\`

## Scan Results

### Python Vulnerabilities
EOF

if [ -f "$SCAN_DIR/python-vulnerabilities-latest.txt" ]; then
    echo '```' >> "$SCAN_DIR/VULNERABILITY_REPORT_$TIMESTAMP.md"
    head -n 50 "$SCAN_DIR/python-vulnerabilities-latest.txt" >> "$SCAN_DIR/VULNERABILITY_REPORT_$TIMESTAMP.md"
    echo '```' >> "$SCAN_DIR/VULNERABILITY_REPORT_$TIMESTAMP.md"
fi

cat >> "$SCAN_DIR/VULNERABILITY_REPORT_$TIMESTAMP.md" << EOF

### Java Vulnerabilities

See HTML report for detailed analysis: \`java-vulnerabilities-latest.html\`

## Remediation Priority

### Critical Vulnerabilities
- **Action Required**: Immediate update or mitigation
- **Timeline**: Within 24 hours

### High Vulnerabilities
- **Action Required**: Update within 1 week
- **Timeline**: Within 7 days

### Medium Vulnerabilities
- **Action Required**: Plan update in next sprint
- **Timeline**: Within 30 days

### Low Vulnerabilities
- **Action Required**: Monitor and update as convenient
- **Timeline**: Next major release

## Next Steps

1. Review detailed scan results
2. Prioritize vulnerabilities by severity
3. Update affected dependencies
4. Re-run scan to verify fixes
5. Update SBOM

## Commands

\`\`\`bash
# Update dependencies
./scripts/update_dependencies.sh

# Re-scan after updates
./scripts/scan_vulnerabilities.sh

# Regenerate SBOM
./scripts/generate_sbom.sh
\`\`\`

## Resources

- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/)
- [pip-audit Documentation](https://pypi.org/project/pip-audit/)
- [CVE Database](https://cve.mitre.org/)
- [GitHub Advisory Database](https://github.com/advisories)
EOF

ln -sf "VULNERABILITY_REPORT_$TIMESTAMP.md" "$SCAN_DIR/VULNERABILITY_REPORT_LATEST.md"

log_success "Combined report created: $SCAN_DIR/VULNERABILITY_REPORT_LATEST.md"

# ============================================================
# Display Results Summary
# ============================================================
echo ""
if [ $PYTHON_VULNS_FOUND -eq 0 ] && [ $JAVA_VULNS_FOUND -eq 0 ]; then
    log_success "✅ No vulnerabilities found!"
else
    log_warning "⚠️  Vulnerabilities detected - review scan results"
    echo ""
    echo "Scan results:"
    echo "  - Python: $SCAN_DIR/python-vulnerabilities-latest.txt"
    echo "  - Java: $SCAN_DIR/java-vulnerabilities-latest.html"
    echo "  - Combined: $SCAN_DIR/VULNERABILITY_REPORT_LATEST.md"
    echo ""
    log_info "Next steps:"
    echo "  1. Review vulnerability details"
    echo "  2. Run: ./scripts/update_dependencies.sh"
    echo "  3. Re-scan after updates"
fi

echo ""
log_info "Scan files generated in: $SCAN_DIR/"
ls -lh "$SCAN_DIR" | grep -E "$TIMESTAMP|latest"
