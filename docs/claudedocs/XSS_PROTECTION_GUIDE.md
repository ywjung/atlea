# XSS Protection Implementation Guide

## Overview

This document provides guidelines for completing XSS protection across the entire codebase using DOMPurify.

**Status**: Phase 1-2 Partial (Critical paths protected)
**Date**: 2026-02-02

---

## Completed Work

### 1. DOMPurify Integration ✅
- **Library**: DOMPurify v3.0.8 (CDN)
- **Location**: `static/index.html` line 150-154
- **Integrity**: SHA-512 hash verified

### 2. Sanitization Helpers ✅
- **Function**: `sanitizeHTML(dirty, config)`
- **Function**: `safeSetInnerHTML(element, html, config)`
- **Location**: `static/script.js` lines 1-59

### 3. Critical Sanitization Applied ✅
| Location | Type | Lines | Status |
|----------|------|-------|--------|
| Markdown rendering | `marked.parse()` | 5 locations | ✅ Protected |
| Toast notifications | User messages | line 422 | ✅ Protected |

---

## Remaining Work (108 locations)

### Priority 1: User Input Display (HIGH RISK)

#### Conversation List (20 locations)
```javascript
// BEFORE (Vulnerable)
item.innerHTML = `
    <div class="conversation-preview">
        ${conversation.title}
    </div>
`;

// AFTER (Protected)
item.innerHTML = sanitizeHTML(`
    <div class="conversation-preview">
        ${conversation.title}
    </div>
`);
```

**Files to update**:
- `static/script.js` lines: 1164, 1105, 1068-1155

#### Chat Message Display (15 locations)
```javascript
// BEFORE (Vulnerable)
messageDiv.innerHTML = userMessage;

// AFTER (Protected)
safeSetInnerHTML(messageDiv, userMessage);
```

**Files to update**:
- `static/script.js` lines: 1425-2500 (chat rendering functions)

### Priority 2: Dynamic Content (MEDIUM RISK)

#### Loading Animations (10 locations)
```javascript
// BEFORE
loadingAnimation.innerHTML = `<div class="spinner"></div>`;

// AFTER (Safe - static content, but good practice)
loadingAnimation.innerHTML = sanitizeHTML(`<div class="spinner"></div>`);
```

#### Button/Control Updates (30 locations)
```javascript
// BEFORE
btn.innerHTML = `<i class="icon">${iconName}</i> Label`;

// AFTER
safeSetInnerHTML(btn, `<i class="icon">${iconName}</i> Label`);
```

### Priority 3: Static Templates (LOW RISK)

#### Static HTML Templates (43 locations)
These are low risk as they don't include user input, but should still be updated for consistency:

```javascript
// BEFORE
container.innerHTML = `
    <div class="static-template">
        <button>Click</button>
    </div>
`;

// AFTER (Optional but recommended)
container.innerHTML = `
    <div class="static-template">
        <button>Click</button>
    </div>
`; // No sanitization needed for purely static content
```

---

## Implementation Checklist

### Phase 1: User Input (Complete by: Week 1)
- [ ] Sanitize all conversation list items
- [ ] Sanitize all chat message displays
- [ ] Sanitize user profile displays
- [ ] Sanitize search results
- [ ] Test with XSS payloads

### Phase 2: Dynamic Content (Complete by: Week 2)
- [ ] Sanitize loading animations with dynamic text
- [ ] Sanitize error messages
- [ ] Sanitize success messages
- [ ] Sanitize modal content

### Phase 3: Controls & UI (Complete by: Week 3)
- [ ] Sanitize button labels
- [ ] Sanitize menu items
- [ ] Sanitize tooltips
- [ ] Sanitize status indicators

### Phase 4: Static Templates (Optional)
- [ ] Review and sanitize remaining static templates
- [ ] Document exceptions (if any)

---

## Testing Strategy

### 1. XSS Payload Testing

Test with common XSS payloads:

```javascript
const xssPayloads = [
    '<script>alert("XSS")</script>',
    '<img src=x onerror=alert("XSS")>',
    '<svg onload=alert("XSS")>',
    'javascript:alert("XSS")',
    '<iframe src="javascript:alert(\'XSS\')">',
    '<body onload=alert("XSS")>',
    '<input onfocus=alert("XSS") autofocus>',
    '<marquee onstart=alert("XSS")>',
    '"><script>alert(String.fromCharCode(88,83,83))</script>',
    '<SCRIPT SRC=http://evil.com/xss.js></SCRIPT>'
];

// Test each payload in:
// 1. Chat messages
// 2. Conversation titles
// 3. User profile data
// 4. Search queries
// 5. File names
```

### 2. Automated Testing

Create test suite:

```javascript
// tests/xss_protection.test.js
describe('XSS Protection', () => {
    it('should sanitize script tags', () => {
        const dirty = '<script>alert("XSS")</script>';
        const clean = sanitizeHTML(dirty);
        expect(clean).not.toContain('<script>');
    });

    it('should sanitize event handlers', () => {
        const dirty = '<img src=x onerror=alert("XSS")>';
        const clean = sanitizeHTML(dirty);
        expect(clean).not.toContain('onerror');
    });

    // Add more tests...
});
```

### 3. Manual Testing Checklist

