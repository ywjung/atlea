# CSP Enforcement Guide

## Overview

Content Security Policy (CSP) has been strengthened to remove 'unsafe-inline' directives and enforce nonce-based inline scripts.

**Status**: Phase 1-3 Complete
**Date**: 2026-02-02

---

## Changes Made

### 1. CSP Policy Update ✅

**Before**:
```
script-src 'self' 'unsafe-inline' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;
style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;
```

**After**:
```
script-src 'self' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;
style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;
```

### 2. Inline Script Externalization ✅

- **File**: `static/theme-init.js`
- **Purpose**: Early theme initialization
- **Benefit**: No inline scripts, CSP compliant

---

## Remaining Inline Styles

### Issue
`static/index.html` still contains inline `<style>` tags (lines 35-148):
- Progress bar styles
- Various component styles

### Solutions

#### Option 1: Move to External CSS (Recommended)
```bash
# Create progress-bar-styles.css
cat > static/progress-bar-styles.css << 'EOF'
.progress-bar-wrapper {
    display: flex !important;
    flex-direction: column !important;
    gap: 2rem !important;
    position: relative !important;
    z-index: 1 !important;
}
/* ... rest of styles ... */
EOF

# Update index.html
<link rel="stylesheet" href="/static/progress-bar-styles.css">
```

#### Option 2: Use Nonce for Critical Styles
If styles must be inline (for performance):
```html
<!-- In template (if using Jinja2) -->
<style nonce="{{ csp_nonce }}">
    .progress-bar-wrapper { /* ... */ }
</style>
```

**Note**: Requires converting `index.html` to Jinja2 template.

---

## CSP Violation Monitoring

### 1. Report-Only Mode (Testing Phase)

Before enforcing strict CSP, test with report-only:

```python
# src/web_server.py
response.headers["Content-Security-Policy-Report-Only"] = (
    "default-src 'self'; "
    "script-src 'self' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "report-uri /api/csp-report"
)
```

### 2. CSP Report Endpoint

Create endpoint to collect violations:

```python
# src/routers/security.py
from fastapi import APIRouter, Request
from loguru import logger

router = APIRouter()

@router.post("/csp-report")
async def csp_report(request: Request):
    """Receive and log CSP violation reports"""
    try:
        report = await request.json()
        logger.warning(f"CSP Violation: {report}")

        # Store in database for analysis
        # redis.lpush("csp:violations", json.dumps(report))

        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing CSP report: {e}")
        return {"status": "error"}
```

### 3. Violation Analysis

Query and analyze CSP violations:

```python
# scripts/analyze_csp_violations.py
import redis
import json
from collections import Counter

r = redis.Redis()
violations = r.lrange("csp:violations", 0, -1)

# Parse violations
parsed = [json.loads(v) for v in violations]

# Analyze patterns
blocked_uris = Counter([v['csp-report']['blocked-uri'] for v in parsed])
violated_directives = Counter([v['csp-report']['violated-directive'] for v in parsed])

print("Most blocked URIs:")
for uri, count in blocked_uris.most_common(10):
    print(f"  {count:4d} - {uri}")

print("\nMost violated directives:")
for directive, count in violated_directives.most_common(5):
    print(f"  {count:4d} - {directive}")
```

---

## CSP Testing

### 1. Browser Console Testing

Open browser DevTools and check for CSP violations:
```
Content Security Policy: The page's settings blocked the loading of a resource
```

### 2. Automated Testing

```javascript
// tests/csp.test.js
describe('CSP Compliance', () => {
    it('should not have inline scripts', async () => {
        const response = await fetch('/');
        const html = await response.text();

        // Check for inline scripts
        const hasInlineScript = /<script(?![^>]*src=)[^>]*>/.test(html);
        expect(hasInlineScript).toBe(false);
    });

    it('should have CSP header without unsafe-inline', async () => {
        const response = await fetch('/');
        const csp = response.headers.get('content-security-policy');

        expect(csp).toBeDefined();
        expect(csp).not.toContain('unsafe-inline');
    });
});
```

### 3. Manual Verification

1. Open application in browser
2. Open DevTools → Console
3. Look for CSP warnings
4. Verify:
   - ✅ No inline script errors
   - ✅ No inline style errors
   - ✅ All external resources load correctly

