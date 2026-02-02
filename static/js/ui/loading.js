/**
 * Loading Indicator
 *
 * Shows loading animations in chat container.
 */

import { createElement } from '../utils/dom.js';

/**
 * Show loading indicator in chat container
 * @param {HTMLElement} container - Chat container element
 * @param {string} message - Loading message
 * @param {Function} onStop - Stop button callback
 * @returns {string} - Loading element ID
 */
export function showLoading(container, message = '로딩 중...', onStop = null) {
    const loadingDiv = createElement('div', {
        className: 'message bot',
        id: 'loading-msg'
    });

    const contentDiv = createElement('div', {
        className: 'message-content'
    });

    const loadingAnimation = document.createElement('div');
    loadingAnimation.className = 'loading';
    loadingAnimation.innerHTML = `
        <div class="loading-text" id="loading-text">${message}</div>
        <div class="loading-dots">
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
        </div>
        ${onStop ? `<button class="stop-btn" id="stop-btn" title="중단">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect x="4" y="4" width="8" height="8" rx="1"/>
            </svg>
        </button>` : ''}
    `;

    if (onStop) {
        const stopBtn = loadingAnimation.querySelector('#stop-btn');
        if (stopBtn) {
            stopBtn.addEventListener('click', onStop);
        }
    }

    contentDiv.appendChild(loadingAnimation);
    loadingDiv.appendChild(contentDiv);
    container.appendChild(loadingDiv);

    // Auto-scroll
    container.scrollTop = container.scrollHeight;

    return 'loading-msg';
}

/**
 * Update loading message
 * @param {string} message - New loading message
 */
export function updateLoadingMessage(message) {
    const loadingText = document.getElementById('loading-text');
    if (loadingText) {
        loadingText.textContent = message;
    }
}

/**
 * Hide loading indicator
 */
export function hideLoading() {
    const loadingMsg = document.getElementById('loading-msg');
    if (loadingMsg) {
        loadingMsg.remove();
    }
}

/**
 * Create generic loading spinner element
 * @param {string} size - Spinner size (small, medium, large)
 * @returns {HTMLElement} - Spinner element
 */
export function createSpinner(size = 'medium') {
    const spinner = createElement('div', {
        className: 'spinner spinner-' + size
    });

    spinner.innerHTML = `
        <div class="spinner-dot"></div>
        <div class="spinner-dot"></div>
        <div class="spinner-dot"></div>
    `;

    return spinner;
}
