/**
 * Toast Notification
 *
 * Shows temporary notification messages with animations.
 */

import { sanitizeHTML, safeSetInnerHTML } from '../utils/sanitize.js';

/**
 * Show toast notification
 * @param {string} message - Message text
 * @param {string} type - Notification type (info, success, warning, error)
 * @param {number} duration - Display duration in ms (default: 3000)
 */
export function showToast(message, type = 'info', duration = 3000) {
    // Remove existing notification if any
    const existing = document.querySelector('.toast-notification');
    if (existing) {
        existing.remove();
    }

    const icons = {
        info: 'ℹ️',
        success: '✅',
        warning: '⚠️',
        error: '❌'
    };

    const colors = {
        info: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
        success: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
        warning: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
        error: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)'
    };

    const notification = document.createElement('div');
    notification.className = 'toast-notification';

    // Sanitize message to prevent XSS
    const safeMessage = sanitizeHTML(message, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });
    safeSetInnerHTML(notification, `<span class="toast-icon">${icons[type] || icons.info}</span><span class="toast-message">${safeMessage}</span>`);

    notification.style.cssText = `
        position: fixed;
        bottom: 100px;
        left: 50%;
        transform: translateX(-50%) translateY(20px);
        background: ${colors[type] || colors.info};
        color: white;
        padding: 12px 24px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        z-index: 10000;
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 14px;
        font-weight: 500;
        opacity: 0;
        transition: opacity 0.3s ease, transform 0.3s ease;
    `;

    document.body.appendChild(notification);

    // Animate in
    requestAnimationFrame(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateX(-50%) translateY(0)';
    });

    // Auto-remove after duration
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(-50%) translateY(20px)';
        setTimeout(() => notification.remove(), 300);
    }, duration);
}

/**
 * Alias for showToast
 * @deprecated Use showToast instead
 */
export function showNotification(message, type = 'info') {
    return showToast(message, type);
}
