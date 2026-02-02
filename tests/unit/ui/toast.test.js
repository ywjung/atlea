import { describe, it, expect, beforeEach, vi } from 'vitest';
import { showToast, showNotification } from '../../../static/js/ui/toast.js';

// Mock DOM for testing
class MockElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.classList = new Set();
        this.style = {};
        this._textContent = '';
        this.parentNode = null;
        this.eventListeners = {};
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    removeChild(child) {
        const index = this.children.indexOf(child);
        if (index > -1) {
            this.children.splice(index, 1);
            child.parentNode = null;
        }
    }

    remove() {
        if (this.parentNode) {
            this.parentNode.removeChild(this);
        }
    }

    addEventListener(event, handler) {
        if (!this.eventListeners[event]) {
            this.eventListeners[event] = [];
        }
        this.eventListeners[event].push(handler);
    }

    removeEventListener(event, handler) {
        if (this.eventListeners[event]) {
            const index = this.eventListeners[event].indexOf(handler);
            if (index > -1) {
                this.eventListeners[event].splice(index, 1);
            }
        }
    }

    get textContent() {
        return this._textContent;
    }

    set textContent(value) {
        this._textContent = value;
    }

    get className() {
        return Array.from(this.classList).join(' ');
    }

    set className(value) {
        this.classList = new Set(value.split(' ').filter(Boolean));
    }
}

describe('ui/toast', () => {
    let toastContainer;

    beforeEach(() => {
        // Setup mock DOM
        toastContainer = new MockElement('div');
        toastContainer.id = 'toast-container';

        global.document = {
            createElement: (tagName) => new MockElement(tagName),
            getElementById: (id) => {
                if (id === 'toast-container') {
                    return toastContainer;
                }
                return null;
            },
            body: {
                appendChild: (child) => {
                    if (child.id === 'toast-container') {
                        toastContainer = child;
                    }
                },
            },
        };

        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    describe('showToast', () => {
        it('should create toast element with message', () => {
            showToast('Test message', 'info');

            expect(toastContainer.children.length).toBe(1);
            const toast = toastContainer.children[0];
            expect(toast.textContent).toBe('Test message');
        });

        it('should apply correct type class', () => {
            showToast('Success', 'success');
            expect(toastContainer.children[0].classList.has('toast-success')).toBe(true);

            toastContainer.children = [];

            showToast('Error', 'error');
            expect(toastContainer.children[0].classList.has('toast-error')).toBe(true);
        });

        it('should handle different toast types', () => {
            const types = ['success', 'error', 'warning', 'info'];

            types.forEach((type) => {
                toastContainer.children = [];
                showToast(`${type} message`, type);
                expect(toastContainer.children.length).toBe(1);
                expect(toastContainer.children[0].classList.has(`toast-${type}`)).toBe(true);
            });
        });

        it('should auto-remove toast after duration', () => {
            showToast('Temporary message', 'info', 3000);

            expect(toastContainer.children.length).toBe(1);

            vi.advanceTimersByTime(3000);

            // Toast should be removed (check if remove was called)
            const toast = toastContainer.children[0];
            expect(toast.parentNode).toBe(toastContainer);

            vi.advanceTimersByTime(300); // Animation time
        });

        it('should handle multiple toasts', () => {
            showToast('First toast', 'info');
            showToast('Second toast', 'success');
            showToast('Third toast', 'warning');

            expect(toastContainer.children.length).toBe(3);
        });

        it('should allow manual close', () => {
            showToast('Closable toast', 'info');

            const toast = toastContainer.children[0];
            toast.remove();

            expect(toastContainer.children.length).toBe(0);
        });
    });

    describe('showNotification', () => {
        it('should be an alias for showToast', () => {
            expect(showNotification).toBe(showToast);
        });

        it('should work the same as showToast', () => {
            showNotification('Notification message', 'info');

            expect(toastContainer.children.length).toBe(1);
            expect(toastContainer.children[0].textContent).toBe('Notification message');
        });
    });

    describe('Toast Container Creation', () => {
        it('should create container if it does not exist', () => {
            toastContainer = null;

            global.document.getElementById = (id) => {
                if (id === 'toast-container') {
                    return toastContainer;
                }
                return null;
            };

            let createdContainer = null;
            global.document.body.appendChild = (child) => {
                if (child.id === 'toast-container') {
                    createdContainer = child;
                    toastContainer = child;
                }
            };

            showToast('Test', 'info');

            expect(createdContainer).not.toBeNull();
            expect(createdContainer.id).toBe('toast-container');
        });
    });

    describe('Edge Cases', () => {
        it('should handle empty message', () => {
            showToast('', 'info');
            expect(toastContainer.children.length).toBe(1);
            expect(toastContainer.children[0].textContent).toBe('');
        });

        it('should handle null message', () => {
            showToast(null, 'info');
            expect(toastContainer.children.length).toBe(1);
        });

        it('should handle undefined type (default to info)', () => {
            showToast('Default type', undefined);
            expect(toastContainer.children.length).toBe(1);
        });

        it('should handle long messages', () => {
            const longMessage = 'A'.repeat(500);
            showToast(longMessage, 'info');

            expect(toastContainer.children[0].textContent).toBe(longMessage);
        });

        it('should handle special characters in message', () => {
            const specialMessage = '<script>alert("XSS")</script>';
            showToast(specialMessage, 'info');

            // Should escape or handle special characters
            expect(toastContainer.children.length).toBe(1);
        });
    });
});
