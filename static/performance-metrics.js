/**
 * Performance Metrics - Frontend performance monitoring and analytics
 *
 * Changelog:
 * - 2025-12-30: Created performance monitoring system
 *   - Page load metrics (LCP, FID, CLS)
 *   - API call latency tracking
 *   - User interaction metrics
 *   - Error rate monitoring
 */

class PerformanceMetrics {
    constructor() {
        this.metrics = {
            pageLoad: {},
            apiCalls: [],
            interactions: [],
            errors: [],
            webVitals: {}
        };

        this.startTime = performance.now();
        this.apiCallCounter = 0;
        this.errorCounter = 0;

        // Initialize monitoring
        this.initPageLoadMetrics();
        this.initWebVitals();
        this.initAPIMonitoring();
        this.initErrorTracking();

        logger.info('📊 Performance metrics initialized');
    }

    /**
     * Initialize page load metrics
     */
    initPageLoadMetrics() {
        if (document.readyState === 'complete') {
            this.capturePageLoadMetrics();
        } else {
            window.addEventListener('load', () => this.capturePageLoadMetrics());
        }
    }

    /**
     * Capture page load performance metrics
     */
    capturePageLoadMetrics() {
        const perfData = performance.getEntriesByType('navigation')[0];
        if (!perfData) return;

        this.metrics.pageLoad = {
            dns: perfData.domainLookupEnd - perfData.domainLookupStart,
            tcp: perfData.connectEnd - perfData.connectStart,
            ttfb: perfData.responseStart - perfData.requestStart,
            download: perfData.responseEnd - perfData.responseStart,
            domReady: perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart,
            loadComplete: perfData.loadEventEnd - perfData.loadEventStart,
            totalLoad: perfData.loadEventEnd - perfData.fetchStart
        };

        logger.debug('Page load metrics:', this.metrics.pageLoad);
    }

    /**
     * Initialize Web Vitals monitoring (Core Web Vitals)
     */
    initWebVitals() {
        // LCP (Largest Contentful Paint)
        this.observeLCP();

        // FID (First Input Delay) / INP (Interaction to Next Paint)
        this.observeFID();

        // CLS (Cumulative Layout Shift)
        this.observeCLS();
    }

    /**
     * Observe Largest Contentful Paint
     */
    observeLCP() {
        const observer = new PerformanceObserver((list) => {
            const entries = list.getEntries();
            const lastEntry = entries[entries.length - 1];
            this.metrics.webVitals.lcp = lastEntry.renderTime || lastEntry.loadTime;
            logger.debug(`📏 LCP: ${this.metrics.webVitals.lcp}ms`);
        });

        observer.observe({ type: 'largest-contentful-paint', buffered: true });
    }

    /**
     * Observe First Input Delay
     */
    observeFID() {
        const observer = new PerformanceObserver((list) => {
            const entries = list.getEntries();
            entries.forEach((entry) => {
                this.metrics.webVitals.fid = entry.processingStart - entry.startTime;
                logger.debug(`⚡ FID: ${this.metrics.webVitals.fid}ms`);
            });
        });

        observer.observe({ type: 'first-input', buffered: true });
    }

