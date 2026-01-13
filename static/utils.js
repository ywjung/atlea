/**
 * Performance Utilities
 * Reusable helper functions for optimization
 */

// Debounce function - prevents excessive function calls
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Throttle function - limits function execution rate
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// DOM element cache - prevents repeated queries
class DOMCache {
    constructor() {
        this.cache = new Map();
    }

    get(selector, useId = true) {
        if (!this.cache.has(selector)) {
            const element = useId ?
                document.getElementById(selector) :
                document.querySelector(selector);
            if (element) {
                this.cache.set(selector, element);
            }
        }
        return this.cache.get(selector);
    }

    clear() {
        this.cache.clear();
    }

    refresh(selector) {
        this.cache.delete(selector);
        return this.get(selector);
    }
}

// Global DOM cache instance
const domCache = new DOMCache();

// Lazy loader for non-critical features
class LazyLoader {
    constructor() {
        this.loaded = new Set();
    }

    async load(feature, loader) {
        if (this.loaded.has(feature)) {
            return;
        }

        try {
            await loader();
            this.loaded.add(feature);
        } catch (error) {
            logger.error(`Failed to load feature: ${feature}`, error);
        }
    }

    isLoaded(feature) {
        return this.loaded.has(feature);
    }
}

const lazyLoader = new LazyLoader();

// Request queue for batching API calls
class RequestQueue {
    constructor(batchDelay = 50) {
        this.queue = [];
        this.batchDelay = batchDelay;
        this.timeout = null;
    }

    add(request) {
        return new Promise((resolve, reject) => {
            this.queue.push({ request, resolve, reject });

            if (this.timeout) {
                clearTimeout(this.timeout);
            }

            this.timeout = setTimeout(() => {
                this.flush();
            }, this.batchDelay);
        });
    }

    async flush() {
        if (this.queue.length === 0) return;

        const batch = [...this.queue];
        this.queue = [];

        // Process batch
        for (const { request, resolve, reject } of batch) {
            try {
                const result = await request();
                resolve(result);
            } catch (error) {
                reject(error);
            }
        }
    }
}

// Memory-efficient event delegation
function delegateEvent(parent, eventType, selector, handler) {
    parent.addEventListener(eventType, function(event) {
        const target = event.target.closest(selector);
        if (target) {
            handler.call(target, event);
        }
    });
}

// Performance monitoring
class PerformanceMonitor {
    constructor() {
        this.marks = new Map();
    }

    start(label) {
        this.marks.set(label, performance.now());
    }

    end(label) {
        const startTime = this.marks.get(label);
        if (startTime) {
            const duration = performance.now() - startTime;
            this.marks.delete(label);
            return duration;
        }
        return null;
    }

    measure(label, func) {
        this.start(label);
        const result = func();
        this.end(label);
        return result;
    }

    async measureAsync(label, func) {
        this.start(label);
        const result = await func();
        this.end(label);
        return result;
    }
}

const perfMonitor = new PerformanceMonitor();

// Efficient array chunking for large datasets
function chunkArray(array, size) {
    const chunks = [];
    for (let i = 0; i < array.length; i += size) {
        chunks.push(array.slice(i, i + size));
    }
    return chunks;
}

// Safe JSON parse with fallback
function safeJSONParse(str, fallback = null) {
    try {
        return JSON.parse(str);
    } catch (error) {
        logger.error('JSON parse error:', error);
        return fallback;
    }
}

// Memoization for expensive computations
function memoize(func) {
    const cache = new Map();
    return function(...args) {
        const key = JSON.stringify(args);
        if (cache.has(key)) {
            return cache.get(key);
        }
        const result = func.apply(this, args);
        cache.set(key, result);
        return result;
    };
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        debounce,
        throttle,
        domCache,
        lazyLoader,
        RequestQueue,
        delegateEvent,
        perfMonitor,
        chunkArray,
        safeJSONParse,
        memoize
    };
}
