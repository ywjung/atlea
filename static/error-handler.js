/**
 * Error Handler
 * Handles network errors, timeouts, and retry logic with user-friendly messages
 */

// HTML escape helper to prevent XSS
function escapeHtmlForError(text) {
    if (typeof text !== 'string') return String(text);
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

class ErrorHandler {
    constructor() {
        this.maxRetries = 3;
        this.baseDelay = 1000; // 1 second
        this.timeout = 120000; // 120 seconds (increased for slower LLM models like glm-4.7-flash)
        this.retryCount = 0;
    }

    /**
     * Main error handling method
     * @param {Error} error - The error object
     * @param {string} context - Context where error occurred
     * @returns {Object} - Error details and suggested action
     */
    handleError(error, context = 'general') {
        const errorType = this.classifyError(error);
        const errorMessage = this.getErrorMessage(errorType, context);

        return {
            type: errorType,
            message: errorMessage,
            canRetry: this.isRetryable(errorType),
            context: context
        };
    }

    /**
     * Classify error type
     * @param {Error} error
     * @returns {string} - Error type
     */
    classifyError(error) {
        if (!error) return 'unknown';

        // Network errors
        if (error.name === 'NetworkError' || error.message.includes('Failed to fetch')) {
            return 'network';
        }

        // Timeout errors
        if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
            return 'timeout';
        }

        // Server errors (5xx)
        if (error.status >= 500 && error.status < 600) {
            return 'server';
        }

        // Client errors (4xx)
        if (error.status >= 400 && error.status < 500) {
            return 'client';
        }

        // Abort errors (user cancelled)
        if (error.name === 'AbortError') {
            return 'aborted';
        }

        return 'unknown';
    }

    /**
     * Get user-friendly error message
     * @param {string} errorType
     * @param {string} context
     * @returns {string}
     */
    getErrorMessage(errorType, context) {
        const messages = {
            network: '네트워크 연결에 실패했습니다. 인터넷 연결을 확인해주세요.',
            timeout: '응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.',
            server: '서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.',
            client: '요청을 처리할 수 없습니다. 입력 내용을 확인해주세요.',
            aborted: '요청이 취소되었습니다.',
            unknown: '예상치 못한 오류가 발생했습니다. 다시 시도해주세요.'
        };

        return messages[errorType] || messages.unknown;
    }

    /**
     * Check if error is retryable
     * @param {string} errorType
     * @returns {boolean}
     */
    isRetryable(errorType) {
        const retryableTypes = ['network', 'timeout', 'server'];
        return retryableTypes.includes(errorType);
    }

    /**
     * Execute function with retry logic
     * @param {Function} fn - Async function to execute
     * @param {number} maxRetries - Maximum retry attempts
     * @returns {Promise} - Function result or throws error
     */
    async withRetry(fn, maxRetries = this.maxRetries) {
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                this.retryCount = attempt;
                const result = await fn();
                this.retryCount = 0; // Reset on success
                return result;
            } catch (error) {
                const errorInfo = this.handleError(error);

                // Don't retry if not retryable or last attempt
                if (!errorInfo.canRetry || attempt === maxRetries) {
                    this.retryCount = 0;
                    throw error;
                }

                // Calculate exponential backoff delay
                const delay = this.baseDelay * Math.pow(2, attempt);

                // Show retry notification
                this.showRetryNotification(attempt + 1, maxRetries, delay);

                await this.sleep(delay);
            }
        }
    }

    /**
     * Execute function with timeout
     * @param {Function} fn - Async function to execute
     * @param {number} timeout - Timeout in milliseconds
     * @returns {Promise} - Function result or timeout error
     */
    async withTimeout(fn, timeout = this.timeout) {
        return Promise.race([
            fn(),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Request timeout')), timeout)
            )
        ]);
    }

    /**
     * Sleep utility
     * @param {number} ms - Milliseconds to sleep
     * @returns {Promise}
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Show error message to user
     * @param {Object} errorInfo - Error information
     * @param {boolean} showRetryButton - Whether to show retry button
     */
    showErrorMessage(errorInfo, showRetryButton = false) {
        const errorContainer = document.createElement('div');
        errorContainer.className = 'error-message-container';
        errorContainer.innerHTML = `
            <div class="error-message">
                <div class="error-icon">⚠️</div>
                <div class="error-content">
                    <div class="error-title">오류 발생</div>
                    <div class="error-text">${escapeHtmlForError(errorInfo.message)}</div>
                </div>
                ${showRetryButton ? `
                    <div class="error-actions">
                        <button class="retry-button">
                            다시 시도
                        </button>
                        <button class="cancel-button">
                            취소
                        </button>
                    </div>
                ` : ''}
            </div>
        `;

        // Add to chat container
        const chatContainer = document.getElementById('chatContainer');
        if (chatContainer) {
            chatContainer.appendChild(errorContainer);

            // Add event listeners for buttons
            if (showRetryButton) {
                const retryBtn = errorContainer.querySelector('.retry-button');
                const cancelBtn = errorContainer.querySelector('.cancel-button');

                if (retryBtn) {
                    retryBtn.onclick = () => {
                        errorContainer.remove();
                        // Trigger sendMessage with regenerate=true
                        if (typeof sendMessage === 'function') {
                            sendMessage(true);
                        }
                    };
                }

                if (cancelBtn) {
                    cancelBtn.onclick = () => {
                        errorContainer.remove();
                    };
                }
            }

            // Auto-remove after 5 seconds if no retry button
            if (!showRetryButton) {
                setTimeout(() => {
                    if (errorContainer.parentNode) {
                        errorContainer.remove();
                    }
                }, 5000);
            }
        }
    }

    /**
     * Show retry notification
     * @param {number} attempt - Current attempt number
     * @param {number} maxRetries - Maximum retries
     * @param {number} delay - Delay before retry in ms
     */
    showRetryNotification(attempt, maxRetries, delay) {
        const notification = document.createElement('div');
        notification.className = 'retry-notification';
        notification.innerHTML = `
            <div class="retry-content">
                <span class="retry-icon">🔄</span>
                <span class="retry-text">재시도 중... (${attempt}/${maxRetries})</span>
                <span class="retry-timer">${(delay / 1000).toFixed(1)}초 후</span>
            </div>
        `;

        const chatContainer = document.getElementById('chatContainer');
        if (chatContainer) {
            chatContainer.appendChild(notification);

            // Remove after delay
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, delay);
        }
    }

    /**
     * Show loading indicator with cancel button
     * @param {AbortController} abortController - Controller to cancel request
     * @returns {HTMLElement} - Loading element
     */
    showLoadingWithCancel(abortController) {
        const loadingContainer = document.createElement('div');
        loadingContainer.className = 'loading-container';
        loadingContainer.id = 'loadingIndicator';
        loadingContainer.innerHTML = `
            <div class="loading-content">
                <div class="loading-spinner"></div>
                <span class="loading-text">응답 생성 중...</span>
                <button class="cancel-button" id="cancelRequestBtn">
                    취소
                </button>
            </div>
        `;

        const chatContainer = document.getElementById('chatContainer');
        if (chatContainer) {
            chatContainer.appendChild(loadingContainer);
        }

        // Add cancel event listener
        const cancelBtn = document.getElementById('cancelRequestBtn');
        if (cancelBtn && abortController) {
            cancelBtn.addEventListener('click', () => {
                abortController.abort();
                if (loadingContainer.parentNode) {
                    loadingContainer.remove();
                }
            });
        }

        return loadingContainer;
    }

    /**
     * Remove loading indicator
     */
    hideLoading() {
        const loadingIndicator = document.getElementById('loadingIndicator');
        if (loadingIndicator && loadingIndicator.parentNode) {
            loadingIndicator.remove();
        }
    }

    /**
     * Get current retry count
     * @returns {number}
     */
    getCurrentRetryCount() {
        return this.retryCount;
    }

    /**
     * Reset retry count
     */
    resetRetryCount() {
        this.retryCount = 0;
    }
}

// Export for use in main script
window.ErrorHandler = ErrorHandler;
