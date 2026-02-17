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
     * Show simple typing indicator
     * @param {HTMLElement} container - Container to append indicator
     * @returns {HTMLElement} - The indicator element
     */
    showTypingIndicator(container) {
        this.startTime = Date.now();
        this.tokenCount = 0;

        // Show simple, clean loading UI
        const indicator = document.createElement('div');
        indicator.className = 'streaming-indicator simple-indicator';
        indicator.id = 'streamingProgress';
        indicator.innerHTML = `
            <div class="simple-indicator-content">
                <div class="macos-dots">
                    <span class="dot dot-red"></span>
                    <span class="dot dot-yellow"></span>
                    <span class="dot dot-green"></span>
                </div>
                <span class="simple-text">답변 생성 중...</span>
            </div>
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
        // Keep the same simple UI, no need to change
        return this.currentIndicator;
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
                elapsedTimeEl.textContent = elapsed.toFixed(1);
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
        if (this.currentIndicator) {
            // Simply fade out and remove
            this.currentIndicator.style.opacity = '0';
            setTimeout(() => {
                this.hide();
            }, 300);
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
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-content';
            const iconSpan = document.createElement('span');
            iconSpan.className = 'error-icon';
            iconSpan.textContent = '⚠️';
            const textSpan = document.createElement('span');
            textSpan.className = 'error-text';
            textSpan.textContent = errorMessage;
            errorDiv.appendChild(iconSpan);
            errorDiv.appendChild(textSpan);
            this.currentIndicator.innerHTML = '';
            this.currentIndicator.appendChild(errorDiv);

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
