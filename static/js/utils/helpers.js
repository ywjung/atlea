/**
 * Helper Utilities
 *
 * Miscellaneous utility functions.
 */

/**
 * Generate unique session ID
 * @returns {string} - Unique session ID
 */
export function generateSessionId() {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Generate unique ID
 * @param {string} prefix - Optional prefix for the ID
 * @returns {string} - Unique ID
 */
export function generateId(prefix = 'id') {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Generate UUID v4
 * @returns {string} - UUID
 */
export function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

/**
 * Sleep for specified milliseconds
 * @param {number} ms - Milliseconds to sleep
 * @returns {Promise<void>}
 */
export function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry async operation with exponential backoff
 * @param {Function} fn - Async function to retry
 * @param {number} maxRetries - Maximum number of retries
 * @param {number} initialDelay - Initial delay in ms
 * @returns {Promise<any>} - Result of successful operation
 */
export async function retry(fn, maxRetries = 3, initialDelay = 1000) {
    let lastError;

    for (let i = 0; i < maxRetries; i++) {
        try {
            return await fn();
        } catch (error) {
            lastError = error;
            if (i < maxRetries - 1) {
                const delay = initialDelay * Math.pow(2, i);
                await sleep(delay);
            }
        }
    }

    throw lastError;
}

/**
 * Copy text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} - True if successful
 */
export async function copyToClipboard(text) {
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
        } else {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            const success = document.execCommand('copy');
            document.body.removeChild(textarea);
            return success;
        }
    } catch (error) {
        console.error('Failed to copy to clipboard:', error);
        return false;
    }
}

/**
 * Download text as file
 * @param {string} content - File content
 * @param {string} filename - File name
 * @param {string} mimeType - MIME type
 */
export function downloadAsFile(content, filename, mimeType = 'text/plain') {
    const blob = new Blob([content], { type: mimeType + ';charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/**
 * Parse query string to object
 * @param {string} queryString - Query string (with or without ?)
 * @returns {Object} - Parsed parameters
 */
export function parseQueryString(queryString) {
    const params = {};
    const search = queryString.startsWith('?') ? queryString.substring(1) : queryString;

    if (!search) return params;

    const pairs = search.split('&');
    for (const pair of pairs) {
        const [key, value] = pair.split('=');
        if (key) {
            params[decodeURIComponent(key)] = value ? decodeURIComponent(value) : '';
        }
    }

    return params;
}

/**
 * Build query string from object
 * @param {Object} params - Parameters object
 * @returns {string} - Query string (without ?)
 */
export function buildQueryString(params) {
    const pairs = [];
    for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined) {
            pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
        }
    }
    return pairs.join('&');
}

/**
 * Get current URL parameters
 * @returns {Object} - URL parameters
 */
export function getUrlParams() {
    return parseQueryString(window.location.search);
}

/**
 * Check if element is in viewport
 * @param {HTMLElement} element - Element to check
 * @returns {boolean} - True if in viewport
 */
export function isInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
}

/**
 * Scroll element into view smoothly
 * @param {HTMLElement} element - Element to scroll to
 * @param {string} behavior - Scroll behavior ('auto' or 'smooth')
 */
export function scrollIntoView(element, behavior = 'smooth') {
    if (element) {
        element.scrollIntoView({ behavior, block: 'nearest' });
    }
}

/**
 * Get browser information
 * @returns {Object} - Browser info {name, version, os}
 */
export function getBrowserInfo() {
    const ua = navigator.userAgent;
    let browserName = 'Unknown';
    let browserVersion = 'Unknown';
    let os = 'Unknown';

    // Detect browser
    if (ua.indexOf('Firefox') > -1) {
        browserName = 'Firefox';
        browserVersion = ua.match(/Firefox\/(\d+\.\d+)/)?.[1] || 'Unknown';
    } else if (ua.indexOf('Chrome') > -1 && ua.indexOf('Edg') === -1) {
        browserName = 'Chrome';
        browserVersion = ua.match(/Chrome\/(\d+\.\d+)/)?.[1] || 'Unknown';
    } else if (ua.indexOf('Safari') > -1 && ua.indexOf('Chrome') === -1) {
        browserName = 'Safari';
        browserVersion = ua.match(/Version\/(\d+\.\d+)/)?.[1] || 'Unknown';
    } else if (ua.indexOf('Edg') > -1) {
        browserName = 'Edge';
        browserVersion = ua.match(/Edg\/(\d+\.\d+)/)?.[1] || 'Unknown';
    }

    // Detect OS
    if (ua.indexOf('Win') > -1) os = 'Windows';
    else if (ua.indexOf('Mac') > -1) os = 'macOS';
    else if (ua.indexOf('Linux') > -1) os = 'Linux';
    else if (ua.indexOf('Android') > -1) os = 'Android';
    else if (ua.indexOf('iOS') > -1) os = 'iOS';

    return { name: browserName, version: browserVersion, os };
}

/**
 * Check if feature is supported
 * @param {string} feature - Feature name
 * @returns {boolean} - True if supported
 */
export function isFeatureSupported(feature) {
    const features = {
        'localStorage': typeof Storage !== 'undefined',
        'sessionStorage': typeof Storage !== 'undefined',
        'webWorker': typeof Worker !== 'undefined',
        'serviceWorker': 'serviceWorker' in navigator,
        'webSocket': 'WebSocket' in window,
        'clipboard': navigator.clipboard && navigator.clipboard.writeText,
        'notification': 'Notification' in window,
        'geolocation': 'geolocation' in navigator,
        'fileReader': typeof FileReader !== 'undefined'
    };

    return features[feature] || false;
}
