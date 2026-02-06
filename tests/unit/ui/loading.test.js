import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    showLoading,
    updateLoadingMessage,
    hideLoading,
    createSpinner,
} from '../../../static/js/ui/loading.js';

// Mock createElement from dom.js
vi.mock('../../../static/js/utils/dom.js', () => ({
    createElement: (tag, attributes = {}, children = []) => {
        const element = document.createElement(tag);
        Object.entries(attributes).forEach(([key, value]) => {
            if (key === 'className') {
                element.className = value;
            } else {
                element.setAttribute(key, value);
            }
        });
        children.forEach(child => {
            if (typeof child === 'string') {
                element.appendChild(document.createTextNode(child));
            } else {
                element.appendChild(child);
            }
        });
        return element;
    }
}));

describe('ui/loading', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
    });

    describe('showLoading', () => {
        it('should create loading indicator in container', () => {
            const container = document.createElement('div');
            document.body.appendChild(container);

            const loadingId = showLoading(container);

            expect(loadingId).toBe('loading-msg');
            expect(container.querySelector('#loading-msg')).not.toBeNull();
        });

        it('should display custom message', () => {
            const container = document.createElement('div');
            document.body.appendChild(container);

            showLoading(container, '처리 중...');

            const loadingText = container.querySelector('#loading-text');
            expect(loadingText.textContent).toBe('처리 중...');
        });

        it('should create stop button when onStop is provided', () => {
            const container = document.createElement('div');
            const onStop = vi.fn();

            showLoading(container, '로딩 중...', onStop);

            const stopBtn = container.querySelector('#stop-btn');
            expect(stopBtn).not.toBeNull();
        });

        it('should call onStop when stop button is clicked', () => {
            const container = document.createElement('div');
            const onStop = vi.fn();

            showLoading(container, '로딩 중...', onStop);

            const stopBtn = container.querySelector('#stop-btn');
            stopBtn.click();

            expect(onStop).toHaveBeenCalled();
        });

        it('should not create stop button when onStop is null', () => {
            const container = document.createElement('div');

            showLoading(container, '로딩 중...', null);

            const stopBtn = container.querySelector('#stop-btn');
            expect(stopBtn).toBeNull();
        });

        it('should auto-scroll container', () => {
            const container = document.createElement('div');
            container.style.height = '100px';
            container.style.overflow = 'auto';
            document.body.appendChild(container);

            // Add some content to enable scrolling
            for (let i = 0; i < 10; i++) {
                const div = document.createElement('div');
                div.style.height = '50px';
                container.appendChild(div);
            }

            const originalScrollHeight = container.scrollHeight;
            showLoading(container);

            // scrollTop should be set to scrollHeight
            expect(container.scrollTop).toBe(originalScrollHeight);
        });
    });

    describe('updateLoadingMessage', () => {
        it('should update loading text', () => {
            const loadingText = document.createElement('div');
            loadingText.id = 'loading-text';
            loadingText.textContent = '로딩 중...';
            document.body.appendChild(loadingText);

            updateLoadingMessage('업데이트 중...');

            expect(loadingText.textContent).toBe('업데이트 중...');
        });

        it('should handle missing loading element', () => {
            expect(() => updateLoadingMessage('테스트')).not.toThrow();
        });
    });

    describe('hideLoading', () => {
        it('should remove loading indicator', () => {
            const loadingMsg = document.createElement('div');
            loadingMsg.id = 'loading-msg';
            document.body.appendChild(loadingMsg);

            expect(document.getElementById('loading-msg')).not.toBeNull();

            hideLoading();

            expect(document.getElementById('loading-msg')).toBeNull();
        });

        it('should handle missing loading element', () => {
            expect(() => hideLoading()).not.toThrow();
        });
    });

    describe('createSpinner', () => {
        it('should create spinner with default size', () => {
            const spinner = createSpinner();

            expect(spinner.className).toContain('spinner');
            expect(spinner.className).toContain('spinner-medium');
        });

        it('should create spinner with custom size', () => {
            const small = createSpinner('small');
            expect(small.className).toContain('spinner-small');

            const large = createSpinner('large');
            expect(large.className).toContain('spinner-large');
        });

        it('should contain spinner dots', () => {
            const spinner = createSpinner();
            const dots = spinner.querySelectorAll('.spinner-dot');
            expect(dots.length).toBe(3);
        });
    });
});
