/**
 * Utilities Module Index
 * 
 * Central export point for all utility modules.
 */

// Re-export all utilities
export * from './sanitize.js';
export * from './formatters.js';
export * from './http.js';
export * from './storage.js';
export * from './dom.js';
export * from './validation.js';

// Named imports for convenience
export { sanitizeHTML, safeSetInnerHTML, escapeHtml } from './sanitize.js';
export { formatTimestamp, formatDate, formatDateTime, formatFileSize, formatNumber } from './formatters.js';
export { apiCall, get, post, put, del, uploadFile } from './http.js';
export { getItem, setItem, removeItem, clear, hasItem, getAllKeys, session } from './storage.js';
export {
    createElement, $, $$, addClass, removeClass, toggleClass, hasClass,
    show, hide, toggle, empty, text, waitForElement, debounce, throttle
} from './dom.js';
export {
    INPUT_VALIDATION, validateInput, validateEmail, validatePassword,
    validateUsername, sanitizeFilename
} from './validation.js';