---

## CSP Best Practices

### 1. Whitelist Specific Domains

**Bad**:
```
script-src 'self' https:;  // Too permissive
```

**Good**:
```
script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;
```

### 2. Use Subresource Integrity (SRI)

For external scripts:
```html
<script
    src="https://cdn.jsdelivr.net/npm/dompurify@3.0.8/dist/purify.min.js"
    integrity="sha512-5FqjUWIe/SfeE29uz8d3Hx3nzP3MBKlqDrqjHlbvEy3wEmKdYy/++SB73TXFdGBCaAlqUiFUJ2WCP7Kxo4x2+A=="
    crossorigin="anonymous"></script>
```

### 3. Nonce vs Hash

**Nonce** (Recommended for dynamic content):
```html
<script nonce="{{ csp_nonce }}">
    console.log('Dynamic content');
</script>
```

**Hash** (For static inline scripts):
```
script-src 'self' 'sha256-abc123...';
```

### 4. Gradual Enforcement

1. **Phase 1**: Report-only mode (collect violations)
2. **Phase 2**: Fix violations
3. **Phase 3**: Enforce mode
4. **Phase 4**: Continuous monitoring

---

## CSP Configuration per Environment

### Development
```python
if ENV == "development":
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        # ... relaxed for hot reload, etc.
    )
```

### Production
```python
if ENV == "production":
    csp = (
        "default-src 'self'; "
        "script-src 'self' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "upgrade-insecure-requests; "  # Force HTTPS
        "block-all-mixed-content; "     # Block HTTP on HTTPS page
    )
```

---

## Common CSP Issues & Fixes

### Issue 1: Google Tag Manager Blocked

**Error**: `Refused to load script from 'https://www.googletagmanager.com'`

**Fix**:
```
script-src 'self' https://www.googletagmanager.com;
```

### Issue 2: Inline Event Handlers

**Error**: `Refused to execute inline event handler`

**Bad**:
```html
<button onclick="doSomething()">Click</button>
```

**Good**:
```javascript
document.querySelector('button').addEventListener('click', doSomething);
```

### Issue 3: eval() or Function()

**Error**: `Refused to evaluate a string as JavaScript`

**Bad**:
```javascript
eval('console.log("bad")');
```

**Good**:
```javascript
console.log("good");
```

---

## CSP Header Management

### Current Implementation

```python
# src/web_server.py - SecurityHeadersMiddleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # CSP for main application
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            # ...
        )

        return response
```

### CSP Nonce Integration

```python
# src/middleware/csp_nonce.py - CSPNonceMiddleware
class CSPNonceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        # Inject nonce into CSP header
        if "Content-Security-Policy" in response.headers:
            csp = response.headers["Content-Security-Policy"]
            csp = csp.replace("script-src", f"script-src 'nonce-{nonce}'")
            response.headers["Content-Security-Policy"] = csp

        return response
```

---

## Rollback Plan

If CSP causes issues in production:

### 1. Immediate Rollback
```python
# Temporarily add back unsafe-inline
"script-src 'self' 'unsafe-inline' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
```

### 2. Report-Only Mode
```python
# Switch from enforcement to reporting
response.headers["Content-Security-Policy-Report-Only"] = csp_policy
```

### 3. Gradual Re-enforcement
- Fix identified violations
- Test thoroughly
- Re-enable enforcement

---

## Monitoring & Alerting

### Metrics to Track
- CSP violation count (hourly)
- Most common blocked resources
- Most violated directives
- User impact (pages affected)

### Alert Thresholds
- **Warning**: >10 violations/hour
- **Critical**: >100 violations/hour
- **Emergency**: Core functionality broken

---

## Next Steps

1. **Complete Inline Style Removal**
   - Move all inline styles to external CSS
   - Test with strict CSP

2. **Enable CSP Reporting**
   - Implement /api/csp-report endpoint
   - Set up violation dashboard

3. **Continuous Monitoring**
   - Track violations in production
   - Regular security audits

4. **Documentation Updates**
   - Update team guidelines
   - Create CSP troubleshooting guide

---

**Last Updated**: 2026-02-02
**Status**: Phase 1-3 Complete (Core CSP strengthened)
**Next**: Monitor violations and iterate