- [ ] Create conversation with XSS payload in title
- [ ] Send message with XSS payload
- [ ] Upload file with XSS payload in name
- [ ] Update profile with XSS payload
- [ ] Search with XSS payload
- [ ] Verify all payloads are sanitized

---

## DOMPurify Configuration Guide

### Default Configuration (Recommended)

```javascript
const defaultConfig = {
    ALLOWED_TAGS: [
        'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'dd', 'del', 'div',
        'dl', 'dt', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i',
        'img', 'ins', 'kbd', 'li', 'mark', 'ol', 'p', 'pre', 's', 'span',
        'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th',
        'thead', 'tr', 'u', 'ul'
    ],
    ALLOWED_ATTR: [
        'class', 'id', 'href', 'title', 'alt', 'src', 'width', 'height',
        'data-*', 'aria-*', 'role', 'target', 'rel'
    ],
    ALLOW_DATA_ATTR: true,
    ALLOW_ARIA_ATTR: true,
    FORBID_ATTR: ['onerror', 'onload', 'onclick'],
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'link', 'style']
};
```

### Strict Configuration (User Input)

For user-generated content with no HTML allowed:

```javascript
const strictConfig = {
    ALLOWED_TAGS: [],        // No HTML tags
    ALLOWED_ATTR: [],        // No attributes
    KEEP_CONTENT: true       // Keep text content
};

// Usage
const safeText = sanitizeHTML(userInput, strictConfig);
```

### Markdown Configuration

For markdown-rendered content:

```javascript
const markdownConfig = {
    ALLOWED_TAGS: [
        'a', 'b', 'blockquote', 'br', 'code', 'del', 'div', 'em',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img',
        'li', 'ol', 'p', 'pre', 'strong', 'ul'
    ],
    ALLOWED_ATTR: ['class', 'href', 'title', 'alt', 'src'],
    FORBID_TAGS: ['script', 'iframe', 'style']
};

// Usage
contentDiv.innerHTML = sanitizeHTML(marked.parse(markdown), markdownConfig);
```

---

## Common Pitfalls

### ❌ DON'T: Sanitize after insertion
```javascript
// WRONG - Too late!
element.innerHTML = userInput;
element.innerHTML = sanitizeHTML(element.innerHTML);
```

### ✅ DO: Sanitize before insertion
```javascript
// CORRECT
element.innerHTML = sanitizeHTML(userInput);
```

### ❌ DON'T: Trust "safe" sources without validation
```javascript
// WRONG - API responses can be compromised
element.innerHTML = response.data.message;
```

### ✅ DO: Always sanitize external data
```javascript
// CORRECT
element.innerHTML = sanitizeHTML(response.data.message);
```

### ❌ DON'T: Use innerHTML for plain text
```javascript
// WRONG - Unnecessary HTML parsing
element.innerHTML = plainText;
```

### ✅ DO: Use textContent for plain text
```javascript
// CORRECT - Safer and faster
element.textContent = plainText;
```

---

## Performance Considerations

### Batch Operations

When updating multiple elements, batch sanitization:

```javascript
// BEFORE (Inefficient)
messages.forEach(msg => {
    const div = document.createElement('div');
    div.innerHTML = sanitizeHTML(msg.content);
    container.appendChild(div);
});

// AFTER (Efficient)
const fragment = document.createDocumentFragment();
messages.forEach(msg => {
    const div = document.createElement('div');
    div.innerHTML = sanitizeHTML(msg.content);
    fragment.appendChild(div);
});
container.appendChild(fragment);
```

### Cache Sanitized Content

For repeated rendering of same content:

```javascript
// Cache sanitized markdown
const sanitizedCache = new Map();

function getSanitizedMarkdown(markdown) {
    if (sanitizedCache.has(markdown)) {
        return sanitizedCache.get(markdown);
    }
    const sanitized = sanitizeHTML(marked.parse(markdown));
    sanitizedCache.set(markdown, sanitized);
    return sanitized;
}
```

---

## Security Audit Checklist

### Code Review
- [ ] All innerHTML assignments use sanitizeHTML
- [ ] All insertAdjacentHTML uses sanitized content
- [ ] No eval() or Function() with user input
- [ ] No document.write() with user input
- [ ] Template literals properly escaped

### Configuration Review
- [ ] DOMPurify config doesn't allow dangerous tags
- [ ] Event handlers forbidden
- [ ] Data URIs properly handled
- [ ] External links sanitized

### Testing
- [ ] All XSS payloads blocked
- [ ] Legitimate HTML preserved
- [ ] No false positives
- [ ] Performance acceptable

---

## References

- **DOMPurify Documentation**: https://github.com/cure53/DOMPurify
- **OWASP XSS Guide**: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- **CSP Best Practices**: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP

---

## Next Steps

1. **Complete Phase 1** (User Input): Focus on high-risk areas
2. **Implement Testing**: Create automated XSS test suite
3. **CSP Enhancement**: Remove 'unsafe-inline' (Phase 1-3)
4. **Security Audit**: Regular penetration testing
5. **Documentation**: Update as new patterns emerge

---

**Last Updated**: 2026-02-02
**Maintainer**: Development Team
**Status**: In Progress (Critical paths protected)
