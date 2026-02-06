import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    createElement,
    $,
    $$,
    addClass,
    removeClass,
    toggleClass,
    hasClass,
    show,
    hide,
    toggle,
    empty,
    text,
    waitForElement,
    debounce,
    throttle,
} from '../../../static/js/utils/dom.js';

describe('utils/dom', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
    });

    describe('createElement', () => {
        it('should create element with tag', () => {
            const el = createElement('div');
            expect(el.tagName).toBe('DIV');
        });

        it('should set class name', () => {
            const el = createElement('div', { className: 'test-class' });
            expect(el.className).toBe('test-class');
        });

        it('should set attributes', () => {
            const el = createElement('div', { id: 'test-id', title: 'Test' });
            expect(el.id).toBe('test-id');
            expect(el.getAttribute('title')).toBe('Test');
        });

        it('should set dataset', () => {
            const el = createElement('div', { dataset: { userId: '123', role: 'admin' } });
            expect(el.dataset.userId).toBe('123');
            expect(el.dataset.role).toBe('admin');
        });

        it('should add event listeners', () => {
            const onClick = vi.fn();
            const el = createElement('button', { onClick });
            el.click();
            expect(onClick).toHaveBeenCalled();
        });

        it('should append text children', () => {
            const el = createElement('div', {}, ['Hello', ' ', 'World']);
            expect(el.textContent).toBe('Hello World');
        });

        it('should append element children', () => {
            const child = document.createElement('span');
            const el = createElement('div', {}, [child]);
            expect(el.children.length).toBe(1);
            expect(el.children[0].tagName).toBe('SPAN');
        });
    });

    describe('$ (querySelector)', () => {
        it('should find element', () => {
            document.body.innerHTML = '<div id="test">Test</div>';
            const el = $('#test');
            expect(el).not.toBeNull();
            expect(el.id).toBe('test');
        });

        it('should return null for non-existent element', () => {
            const el = $('#non-existent');
            expect(el).toBeNull();
        });

        it('should search within parent', () => {
            const parent = createElement('div', {}, [
                createElement('span', { id: 'child' })
            ]);
            const child = $('#child', parent);
            expect(child).not.toBeNull();
            expect(child.id).toBe('child');
        });

        it('should handle invalid selector', () => {
            const el = $('<<<invalid>>>');
            expect(el).toBeNull();
        });
    });

    describe('$$ (querySelectorAll)', () => {
        it('should find all elements', () => {
            document.body.innerHTML = '<div class="test"></div><div class="test"></div>';
            const els = $$('.test');
            expect(els).toHaveLength(2);
        });

        it('should return empty array for non-existent elements', () => {
            const els = $$('.non-existent');
            expect(els).toEqual([]);
        });

        it('should search within parent', () => {
            const parent = createElement('div', {}, [
                createElement('span', { className: 'child' }),
                createElement('span', { className: 'child' })
            ]);
            const children = $$('.child', parent);
            expect(children).toHaveLength(2);
        });
    });

    describe('addClass', () => {
        it('should add single class', () => {
            const el = document.createElement('div');
            addClass(el, 'test');
            expect(el.classList.contains('test')).toBe(true);
        });

        it('should add multiple classes', () => {
            const el = document.createElement('div');
            addClass(el, 'class1', 'class2', 'class3');
            expect(el.classList.contains('class1')).toBe(true);
            expect(el.classList.contains('class2')).toBe(true);
            expect(el.classList.contains('class3')).toBe(true);
        });

        it('should handle null element', () => {
            expect(() => addClass(null, 'test')).not.toThrow();
        });
    });

    describe('removeClass', () => {
        it('should remove single class', () => {
            const el = document.createElement('div');
            el.className = 'test remove';
            removeClass(el, 'remove');
            expect(el.classList.contains('remove')).toBe(false);
            expect(el.classList.contains('test')).toBe(true);
        });

        it('should remove multiple classes', () => {
            const el = document.createElement('div');
            el.className = 'class1 class2 class3';
            removeClass(el, 'class1', 'class3');
            expect(el.classList.contains('class2')).toBe(true);
            expect(el.classList.contains('class1')).toBe(false);
            expect(el.classList.contains('class3')).toBe(false);
        });

        it('should handle null element', () => {
            expect(() => removeClass(null, 'test')).not.toThrow();
        });
    });

    describe('toggleClass', () => {
        it('should toggle class', () => {
            const el = document.createElement('div');
            toggleClass(el, 'test');
            expect(el.classList.contains('test')).toBe(true);
            toggleClass(el, 'test');
            expect(el.classList.contains('test')).toBe(false);
        });

        it('should force add class', () => {
            const el = document.createElement('div');
            toggleClass(el, 'test', true);
            expect(el.classList.contains('test')).toBe(true);
            toggleClass(el, 'test', true);
            expect(el.classList.contains('test')).toBe(true);
        });

        it('should force remove class', () => {
            const el = document.createElement('div');
            el.className = 'test';
            toggleClass(el, 'test', false);
            expect(el.classList.contains('test')).toBe(false);
        });

        it('should return false for null element', () => {
            expect(toggleClass(null, 'test')).toBe(false);
        });
    });

    describe('hasClass', () => {
        it('should return true if element has class', () => {
            const el = document.createElement('div');
            el.className = 'test active';
            expect(hasClass(el, 'test')).toBe(true);
            expect(hasClass(el, 'active')).toBe(true);
        });

        it('should return false if element does not have class', () => {
            const el = document.createElement('div');
            expect(hasClass(el, 'test')).toBe(false);
        });

        it('should return false for null element', () => {
            expect(hasClass(null, 'test')).toBe(false);
        });
    });

    describe('show/hide/toggle', () => {
        it('should show element', () => {
            const el = document.createElement('div');
            el.style.display = 'none';
            show(el);
            expect(el.style.display).toBe('block');
        });

        it('should show element with custom display', () => {
            const el = document.createElement('div');
            show(el, 'flex');
            expect(el.style.display).toBe('flex');
        });

        it('should hide element', () => {
            const el = document.createElement('div');
            hide(el);
            expect(el.style.display).toBe('none');
        });

        it('should toggle element', () => {
            const el = document.createElement('div');
            el.style.display = 'block';
            toggle(el);
            expect(el.style.display).toBe('none');
            toggle(el);
            expect(el.style.display).toBe('block');
        });

        it('should force show', () => {
            const el = document.createElement('div');
            el.style.display = 'none';
            toggle(el, true);
            expect(el.style.display).toBe('block');
        });

        it('should force hide', () => {
            const el = document.createElement('div');
            toggle(el, false);
            expect(el.style.display).toBe('none');
        });
    });

    describe('empty', () => {
        it('should remove all children', () => {
            const el = createElement('div', {}, [
                'text',
                createElement('span'),
                createElement('div')
            ]);
            expect(el.childNodes.length).toBe(3);
            empty(el);
            expect(el.childNodes.length).toBe(0);
        });

        it('should handle null element', () => {
            expect(() => empty(null)).not.toThrow();
        });
    });

    describe('text', () => {
        it('should get text content', () => {
            const el = createElement('div', {}, ['Hello World']);
            expect(text(el)).toBe('Hello World');
        });

        it('should set text content', () => {
            const el = createElement('div');
            text(el, 'New Text');
            expect(el.textContent).toBe('New Text');
        });

        it('should return empty string for null element', () => {
            expect(text(null)).toBe('');
        });
    });

    describe('debounce', () => {
        it('should debounce function calls', async () => {
            vi.useFakeTimers();
            const fn = vi.fn();
            const debounced = debounce(fn, 100);

            debounced();
            debounced();
            debounced();

            expect(fn).not.toHaveBeenCalled();

            vi.advanceTimersByTime(100);
            expect(fn).toHaveBeenCalledTimes(1);

            vi.useRealTimers();
        });
    });

    describe('throttle', () => {
        it('should throttle function calls', async () => {
            vi.useFakeTimers();
            const fn = vi.fn();
            const throttled = throttle(fn, 100);

            throttled();
            throttled();
            throttled();

            expect(fn).toHaveBeenCalledTimes(1);

            vi.advanceTimersByTime(100);
            throttled();
            expect(fn).toHaveBeenCalledTimes(2);

            vi.useRealTimers();
        });
    });

    describe('waitForElement', () => {
        it('should resolve immediately if element exists', async () => {
            document.body.innerHTML = '<div id="exists">Test</div>';
            const el = await waitForElement('#exists');
            expect(el.id).toBe('exists');
        });

        it.skip('should wait for element to appear', async () => {
            // Complex MutationObserver test - skip for now
            const promise = waitForElement('#delayed', 1000);
            setTimeout(() => {
                document.body.innerHTML = '<div id="delayed">Test</div>';
            }, 100);
            const el = await promise;
            expect(el.id).toBe('delayed');
        });
    });
});
