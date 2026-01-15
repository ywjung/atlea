/**
 * Common Utility Functions
 */

// Input validation constants
const INPUT_VALIDATION = {
    MIN_LENGTH: 1,
    MAX_LENGTH: 5000,
    FORBIDDEN_PATTERNS: [
        /<script[^>]*>.*?<\/script>/gi,  // Script tags
        /<iframe[^>]*>.*?<\/iframe>/gi,  // Iframe tags
        /javascript:/gi,                  // JavaScript protocol
        /on\w+\s*=/gi                     // Event handlers (onclick, onload, etc.)
    ]
};

/**
 * Clean <think> tags from response
 */
function cleanThinkTags(text) {
    // Remove <think>...</think> blocks (including multiline)
    let cleaned = text.replace(/<think>[\s\S]*?<\/think>/g, '');
    // Remove any remaining tags
    cleaned = cleaned.replace(/<\/?think>/g, '');
    // Clean up extra whitespace
    cleaned = cleaned.replace(/\n\s*\n\s*\n/g, '\n\n');
    return cleaned.trim();
}

/**
 * Validate user input
 */
function validateInput(text) {
    // Remove leading/trailing whitespace
    const trimmed = text.trim();

    // Check if empty
    if (trimmed.length === 0) {
        return { valid: false, error: '질문을 입력해주세요.' };
    }

    // Check minimum length
    if (trimmed.length < INPUT_VALIDATION.MIN_LENGTH) {
        return { valid: false, error: `최소 ${INPUT_VALIDATION.MIN_LENGTH}자 이상 입력해주세요.` };
    }

    // Check maximum length
    if (trimmed.length > INPUT_VALIDATION.MAX_LENGTH) {
        return { valid: false, error: `최대 ${INPUT_VALIDATION.MAX_LENGTH}자까지 입력 가능합니다. (현재: ${trimmed.length}자)` };
    }

    // Check for forbidden patterns (XSS prevention)
    for (const pattern of INPUT_VALIDATION.FORBIDDEN_PATTERNS) {
        if (pattern.test(trimmed)) {
            return { valid: false, error: '허용되지 않는 문자나 태그가 포함되어 있습니다.' };
        }
    }

    // Normalize consecutive whitespace
    const normalized = trimmed.replace(/\s+/g, ' ');

    return { valid: true, normalized };
}

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return '방금 전';
    if (diffMins < 60) return `${diffMins}분 전`;
    if (diffHours < 24) return `${diffHours}시간 전`;
    if (diffDays < 7) return `${diffDays}일 전`;

    return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

/**
 * Format file size for display
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Debounce function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Throttle function
 */
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Export functions
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        INPUT_VALIDATION,
        cleanThinkTags,
        validateInput,
        formatTimestamp,
        formatFileSize,
        escapeHtml,
        debounce,
        throttle,
        showToast
    };
}
