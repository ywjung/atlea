/**
 * Markdown Configuration
 *
 * Configure marked.js for rendering markdown with syntax highlighting.
 */

import { isAsciiArt } from './helpers.js';

/**
 * Initialize marked.js with custom configuration
 */
export function initMarked() {
    if (typeof marked === 'undefined') {
        console.warn('marked.js not loaded');
        return;
    }

    // Custom renderer for marked.js
    const renderer = new marked.Renderer();
    const originalCodeRenderer = renderer.code.bind(renderer);

    renderer.code = function(code, language) {
        // Check if it's ASCII art
        if (isAsciiArt(code, language)) {
            const escaped = code
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
            return `<pre class="ascii-art"><code>${escaped}</code></pre>`;
        }

        // Use default renderer for code with language
        return originalCodeRenderer(code, language);
    };

    // Configure marked.js
    marked.setOptions({
        renderer: renderer,
        highlight: function(code, lang) {
            // Use shared ASCII art detection function
            if (isAsciiArt(code, lang)) {
                // Return plain text WITHOUT any highlighting
                // This will be used inside <pre class="ascii-art"><code>
                return code;
            }

            // Apply syntax highlighting for code with specified language
            if (lang && typeof hljs !== 'undefined' && hljs.getLanguage(lang)) {
                try {
                    return hljs.highlight(code, { language: lang }).value;
                } catch (e) {
                    console.warn('Highlight.js error:', e);
                    return code;
                }
            }

            // For code blocks without language, don't auto-detect to avoid false positives
            // Just return plain code
            return code;
        },
        breaks: true,
        gfm: true
    });
}

/**
 * Parse markdown to HTML
 * @param {string} text - Markdown text
 * @returns {string} - HTML string
 */
export function parseMarkdown(text) {
    if (typeof marked === 'undefined') {
        return text;
    }
    return marked.parse(text);
}
