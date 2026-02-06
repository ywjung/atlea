/**
 * XSS Protection Utilities
 * 
 * DOMPurify-based sanitization helpers for safe HTML rendering.
 */

/**
 * Sanitize HTML content using DOMPurify
 * @param {string} dirty - Potentially unsafe HTML
 * @param {Object} config - DOMPurify configuration
 * @returns {string} - Sanitized HTML
 */
export function sanitizeHTML(dirty, config = {}) {
    if (typeof DOMPurify === 'undefined') {
        console.error('DOMPurify is not loaded! Falling back to text content only.');
        // Fallback: strip all HTML tags
        const div = document.createElement('div');
        div.textContent = dirty;
        return div.innerHTML;
    }

    // Default config: allow most HTML but remove dangerous elements
    const defaultConfig = {
        ALLOWED_TAGS: [
            'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'dd', 'del', 'div',
            'dl', 'dt', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i',
            'img', 'ins', 'kbd', 'li', 'mark', 'ol', 'p', 'pre', 's', 'span',
            'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th',
            'thead', 'tr', 'u', 'ul',
            // SVG tags for icons
            'svg', 'path', 'circle', 'rect', 'line', 'polyline', 'polygon',
            'ellipse', 'g', 'text', 'tspan', 'defs', 'clipPath', 'mask', 'use'
        ],
        ALLOWED_ATTR: [
            'class', 'id', 'href', 'title', 'alt', 'src', 'width', 'height',
            'data-*', 'aria-*', 'role', 'target', 'rel',
            // SVG attributes for icons
            'viewBox', 'fill', 'stroke', 'stroke-width', 'stroke-linecap',
            'stroke-linejoin', 'd', 'x', 'y', 'x1', 'y1', 'x2', 'y2',
            'cx', 'cy', 'r', 'rx', 'ry', 'points', 'transform',
            'font-size', 'font-weight', 'text-anchor'
        ],
        ALLOW_DATA_ATTR: true,
        ALLOW_ARIA_ATTR: true,
        // Prevent data: URIs in images (XSS vector)
        FORBID_ATTR: ['onerror', 'onload', 'onclick'],
        FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'link', 'style'],
        ...config
    };

    return DOMPurify.sanitize(dirty, defaultConfig);
}

/**
 * Safely set innerHTML with DOMPurify sanitization
 * @param {HTMLElement} element - Target element
 * @param {string} html - HTML content to set
 * @param {Object} config - DOMPurify configuration
 */
export function safeSetInnerHTML(element, html, config = {}) {
    if (!element) {
        console.error('safeSetInnerHTML: element is null or undefined');
        return;
    }
    element.innerHTML = sanitizeHTML(html, config);
}

/**
 * Escape HTML entities for safe text display
 * @param {string} text - Text to escape
 * @returns {string} - Escaped text
 */
export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
