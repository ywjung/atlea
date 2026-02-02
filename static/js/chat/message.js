/**
 * Message Rendering
 * 
 * Renders chat messages with markdown support.
 */

import { sanitizeHTML } from '../utils/sanitize.js';
import { createElement } from '../utils/dom.js';

/**
 * Render user message
 * @param {string} text - Message text
 * @returns {HTMLElement} - Message element
 */
export function renderUserMessage(text) {
    const messageDiv = createElement('div', {
        className: 'message user-message'
    });

    const contentDiv = createElement('div', {
        className: 'message-content'
    });
    contentDiv.textContent = text;

    messageDiv.appendChild(contentDiv);
    return messageDiv;
}

/**
 * Render assistant message with markdown
 * @param {string} text - Message text (markdown)
 * @returns {HTMLElement} - Message element
 */
export function renderAssistantMessage(text) {
    const messageDiv = createElement('div', {
        className: 'message assistant-message'
    });

    const contentDiv = createElement('div', {
        className: 'message-content markdown-content'
    });

    // Use marked.js for markdown rendering
    if (typeof marked !== 'undefined') {
        const html = marked.parse(text);
        contentDiv.innerHTML = sanitizeHTML(html);
    } else {
        contentDiv.textContent = text;
    }

    messageDiv.appendChild(contentDiv);
    return messageDiv;
}

/**
 * Render system message
 * @param {string} text - Message text
 * @param {string} type - Message type (info, warning, error)
 * @returns {HTMLElement} - Message element
 */
export function renderSystemMessage(text, type = 'info') {
    const messageDiv = createElement('div', {
        className: 'message system-message system-message-' + type
    });

    const contentDiv = createElement('div', {
        className: 'message-content'
    });
    contentDiv.textContent = text;

    messageDiv.appendChild(contentDiv);
    return messageDiv;
}

/**
 * Create loading indicator
 * @returns {HTMLElement} - Loading element
 */
export function createLoadingIndicator() {
    const loadingDiv = createElement('div', {
        className: 'message assistant-message loading'
    });

    const contentDiv = createElement('div', {
        className: 'message-content'
    });

    const spinner = createElement('div', {
        className: 'spinner'
    });

    contentDiv.appendChild(spinner);
    contentDiv.appendChild(document.createTextNode('생각중...'));
    loadingDiv.appendChild(contentDiv);

    return loadingDiv;
}

/**
 * Update message content (for streaming)
 * @param {HTMLElement} element - Message element
 * @param {string} text - New text
 */
export function updateMessageContent(element, text) {
    const contentDiv = element.querySelector('.message-content');
    if (!contentDiv) return;

    if (element.classList.contains('assistant-message')) {
        // Render markdown for assistant messages
        if (typeof marked !== 'undefined') {
            const html = marked.parse(text);
            contentDiv.innerHTML = sanitizeHTML(html);
        } else {
            contentDiv.textContent = text;
        }
    } else {
        contentDiv.textContent = text;
    }
}

/**
 * Add action buttons to message
 * @param {HTMLElement} messageElement - Message element
 * @param {Object} actions - Action callbacks
 */
export function addMessageActions(messageElement, actions = {}) {
    const actionsDiv = createElement('div', {
        className: 'message-actions'
    });

    if (actions.copy) {
        const copyBtn = createElement('button', {
            className: 'action-btn copy-btn',
            title: '복사',
            onclick: actions.copy
        });
        copyBtn.textContent = '📋';
        actionsDiv.appendChild(copyBtn);
    }

    if (actions.regenerate) {
        const regenBtn = createElement('button', {
            className: 'action-btn regenerate-btn',
            title: '재생성',
            onclick: actions.regenerate
        });
        regenBtn.textContent = '🔄';
        actionsDiv.appendChild(regenBtn);
    }

    if (actions.thumbsUp) {
        const upBtn = createElement('button', {
            className: 'action-btn thumbs-up-btn',
            title: '좋아요',
            onclick: actions.thumbsUp
        });
        upBtn.textContent = '👍';
        actionsDiv.appendChild(upBtn);
    }

    if (actions.thumbsDown) {
        const downBtn = createElement('button', {
            className: 'action-btn thumbs-down-btn',
            title: '싫어요',
            onclick: actions.thumbsDown
        });
        downBtn.textContent = '👎';
        actionsDiv.appendChild(downBtn);
    }

    messageElement.appendChild(actionsDiv);
}