    /**
     * Observe Cumulative Layout Shift
     */
    observeCLS() {
        let clsValue = 0;
        const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (!entry.hadRecentInput) {
                    clsValue += entry.value;
                }
            }
            this.metrics.webVitals.cls = clsValue;
            logger.debug(`📐 CLS: ${clsValue.toFixed(3)}`);
        });

        observer.observe({ type: 'layout-shift', buffered: true });
    }

    /**
     * Initialize API call monitoring
     */
    initAPIMonitoring() {
        // Intercept fetch calls
        const originalFetch = window.fetch;
        const self = this;

        window.fetch = async function(...args) {
            const startTime = performance.now();
            const url = args[0];
            const callId = ++self.apiCallCounter;

            try {
                const response = await originalFetch.apply(this, args);
                const duration = performance.now() - startTime;

                self.recordAPICall({
                    id: callId,
                    url: url,
                    method: args[1]?.method || 'GET',
                    status: response.status,
                    duration: duration,
                    success: response.ok,
                    timestamp: Date.now()
                });

                return response;
            } catch (error) {
                const duration = performance.now() - startTime;

                self.recordAPICall({
                    id: callId,
                    url: url,
                    method: args[1]?.method || 'GET',
                    status: 0,
                    duration: duration,
                    success: false,
                    error: error.message,
                    timestamp: Date.now()
                });

                throw error;
            }
        };
    }

    /**
     * Record API call metrics
     */
    recordAPICall(callData) {
        this.metrics.apiCalls.push(callData);

        // Keep only last 100 API calls
        if (this.metrics.apiCalls.length > 100) {
            this.metrics.apiCalls.shift();
        }

        // Log slow API calls (> 1s)
        if (callData.duration > 1000) {
            logger.warn(`🐌 Slow API call: ${callData.url} took ${callData.duration.toFixed(2)}ms`);
        }

        logger.debug(`API ${callData.method} ${callData.url}: ${callData.duration.toFixed(2)}ms [${callData.status}]`);
    }

    /**
     * Initialize error tracking
     */
    initErrorTracking() {
        window.addEventListener('error', (event) => {
            this.recordError({
                type: 'javascript',
                message: event.message,
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
                stack: event.error?.stack,
                timestamp: Date.now()
            });
        });

        window.addEventListener('unhandledrejection', (event) => {
            this.recordError({
                type: 'promise',
                message: event.reason?.message || 'Unhandled Promise Rejection',
                stack: event.reason?.stack,
                timestamp: Date.now()
            });
        });
    }

    /**
     * Record error
     */
    recordError(errorData) {
        this.metrics.errors.push(errorData);
        this.errorCounter++;

        // Keep only last 50 errors
        if (this.metrics.errors.length > 50) {
            this.metrics.errors.shift();
        }

        logger.error(`❌ Error recorded:`, errorData);
    }

    /**
     * Record user interaction
     */
    recordInteraction(type, metadata = {}) {
        this.metrics.interactions.push({
            type: type,
            metadata: metadata,
            timestamp: Date.now()
        });

        // Keep only last 100 interactions
        if (this.metrics.interactions.length > 100) {
            this.metrics.interactions.shift();
        }

        logger.debug(`👆 Interaction: ${type}`, metadata);
    }

    /**
     * Get API call statistics
     */
    getAPIStats() {
        if (this.metrics.apiCalls.length === 0) {
            return {
                total: 0,
                avgDuration: 0,
                successRate: 0,
                slowCalls: 0
            };
        }

        const total = this.metrics.apiCalls.length;
        const successful = this.metrics.apiCalls.filter(c => c.success).length;
        const durations = this.metrics.apiCalls.map(c => c.duration);
        const avgDuration = durations.reduce((a, b) => a + b, 0) / total;
        const slowCalls = this.metrics.apiCalls.filter(c => c.duration > 1000).length;

        return {
            total: total,
            avgDuration: avgDuration,
            successRate: (successful / total) * 100,
            slowCalls: slowCalls,
            minDuration: Math.min(...durations),
            maxDuration: Math.max(...durations)
        };
    }

    /**
     * Get performance summary
     */
    getSummary() {
        const apiStats = this.getAPIStats();
        const uptime = ((Date.now() - this.startTime) / 1000).toFixed(2);

        return {
            uptime: `${uptime}s`,
            pageLoad: this.metrics.pageLoad,
            webVitals: {
                lcp: this.metrics.webVitals.lcp ? `${this.metrics.webVitals.lcp.toFixed(2)}ms` : 'N/A',
                fid: this.metrics.webVitals.fid ? `${this.metrics.webVitals.fid.toFixed(2)}ms` : 'N/A',
                cls: this.metrics.webVitals.cls ? this.metrics.webVitals.cls.toFixed(3) : 'N/A'
            },
            api: {
                totalCalls: apiStats.total,
                avgLatency: `${apiStats.avgDuration.toFixed(2)}ms`,
                successRate: `${apiStats.successRate.toFixed(1)}%`,
                slowCalls: apiStats.slowCalls
            },
            errors: {
                total: this.errorCounter,
                recent: this.metrics.errors.length
            },
            interactions: {
                total: this.metrics.interactions.length
            }
        };
    }

    /**
     * Print performance report to console
     */
    printReport() {
        // Only print in development mode or when explicitly called
        const DEBUG_MODE = false; // Set to true to enable performance logging
        if (!DEBUG_MODE) return;

        const summary = this.getSummary();

        console.group('%c📊 Performance Report', 'font-weight: bold; font-size: 1.2em; color: #667eea;');

        logger.debug('%c⏱️  Uptime:', 'font-weight: bold;', summary.uptime);

        console.group('%c📄 Page Load', 'font-weight: bold;');
        Object.entries(summary.pageLoad).forEach(([key, value]) => {
            logger.debug(`${key}: ${value}ms`);
        });
        console.groupEnd();

        console.group('%c🎯 Core Web Vitals', 'font-weight: bold;');
        logger.debug(`LCP (Largest Contentful Paint): ${summary.webVitals.lcp}`);
        logger.debug(`FID (First Input Delay): ${summary.webVitals.fid}`);
        logger.debug(`CLS (Cumulative Layout Shift): ${summary.webVitals.cls}`);
        console.groupEnd();

        console.group('%c🌐 API Calls', 'font-weight: bold;');
        logger.debug(`Total Calls: ${summary.api.totalCalls}`);
        logger.debug(`Average Latency: ${summary.api.avgLatency}`);
        logger.debug(`Success Rate: ${summary.api.successRate}`);
        logger.debug(`Slow Calls (>1s): ${summary.api.slowCalls}`);
        console.groupEnd();

        console.group('%c❌ Errors', 'font-weight: bold;');
        logger.debug(`Total Errors: ${summary.errors.total}`);
        logger.debug(`Recent Errors: ${summary.errors.recent}`);
        console.groupEnd();

        console.groupEnd();
    }

    /**
     * Send metrics to server (optional analytics endpoint)
     */
    async sendToServer() {
        const summary = this.getSummary();

        try {
            await fetch('/api/metrics', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(summary)
            });
            logger.debug('📤 Metrics sent to server');
        } catch (error) {
            logger.warn('Failed to send metrics:', error);
        }
    }
}

// Create global performance metrics instance
const performanceMetrics = new PerformanceMetrics();

// Expose to window for debugging
window.performanceMetrics = performanceMetrics;

// Print report on demand (Ctrl+Shift+P)
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'P') {
        e.preventDefault();
        performanceMetrics.printReport();
    }
});

// Auto-print report every 5 minutes in development
if (logger.environment === 'development') {
    setInterval(() => {
        performanceMetrics.printReport();
    }, 5 * 60 * 1000);
}
