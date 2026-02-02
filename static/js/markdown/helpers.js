/**
 * Markdown Helpers
 *
 * Utility functions for markdown processing.
 */

/**
 * Detect if code block is ASCII art
 * @param {string} code - Code content
 * @param {string} language - Language identifier
 * @returns {boolean}
 */
export function isAsciiArt(code, language) {
    // If language is specified and it's a known programming language, it's not ASCII art
    if (language && ['javascript', 'python', 'java', 'cpp', 'c', 'csharp', 'go', 'rust',
                      'typescript', 'ruby', 'php', 'swift', 'kotlin', 'scala', 'sql',
                      'html', 'css', 'json', 'xml', 'yaml', 'bash', 'shell'].includes(language.toLowerCase())) {
        return false;
    }

    // Check for box-drawing characters (Unicode box drawing)
    const hasBoxDrawing = /[│┤┐└┴┬├─┼╔╗╚╝═║╠╣╦╩╬▀▄█▌▐░▒▓■□▪▫┌┘]/.test(code);
    if (hasBoxDrawing) return true;

    // Check for ASCII art patterns (multiple lines with drawing characters)
    const lines = code.split('\n');
    if (lines.length < 3) return false; // Too short to be ASCII art

    // Count lines with ASCII drawing characters
    const drawingChars = /[\|\/\\_\-\+\=\[\]\{\}\(\)\<\>\~\`\']/;
    const linesWithDrawing = lines.filter(line => drawingChars.test(line)).length;

    // If more than 60% of lines have drawing characters, it's likely ASCII art
    if (linesWithDrawing / lines.length > 0.6) return true;

    // Check for diagram keywords in combination with drawing characters
    const hasKeywords = /(┐|┌|└|┘|\||─|╔|╗|╚|╝|diagram|chart|graph|tree|flow)/i.test(code);
    if (hasKeywords && drawingChars.test(code)) return true;

    return false;
}

/**
 * Normalize language class names for highlight.js
 * @param {HTMLElement} block - Code block element
 */
export function normalizeLanguageClass(block) {
    const classList = Array.from(block.classList);

    // Map of incorrect/unsupported -> correct language codes
    const languageMap = {
        'language-jav': 'language-java',
        'language-ja': 'language-java',
        'language-py': 'language-python',
        'language-js': 'language-javascript',
        'language-ts': 'language-typescript',
        'language-yml': 'language-yaml',
        'language-sh': 'language-bash',
        'language-props': 'language-properties',
        'language-prop': 'language-properties',
        // Unsupported languages -> fallback to similar or plaintext
        'language-gradle': 'language-groovy',
        'language-kt': 'language-kotlin',
        'language-dockerfile': 'language-docker',
        'language-env': 'language-properties',
        'language-dotenv': 'language-properties',
        'language-conf': 'language-ini',
        'language-config': 'language-ini',
        'language-txt': 'language-plaintext',
        'language-text': 'language-plaintext',
        'language-log': 'language-plaintext'
    };

    // List of languages supported by highlight.js (common subset)
    const supportedLanguages = new Set([
        'javascript', 'typescript', 'python', 'java', 'kotlin', 'groovy',
        'c', 'cpp', 'csharp', 'go', 'rust', 'ruby', 'php', 'swift',
        'html', 'xml', 'css', 'scss', 'less', 'json', 'yaml', 'markdown',
        'sql', 'bash', 'shell', 'powershell', 'docker', 'nginx',
        'ini', 'properties', 'plaintext', 'diff', 'makefile'
    ]);

    // Replace incorrect language classes
    classList.forEach(className => {
        if (languageMap[className]) {
            block.classList.remove(className);
            block.classList.add(languageMap[className]);
        } else if (className.startsWith('language-')) {
            // Check if language is supported, if not fallback to plaintext
            const lang = className.replace('language-', '');
            if (!supportedLanguages.has(lang) && typeof hljs !== 'undefined') {
                // Check if hljs has this language
                if (!hljs.getLanguage(lang)) {
                    block.classList.remove(className);
                    block.classList.add('language-plaintext');
                }
            }
        }
    });
}

/**
 * Render math in element using KaTeX
 * @param {HTMLElement} element - Element to render math in
 */
export function renderMath(element) {
    if (typeof renderMathInElement !== 'undefined') {
        try {
            renderMathInElement(element, {
                delimiters: [
                    {left: '$$', right: '$$', display: true},   // Block math
                    {left: '$', right: '$', display: false},     // Inline math
                    {left: '\\[', right: '\\]', display: true},  // LaTeX block
                    {left: '\\(', right: '\\)', display: false}  // LaTeX inline
                ],
                throwOnError: false,
                errorColor: '#cc0000',
                strict: false,
                trust: (context) => ['\\ce', '\\pu'].includes(context.command), // Allow mhchem commands
                macros: {
                    "\\RR": "\\mathbb{R}",
                    "\\NN": "\\mathbb{N}",
                    "\\ZZ": "\\mathbb{Z}",
                    "\\QQ": "\\mathbb{Q}",
                    "\\CC": "\\mathbb{C}"
                }
            });
        } catch (error) {
            console.error('KaTeX rendering error:', error);
        }
    }
}

/**
 * Setup syntax highlighting for code blocks
 * @param {HTMLElement} container - Container with code blocks
 */
export function highlightCodeBlocks(container) {
    if (typeof hljs === 'undefined') return;

    const codeBlocks = container.querySelectorAll('pre code');
    codeBlocks.forEach(block => {
        // Normalize language class before highlighting
        normalizeLanguageClass(block);

        // Skip if already highlighted
        if (block.classList.contains('hljs')) return;

        // Check for ASCII art class
        const parent = block.parentElement;
        if (parent && parent.classList.contains('ascii-art')) return;

        try {
            hljs.highlightElement(block);
        } catch (error) {
            console.error('Syntax highlighting error:', error);
        }
    });
}
