import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    isAsciiArt,
    normalizeLanguageClass,
    renderMath,
    highlightCodeBlocks,
} from '../../../static/js/markdown/helpers.js';

describe('markdown/helpers', () => {
    describe('isAsciiArt', () => {
        it('should return false for known programming languages', () => {
            expect(isAsciiArt('const x = 1;', 'javascript')).toBe(false);
            expect(isAsciiArt('def foo():', 'python')).toBe(false);
            expect(isAsciiArt('public class Test {}', 'java')).toBe(false);
        });

        it('should detect box-drawing characters', () => {
            const boxArt = '┌─────┐\n│ Box │\n└─────┘';
            expect(isAsciiArt(boxArt, '')).toBe(true);
        });

        it('should detect ASCII art patterns', () => {
            const asciiArt = `
            +-----+
            |     |
            +-----+
            `;
            expect(isAsciiArt(asciiArt, '')).toBe(true);
        });

        it('should return false for short text', () => {
            expect(isAsciiArt('x', '')).toBe(false);
            expect(isAsciiArt('line1\nline2', '')).toBe(false);
        });

        it('should detect diagram keywords', () => {
            const diagram = '┌─ diagram ─┐';
            expect(isAsciiArt(diagram, '')).toBe(true);
        });
    });

    describe('normalizeLanguageClass', () => {
        it('should normalize java abbreviations', () => {
            const block = document.createElement('code');
            block.className = 'language-jav';
            normalizeLanguageClass(block);
            expect(block.classList.contains('language-java')).toBe(true);
            expect(block.classList.contains('language-jav')).toBe(false);
        });

        it('should normalize python abbreviations', () => {
            const block = document.createElement('code');
            block.className = 'language-py';
            normalizeLanguageClass(block);
            expect(block.classList.contains('language-python')).toBe(true);
        });

        it('should normalize javascript abbreviations', () => {
            const block = document.createElement('code');
            block.className = 'language-js';
            normalizeLanguageClass(block);
            expect(block.classList.contains('language-javascript')).toBe(true);
        });

        it('should normalize typescript abbreviations', () => {
            const block = document.createElement('code');
            block.className = 'language-ts';
            normalizeLanguageClass(block);
            expect(block.classList.contains('language-typescript')).toBe(true);
        });

        it('should normalize yaml abbreviations', () => {
            const block = document.createElement('code');
            block.className = 'language-yml';
            normalizeLanguageClass(block);
            expect(block.classList.contains('language-yaml')).toBe(true);
        });

        it('should normalize shell abbreviations', () => {
            const block = document.createElement('code');
            block.className = 'language-sh';
            normalizeLanguageClass(block);
            expect(block.classList.contains('language-bash')).toBe(true);
        });

        it('should fallback unsupported to plaintext', () => {
            global.hljs = {
                getLanguage: vi.fn(() => null)
            };
            const block = document.createElement('code');
            block.className = 'language-unknownlang';
            normalizeLanguageClass(block);
            expect(block.classList.contains('language-plaintext')).toBe(true);
        });

        it('should keep supported languages', () => {
            const block = document.createElement('code');
            block.className = 'language-javascript';
            normalizeLanguageClass(block);
            expect(block.classList.contains('language-javascript')).toBe(true);
        });
    });

    describe('renderMath', () => {
        it('should skip when KaTeX is not available', () => {
            const element = document.createElement('div');
            expect(() => renderMath(element)).not.toThrow();
        });

        it('should call renderMathInElement when available', () => {
            const mockRender = vi.fn();
            global.renderMathInElement = mockRender;
            
            const element = document.createElement('div');
            renderMath(element);
            
            expect(mockRender).toHaveBeenCalledWith(element, expect.any(Object));
            delete global.renderMathInElement;
        });

        it('should handle rendering errors', () => {
            global.renderMathInElement = vi.fn(() => {
                throw new Error('Render error');
            });
            
            const element = document.createElement('div');
            expect(() => renderMath(element)).not.toThrow();
            
            delete global.renderMathInElement;
        });
    });

    describe('highlightCodeBlocks', () => {
        beforeEach(() => {
            delete global.hljs;
        });

        it('should skip when hljs is not available', () => {
            const container = document.createElement('div');
            container.innerHTML = '<pre><code>test</code></pre>';
            expect(() => highlightCodeBlocks(container)).not.toThrow();
        });

        it('should highlight code blocks', () => {
            global.hljs = {
                highlightElement: vi.fn(),
                getLanguage: vi.fn(() => ({ name: 'javascript' }))
            };
            
            const container = document.createElement('div');
            container.innerHTML = '<pre><code class="language-javascript">const x = 1;</code></pre>';
            
            highlightCodeBlocks(container);
            
            expect(global.hljs.highlightElement).toHaveBeenCalled();
        });

        it('should skip already highlighted blocks', () => {
            global.hljs = {
                highlightElement: vi.fn()
            };
            
            const container = document.createElement('div');
            container.innerHTML = '<pre><code class="hljs">already highlighted</code></pre>';
            
            highlightCodeBlocks(container);
            
            expect(global.hljs.highlightElement).not.toHaveBeenCalled();
        });

        it('should skip ASCII art blocks', () => {
            global.hljs = {
                highlightElement: vi.fn()
            };
            
            const container = document.createElement('div');
            container.innerHTML = '<pre class="ascii-art"><code>┌─┐</code></pre>';
            
            highlightCodeBlocks(container);
            
            expect(global.hljs.highlightElement).not.toHaveBeenCalled();
        });
    });
});
