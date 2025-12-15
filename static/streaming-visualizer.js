/**
 * Streaming Visualizer
 * Provides visual feedback during streaming response generation
 */

class StreamingVisualizer {
    constructor() {
        this.currentIndicator = null;
        this.startTime = null;
        this.tokenCount = 0;
        this.estimatedTotal = 0;
        this.updateInterval = null;
    }

    /**
     * Show typing indicator while waiting for first token
     * @param {HTMLElement} container - Container to append indicator
     * @returns {HTMLElement} - The indicator element
     */
    showTypingIndicator(container) {
        this.startTime = Date.now();
        this.tokenCount = 0;

        const indicator = document.createElement('div');
        indicator.className = 'streaming-indicator typing-indicator';
        indicator.innerHTML = `
            <div class="typing-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
            <span class="status-text">답변 생성 중...</span>
        `;

        container.appendChild(indicator);
        this.currentIndicator = indicator;

        return indicator;
    }

    /**
     * Switch to streaming progress indicator
     * @param {HTMLElement} container - Container element
     */
    showStreamingProgress(container) {
        // Remove typing indicator
        if (this.currentIndicator) {
            this.currentIndicator.remove();
        }

        // Create streaming progress indicator
        const indicator = document.createElement('div');
        indicator.className = 'streaming-indicator progress-indicator';
        indicator.id = 'streamingProgress';
        indicator.innerHTML = `
            <div class="progress-content">
                <div class="progress-info">
                    <span class="progress-icon">✍️</span>
                    <div class="progress-details">
                        <span class="progress-text">실시간 생성 중</span>
                        <div class="progress-stats">
                            <span class="token-count" id="tokenCount">0</span> 토큰 생성됨
                            <span class="separator">•</span>
                            <span class="elapsed-time" id="elapsedTime">0.0s</span>
                        </div>
                    </div>
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar" id="progressBar"></div>
                </div>
            </div>
        `;

        container.appendChild(indicator);
        this.currentIndicator = indicator;

        // Start updating stats
        this.startStatsUpdate();

        return indicator;
    }

    /**
     * Update token count
     * @param {number} count - Number of tokens generated
     */
    updateTokenCount(count) {
        this.tokenCount = count;

        const tokenCountEl = document.getElementById('tokenCount');
        if (tokenCountEl) {
            tokenCountEl.textContent = count;
        }

        // Update progress bar (estimated)
        this.updateProgressBar();
    }

    /**
     * Update progress bar based on estimated completion
     */
    updateProgressBar() {
        const progressBar = document.getElementById('progressBar');
        if (!progressBar) return;

        // Estimate total tokens based on current rate
        // Assume average response is ~200-500 tokens
        const avgTokens = 350;
        const progress = Math.min((this.tokenCount / avgTokens) * 100, 95);

        progressBar.style.width = `${progress}%`;
    }

    /**
     * Start periodic stats update
     */
    startStatsUpdate() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }

        this.updateInterval = setInterval(() => {
            const elapsedTimeEl = document.getElementById('elapsedTime');
            if (elapsedTimeEl && this.startTime) {
                const elapsed = (Date.now() - this.startTime) / 1000;
                elapsedTimeEl.textContent = `${elapsed.toFixed(1)}s`;
            }
        }, 100); // Update every 100ms
    }

    /**
     * Stop stats update
     */
    stopStatsUpdate() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    /**
     * Show completion indicator
     * @param {number} finalTokenCount - Final token count
     * @param {number} totalTime - Total time in seconds
     */
    showCompletion(finalTokenCount, totalTime) {
        this.stopStatsUpdate();

        if (this.currentIndicator) {
            // Update to completion state
            const progressBar = document.getElementById('progressBar');
            if (progressBar) {
                progressBar.style.width = '100%';
                progressBar.style.background = 'linear-gradient(90deg, #4CAF50 0%, #66BB6A 100%)';
            }

            // Show final stats briefly
            const tokenCountEl = document.getElementById('tokenCount');
            const elapsedTimeEl = document.getElementById('elapsedTime');

            if (tokenCountEl) tokenCountEl.textContent = finalTokenCount;
            if (elapsedTimeEl) elapsedTimeEl.textContent = `${totalTime.toFixed(1)}s`;

            // Add completion class for animation
            this.currentIndicator.classList.add('completed');

            // Remove after animation
            setTimeout(() => {
                this.hide();
            }, 1500);
        }
    }

    /**
     * Hide indicator
     */
    hide() {
        this.stopStatsUpdate();

        if (this.currentIndicator && this.currentIndicator.parentNode) {
            this.currentIndicator.remove();
        }

        this.currentIndicator = null;
        this.startTime = null;
        this.tokenCount = 0;
    }

    /**
     * Show error state
     * @param {string} errorMessage - Error message
     */
    showError(errorMessage) {
        this.stopStatsUpdate();

        if (this.currentIndicator) {
            this.currentIndicator.className = 'streaming-indicator error-indicator';
            this.currentIndicator.innerHTML = `
                <div class="error-content">
                    <span class="error-icon">⚠️</span>
                    <span class="error-text">${errorMessage}</span>
                </div>
            `;

            // Auto-hide after 3 seconds
            setTimeout(() => {
                this.hide();
            }, 3000);
        }
    }

    /**
     * Calculate tokens per second
     * @returns {number} - Tokens per second
     */
    getTokensPerSecond() {
        if (!this.startTime || this.tokenCount === 0) return 0;

        const elapsed = (Date.now() - this.startTime) / 1000;
        return this.tokenCount / elapsed;
    }

    /**
     * Get current stats
     * @returns {Object} - Current statistics
     */
    getStats() {
        const elapsed = this.startTime ? (Date.now() - this.startTime) / 1000 : 0;
        const tokensPerSec = this.getTokensPerSecond();

        return {
            tokenCount: this.tokenCount,
            elapsedTime: elapsed,
            tokensPerSecond: tokensPerSec.toFixed(1),
            estimatedCompletion: this.estimatedTotal > 0
                ? ((this.estimatedTotal - this.tokenCount) / tokensPerSec).toFixed(1)
                : 0
        };
    }

    /**
     * Reset visualizer state
     */
    reset() {
        this.stopStatsUpdate();
        this.hide();
        this.tokenCount = 0;
        this.startTime = null;
        this.estimatedTotal = 0;
    }
}

// Export for use in main script
window.StreamingVisualizer = StreamingVisualizer;
