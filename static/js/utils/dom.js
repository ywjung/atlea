/**
 * DOM Manipulation Utilities
 * 
 * Helpers for creating and manipulating DOM elements.
 */

/**
 * Create element with attributes and children
 * @param {string} tag - HTML tag name
 * @param {Object} attributes - Element attributes
 * @param {Array<Node|string>} children - Child elements or text
 * @returns {HTMLElement} - Created element
 */
export function createElement(tag, attributes = {}, children = []) {
    const element = document.createElement(tag);
    
    // Set attributes
    Object.entries(attributes).forEach(([key, value]) => {
        if (key === 'className') {
            element.className = value;
        } else if (key === 'dataset') {
            Object.entries(value).forEach(([dataKey, dataValue]) => {
                element.dataset[dataKey] = dataValue;
            });
        } else if (key.startsWith('on') && typeof value === 'function') {
            const event = key.substring(2).toLowerCase();
            element.addEventListener(event, value);
        } else {
            element.setAttribute(key, value);
        }
    });
    
    // Append children
    children.forEach(child => {
        if (typeof child === 'string') {
            element.appendChild(document.createTextNode(child));
        } else if (child instanceof Node) {
            element.appendChild(child);
        }
    });
    
    return element;
}

/**
 * Query selector with error handling
 * @param {string} selector - CSS selector
 * @param {Element} parent - Parent element (default: document)
 * @returns {Element|null} - Found element or null
 */
export function $(selector, parent = document) {
    try {
        return parent.querySelector(selector);
    } catch (error) {
        console.error(`Invalid selector: ${selector}`, error);
        return null;
    }
}

/**
 * Query selector all with error handling
 * @param {string} selector - CSS selector
 * @param {Element} parent - Parent element (default: document)
 * @returns {Element[]} - Array of found elements
 */
export function $$(selector, parent = document) {
    try {
        return Array.from(parent.querySelectorAll(selector));
    } catch (error) {
        console.error(`Invalid selector: ${selector}`, error);
        return [];
    }
}

/**
 * Add class to element
 * @param {Element} element - Target element
 * @param {...string} classes - Classes to add
 */
export function addClass(element, ...classes) {
    if (element) {
        element.classList.add(...classes);
    }
}

/**
 * Remove class from element
 * @param {Element} element - Target element
 * @param {...string} classes - Classes to remove
 */
export function removeClass(element, ...classes) {
    if (element) {
        element.classList.remove(...classes);
    }
}

/**
 * Toggle class on element
 * @param {Element} element - Target element
 * @param {string} className - Class to toggle
 * @param {boolean} force - Force add/remove
 * @returns {boolean} - True if class is now present
 */
export function toggleClass(element, className, force = undefined) {
    if (element) {
        return element.classList.toggle(className, force);
    }
    return false;
}

/**
 * Check if element has class
 * @param {Element} element - Target element
 * @param {string} className - Class to check
 * @returns {boolean} - True if element has class
 */
export function hasClass(element, className) {
    return element ? element.classList.contains(className) : false;
}

/**
 * Show element
 * @param {Element} element - Target element
 * @param {string} display - Display value (default: 'block')
 */
export function show(element, display = 'block') {
    if (element) {
        element.style.display = display;
    }
}

/**
 * Hide element
 * @param {Element} element - Target element
 */
export function hide(element) {
    if (element) {
        element.style.display = 'none';
    }
}

/**
 * Toggle element visibility
 * @param {Element} element - Target element
 * @param {boolean} force - Force show/hide
 */
export function toggle(element, force = undefined) {
    if (!element) return;
    
    if (force === true) {
        show(element);
    } else if (force === false) {
        hide(element);
    } else {
        if (element.style.display === 'none') {
            show(element);
        } else {
            hide(element);
        }
    }
}

/**
 * Remove all children from element
 * @param {Element} element - Target element
 */
export function empty(element) {
    if (element) {
        while (element.firstChild) {
            element.removeChild(element.firstChild);
        }
    }
}

/**
 * Get or set element text content
 * @param {Element} element - Target element
 * @param {string} text - Text to set (optional)
 * @returns {string|void} - Current text if getting
 */
export function text(element, text = undefined) {
    if (!element) return '';
    
    if (text === undefined) {
        return element.textContent;
    } else {
        element.textContent = text;
    }
}

/**
 * Wait for element to appear in DOM
 * @param {string} selector - CSS selector
 * @param {number} timeout - Timeout in ms (default: 5000)
 * @returns {Promise<Element>} - Found element
 */
export function waitForElement(selector, timeout = 5000) {
    return new Promise((resolve, reject) => {
        const element = document.querySelector(selector);
        if (element) {
            resolve(element);
            return;
        }

        const observer = new MutationObserver(() => {
            const element = document.querySelector(selector);
            if (element) {
                observer.disconnect();
                resolve(element);
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        setTimeout(() => {
            observer.disconnect();
            reject(new Error(`Element not found: ${selector}`));
        }, timeout);
    });
}

/**
 * Debounce function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @returns {Function} - Debounced function
 */
export function debounce(func, wait) {
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

/**
 * Throttle function calls
 * @param {Function} func - Function to throttle
 * @param {number} limit - Time limit in ms
 * @returns {Function} - Throttled function
 */
export function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}
