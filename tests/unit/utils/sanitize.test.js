import { describe, it, expect, beforeEach, vi } from 'vitest';
import { sanitizeHTML, safeSetInnerHTML, escapeHtml } from '../../../static/js/utils/sanitize.js';

describe('utils/sanitize', () => {
    describe('escapeHtml', () => {
        it('should escape HTML entities', () => {
            expect(escapeHtml('<script>alert("xss")</script>')).toBe(
                '&lt;script&gt;alert("xss")&lt;/script&gt;'
            );
        });

        it('should escape special characters', () => {
            expect(escapeHtml('< > & " \'')).toContain('&lt;');
            expect(escapeHtml('< > & " \'')).toContain('&gt;');
            expect(escapeHtml('< > & " \'')).toContain('&amp;');
        });

        it('should handle normal text', () => {
            expect(escapeHtml('Hello World')).toBe('Hello World');
        });

        it('should handle empty string', () => {
            expect(escapeHtml('')).toBe('');
        });
    });

    describe('sanitizeHTML', () => {
        beforeEach(() => {
            // Mock DOMPurify
            global.DOMPurify = {
                sanitize: vi.fn((dirty, config) => {
                    // Simple mock: remove script tags
                    return dirty.replace(/<script[^>]*>.*?<\/script>/gi, '');
                })
            };
        });

        it('should sanitize HTML', () => {
            const dirty = '<div>Safe</div><script>alert("xss")</script>';
            const clean = sanitizeHTML(dirty);
            expect(clean).toBe('<div>Safe</div>');
            expect(global.DOMPurify.sanitize).toHaveBeenCalled();
        });

        it('should pass config to DOMPurify', () => {
            const config = { ALLOWED_TAGS: ['div'] };
            sanitizeHTML('<div>test</div>', config);
            expect(global.DOMPurify.sanitize).toHaveBeenCalledWith(
                '<div>test</div>',
                expect.objectContaining(config)
            );
        });

        it('should fallback when DOMPurify is not available', () => {
            delete global.DOMPurify;
            const dirty = '<div>Test</div><script>alert("xss")</script>';
            const clean = sanitizeHTML(dirty);
            // Should strip all HTML tags
            expect(clean).not.toContain('<script>');
            expect(clean).not.toContain('<div>');
        });
    });

    describe('safeSetInnerHTML', () => {
        beforeEach(() => {
            global.DOMPurify = {
                sanitize: vi.fn((dirty) => dirty.replace(/<script[^>]*>.*?<\/script>/gi, ''))
            };
        });

        it('should set sanitized HTML', () => {
            const el = document.createElement('div');
            const html = '<p>Safe</p><script>alert("xss")</script>';
            safeSetInnerHTML(el, html);
            expect(el.innerHTML).toBe('<p>Safe</p>');
        });

        it('should handle null element', () => {
            expect(() => safeSetInnerHTML(null, '<div>test</div>')).not.toThrow();
        });

        it('should pass config to sanitizeHTML', () => {
            const el = document.createElement('div');
            const config = { ALLOWED_TAGS: ['p'] };
            safeSetInnerHTML(el, '<p>test</p>', config);
            expect(global.DOMPurify.sanitize).toHaveBeenCalledWith(
                '<p>test</p>',
                expect.objectContaining(config)
            );
        });
    });
});
