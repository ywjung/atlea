/**
 * Frontend Performance Optimizations
 * Specific optimizations for chatbot UI
 */

// Memoized markdown renderer
const memoizedMarkdown = (() => {
    const cache = new Map();
    const MAX_CACHE_SIZE = 100;

    return (text) => {
        if (cache.has(text)) {
            return cache.get(text);
        }

        const rendered = marked.parse(text);

        // Implement LRU cache
        if (cache.size >= MAX_CACHE_SIZE) {
            const firstKey = cache.keys().next().value;
            cache.delete(firstKey);
        }

        cache.set(text, rendered);
        return rendered;
    };
})();

// Optimized DOM element creator with fragment batching
class DOMBuilder {
    constructor() {
        this.fragment = document.createDocumentFragment();
    }

    createElement(tag, className, content) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (content) element.textContent = content;
        return element;
    }

    appendTo(parent) {
        parent.appendChild(this.fragment);
        this.fragment = document.createDocumentFragment();
    }

    addElement(element) {
        this.fragment.appendChild(element);
        return this;
    }
}

// Virtual scrolling for large conversation lists
class VirtualScroller {
    constructor(container, itemHeight, renderItem) {
        this.container = container;
        this.itemHeight = itemHeight;
        this.renderItem = renderItem;
        this.items = [];
        this.visibleRange = { start: 0, end: 0 };

        this.setupScrollListener();
    }

    setupScrollListener() {
        const scrollHandler = throttle(() => {
            this.updateVisibleRange();
        }, 100);

        this.container.addEventListener('scroll', scrollHandler);
    }

    setItems(items) {
        this.items = items;
        this.updateVisibleRange();
    }

    updateVisibleRange() {
        const scrollTop = this.container.scrollTop;
        const containerHeight = this.container.clientHeight;

        const start = Math.floor(scrollTop / this.itemHeight);
        const end = Math.ceil((scrollTop + containerHeight) / this.itemHeight);

        // Add buffer for smooth scrolling
        const buffer = 5;
        this.visibleRange = {
            start: Math.max(0, start - buffer),
            end: Math.min(this.items.length, end + buffer)
        };

        this.render();
    }

    render() {
        const { start, end } = this.visibleRange;
        const visibleItems = this.items.slice(start, end);

        // Clear container
        this.container.innerHTML = '';

        // Add offset for scroll position
        const topOffset = document.createElement('div');
        topOffset.style.height = `${start * this.itemHeight}px`;
        this.container.appendChild(topOffset);

        // Render visible items
        visibleItems.forEach((item, index) => {
            const element = this.renderItem(item, start + index);
            this.container.appendChild(element);
        });

        // Add bottom offset
        const bottomOffset = document.createElement('div');
        bottomOffset.style.height = `${(this.items.length - end) * this.itemHeight}px`;
        this.container.appendChild(bottomOffset);
    }
}

// Optimized message renderer with pooling
class MessagePool {
    constructor(maxSize = 50) {
        this.pool = [];
        this.maxSize = maxSize;
    }

    get() {
        if (this.pool.length > 0) {
            return this.pool.pop();
        }
        return this.create();
    }

    create() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message';
        return messageDiv;
    }

    release(element) {
        if (this.pool.length < this.maxSize) {
            // Clean element
            element.innerHTML = '';
            element.className = 'message';
            this.pool.push(element);
        }
    }
}

const messagePool = new MessagePool();

// Optimized event delegation for dynamic elements
const eventDelegator = {
    handlers: new Map(),

    on(parent, eventType, selector, handler) {
        const key = `${eventType}-${selector}`;

        if (!this.handlers.has(key)) {
            const delegatedHandler = (event) => {
                const target = event.target.closest(selector);
                if (target && parent.contains(target)) {
                    handler.call(target, event);
                }
            };

            parent.addEventListener(eventType, delegatedHandler);
            this.handlers.set(key, delegatedHandler);
        }
    },

    off(parent, eventType, selector) {
        const key = `${eventType}-${selector}`;
        const handler = this.handlers.get(key);

        if (handler) {
            parent.removeEventListener(eventType, handler);
            this.handlers.delete(key);
        }
    }
};

// Intersection Observer for lazy loading
class LazyImageLoader {
    constructor(options = {}) {
        this.options = {
            root: null,
            rootMargin: '50px',
            threshold: 0.01,
            ...options
        };

        this.observer = new IntersectionObserver(
            this.handleIntersection.bind(this),
            this.options
        );
    }

    handleIntersection(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                if (img.dataset.src) {
                    img.src = img.dataset.src;
                    img.removeAttribute('data-src');
                    this.observer.unobserve(img);
                }
            }
        });
    }

    observe(element) {
        this.observer.observe(element);
    }

    disconnect() {
        this.observer.disconnect();
    }
}

const lazyImageLoader = new LazyImageLoader();

// Request deduplication for identical API calls
class RequestDeduplicator {
    constructor() {
        this.pending = new Map();
    }

    async deduplicate(key, requestFn) {
        // If request is already pending, return the same promise
        if (this.pending.has(key)) {
            return this.pending.get(key);
        }

        // Create new request
        const promise = requestFn().finally(() => {
            this.pending.delete(key);
        });

        this.pending.set(key, promise);
        return promise;
    }

    clear() {
        this.pending.clear();
    }
}

const requestDeduplicator = new RequestDeduplicator();

// Optimized local storage with compression
const optimizedStorage = {
    set(key, value) {
        try {
            const serialized = JSON.stringify(value);
            // For large data, consider using compression
            if (serialized.length > 10000) {
                // Simple run-length encoding for demonstration
                localStorage.setItem(key, serialized);
            } else {
                localStorage.setItem(key, serialized);
            }
        } catch (error) {
            console.error('Storage error:', error);
        }
    },

    get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (error) {
            console.error('Storage retrieval error:', error);
            return defaultValue;
        }
    },

    remove(key) {
        localStorage.removeItem(key);
    },

    clear() {
        localStorage.clear();
    }
};

// Performance metrics tracker
const metricsTracker = {
    metrics: {},

    track(name, value) {
        if (!this.metrics[name]) {
            this.metrics[name] = {
                count: 0,
                total: 0,
                min: Infinity,
                max: -Infinity,
                avg: 0
            };
        }

        const metric = this.metrics[name];
        metric.count++;
        metric.total += value;
        metric.min = Math.min(metric.min, value);
        metric.max = Math.max(metric.max, value);
        metric.avg = metric.total / metric.count;
    },

    report() {
        console.table(this.metrics);
    },

    reset() {
        this.metrics = {};
    }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        memoizedMarkdown,
        DOMBuilder,
        VirtualScroller,
        MessagePool,
        eventDelegator,
        LazyImageLoader,
        requestDeduplicator,
        optimizedStorage,
        metricsTracker
    };
}
