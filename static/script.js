// ========================================
// XSS Protection with DOMPurify
// ========================================

/**
 * Sanitize HTML content using DOMPurify
 * @param {string} dirty - Potentially unsafe HTML
 * @param {Object} config - DOMPurify configuration
 * @returns {string} - Sanitized HTML
 */
function sanitizeHTML(dirty, config = {}) {
    if (typeof DOMPurify === 'undefined') {
        console.error('DOMPurify is not loaded! Falling back to text content only.');
        // Fallback: strip all HTML tags
        const div = document.createElement('div');
        div.textContent = dirty;
        return div.innerHTML;
    }

    // Default config: allow most HTML but remove dangerous elements
    const defaultConfig = {
        ALLOWED_TAGS: [
            'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'dd', 'del', 'div',
            'dl', 'dt', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i',
            'img', 'ins', 'kbd', 'li', 'mark', 'ol', 'p', 'pre', 's', 'span',
            'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th',
            'thead', 'tr', 'u', 'ul'
        ],
        ALLOWED_ATTR: [
            'class', 'id', 'href', 'title', 'alt', 'src', 'width', 'height',
            'data-*', 'aria-*', 'role', 'target', 'rel'
        ],
        ALLOW_DATA_ATTR: true,
        ALLOW_ARIA_ATTR: true,
        // Prevent data: URIs in images (XSS vector)
        FORBID_ATTR: ['onerror', 'onload', 'onclick'],
        FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'link', 'style'],
        ...config
    };

    return DOMPurify.sanitize(dirty, defaultConfig);
}

/**
 * Safely set innerHTML with DOMPurify sanitization
 * @param {HTMLElement} element - Target element
 * @param {string} html - HTML content to set
 * @param {Object} config - DOMPurify configuration
 */
function safeSetInnerHTML(element, html, config = {}) {
    if (!element) {
        console.error('safeSetInnerHTML: element is null or undefined');
        return;
    }
    element.innerHTML = sanitizeHTML(html, config);
}

// ========================================
// ASCII art detection function (shared between renderer and highlighter)
// ========================================
function isAsciiArt(code, language) {
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

// Normalize language class names for highlight.js
function normalizeLanguageClass(block) {
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
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(code, { language: lang }).value;
            } catch (e) {
                logger.warn('Highlight.js error:', e);
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

// Get searching message based on Hybrid RAG status
function getSearchingMessage(searchMode) {
    // Hybrid RAG가 비활성화되어 있으면 항상 일반 검색 메시지
    if (!isHybridRagEnabled) {
        return '검색 및 답변 생성 중...';
    }

    // Hybrid RAG가 활성화된 경우 search_mode 기반 메시지 결정
    // local-only: 로컬 문서만 사용
    // smart, web-enhanced, comprehensive: 하이브리드 검색 가능
    if (searchMode === 'local-only') {
        return '검색 및 답변 생성 중...';
    } else {
        // smart, web-enhanced, comprehensive
        return '하이브리드 검색 및 답변 생성 중...';
    }
}

// Generate unique session ID
function generateSessionId() {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// Math rendering helper function
function renderMath(element) {
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
        } catch (e) {
            logger.error('KaTeX rendering error:', e);
        }
    }
}

// Mermaid diagram rendering
function renderMermaid(element) {
    if (typeof mermaid !== 'undefined') {
        try {
            // Initialize Mermaid with theme based on current theme
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            mermaid.initialize({
                startOnLoad: false,
                theme: isDark ? 'dark' : 'default',
                securityLevel: 'loose',
                fontFamily: 'var(--font-sans)',
                flowchart: {
                    useMaxWidth: true,
                    htmlLabels: true,
                    curve: 'basis'
                }
            });

            // Find all mermaid code blocks
            const mermaidBlocks = element.querySelectorAll('pre code.language-mermaid');
            mermaidBlocks.forEach((block, index) => {
                const code = block.textContent;
                const pre = block.parentElement;

                // Create container for mermaid diagram
                const container = document.createElement('div');
                container.className = 'mermaid-container';
                container.id = `mermaid-${Date.now()}-${index}`;

                // Replace pre with container
                pre.parentElement.replaceChild(container, pre);

                // Render mermaid
                mermaid.render(`mermaid-svg-${Date.now()}-${index}`, code).then(result => {
                    container.innerHTML = result.svg;
                }).catch(err => {
                    logger.error('Mermaid rendering error:', err);
                    container.innerHTML = `<div class="render-error">❌ Diagram rendering error: ${escapeHtml(err.message)}</div>`;
                });
            });
        } catch (e) {
            logger.error('Mermaid initialization error:', e);
        }
    }
}

// ABC notation music rendering
function renderMusic(element) {
    if (typeof ABCJS !== 'undefined') {
        try {
            // Find all ABC notation blocks
            const abcBlocks = element.querySelectorAll('pre code.language-abc');
            abcBlocks.forEach((block, index) => {
                const code = block.textContent;
                const pre = block.parentElement;

                // Create container for music notation
                const container = document.createElement('div');
                container.className = 'abc-container';
                container.id = `abc-${Date.now()}-${index}`;

                // Replace pre with container
                pre.parentElement.replaceChild(container, pre);

                try {
                    // Render ABC notation
                    ABCJS.renderAbc(container.id, code, {
                        responsive: 'resize',
                        staffwidth: container.offsetWidth || 600,
                        scale: 1.0,
                        add_classes: true
                    });
                } catch (err) {
                    logger.error('ABC rendering error:', err);
                    container.innerHTML = `<div class="render-error">❌ Music notation error: ${escapeHtml(err.message)}</div>`;
                }
            });
        } catch (e) {
            logger.error('ABC initialization error:', e);
        }
    }
}

// Chart.js rendering
function renderCharts(element) {
    if (typeof Chart !== 'undefined') {
        try {
            // Find all chart code blocks
            const chartBlocks = element.querySelectorAll('pre code.language-chart');
            chartBlocks.forEach((block, index) => {
                const code = block.textContent;
                const pre = block.parentElement;

                try {
                    // Parse chart configuration
                    const config = JSON.parse(code);

                    // Create canvas for chart
                    const container = document.createElement('div');
                    container.className = 'chart-container';

                    const canvas = document.createElement('canvas');
                    canvas.id = `chart-${Date.now()}-${index}`;
                    container.appendChild(canvas);

                    // Replace pre with container
                    pre.parentElement.replaceChild(container, pre);

                    // Render chart
                    new Chart(canvas, config);
                } catch (err) {
                    logger.error('Chart rendering error:', err);
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'render-error';
                    errorDiv.textContent = `❌ Chart rendering error: ${err.message}`;
                    pre.parentElement.replaceChild(errorDiv, pre);
                }
            });
        } catch (e) {
            logger.error('Chart.js initialization error:', e);
        }
    }
}

// Combined rendering function for all special content
function renderSpecialContent(element) {
    renderMath(element);
    renderMermaid(element);
    renderMusic(element);
    renderCharts(element);
}

// Debug logging (automatically suppressed in production via logger)
const devLog = (...args) => logger.debug(...args);
const devWarn = (...args) => logger.warn(...args);

// Simple notification functions for export operations
function showInfo(message) {
    logger.info('ℹ️', message);
}

function showError(message) {
    logger.error('❌', message);
    alert(message);
}

function showSuccess(message) {
    logger.info('✅', message);
}

// Toast-style notification
function showNotification(message, type = 'info') {
    // Remove existing notification if any
    const existing = document.querySelector('.toast-notification');
    if (existing) {
        existing.remove();
    }

    const icons = {
        info: 'ℹ️',
        success: '✅',
        warning: '⚠️',
        error: '❌'
    };

    const colors = {
        info: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
        success: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
        warning: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
        error: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)'
    };

    const notification = document.createElement('div');
    notification.className = 'toast-notification';
    notification.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span class="toast-message">${message}</span>`;
    notification.style.cssText = `
        position: fixed;
        bottom: 100px;
        left: 50%;
        transform: translateX(-50%) translateY(20px);
        background: ${colors[type] || colors.info};
        color: white;
        padding: 12px 24px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        z-index: 10000;
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 14px;
        font-weight: 500;
        opacity: 0;
        transition: opacity 0.3s ease, transform 0.3s ease;
    `;

    document.body.appendChild(notification);

    // Animate in
    requestAnimationFrame(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateX(-50%) translateY(0)';
    });

    // Auto-remove after 3 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(-50%) translateY(20px)';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// DOM elements
const chatContainer = document.getElementById('chatContainer');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const voiceBtn = document.getElementById('voiceBtn');
const clearBtn = document.getElementById('clearBtn');
const exportBtn = document.getElementById('exportBtn');
const importBtn = document.getElementById('importBtn');
const reindexBtn = document.getElementById('reindexBtn');
const statusEl = document.getElementById('status');
const docCountEl = document.getElementById('doc-count');
const themeToggle = document.getElementById('themeToggle');
const refreshSuggestionsBtn = document.getElementById('refreshSuggestionsBtn');

// Conversation history elements
const historyToggleBtn = document.getElementById('historyToggleBtn');
const conversationSidebar = document.getElementById('conversationSidebar');
const newChatBtn = document.getElementById('newChatBtn');
const deleteAllChatsBtn = document.getElementById('deleteAllChatsBtn');
const conversationList = document.getElementById('conversationList');
const container = document.querySelector('.container');

// Current conversation session
let currentSessionId = null;

// Source modal elements
const sourceModal = document.getElementById('sourceModal');
const closeSourceModal = document.getElementById('closeSourceModal');
const sourceFilename = document.getElementById('sourceFilename');
const sourceScore = document.getElementById('sourceScore');
const sourceText = document.getElementById('sourceText');

// Help modal elements
const helpModal = document.getElementById('helpModal');
const helpBtn = document.getElementById('helpBtn');
const closeHelpModal = document.getElementById('closeHelpModal');

// Chunk viewer modal elements
const chunkViewerModal = document.getElementById('chunkViewerModal');
const closeChunkViewerModal = document.getElementById('closeChunkViewerModal');
const chunkViewerFilename = document.getElementById('chunkViewerFilename');
const chunkViewerCount = document.getElementById('chunkViewerCount');
const chunkViewerList = document.getElementById('chunkViewerList');

// State
let isLoading = false;
let conversationHistory = [];  // Store conversation history
let currentAbortController = null;  // For stopping generation
let lastUserQuestion = '';  // For regenerate function
let lastFilterState = null;  // Track last filter state to detect changes
let modalStack = [];  // Track which modals are open in order (for ESC key handling)
let isHybridRagEnabled = false;  // Hybrid RAG 활성화 상태

// Modal stack management helpers
function pushModal(modalElement, modalName) {
    // Remove if already in stack (prevent duplicates)
    modalStack = modalStack.filter(item => item.element !== modalElement);
    // Add to end of stack (most recent)
    modalStack.push({ element: modalElement, name: modalName });
}

function popModal(modalElement) {
    modalStack = modalStack.filter(item => item.element !== modalElement);
}

function getTopmostModal() {
    if (modalStack.length === 0) return null;
    return modalStack[modalStack.length - 1];
}

// Initialize feature modules
const errorHandler = new ErrorHandler();
const streamingVisualizer = new StreamingVisualizer();
let questionAutoComplete = null;  // Will be initialized after fetching questions
let currentContextData = [];  // Store context data for source details
const followUpQuestions = new FollowUpQuestions();  // Initialize follow-up questions feature

// Initialize
async function init() {
    const startTime = performance.now();

    // Synchronous setup
    initTheme();
    setupEventListeners();
    setupScrollButton();
    initVoiceButton();

    // Load settings from localStorage
    loadSettings();

    // Parallel async operations (use allSettled to prevent one failure from blocking all)
    const initResults = await Promise.allSettled([
        checkStatus(),
        loadSuggestedQuestions(),
        loadSystemPromptFromServer()  // Load admin-configured system prompt
    ]);

    // Log any failures but continue initialization
    initResults.forEach((result, index) => {
        const taskNames = ['checkStatus', 'loadSuggestedQuestions', 'loadSystemPromptFromServer'];
        if (result.status === 'rejected') {
            logger.error(`❌ ${taskNames[index]} failed:`, result.reason);
        }
    });

    // Initialize AutoComplete after loading suggested questions
    await initializeAutoComplete();

    // Initialize activity monitoring for auto-logout
    if (Auth && typeof Auth.initActivityMonitor === 'function') {
        Auth.initActivityMonitor();
    }

    // Initialize session validation (periodic check for session invalidation)
    if (Auth && typeof Auth.startSessionValidation === 'function') {
        Auth.startSessionValidation();
    }

    // Check authentication and update UI accordingly
    checkAuthenticationStatus();

    const initTime = performance.now() - startTime;
    logger.debug(`Core init completed in ${initTime.toFixed(2)}ms`);

    userInput.focus();
}

/**
 * Check authentication status and update UI
 * Disables chat input for non-authenticated users
 */
function checkAuthenticationStatus() {
    const token = localStorage.getItem('access_token');

    if (!token) {
        // Not authenticated - show login message and disable input
        const loginMessage = document.createElement('div');
        loginMessage.className = 'message bot';
        loginMessage.innerHTML = `
            <div class="message-content">
                <p><strong>🔒 로그인이 필요합니다</strong></p>
                <p>챗봇을 사용하려면 먼저 로그인해주세요.</p>
                <p style="margin-top: 15px;">
                    <a href="/login.html" style="
                        display: inline-block;
                        padding: 10px 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        text-decoration: none;
                        border-radius: 8px;
                        font-weight: 500;
                    ">로그인하기</a>
                </p>
            </div>
        `;
        chatContainer.appendChild(loginMessage);

        // Disable input
        userInput.disabled = true;
        userInput.placeholder = '로그인 후 이용 가능합니다';
        sendBtn.disabled = true;

        logger.info('🔒 Chat disabled - authentication required');
    } else {
        logger.info('✅ User authenticated - chat enabled');
    }
}

// Initialize AutoComplete
async function initializeAutoComplete() {
    try {
        // Skip autocomplete if not authenticated (requires login)
        const token = localStorage.getItem('access_token');
        if (!token) {
            return; // Silent skip - autocomplete is optional feature
        }

        const data = await Auth.apiCall('/api/suggested-questions');
        if (data && data.questions) {
            const questions = data.questions || [];
            questionAutoComplete = new QuestionAutoComplete(userInput, questions);
        }
    } catch (error) {
        // Silent fail - autocomplete is optional feature
    }
}

// Setup event listeners
function setupEventListeners() {
    sendBtn.addEventListener('click', (e) => {
        e.preventDefault();
        sendMessage();
    });
    clearBtn.addEventListener('click', async () => {
        await clearChat();
    });
    exportBtn.addEventListener('click', exportHistory);
    importBtn.addEventListener('click', importHistory);

    // Reindex button may not exist (moved to admin page)
    if (reindexBtn) {
        reindexBtn.addEventListener('click', reindexDocuments);
    }

    // Cancel reindex button event listener
    const cancelReindexBtn = document.getElementById('cancelReindexBtn');
    if (cancelReindexBtn) {
        cancelReindexBtn.addEventListener('click', async () => {
            // Show confirmation dialog
            const confirmed = confirm('재색인을 중지하시겠습니까?\n\n진행 중인 작업이 취소되고, 이미 처리된 데이터는 손실될 수 있습니다.');

            if (confirmed) {
                try {
                    devLog('🛑 Requesting reindex cancellation...');

                    // Disable cancel button to prevent multiple clicks
                    cancelReindexBtn.disabled = true;
                    cancelReindexBtn.textContent = '🛑 취소 중...';

                    const response = await fetch('/api/reindex/cancel', {
                        method: 'POST'
                    });

                    const result = await response.json();
                    devLog('Cancel response:', result);

                    if (response.ok) {
                        devLog('✅ Cancellation request sent successfully');
                    } else {
                        logger.error('❌ Failed to cancel reindex:', result.detail);
                        alert('재색인 취소에 실패했습니다: ' + result.detail);

                        // Re-enable button on error
                        cancelReindexBtn.disabled = false;
                        cancelReindexBtn.textContent = '🛑 재색인 중지';
                    }
                } catch (error) {
                    logger.error('❌ Error cancelling reindex:', error);
                    alert('재색인 취소 중 오류가 발생했습니다: ' + error.message);

                    // Re-enable button on error
                    cancelReindexBtn.disabled = false;
                    cancelReindexBtn.textContent = '🛑 재색인 중지';
                }
            }
        });
    }

    themeToggle.addEventListener('click', toggleTheme);

    // Help modal event listeners
    helpBtn.addEventListener('click', () => {
        helpModal.classList.add('active');
        pushModal(helpModal, 'help');
    });

    closeHelpModal.addEventListener('click', () => {
        helpModal.classList.remove('active');
        popModal(helpModal);
    });

    // Close help modal when clicking outside
    helpModal.addEventListener('click', (e) => {
        if (e.target === helpModal) {
            helpModal.classList.remove('active');
            popModal(helpModal);
        }
    });

    // Source modal event listeners
    closeSourceModal.addEventListener('click', () => {
        sourceModal.classList.remove('active');
        popModal(sourceModal);
    });

    // Close modal when clicking outside
    sourceModal.addEventListener('click', (e) => {
        if (e.target === sourceModal) {
            sourceModal.classList.remove('active');
            popModal(sourceModal);
        }
    });

    // Chunk viewer modal event listeners
    closeChunkViewerModal.addEventListener('click', () => {
        chunkViewerModal.classList.remove('active');
        popModal(chunkViewerModal);
    });

    // Close modal when clicking outside
    chunkViewerModal.addEventListener('click', (e) => {
        if (e.target === chunkViewerModal) {
            chunkViewerModal.classList.remove('active');
            popModal(chunkViewerModal);
        }
    });

    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Refresh suggestions button
    if (refreshSuggestionsBtn) {
        refreshSuggestionsBtn.addEventListener('click', refreshSuggestedQuestions);
    }

    // Conversation history event listeners
    historyToggleBtn.addEventListener('click', async () => {
        const isOpening = !conversationSidebar.classList.contains('active');

        conversationSidebar.classList.toggle('active');
        container.classList.toggle('sidebar-active');
        historyToggleBtn.classList.toggle('active');

        // Update modal stack
        if (isOpening) {
            pushModal(conversationSidebar, 'sidebar');
            await loadConversations();
        } else {
            popModal(conversationSidebar);
        }
    });

    newChatBtn.addEventListener('click', createNewConversation);

    deleteAllChatsBtn.addEventListener('click', async () => {
        // Check authentication (required to delete conversations)
        const token = localStorage.getItem('access_token');
        if (!token) {
            alert('로그인이 필요합니다.');
            return;
        }

        const conversationCount = document.querySelectorAll('.conversation-item').length;

        if (conversationCount === 0) {
            alert('삭제할 대화가 없습니다.');
            return;
        }

        const confirmed = confirm(`정말로 모든 대화(${conversationCount}개)를 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.`);

        if (!confirmed) {
            return;
        }

        try {
            const response = await fetch('/api/conversations', {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                throw new Error('Failed to delete all conversations');
            }

            const data = await response.json();

            // Create new conversation (this clears session and shows welcome screen)
            await createNewConversation();

            // Reload conversation list (should be empty now)
            await loadConversations();

            alert(`${data.deleted_count}개의 대화가 삭제되었습니다.\n새 대화가 시작되었습니다.`);
        } catch (error) {
            logger.error('Error deleting all conversations:', error);
            alert('전체 삭제에 실패했습니다.');
        }
    });

    userInput.addEventListener('input', () => {
        autoResize();
        updateSendButton();
        updateCharCount();
        saveDraft(); // Auto-save draft
    });

    // Event delegation for source tags (handles dynamically created elements)
    chatContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('source-tag')) {
            const filename = e.target.textContent;
            devLog('[Event Delegation] Source tag clicked:', filename);
            showSourceDetails(filename);
        }
    });

    // Global keyboard shortcuts
    setupKeyboardShortcuts();
}

// Global keyboard shortcuts
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // F1 - Toggle help modal
        if (e.key === 'F1') {
            e.preventDefault();
            if (helpModal.classList.contains('active')) {
                helpModal.classList.remove('active');
                popModal(helpModal);
            } else {
                helpModal.classList.add('active');
                pushModal(helpModal, 'help');
            }
            return;
        }

        // Esc - Close only the topmost modal
        if (e.key === 'Escape') {
            const topModal = getTopmostModal();
            if (topModal) {
                // Close the topmost modal
                topModal.element.classList.remove('active');
                popModal(topModal.element);

                // Special handling for specific modals
                if (topModal.name === 'settings') {
                    closeSettings();
                } else if (topModal.name === 'sidebar') {
                    container.classList.remove('sidebar-active');
                    historyToggleBtn.classList.remove('active');
                }
                return;
            }
        }

        // Ctrl/Cmd + K - New chat
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (confirm('새 대화를 시작하시겠습니까? 현재 대화는 저장됩니다.')) {
                clearChat();
                userInput.focus();
            }
        }

        // Ctrl/Cmd + / - Open settings
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            if (settingsPanel.classList.contains('active')) {
                closeSettings();
            } else {
                settingsPanel.classList.add('active');
                settingsOverlay.classList.add('active');
                pushModal(settingsPanel, 'settings');
            }
        }

        // Ctrl/Cmd + E - Export history
        if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
            e.preventDefault();
            exportHistory();
            return;
        }

        // Ctrl/Cmd + H - Toggle conversation history sidebar
        if ((e.ctrlKey || e.metaKey) && e.key === 'h') {
            e.preventDefault();
            historyToggleBtn.click();
            return;
        }

        // Ctrl/Cmd + D - Open document management
        if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
            e.preventDefault();
            const docModal = document.getElementById('documentModal');
            if (docModal) {
                docModal.classList.add('active');
                pushModal(docModal, 'documents');
                loadDocuments();
            }
            return;
        }

        // Ctrl/Cmd + I - Import history
        if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
            e.preventDefault();
            importHistory();
            return;
        }

        // Ctrl/Cmd + Shift + D - Toggle dark mode
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
            e.preventDefault();
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            const themeSwitch = document.getElementById('themeSwitch');
            if (themeSwitch) {
                themeSwitch.checked = newTheme === 'dark';
            }
            logger.info(`테마 변경: ${newTheme === 'dark' ? '다크 모드' : '라이트 모드'}`);
            return;
        }

        // Ctrl/Cmd + B - Toggle sidebar (document filter)
        if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
            e.preventDefault();
            const filterBtn = document.getElementById('filter-toggle-btn');
            if (filterBtn) {
                filterBtn.click();
            }
            return;
        }

        // Ctrl/Cmd + Enter - Send message (when focused on input)
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            if (document.activeElement === userInput) {
                e.preventDefault();
                sendBtn.click();
                return;
            }
        }
    });
}

// Auto-resize textarea
function autoResize() {
    userInput.style.height = 'auto';
    const newHeight = Math.min(userInput.scrollHeight, 150);
    userInput.style.height = newHeight + 'px';

    // Only show scrollbar when content actually exceeds max height
    if (userInput.scrollHeight > 150) {
        userInput.style.overflowY = 'auto';
    } else {
        userInput.style.overflowY = 'hidden';
    }
}

// Clean <think> tags from response
function cleanThinkTags(text) {
    // Remove <think>...</think> blocks (including multiline)
    let cleaned = text.replace(/<think>[\s\S]*?<\/think>/g, '');
    // Remove any remaining tags
    cleaned = cleaned.replace(/<\/?think>/g, '');
    // Clean up extra whitespace
    cleaned = cleaned.replace(/\n\s*\n\s*\n/g, '\n\n');
    return cleaned.trim();
}

// Update send button state
function updateSendButton() {
    const hasText = userInput.value.trim().length > 0;
    sendBtn.disabled = !hasText || isLoading;
}

// Check system status
async function checkStatus() {
    try {
        const data = await Auth.apiCall('/api/status');

        // Update model information from server (관리자 페이지에서 변경 시 즉시 반영)
        if (data.llm_model) {
            currentSettings.llm_model = data.llm_model;
        }
        if (data.embedding_model) {
            currentSettings.embedding_model = data.embedding_model;
        }

        // Show/hide reindex banner
        const reindexBanner = document.getElementById('reindexBanner');
        if (reindexBanner) {
            if (data.is_reindexing) {
                reindexBanner.classList.add('show');
            } else {
                reindexBanner.classList.remove('show');
            }
        }

        if (data.status === 'ready') {
            statusEl.textContent = '준비됨';
            statusEl.style.color = '#4ade80';
            docCountEl.textContent = `📄 문서 ${data.pdf_count}개 (청크 ${data.chunk_count}개)`;
            sendBtn.disabled = false;
        } else if (data.status === 'reindexing') {
            statusEl.textContent = '재색인 중...';
            statusEl.style.color = '#fbbf24';
            docCountEl.textContent = `📄 문서 ${data.pdf_count}개 (청크 ${data.chunk_count}개)`;
            sendBtn.disabled = false;  // Allow queries during reindex
            setTimeout(checkStatus, 2000);  // Check again in 2 seconds
        } else {
            statusEl.textContent = '초기화 중...';
            statusEl.style.color = '#fbbf24';
            setTimeout(checkStatus, 2000);
        }
    } catch (error) {
        logger.error('Status check failed:', error);
        statusEl.textContent = '연결 실패';
        statusEl.style.color = '#ef4444';
        setTimeout(checkStatus, 5000);
    }
}

// Input validation constants
const INPUT_VALIDATION = {
    MIN_LENGTH: 1,
    MAX_LENGTH: 5000,
    FORBIDDEN_PATTERNS: [
        /<script[^>]*>.*?<\/script>/gi,  // Script tags
        /<iframe[^>]*>.*?<\/iframe>/gi,  // Iframe tags
        /javascript:/gi,                  // JavaScript protocol
        /on\w+\s*=/gi                     // Event handlers (onclick, onload, etc.)
    ]
};

// Validate user input
function validateInput(text) {
    // Remove leading/trailing whitespace
    const trimmed = text.trim();

    // Check if empty
    if (trimmed.length === 0) {
        return { valid: false, error: '질문을 입력해주세요.' };
    }

    // Check minimum length
    if (trimmed.length < INPUT_VALIDATION.MIN_LENGTH) {
        return { valid: false, error: `최소 ${INPUT_VALIDATION.MIN_LENGTH}자 이상 입력해주세요.` };
    }

    // Check maximum length
    if (trimmed.length > INPUT_VALIDATION.MAX_LENGTH) {
        return { valid: false, error: `최대 ${INPUT_VALIDATION.MAX_LENGTH}자까지 입력 가능합니다. (현재: ${trimmed.length}자)` };
    }

    // Check for forbidden patterns (XSS prevention)
    for (const pattern of INPUT_VALIDATION.FORBIDDEN_PATTERNS) {
        if (pattern.test(trimmed)) {
            return { valid: false, error: '허용되지 않는 문자나 태그가 포함되어 있습니다.' };
        }
    }

    // Normalize consecutive whitespace
    const normalized = trimmed.replace(/\s+/g, ' ');

    return { valid: true, normalized };
}

// ===== Conversation History Functions =====

// Load conversation list
let isLoadingConversations = false;
let showBookmarkedOnly = false;  // Filter state for showing only bookmarked conversations

async function loadConversations() {
    // Prevent concurrent loads
    if (isLoadingConversations) {
        devLog('Already loading conversations, skipping...');
        return;
    }

    isLoadingConversations = true;

    try {
        // Fetch conversations or bookmarked conversations based on filter state
        const endpoint = showBookmarkedOnly ? '/api/conversations/bookmarked/list' : '/api/conversations';
        const data = await Auth.apiCall(endpoint);
        if (!data) {
            throw new Error('Failed to load conversations');
        }
        const conversations = data.sessions || [];

        conversationList.innerHTML = '';

        if (conversations.length === 0) {
            const emptyMessage = showBookmarkedOnly ? '북마크된 대화가 없습니다' : '대화 기록이 없습니다';
            conversationList.innerHTML = `<div class="loading-conversations"><span>${emptyMessage}</span></div>`;
            return;
        }

        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            item.setAttribute('data-id', conv.id);
            const isCurrentSession = conv.id === currentSessionId;
            const isBookmarked = conv.is_bookmarked === '1';

            if (isCurrentSession) {
                item.classList.add('active');
            }

            // Bookmark button (always visible, filled if bookmarked)
            const bookmarkButtonHTML = `
                <button class="conversation-bookmark-btn ${isBookmarked ? 'bookmarked' : ''}" title="${isBookmarked ? '북마크 해제' : '북마크'}" data-session-id="${conv.id}">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="${isBookmarked ? 'currentColor' : 'none'}" stroke="currentColor">
                        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            `;

            // Only show delete button if it's not the current session
            const deleteButtonHTML = isCurrentSession ? '' : `
                <button class="conversation-delete-btn" title="삭제">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            `;

            item.innerHTML = `
                <div class="conversation-item-header">
                    <div class="conversation-title">${escapeHtml(conv.title)}</div>
                    <div class="conversation-actions">
                        ${bookmarkButtonHTML}
                        ${deleteButtonHTML}
                    </div>
                </div>
                <div class="conversation-time">${formatTimestamp(conv.updated_at)}</div>
            `;

            // Click to load conversation (use event delegation later, but keep individual for now)
            item.addEventListener('click', (e) => {
                if (!e.target.closest('.conversation-bookmark-btn') && !e.target.closest('.conversation-delete-btn')) {
                    loadConversation(conv.id);
                }
            }, { once: true }); // Use once:true to prevent duplicate listeners

            // Bookmark button listener
            const bookmarkBtn = item.querySelector('.conversation-bookmark-btn');
            if (bookmarkBtn) {
                bookmarkBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    const sessionId = bookmarkBtn.getAttribute('data-session-id');
                    await toggleBookmark(sessionId);
                }, { once: true });
            }

            // Delete button - only add listener if button exists
            if (!isCurrentSession) {
                const deleteBtn = item.querySelector('.conversation-delete-btn');
                if (deleteBtn) {
                    deleteBtn.addEventListener('click', async (e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        const sessionId = item.getAttribute('data-id');
                        if (confirm('이 대화를 삭제하시겠습니까?')) {
                            // Disable button during deletion
                            deleteBtn.disabled = true;
                            await deleteConversation(sessionId);
                        }
                    }, { once: true });
                }
            }

            conversationList.appendChild(item);
        });
    } catch (error) {
        logger.error('Error loading conversations:', error);
        conversationList.innerHTML = '<div class="loading-conversations"><span>대화 목록 로딩 실패</span></div>';
    } finally {
        isLoadingConversations = false;
    }
}

// Toggle bookmark for a conversation
async function toggleBookmark(sessionId) {
    try {
        const data = await Auth.apiCall(`/api/conversations/${sessionId}/bookmark`, {
            method: 'POST'
        });

        if (!data) {
            throw new Error('Failed to toggle bookmark');
        }

        // Reload conversation list to reflect bookmark status
        await loadConversations();

        // Show brief feedback
        devLog(`Bookmark ${data.is_bookmarked ? 'added' : 'removed'} for session ${sessionId}`);
    } catch (error) {
        logger.error('Error toggling bookmark:', error);
        alert('북마크 변경에 실패했습니다.');
    }
}

// Toggle bookmark filter
function toggleBookmarkFilter() {
    showBookmarkedOnly = !showBookmarkedOnly;

    // Update button state
    const filterBtn = document.getElementById('bookmarkFilterBtn');
    if (filterBtn) {
        if (showBookmarkedOnly) {
            filterBtn.classList.add('active');
            filterBtn.title = '전체 대화 보기';
        } else {
            filterBtn.classList.remove('active');
            filterBtn.title = '북마크만 보기';
        }
    }

    // Reload conversations with filter
    loadConversations();
}

// Create new conversation
async function createNewConversation() {
    try {
        const data = await Auth.apiCall('/api/conversations', {
            method: 'POST'
        });

        if (!data) {
            throw new Error('Failed to create conversation');
        }

        currentSessionId = data.session_id;

        // Clear conversation history for new conversation
        conversationHistory = [];
        currentContextData = [];
        saveHistory();

        // Show welcome screen for new conversation
        await showWelcomeScreen();

        // Reload conversation list
        await loadConversations();

        devLog('Created new conversation:', currentSessionId);
    } catch (error) {
        logger.error('Error creating conversation:', error);
        alert('새 대화 생성에 실패했습니다.');
    }
}

// Load conversation messages
async function loadConversation(sessionId) {
    try {
        const data = await Auth.apiCall(`/api/conversations/${sessionId}`);
        if (!data) {
            throw new Error('Failed to load conversation');
        }

        currentSessionId = sessionId;

        // Stop all TTS activity before loading new conversation
        stopAllTTS();

        // Invalidate TTS cache so it re-checks availability for new conversation
        invalidateTTSCache();

        // Clear current chat UI
        clearChatUI();

        // Clear and rebuild currentContextData from loaded messages
        currentContextData = [];

        // Clear and rebuild conversationHistory from loaded messages
        conversationHistory = [];

        // Load messages
        data.messages.forEach(msg => {
            if (msg.role === 'user') {
                addMessage(msg.content, 'user');
                // Add to conversationHistory
                conversationHistory.push({
                    role: 'user',
                    content: msg.content,
                    timestamp: msg.timestamp
                });
            } else if (msg.role === 'assistant') {
                const sources = msg.metadata?.sources || [];
                const messageDiv = addMessage(msg.content, 'bot', sources);  // Use 'bot' type for markdown rendering

                // Add to conversationHistory
                conversationHistory.push({
                    role: 'assistant',
                    content: msg.content,
                    sources: sources,
                    context: msg.metadata?.context || [],
                    timestamp: msg.timestamp
                });

                // Add response time if metadata contains stats
                if (msg.metadata?.elapsed_time) {
                    const elapsed = msg.metadata.elapsed_time;
                    const cached = msg.metadata.cached || false;
                    const stats = msg.metadata.stats || null;
                    addResponseTime(messageDiv, elapsed, cached, stats);
                }

                // Restore context data for source details modal
                if (msg.metadata?.context && Array.isArray(msg.metadata.context)) {
                    currentContextData.push(...msg.metadata.context);
                }

                // Display follow-up questions if saved in metadata
                if (msg.metadata?.follow_up_questions && msg.metadata.follow_up_questions.length > 0) {
                    const contentDiv = messageDiv.querySelector('.message-content');
                    if (contentDiv) {
                        followUpQuestions.display(contentDiv, msg.metadata.follow_up_questions, (selectedQuestion) => {
                            // When user clicks a follow-up question, populate input and send
                            userInput.value = selectedQuestion;
                            autoResize();
                            updateSendButton();
                            sendMessage();
                        });
                    }
                }
            }
        });

        // Save to localStorage
        saveHistory();

        // Find and set last user question for regenerate function
        lastUserQuestion = '';  // Reset first
        for (let i = data.messages.length - 1; i >= 0; i--) {
            if (data.messages[i].role === 'user') {
                lastUserQuestion = data.messages[i].content;
                break;
            }
        }

        // Update conversation list UI
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('active');
        });
        document.querySelector(`.conversation-item[data-id="${sessionId}"]`)?.classList.add('active');

        // Scroll to bottom
        scrollToBottom();

        devLog('Loaded conversation:', sessionId);
    } catch (error) {
        logger.error('Error loading conversation:', error);
        alert('대화 로딩에 실패했습니다.');
    }
}

// Delete conversation
let isDeletingConversation = false;

async function deleteConversation(sessionId) {
    // Prevent concurrent deletions
    if (isDeletingConversation) {
        devLog('Already deleting a conversation, skipping...');
        return;
    }

    isDeletingConversation = true;

    try {
        devLog('Deleting conversation:', sessionId);

        const result = await Auth.apiCall(`/api/conversations/${sessionId}`, {
            method: 'DELETE'
        });

        if (!result) {
            throw new Error('Failed to delete conversation');
        }

        devLog('Delete result:', result);

        // If deleted current conversation, create new one
        if (sessionId === currentSessionId) {
            devLog('Deleted current conversation, creating new one');
            currentSessionId = null; // Clear current session first
            await createNewConversation();
        } else {
            devLog('Deleted non-current conversation, reloading list');
            await loadConversations();
        }

        devLog('Successfully deleted conversation:', sessionId);
    } catch (error) {
        logger.error('Error deleting conversation:', error);
        alert(`대화 삭제에 실패했습니다: ${error.message}`);
        // Reload list anyway to sync with server state
        await loadConversations();
    } finally {
        isDeletingConversation = false;
    }
}

// Format timestamp
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    // Less than 1 minute
    if (diff < 60000) {
        return '방금 전';
    }

    // Less than 1 hour
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return `${minutes}분 전`;
    }

    // Less than 1 day
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours}시간 전`;
    }

    // Less than 7 days
    if (diff < 604800000) {
        const days = Math.floor(diff / 86400000);
        return `${days}일 전`;
    }

    // Format as date
    return `${date.getMonth() + 1}/${date.getDate()}`;
}

// Clear chat UI only (no confirmation)
function clearChatUI() {
    // Stop all TTS before clearing the UI (buttons/audio will be removed)
    stopAllTTS();

    const chatContainer = document.getElementById('chatContainer');
    if (chatContainer) {
        chatContainer.innerHTML = '';
    }
}

// Show welcome screen with initial UI
async function showWelcomeScreen() {
    const chatContainer = document.getElementById('chatContainer');
    if (chatContainer) {
        chatContainer.innerHTML = `
            <div class="welcome-message">
                <h2>안녕하세요! 👋</h2>
                <p>업로드된 문서 내용에 대해 무엇이든 질문해주세요.</p>
                <p class="hint">문서가 로딩되면 질문을 시작할 수 있습니다.</p>
            </div>

            <!-- Suggested Questions Section -->
            <div class="suggested-questions" id="suggestedQuestions" style="display: none;">
                <div class="suggested-questions-header">
                    <span class="suggested-icon">💡</span>
                    <h3>이런 질문은 어떠세요?</h3>
                    <button id="refreshSuggestionsBtn" class="refresh-suggestions-btn" title="새로운 질문 생성">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M1 4v6h6M23 20v-6h-6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </button>
                </div>
                <div class="suggested-questions-list" id="suggestedQuestionsList">
                    <!-- Questions will be inserted here dynamically -->
                </div>
            </div>
        `;

        // Re-attach event listener for refresh button
        const refreshBtn = document.getElementById('refreshSuggestionsBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', refreshSuggestedQuestions);
        }

        // Load suggested questions
        await loadSuggestedQuestions();
    }
}

// Initialize conversation history
async function initConversationHistory() {
    try {
        // Clear chat UI to ensure fresh start
        clearChatUI();

        // Check if user is authenticated
        const token = localStorage.getItem('access_token');

        if (token) {
            // User is authenticated - try to load existing conversations
            const data = await Auth.apiCall('/api/conversations');
            const conversations = data.sessions || [];

            // Load the most recent conversation
            if (conversations.length > 0) {
                const mostRecent = conversations[0];
                const messageCount = parseInt(mostRecent.message_count || '0');

                if (messageCount === 0) {
                    // Reuse the empty conversation - show welcome screen
                    currentSessionId = mostRecent.id;
                    await showWelcomeScreen();
                    devLog('Reusing empty conversation:', currentSessionId);
                } else {
                    // Most recent has messages - load it to display
                    devLog('Loading most recent conversation:', mostRecent.id);
                    await loadConversation(mostRecent.id);
                }
            } else {
                // No conversations exist, create new one
                devLog('No conversations found, creating new one');
                await createNewConversation();
                await showWelcomeScreen();
            }

            // Load conversation list for sidebar (authenticated users only)
            await loadConversations();
        } else {
            // User is not authenticated - skip conversation loading, create new one
            devLog('Not authenticated, creating new conversation');
            await createNewConversation();
            await showWelcomeScreen();
        }

        // Refresh TTS buttons after conversations are loaded
        refreshTTSButtons();

        devLog('Conversation history initialized');
    } catch (error) {
        logger.error('Failed to initialize conversation history:', error);
        // Fallback: create new conversation
        try {
            await createNewConversation();
        } catch (e) {
            logger.error('Failed to create fallback conversation:', e);
        }
    }
}

// Send message with streaming
async function sendMessage(regenerate = false) {
    // Check authentication - chatbot requires login
    const token = localStorage.getItem('access_token');
    if (!token) {
        // Not authenticated - redirect to login
        if (confirm('챗봇을 사용하려면 로그인이 필요합니다.\n로그인 페이지로 이동하시겠습니까?')) {
            window.location.href = '/login.html';
        }
        return;
    }

    let question;

    if (regenerate) {
        question = lastUserQuestion;
        if (!question) {
            alert('재생성할 질문이 없습니다. 먼저 질문을 입력해주세요.');
            return;
        }
        // Remove last bot response for regeneration
        if (conversationHistory.length > 0 && conversationHistory[conversationHistory.length - 1].role === 'assistant') {
            conversationHistory.pop();
            // Remove last bot message from UI
            const botMessages = chatContainer.querySelectorAll('.message.bot');
            if (botMessages.length > 0) {
                botMessages[botMessages.length - 1].remove();
            }
        }
    } else {
        // Validate input
        const validation = validateInput(userInput.value);
        if (!validation.valid) {
            showValidationError(validation.error);
            return;
        }

        question = validation.normalized;
        if (isLoading) return;

        // Add user message
        addMessage(question, 'user');

        // Add user message to conversation history
        conversationHistory.push({
            role: 'user',
            content: question
        });

        // Hide suggested questions after first user message
        hideSuggestedQuestions();

        // Collapse search scope filter panel after sending message
        const filterContent = document.getElementById('filterContent');
        const toggleBtn = document.querySelector('.toggle-filter-btn');
        if (filterContent && !filterContent.classList.contains('collapsed')) {
            filterContent.classList.add('collapsed');
            if (toggleBtn) {
                const toggleIcon = toggleBtn.querySelector('svg');
                if (toggleIcon) {
                    toggleIcon.style.transform = 'rotate(0deg)';
                }
            }
        }

        // Save to localStorage
        saveHistory();

        // Store for regenerate
        lastUserQuestion = question;

        // Clear input and draft
        userInput.value = '';
        clearDraft();

        // Force IME to reset by triggering composition end
        const event = new Event('input', { bubbles: true });
        userInput.dispatchEvent(event);

        // Reset focus to clear any remaining composition
        setTimeout(() => {
            userInput.blur();
            setTimeout(() => {
                userInput.focus();
            }, 0);
        }, 0);

        autoResize();
        updateSendButton();
    }

    // Show step-by-step loading
    isLoading = true;
    showStopButton();

    // Show typing indicator (StreamingVisualizer)
    streamingVisualizer.showTypingIndicator(chatContainer);

    // 🆕 Update indicator text - search_mode 기반 초기 메시지 (메타데이터 수신 시 정확한 메시지로 업데이트)
    setTimeout(() => {
        const indicatorText = document.querySelector('.simple-text');
        if (indicatorText) {
            const searchMode = currentSettings.searchMode || 'smart';
            indicatorText.textContent = getSearchingMessage(searchMode);
        }
    }, 0);

    // Scroll to bottom to show typing indicator
    scrollToBottom();

    // Track response time
    const startTime = Date.now();

    // Abort any previous request before starting a new one
    if (currentAbortController) {
        currentAbortController.abort();
    }

    // Create AbortController for this request
    currentAbortController = new AbortController();

    try {
        // Get filter data based on active tab
        const { documentIds, groupIds } = getActiveFilterData();

        // Validate filter selection
        if (documentIds !== null && documentIds.length === 0) {
            alert('❌ 검색할 문서를 선택해주세요.\n\n"조직 내 전체 문서" 또는 특정 문서를 선택하세요.');
            return;
        }
        if (groupIds !== null && groupIds.length === 0) {
            alert('❌ 검색할 그룹을 선택해주세요.\n\n"조직 내 전체 그룹" 또는 특정 그룹을 선택하세요.');
            return;
        }

        // Check if filter state has changed (document scope changed)
        const currentFilterState = JSON.stringify({ documentIds, groupIds });
        if (lastFilterState !== null && lastFilterState !== currentFilterState) {
            // Filter changed - reset conversation context
            devLog('🔄 검색 범위 변경 감지 - 대화 컨텍스트 초기화');
            conversationHistory = [];

            // Create new session when filter changes
            currentSessionId = generateSessionId();

            // Show user notification
            const notificationDiv = document.createElement('div');
            notificationDiv.className = 'filter-change-notification';
            notificationDiv.textContent = '📝 검색 범위가 변경되어 새로운 대화를 시작합니다';
            chatContainer.appendChild(notificationDiv);
            setTimeout(() => notificationDiv.remove(), 3000);
        }
        // Update last filter state
        lastFilterState = currentFilterState;

        // Validate and sanitize query parameters before sending
        const sanitizedParams = {
            question: question,
            top_k: Math.max(1, Math.min(20, parseInt(currentSettings.top_k) || 5)),
            search_mode: ['smart', 'local-only', 'web-enhanced', 'comprehensive', 'tools-only'].includes(currentSettings.searchMode)
                ? currentSettings.searchMode : 'smart',
            temperature: Math.max(0, Math.min(2, parseFloat(currentSettings.temperature) || 0.7)),
            max_tokens: Math.max(1, Math.min(32768, parseInt(currentSettings.max_tokens) || 2048)),
            system_prompt: currentSettings.system_prompt || null,
            cache_threshold: Math.max(0, Math.min(1, parseFloat(currentSettings.cache_threshold) || 0.95)),
            cache_ttl: parseInt(currentSettings.cache_ttl) || 60,
            document_ids: documentIds,
            session_id: currentSessionId,
            group_ids: groupIds,
            // Filter history to only include role and content (required fields)
            // Limit to last 50 messages (backend validation limit)
            history: conversationHistory.slice(0, -1).slice(-50).map(h => ({
                role: h.role,
                content: h.content || ''
            }))
        };

        // Wrap fetch with ErrorHandler retry and timeout
        const response = await errorHandler.withTimeout(
            () => errorHandler.withRetry(
                async () => {
                    const token = Auth.getAccessToken();
                    const headers = {
                        'Content-Type': 'application/json',
                    };
                    if (token) {
                        headers['Authorization'] = `Bearer ${token}`;
                    }

                    const res = await fetch('/api/query/stream', {
                        method: 'POST',
                        headers: headers,
                        body: JSON.stringify(sanitizedParams),
                        signal: currentAbortController.signal
                    });

                    if (!res.ok) {
                        // Try to extract error message from response (400 Bad Request, 422 Validation Error)
                        if (res.status === 400 || res.status === 422) {
                            try {
                                const errorData = await res.json();
                                // FastAPI validation errors have detail as array or string
                                if (errorData.detail) {
                                    if (Array.isArray(errorData.detail)) {
                                        // Pydantic validation error format: [{loc: [...], msg: "...", type: "..."}]
                                        const messages = errorData.detail.map(e =>
                                            `${e.loc?.join('.') || 'field'}: ${e.msg}`
                                        ).join(', ');
                                        throw new Error(messages);
                                    }
                                    throw new Error(errorData.detail);
                                }
                            } catch (e) {
                                // If JSON parsing fails, use default error
                                if (e.message && !e.message.includes('JSON')) {
                                    throw e;
                                }
                            }
                        }
                        throw new Error(`HTTP error! status: ${res.status}`);
                    }

                    return res;
                }
            ),
            120000 // 120 second timeout (increased for slower LLM models)
        );

        // Create message container for streaming first
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot';
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        messageDiv.appendChild(contentDiv);
        chatContainer.appendChild(messageDiv);

        // Show streaming progress inside message container
        streamingVisualizer.showStreamingProgress(messageDiv);

        // Start streaming TTS if enabled
        streamingTTS.start();

        let sources = null;
        let fullText = '';
        let tokenCount = 0;
        let tokenStats = null;  // Store token generation statistics
        let isFirstChunk = true;  // Track first chunk to hide progress indicator
        let inlineFollowUpQs = null;  // Store follow-up questions from SSE stream

        // Read stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';  // Buffer for incomplete lines

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            // Decode chunk and add to buffer
            buffer += decoder.decode(value, { stream: true });

            // Split by newlines, but keep the last incomplete line in buffer
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';  // Keep last incomplete line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const jsonStr = line.substring(6).trim();
                        if (!jsonStr) continue;  // Skip empty data lines

                        const data = JSON.parse(jsonStr);

                        if (data.type === 'metadata') {
                            sources = data.data.sources;
                            // Store context data for source details
                            currentContextData = data.data.context || [];

                            // Store search summary for hybrid RAG
                            const searchSummary = data.data.search_summary;

                            devLog('🔍 [METADATA] Received metadata:', {
                                sources: sources,
                                sourcesLength: sources ? sources.length : 0,
                                sourcesType: typeof sources,
                                sourcesIsArray: Array.isArray(sources),
                                contextLength: currentContextData.length,
                                cached: data.data.cached,
                                searchSummary: searchSummary
                            });

                            // RAG 품질 개선 디버그 로그
                            if (data.data.rewritten_query) {
                                devLog('✏️ [QUERY REWRITE] 쿼리 확장됨:', {
                                    original: question,
                                    rewritten: data.data.rewritten_query
                                });
                            }
                            if (data.data.query_rewrite_enabled || data.data.reranking_enabled) {
                                devLog('🚀 [RAG QUALITY] 품질 개선 설정:', {
                                    queryRewriteEnabled: data.data.query_rewrite_enabled,
                                    rerankingEnabled: data.data.reranking_enabled
                                });
                            }

                            // 🆕 실제 사용된 소스 기반 메시지 업데이트
                            if (searchSummary && searchSummary.sources_used) {
                                const sourcesUsed = searchSummary.sources_used || [];
                                const isHybrid = sourcesUsed.includes('web') || sourcesUsed.includes('docs');

                                const indicatorText = document.querySelector('.simple-text');
                                if (indicatorText) {
                                    indicatorText.textContent = isHybrid
                                        ? '하이브리드 검색 및 답변 생성 중...'
                                        : '검색 및 답변 생성 중...';
                                }
                            }

                            // Display search info if hybrid RAG was used
                            if (searchSummary) {
                                displaySearchInfo(messageDiv, searchSummary);
                            }
                        } else if (data.type === 'chunk') {
                            // Hide progress indicator on first chunk
                            if (isFirstChunk) {
                                streamingVisualizer.hide();
                                isFirstChunk = false;
                            }

                            fullText += data.data;

                            // Feed chunk to streaming TTS
                            streamingTTS.addChunk(data.data);

                            // Update token count (approximate by splitting on spaces)
                            tokenCount = fullText.split(/\s+/).filter(w => w.length > 0).length;

                            // Server already filters <think> tags, so just render
                            try {
                                contentDiv.innerHTML = sanitizeHTML(marked.parse(fullText);

                                // Highlight code blocks first
                                contentDiv.querySelectorAll('pre code').forEach((block) => {
                                    if (!block.dataset.highlighted) {
                                        normalizeLanguageClass(block);
                                        hljs.highlightElement(block);
                                    }
                                });

                                // Render special content (math, diagrams, music, charts)
                                renderSpecialContent(contentDiv);

                                // Scroll to bottom
                                chatContainer.scrollTop = chatContainer.scrollHeight;
                            } catch (renderError) {
                                logger.error('Render error:', renderError);
                                // Continue streaming even if rendering fails
                            }
                        } else if (data.type === 'stats') {
                            // Capture token generation statistics
                            tokenStats = data.data;
                            devLog('📊 [STATS] Received token statistics:', tokenStats);
                        } else if (data.type === 'follow_up_questions') {
                            // 후속 질문 수신 즉시 표시 (done 전후 모두 처리)
                            inlineFollowUpQs = data.data;
                            console.log('💬 [FOLLOW-UP] Received follow-up questions:', inlineFollowUpQs, 'contentDiv:', !!contentDiv);
                            if (inlineFollowUpQs && inlineFollowUpQs.length > 0 && contentDiv) {
                                try {
                                    followUpQuestions.display(contentDiv, inlineFollowUpQs, (selectedQuestion) => {
                                        userInput.value = selectedQuestion;
                                        autoResize();
                                        updateSendButton();
                                        sendMessage();
                                    });
                                    scrollToBottom();
                                    console.log('💬 [FOLLOW-UP] Display completed successfully');
                                } catch (e) {
                                    console.error('💬 [FOLLOW-UP] Display failed:', e);
                                }
                            } else {
                                console.warn('💬 [FOLLOW-UP] Skipped display:', {
                                    hasData: !!inlineFollowUpQs,
                                    length: inlineFollowUpQs?.length,
                                    hasContentDiv: !!contentDiv
                                });
                            }
                        } else if (data.type === 'replace') {
                            // 서버에서 깨진 문서명 인용 수정 후 전체 텍스트 교체
                            devLog('🔧 [REPLACE] Received corrected response (garbled citation fix)');
                            fullText = data.data;
                            try {
                                contentDiv.innerHTML = sanitizeHTML(marked.parse(fullText);
                                contentDiv.querySelectorAll('pre code').forEach((block) => {
                                    if (!block.dataset.highlighted) {
                                        normalizeLanguageClass(block);
                                        hljs.highlightElement(block);
                                    }
                                });
                                renderSpecialContent(contentDiv);
                            } catch (renderError) {
                                logger.error('Replace render error:', renderError);
                            }
                        } else if (data.type === 'confidence') {
                            // 신뢰도 점수 수신
                            devLog('📊 [CONFIDENCE] Received confidence score:', data.data);
                        } else if (data.type === 'done') {
                            // Finish streaming TTS
                            streamingTTS.finish();

                            // Calculate response time
                            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

                            // Check for empty response
                            if (!fullText || fullText.trim().length === 0) {
                                logger.warn('⚠️ Empty response received from server');
                                fullText = '죄송합니다. 응답을 생성하지 못했습니다. 다시 시도해 주세요.\n\n**가능한 원인:**\n- 모델이 응답을 생성하지 못함\n- 요청 시간 초과\n- 서버 부하로 인한 응답 실패';
                                contentDiv.innerHTML = sanitizeHTML(marked.parse(fullText);
                            }

                            // Show completion (StreamingVisualizer)
                            streamingVisualizer.showCompletion(tokenCount, parseFloat(elapsed));

                            // Scroll to bottom to show completion
                            scrollToBottom();

                            // Add assistant response to conversation history
                            // Server already filtered <think> tags, use fullText directly
                            conversationHistory.push({
                                role: 'assistant',
                                content: fullText,
                                sources: sources || [],  // Save sources for history restoration
                                context: currentContextData || []  // Save context data for source details modal
                            });

                            // Save to localStorage
                            saveHistory();

                            // Add timestamp with token statistics
                            addResponseTime(messageDiv, elapsed, data.data?.cached, tokenStats);

                            // Add action buttons first
                            addActionButtons(contentDiv, fullText);

                            // Add sources if available (after action buttons)
                            devLog('📚 [SOURCES] Checking sources:', {
                                sources: sources,
                                length: sources ? sources.length : 'undefined',
                                type: typeof sources,
                                isArray: Array.isArray(sources)
                            });

                            if (sources && sources.length > 0) {
                                devLog('✅ [SOURCES] Adding sources to UI:', sources);

                                // Add HR separator before sources
                                const hr = document.createElement('hr');
                                hr.className = 'sources-separator';
                                contentDiv.appendChild(hr);

                                // Create sources section
                                const sourcesDiv = document.createElement('div');
                                sourcesDiv.className = 'sources';
                                sourcesDiv.innerHTML = '<strong>📚 참고 문서:</strong><br>';

                                sources.forEach(source => {
                                    const sourceTag = document.createElement('span');
                                    sourceTag.className = 'source-tag';
                                    sourceTag.textContent = source;

                                    // Add click handler to show source details
                                    sourceTag.addEventListener('click', () => {
                                        showSourceDetails(source);
                                    });

                                    sourcesDiv.appendChild(sourceTag);
                                });

                                contentDiv.appendChild(sourcesDiv);
                            } else {
                                devWarn('⚠️ [SOURCES] No sources to display:', {
                                    sources: sources,
                                    sourcesExists: !!sources,
                                    sourcesLength: sources ? sources.length : 0,
                                    type: typeof sources
                                });
                            }

                            // 후속 질문은 follow_up_questions 이벤트에서 직접 표시됨 (done 이후 도착)
                            // 캐시 응답의 경우 done 전에 이미 표시 완료
                        }
                    } catch (parseError) {
                        logger.error('JSON parse error:', parseError, 'Line:', line);
                    }
                }
            }
        }

    } catch (error) {
        logger.error('Query failed:', error);

        // Show error in StreamingVisualizer
        streamingVisualizer.showError('응답 생성 중 오류가 발생했습니다.');

        // Handle error with ErrorHandler
        const errorInfo = errorHandler.handleError(error, 'sendMessage');

        // Handle abort (user stopped generation)
        if (error.name === 'AbortError') {
            addMessage('⚠️ 응답 생성이 중단되었습니다.', 'bot');
            streamingTTS.stop(); // Stop streaming TTS on abort
        } else {
            // Show error message with retry option if available
            errorHandler.showErrorMessage(errorInfo, errorInfo.canRetry);
            streamingTTS.stop(); // Stop streaming TTS on error
        }
    } finally {
        isLoading = false;
        currentAbortController = null;
        hideStopButton();
        updateSendButton();

        // Reset StreamingVisualizer
        streamingVisualizer.reset();

        // Note: Don't stop streaming TTS here - let it finish playing the queued audio

        // Refresh conversation list to update title after message (only if sidebar is open)
        if (currentSessionId && conversationSidebar.classList.contains('active')) {
            // Refresh to show updated title (first message updates title from "새 대화")
            await loadConversations();
        }
    }
}

/**
 * Display hybrid RAG search information
 * @param {HTMLElement} messageDiv - Message container
 * @param {Object} searchSummary - Search summary from hybrid RAG
 */
function displaySearchInfo(messageDiv, searchSummary) {
    if (!searchSummary || !searchSummary.sources_used || searchSummary.sources_used.length === 0) {
        return;
    }

    // Create search info container
    const searchInfoDiv = document.createElement('div');
    searchInfoDiv.className = 'search-info';
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    searchInfoDiv.style.cssText = `
        margin: 8px 0 12px 0;
        padding: 8px 12px;
        background: ${isDark ? 'linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(56, 189, 248, 0.10) 100%)' : 'linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)'};
        border-left: 3px solid ${isDark ? '#38bdf8' : '#0ea5e9'};
        border-radius: 6px;
        font-size: 13px;
        color: ${isDark ? '#7dd3fc' : '#0c4a6e'};
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
    `;

    // Search mode icon and text
    const iconSpan = document.createElement('span');
    iconSpan.textContent = '🔍';
    iconSpan.style.fontSize = '16px';

    const modeText = document.createElement('span');
    modeText.style.fontWeight = '600';
    modeText.textContent = '하이브리드 검색 사용';

    searchInfoDiv.appendChild(iconSpan);
    searchInfoDiv.appendChild(modeText);

    // Add separator
    const separator = document.createElement('span');
    separator.textContent = '|';
    separator.style.cssText = `color: ${isDark ? '#64748b' : '#94a3b8'}; font-weight: 300;`;
    searchInfoDiv.appendChild(separator);

    // Source counts
    const sourcesInfo = [];

    if (searchSummary.local_count > 0) {
        sourcesInfo.push(`📚 로컬 ${searchSummary.local_count}개`);
    }

    if (searchSummary.web_count > 0) {
        sourcesInfo.push(`🌐 웹 ${searchSummary.web_count}개`);
    }

    if (searchSummary.docs_count > 0) {
        sourcesInfo.push(`📖 공식문서 ${searchSummary.docs_count}개`);
    }

    const sourcesText = document.createElement('span');
    sourcesText.textContent = sourcesInfo.join(' · ');
    sourcesText.style.cssText = `color: ${isDark ? '#38bdf8' : '#0369a1'}; font-size: 12px;`;
    searchInfoDiv.appendChild(sourcesText);

    // Insert before message content
    const contentDiv = messageDiv.querySelector('.message-content');
    if (contentDiv) {
        messageDiv.insertBefore(searchInfoDiv, contentDiv);
    } else {
        messageDiv.appendChild(searchInfoDiv);
    }
}

// Add message to chat
function addMessage(text, type, sources = null) {
    // Remove welcome message if exists
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (type === 'bot') {
        // Render markdown
        contentDiv.innerHTML = sanitizeHTML(marked.parse(text);

        // Highlight code blocks
        contentDiv.querySelectorAll('pre code').forEach((block) => {
            if (!block.dataset.highlighted) {
                normalizeLanguageClass(block);
                hljs.highlightElement(block);
            }
        });

        // Render special content (math, diagrams, music, charts)
        renderSpecialContent(contentDiv);

        // Add sources if available
        if (sources && sources.length > 0) {
            // Create wrapper for sources section and action buttons
            const sourcesWrapper = document.createElement('div');
            sourcesWrapper.className = 'sources-wrapper';

            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'sources';
            sourcesDiv.innerHTML = '<strong>📚 참고 문서:</strong><br>';

            sources.forEach(source => {
                const sourceTag = document.createElement('span');
                sourceTag.className = 'source-tag';
                sourceTag.textContent = source;
                sourcesDiv.appendChild(sourceTag);
            });

            sourcesWrapper.appendChild(sourcesDiv);

            // Add action buttons to wrapper (same level as sources)
            addActionButtonsToWrapper(sourcesWrapper, text);

            contentDiv.appendChild(sourcesWrapper);
        }
    } else {
        contentDiv.textContent = text;
    }

    messageDiv.appendChild(contentDiv);
    chatContainer.appendChild(messageDiv);

    // Scroll to bottom
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // Update scroll button visibility after adding message
    setTimeout(() => updateScrollButtonVisibility(), 100);

    return messageDiv;
}

// Show loading animation with message
function showLoading(message = '로딩 중...') {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot';
    loadingDiv.id = 'loading-msg';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const loadingAnimation = document.createElement('div');
    loadingAnimation.className = 'loading';
    loadingAnimation.innerHTML = `
        <div class="loading-text" id="loading-text">${message}</div>
        <div class="loading-dots">
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
        </div>
        <button class="stop-btn" id="stop-btn" onclick="stopGeneration()" title="중단">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect x="4" y="4" width="8" height="8" rx="1"/>
            </svg>
        </button>
    `;

    contentDiv.appendChild(loadingAnimation);
    loadingDiv.appendChild(contentDiv);
    chatContainer.appendChild(loadingDiv);

    chatContainer.scrollTop = chatContainer.scrollHeight;

    return 'loading-msg';
}

// Update loading message
function updateLoadingMessage(loadingId, message) {
    const loadingText = document.getElementById('loading-text');
    if (loadingText) {
        loadingText.textContent = message;
    }
}

// Remove loading animation
function removeLoading(id) {
    const loadingEl = document.getElementById(id);
    if (loadingEl) {
        loadingEl.remove();
    }
}

// Clear chat and create new conversation
async function clearChat() {
    if (confirm('새 대화를 시작하시겠습니까?\n(현재 대화는 히스토리에 저장됩니다)')) {
        // Clear conversation history (both in memory and localStorage)
        clearHistory();

        // Clear AutoComplete
        if (questionAutoComplete) {
            questionAutoComplete.clear();
        }

        // Create new conversation (this will show welcome screen automatically)
        await createNewConversation();
    }
}

// Reindex documents
async function reindexDocuments() {
    // Get modal elements
    const modal = document.getElementById('reindexProgressModal');
    const progressBar = document.getElementById('reindexProgressBar');
    const progressPercent = document.getElementById('reindexProgressPercent');
    const progressStep = document.getElementById('reindexProgressStep');
    const progressStats = document.getElementById('reindexProgressStats');
    const progressTime = document.getElementById('reindexProgressTime');

    // Time tracking for remaining time calculation
    let startTime = null;
    let lastProgress = 0;

    // Check if reindexing is already in progress
    try {
        const checkResponse = await fetch('/api/reindex/progress');
        if (checkResponse.ok) {
            const currentProgress = await checkResponse.json();
            const inProgressSteps = ['문서 처리 중', '임베딩 생성 중', '데이터베이스 저장 중', '메타데이터 저장 중'];

            if (inProgressSteps.includes(currentProgress.step)) {
                // Already in progress - just show the modal
                alert('⚠️ 재색인이 이미 진행 중입니다.\n\n진행 상황을 확인하세요.');

                // Show modal with current progress
                modal.style.display = 'flex';
                reindexBtn.disabled = true;

                // Set current progress
                progressBar.style.width = `${currentProgress.progress}%`;
                progressPercent.textContent = `${currentProgress.progress}%`;
                progressStep.textContent = currentProgress.step;
                if (currentProgress.current_item && currentProgress.total_items) {
                    progressStats.textContent = `${currentProgress.current_item} / ${currentProgress.total_items}`;
                } else {
                    progressStats.textContent = '0 / 0';
                }

                // Start polling to monitor existing reindex
                monitorReindexProgress(modal, progressBar, progressPercent, progressStep, progressStats);
                return;
            }
        }
    } catch (error) {
        logger.error('Failed to check reindex status:', error);
        // If check fails, proceed with confirmation
    }

    // Not in progress - ask for confirmation
    if (!confirm('문서를 재색인하시겠습니까?\n\n⏳ 재색인은 수 분이 걸릴 수 있습니다.\n✓ 진행 상황을 확인할 수 있습니다.')) {
        return;
    }

    // Show modal
    modal.style.display = 'flex';
    reindexBtn.disabled = true;

    // Reset progress - force width update
    progressBar.style.width = '0%';
    progressBar.style.display = 'flex'; // Ensure it's visible
    progressBar.style.background = 'linear-gradient(90deg, #667eea 0%, #764ba2 50%, #f093fb 100%)'; // Reset to original gradient
    progressPercent.textContent = '0%';
    progressStep.textContent = '재색인 시작 중...';
    progressStats.textContent = '0 / 0';
    progressTime.textContent = ''; // Reset time display

    // Reset cancel button state
    const cancelReindexBtn = document.getElementById('cancelReindexBtn');
    if (cancelReindexBtn) {
        cancelReindexBtn.disabled = false;
        cancelReindexBtn.textContent = '🛑 재색인 중지';
    }

    // Reset time tracking variables
    startTime = null;
    lastProgress = 0;

    // Debug: Log initial state
    devLog('Progress bar reset. Width:', progressBar.style.width, 'Background:', progressBar.style.background, 'Element:', progressBar);

    let progressInterval;
    let consecutiveErrors = 0;
    const MAX_CONSECUTIVE_ERRORS = 3;

    try {
        // Start polling for progress
        progressInterval = setInterval(async () => {
            try {
                const progressResponse = await fetch('/api/reindex/progress');

                if (progressResponse.ok) {
                    consecutiveErrors = 0; // Reset error counter on success
                    const progressData = await progressResponse.json();

                    // Update progress bar
                    const progress = progressData.progress || 0;
                    progressBar.style.width = `${progress}%`;
                    progressPercent.textContent = `${progress}%`;

                    // Calculate and update remaining time
                    if (!startTime && progress > 0) {
                        startTime = Date.now();
                    }

                    if (startTime && progress > lastProgress && progress > 0 && progress < 100) {
                        const elapsedSeconds = (Date.now() - startTime) / 1000;
                        const estimatedTotalSeconds = (elapsedSeconds / progress) * 100;
                        const remainingSeconds = Math.max(0, estimatedTotalSeconds - elapsedSeconds);

                        if (remainingSeconds > 0) {
                            const minutes = Math.floor(remainingSeconds / 60);
                            const seconds = Math.floor(remainingSeconds % 60);
                            progressTime.textContent = `약 ${minutes}분 ${seconds}초 남음`;
                        } else {
                            progressTime.textContent = '곧 완료됩니다';
                        }
                    } else if (progress >= 100) {
                        progressTime.textContent = '완료!';
                    }
                    lastProgress = progress;

                    // Debug: Log progress update
                    devLog(`Progress updated: ${progress}%, width: ${progressBar.style.width}, element:`, progressBar);

                    // Update step text
                    progressStep.textContent = progressData.step || '진행 중...';

                    // Update stats if available
                    if (progressData.current_item && progressData.total_items) {
                        progressStats.textContent = `${progressData.current_item} / ${progressData.total_items} 문서`;
                    } else {
                        progressStats.textContent = '0 / 0 문서';
                    }

                    // Check for completion
                    if (progressData.step === '완료') {
                        clearInterval(progressInterval);

                        // Wait a moment to show completion
                        await new Promise(resolve => setTimeout(resolve, 1000));

                        // Hide modal
                        modal.style.display = 'none';

                        // Re-enable button
                        reindexBtn.disabled = false;

                        // Success message
                        const docCount = vector_db ? vector_db.count_documents() : 'unknown';
                        alert(`✅ 재색인이 완료되었습니다!`);
                        await checkStatus();
                    } else if (progressData.step === '오류 발생') {
                        clearInterval(progressInterval);
                        progressBar.style.background = 'linear-gradient(90deg, #ef4444, #dc2626)';

                        await new Promise(resolve => setTimeout(resolve, 2000));

                        modal.style.display = 'none';
                        progressBar.style.background = '';
                        reindexBtn.disabled = false;

                        alert(`❌ 재색인 실패\n\n로그를 확인해주세요.`);
                    } else if (progressData.step === '취소됨' || progressData.step === '취소 중...') {
                        clearInterval(progressInterval);
                        progressBar.style.background = 'linear-gradient(90deg, #f59e0b, #f97316)';

                        await new Promise(resolve => setTimeout(resolve, 1500));

                        modal.style.display = 'none';
                        progressBar.style.background = '';
                        reindexBtn.disabled = false;

                        alert(`🛑 재색인이 취소되었습니다.`);
                        await checkStatus();
                    }
                } else {
                    consecutiveErrors++;
                }
            } catch (error) {
                logger.error('Failed to fetch progress:', error);
                consecutiveErrors++;

                // Stop polling after consecutive errors
                if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                    logger.warn('Too many consecutive errors, stopping progress polling');
                    clearInterval(progressInterval);
                    progressStep.textContent = '서버 연결 실패';
                }
            }
        }, 1000);

        // Start reindexing (returns immediately)
        const response = await fetch('/api/reindex', {
            method: 'POST'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        devLog(`Reindex started: ${data.message}`);

        // Wait for progress polling to detect completion
        // Progress interval will continue until completion or error is detected

    } catch (error) {
        logger.error('Reindex failed:', error);

        // Clear progress polling
        if (progressInterval) {
            clearInterval(progressInterval);
        }

        // Update modal to show error
        progressBar.style.width = '0%';
        progressBar.style.background = 'linear-gradient(90deg, #ef4444, #dc2626)';
        progressStep.textContent = '오류 발생';
        progressDetails.textContent = error.message;

        // Wait a moment to show error
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Hide modal
        modal.style.display = 'none';
        progressBar.style.background = '';

        alert(`❌ 재색인 실패\n\n오류: ${error.message}\n\n로그를 확인해주세요.`);
    } finally {
        reindexBtn.disabled = false;
    }
}

// Monitor ongoing reindex progress (for duplicate prevention)
function monitorReindexProgress(modal, progressBar, progressPercent, progressStep, progressStats) {
    let consecutiveErrors = 0;
    const MAX_CONSECUTIVE_ERRORS = 3;

    const progressInterval = setInterval(async () => {
        try {
            const progressResponse = await fetch('/api/reindex/progress');

            if (progressResponse.ok) {
                consecutiveErrors = 0; // Reset error counter on success
                const progressData = await progressResponse.json();

                // Update progress bar
                const progress = progressData.progress || 0;
                progressBar.style.width = `${progress}%`;
                progressPercent.textContent = `${progress}%`;

                // Calculate and update remaining time (monitor mode)
                if (!startTime && progress > 0) {
                    startTime = Date.now();
                }

                if (startTime && progress > lastProgress && progress > 0 && progress < 100) {
                    const elapsedSeconds = (Date.now() - startTime) / 1000;
                    const estimatedTotalSeconds = (elapsedSeconds / progress) * 100;
                    const remainingSeconds = Math.max(0, estimatedTotalSeconds - elapsedSeconds);

                    if (remainingSeconds > 0) {
                        const minutes = Math.floor(remainingSeconds / 60);
                        const seconds = Math.floor(remainingSeconds % 60);
                        progressTime.textContent = `약 ${minutes}분 ${seconds}초 남음`;
                    } else {
                        progressTime.textContent = '곧 완료됩니다';
                    }
                } else if (progress >= 100) {
                    progressTime.textContent = '완료!';
                }
                lastProgress = progress;

                // Debug: Log progress update
                devLog(`[Monitor] Progress updated: ${progress}%, width: ${progressBar.style.width}, element:`, progressBar);

                // Update step text
                progressStep.textContent = progressData.step || '진행 중...';

                // Update stats if available
                if (progressData.current_item && progressData.total_items) {
                    progressStats.textContent = `${progressData.current_item} / ${progressData.total_items} 문서`;
                } else {
                    progressStats.textContent = '0 / 0 문서';
                }

                // Check if completed or error
                if (progressData.step === '완료') {
                    clearInterval(progressInterval);

                    // Wait a moment to show completion
                    await new Promise(resolve => setTimeout(resolve, 1000));

                    // Hide modal
                    modal.style.display = 'none';

                    // Re-enable button
                    reindexBtn.disabled = false;

                    // Refresh status
                    await checkStatus();
                } else if (progressData.step === '오류 발생') {
                    clearInterval(progressInterval);

                    // Show error
                    progressBar.style.background = 'linear-gradient(90deg, #ef4444, #dc2626)';

                    // Wait a moment
                    await new Promise(resolve => setTimeout(resolve, 2000));

                    // Hide modal
                    modal.style.display = 'none';
                    progressBar.style.background = '';

                    // Re-enable button
                    reindexBtn.disabled = false;
                } else if (progressData.step === '취소됨' || progressData.step === '취소 중...') {
                    clearInterval(progressInterval);

                    // Show cancelled
                    progressBar.style.background = 'linear-gradient(90deg, #f59e0b, #f97316)';

                    // Wait a moment
                    await new Promise(resolve => setTimeout(resolve, 1500));

                    // Hide modal
                    modal.style.display = 'none';
                    progressBar.style.background = '';

                    // Re-enable button
                    reindexBtn.disabled = false;

                    // Refresh status
                    await checkStatus();
                }
            } else {
                consecutiveErrors++;
            }
        } catch (error) {
            logger.error('Failed to fetch progress:', error);
            consecutiveErrors++;

            // Stop polling after consecutive errors
            if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
                logger.warn('Too many consecutive errors, stopping progress polling');
                clearInterval(progressInterval);
                progressStep.textContent = '서버 연결 실패';

                // Wait a moment then hide modal
                setTimeout(() => {
                    modal.style.display = 'none';
                    reindexBtn.disabled = false;
                }, 3000);
            }
        }
    }, 1000);
}

// Stop generation
function stopGeneration() {
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }
}

// Add action buttons (copy + regenerate) to bot message
function addActionButtons(contentDiv, text) {
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions';

    // Feedback buttons (👍/👎) - always show
    const feedbackDiv = document.createElement('div');
    feedbackDiv.className = 'feedback-buttons';

    const thumbsUpBtn = document.createElement('button');
    thumbsUpBtn.className = 'action-btn feedback-btn thumbs-up-btn';
    thumbsUpBtn.setAttribute('title', '도움이 되었어요');
    thumbsUpBtn.setAttribute('aria-label', '긍정 평가');
    thumbsUpBtn.setAttribute('data-feedback-type', 'positive');
    thumbsUpBtn.innerHTML = '👍';
    thumbsUpBtn.onclick = (e) => submitFeedback(e.target, 'positive');

    const thumbsDownBtn = document.createElement('button');
    thumbsDownBtn.className = 'action-btn feedback-btn thumbs-down-btn';
    thumbsDownBtn.setAttribute('title', '개선이 필요해요');
    thumbsDownBtn.setAttribute('aria-label', '부정 평가');
    thumbsDownBtn.setAttribute('data-feedback-type', 'negative');
    thumbsDownBtn.innerHTML = '👎';
    thumbsDownBtn.onclick = (e) => submitFeedback(e.target, 'negative');

    feedbackDiv.appendChild(thumbsUpBtn);
    feedbackDiv.appendChild(thumbsDownBtn);

    // Copy button (icon only)
    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn copy-btn';
    copyBtn.setAttribute('title', '클립보드에 복사');
    copyBtn.setAttribute('aria-label', '클립보드에 복사');
    copyBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <rect x="5" y="5" width="9" height="9" rx="1" stroke-width="1.5"/>
            <path d="M3 11V3C3 2.44772 3.44772 2 4 2H10" stroke-width="1.5"/>
        </svg>
    `;
    copyBtn.onclick = () => copyToClipboard(text, copyBtn);

    // Regenerate button (icon only)
    const regenerateBtn = document.createElement('button');
    regenerateBtn.className = 'action-btn regenerate-btn';
    regenerateBtn.setAttribute('title', '새로운 답변 생성');
    regenerateBtn.setAttribute('aria-label', '새로운 답변 생성');
    regenerateBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <path d="M13 5C11.5 3 9.5 2.5 7 3M3 11C4.5 13 6.5 13.5 9 13" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M13 3V5H11M3 13V11H5" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    `;
    regenerateBtn.onclick = () => sendMessage(true);

    // Download button with dropdown menu
    const downloadContainer = document.createElement('div');
    downloadContainer.className = 'download-container';
    downloadContainer.style.position = 'relative';

    const downloadBtn = document.createElement('button');
    downloadBtn.className = 'action-btn download-btn';
    downloadBtn.setAttribute('title', '답변 다운로드');
    downloadBtn.setAttribute('aria-label', '답변 다운로드');
    downloadBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <path d="M8 2V10M8 10L5 7M8 10L11 7" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M3 13H13" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
    `;

    // Download dropdown menu
    const downloadMenu = document.createElement('div');
    downloadMenu.className = 'download-menu';
    downloadMenu.innerHTML = `
        <div class="download-option" data-format="json">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 3h10v10H3V3zm1 1v8h8V4H4zm1 1h6v1H5V5zm0 2h6v1H5V7zm0 2h4v1H5V9z"/>
            </svg>
            <span>JSON (.json)</span>
        </div>
        <div class="download-option" data-format="markdown">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 2h12v12H2V2zm1 1v10h10V3H3zm1 1h8v1H4V4zm0 2h8v1H4V6zm0 2h5v1H4V8z"/>
            </svg>
            <span>Markdown (.md)</span>
        </div>
        <div class="download-option" data-format="html">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 3h12v10H2V3zm1 1v8h10V4H3zm1 1h8v1H4V5zm0 2h8v1H4V7zm0 2h5v1H4V9z"/>
            </svg>
            <span>HTML (.html)</span>
        </div>
        <div class="download-option" data-format="txt">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 2h12v12H2V2zm1 1v10h10V3H3zm1 1h8v1H4V4zm0 2h8v1H4V6zm0 2h6v1H4V8z"/>
            </svg>
            <span>텍스트 (.txt)</span>
        </div>
        <div class="download-option" data-format="pdf">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 2h7l3 3v9H3V2zm1 1v10h8V6h-3V3H4zm5 0v2h2l-2-2z"/>
                <text x="5" y="12" font-size="6" fill="white" font-weight="bold">PDF</text>
            </svg>
            <span>PDF (.pdf)</span>
        </div>
        <div class="download-option" data-format="docx">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 2h7l3 3v9H3V2zm1 1v10h8V6h-3V3H4zm5 0v2h2l-2-2z"/>
            </svg>
            <span>Word 문서 (.docx)</span>
        </div>
        <div class="download-option" data-format="hwpx">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 2h7l3 3v9H3V2zm1 1v10h8V6h-3V3H4zm5 0v2h2l-2-2z"/>
                <text x="5" y="11" font-size="5" fill="white" font-weight="bold">한</text>
            </svg>
            <span>한글 문서 (.hwpx)</span>
        </div>
    `;
    downloadMenu.style.display = 'none';

    // Toggle menu on button click
    downloadBtn.onclick = (e) => {
        e.stopPropagation();
        const isVisible = downloadMenu.style.display === 'block';

        // Close all other download menus
        document.querySelectorAll('.download-menu').forEach(menu => {
            menu.style.display = 'none';
        });

        downloadMenu.style.display = isVisible ? 'none' : 'block';
    };

    // Handle download option clicks
    downloadMenu.querySelectorAll('.download-option').forEach(option => {
        option.onclick = (e) => {
            e.stopPropagation();
            const format = option.getAttribute('data-format');
            downloadAnswer(text, format, downloadBtn);
            downloadMenu.style.display = 'none';
        };
    });

    // Close menu when clicking outside
    document.addEventListener('click', () => {
        downloadMenu.style.display = 'none';
    });

    downloadContainer.appendChild(downloadBtn);
    downloadContainer.appendChild(downloadMenu);

    // TTS (Text-to-Speech) button
    const ttsBtn = document.createElement('button');
    ttsBtn.className = 'action-btn tts-btn';
    ttsBtn.setAttribute('title', '음성으로 읽기');
    ttsBtn.setAttribute('aria-label', '음성으로 읽기');
    ttsBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <path d="M8 3L4 6H2v4h2l4 3V3z" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M11 5c1.2 1.2 1.2 4.6 0 6" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M13 3c2.4 2.4 2.4 7.6 0 10" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
    `;
    ttsBtn.onclick = () => playTTS(text, ttsBtn);

    // Initially hide TTS button, show based on availability
    ttsBtn.style.display = 'none';
    checkTTSAvailability().then(available => {
        if (available) {
            ttsBtn.style.display = 'inline-flex';
        }
    });

    actionsDiv.appendChild(feedbackDiv);
    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(regenerateBtn);
    actionsDiv.appendChild(downloadContainer);
    actionsDiv.appendChild(ttsBtn);
    contentDiv.appendChild(actionsDiv);
}

// Add action buttons to sources wrapper (positioned on the right side)
function addActionButtonsToWrapper(wrapperDiv, text) {
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions-inline';

    // Feedback buttons (👍/👎)
    const feedbackDiv = document.createElement('div');
    feedbackDiv.className = 'feedback-buttons';

    const thumbsUpBtn = document.createElement('button');
    thumbsUpBtn.className = 'action-btn feedback-btn thumbs-up-btn';
    thumbsUpBtn.setAttribute('title', '도움이 되었어요');
    thumbsUpBtn.setAttribute('aria-label', '긍정 평가');
    thumbsUpBtn.setAttribute('data-feedback-type', 'positive');
    thumbsUpBtn.innerHTML = '👍';
    thumbsUpBtn.onclick = (e) => submitFeedback(e.target, 'positive');

    const thumbsDownBtn = document.createElement('button');
    thumbsDownBtn.className = 'action-btn feedback-btn thumbs-down-btn';
    thumbsDownBtn.setAttribute('title', '개선이 필요해요');
    thumbsDownBtn.setAttribute('aria-label', '부정 평가');
    thumbsDownBtn.setAttribute('data-feedback-type', 'negative');
    thumbsDownBtn.innerHTML = '👎';
    thumbsDownBtn.onclick = (e) => submitFeedback(e.target, 'negative');

    feedbackDiv.appendChild(thumbsUpBtn);
    feedbackDiv.appendChild(thumbsDownBtn);

    // Copy button (icon only)
    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn copy-btn';
    copyBtn.setAttribute('title', '클립보드에 복사');
    copyBtn.setAttribute('aria-label', '클립보드에 복사');
    copyBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <rect x="5" y="5" width="9" height="9" rx="1" stroke-width="1.5"/>
            <path d="M3 11V3C3 2.44772 3.44772 2 4 2H10" stroke-width="1.5"/>
        </svg>
    `;
    copyBtn.onclick = () => copyToClipboard(text, copyBtn);

    // Regenerate button (icon only)
    const regenerateBtn = document.createElement('button');
    regenerateBtn.className = 'action-btn regenerate-btn';
    regenerateBtn.setAttribute('title', '새로운 답변 생성');
    regenerateBtn.setAttribute('aria-label', '새로운 답변 생성');
    regenerateBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <path d="M13 5C11.5 3 9.5 2.5 7 3M3 11C4.5 13 6.5 13.5 9 13" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M13 3V5H11M3 13V11H5" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    `;
    regenerateBtn.onclick = () => sendMessage(true);

    // Download button with dropdown menu
    const downloadContainer = document.createElement('div');
    downloadContainer.className = 'download-container';
    downloadContainer.style.position = 'relative';

    const downloadBtn = document.createElement('button');
    downloadBtn.className = 'action-btn download-btn';
    downloadBtn.setAttribute('title', '답변 다운로드');
    downloadBtn.setAttribute('aria-label', '답변 다운로드');
    downloadBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <path d="M8 2V10M8 10L5 7M8 10L11 7" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M3 13H13" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
    `;

    // Download dropdown menu
    const downloadMenu = document.createElement('div');
    downloadMenu.className = 'download-menu';
    downloadMenu.innerHTML = `
        <div class="download-option" data-format="json">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 3h10v10H3V3zm1 1v8h8V4H4zm1 1h6v1H5V5zm0 2h6v1H5V7zm0 2h4v1H5V9z"/>
            </svg>
            <span>JSON (.json)</span>
        </div>
        <div class="download-option" data-format="markdown">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 2h12v12H2V2zm1 1v10h10V3H3zm1 1h8v1H4V4zm0 2h8v1H4V6zm0 2h5v1H4V8z"/>
            </svg>
            <span>Markdown (.md)</span>
        </div>
        <div class="download-option" data-format="html">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 3h12v10H2V3zm1 1v8h10V4H3zm1 1h8v1H4V5zm0 2h8v1H4V7zm0 2h5v1H4V9z"/>
            </svg>
            <span>HTML (.html)</span>
        </div>
        <div class="download-option" data-format="txt">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 2h12v12H2V2zm1 1v10h10V3H3zm1 1h8v1H4V4zm0 2h8v1H4V6zm0 2h6v1H4V8z"/>
            </svg>
            <span>텍스트 (.txt)</span>
        </div>
        <div class="download-option" data-format="pdf">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 2h7l3 3v9H3V2zm1 1v10h8V6h-3V3H4zm5 0v2h2l-2-2z"/>
                <text x="5" y="12" font-size="6" fill="white" font-weight="bold">PDF</text>
            </svg>
            <span>PDF (.pdf)</span>
        </div>
        <div class="download-option" data-format="docx">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 2h7l3 3v9H3V2zm1 1v10h8V6h-3V3H4zm5 0v2h2l-2-2z"/>
            </svg>
            <span>Word 문서 (.docx)</span>
        </div>
        <div class="download-option" data-format="hwpx">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 2h7l3 3v9H3V2zm1 1v10h8V6h-3V3H4zm5 0v2h2l-2-2z"/>
                <text x="5" y="11" font-size="5" fill="white" font-weight="bold">한</text>
            </svg>
            <span>한글 문서 (.hwpx)</span>
        </div>
    `;
    downloadMenu.style.display = 'none';

    // Toggle menu on button click
    downloadBtn.onclick = (e) => {
        e.stopPropagation();
        const isVisible = downloadMenu.style.display === 'block';

        // Close all other download menus
        document.querySelectorAll('.download-menu').forEach(menu => {
            menu.style.display = 'none';
        });

        downloadMenu.style.display = isVisible ? 'none' : 'block';
    };

    // Handle download option clicks
    downloadMenu.querySelectorAll('.download-option').forEach(option => {
        option.onclick = (e) => {
            e.stopPropagation();
            const format = option.getAttribute('data-format');
            downloadAnswer(text, format, downloadBtn);
            downloadMenu.style.display = 'none';
        };
    });

    // Close menu when clicking outside
    document.addEventListener('click', () => {
        downloadMenu.style.display = 'none';
    });

    downloadContainer.appendChild(downloadBtn);
    downloadContainer.appendChild(downloadMenu);

    // TTS (Text-to-Speech) button
    const ttsBtn = document.createElement('button');
    ttsBtn.className = 'action-btn tts-btn';
    ttsBtn.setAttribute('title', '음성으로 읽기');
    ttsBtn.setAttribute('aria-label', '음성으로 읽기');
    ttsBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <path d="M8 3L4 6H2v4h2l4 3V3z" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M11 5c1.2 1.2 1.2 4.6 0 6" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M13 3c2.4 2.4 2.4 7.6 0 10" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
    `;
    ttsBtn.onclick = () => playTTS(text, ttsBtn);

    // Initially hide TTS button, show based on availability
    ttsBtn.style.display = 'none';
    checkTTSAvailability().then(available => {
        if (available) {
            ttsBtn.style.display = 'inline-flex';
        }
    });

    actionsDiv.appendChild(feedbackDiv);
    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(regenerateBtn);
    actionsDiv.appendChild(downloadContainer);
    actionsDiv.appendChild(ttsBtn);
    wrapperDiv.appendChild(actionsDiv);
}

// ====================================================================
// TTS (Text-to-Speech) Functions
// ====================================================================

// Global TTS state
let ttsAudio = null;
let ttsCacheAvailable = null;
let ttsSessionId = null;              // Track which session TTS was started for
let ttsAbortController = null;        // Abort controller for on-demand playTTS fetch
let ttsStopping = false;              // Flag: stopAllTTS is in progress (suppress error UI)

/**
 * Stop all TTS activity (both on-demand and streaming).
 * Call this when navigating away, loading a new conversation, or cleaning up.
 */
function stopAllTTS() {
    ttsStopping = true;

    // Abort in-flight on-demand TTS fetch
    if (ttsAbortController) {
        ttsAbortController.abort();
        ttsAbortController = null;
    }

    // Stop on-demand TTS audio playback
    if (ttsAudio) {
        try {
            ttsAudio.pause();
            ttsAudio.src = '';
            ttsAudio = null;
        } catch (e) { /* ignore */ }
    }
    if (currentTTSButton) {
        safeUpdateTTSButton(currentTTSButton, (btn) => {
            btn.classList.remove('tts-playing');
            btn.disabled = false;
            resetTTSButton(btn);
        });
        currentTTSButton = null;
    }
    hideTTSIndicator();

    // Stop streaming TTS
    streamingTTS.stop();

    ttsSessionId = null;

    // Reset the stopping flag after a delay so in-flight onerror/catch blocks see it
    setTimeout(() => { ttsStopping = false; }, 500);
}

// Check if TTS is available
async function checkTTSAvailability() {
    // Use cached result if available
    if (ttsCacheAvailable !== null) {
        return ttsCacheAvailable;
    }

    try {
        const response = await fetch('/api/tts/available');
        if (response.ok) {
            const data = await response.json();
            // enabled만 확인 - available은 lazy loading으로 첫 사용 시 true가 됨
            ttsCacheAvailable = data.enabled;
            return ttsCacheAvailable;
        }
    } catch (error) {
        devLog('TTS availability check failed:', error);
    }

    ttsCacheAvailable = false;
    return false;
}

// TTS model name mapping for display
const TTS_MODEL_NAMES = {
    'edge-tts': 'Edge TTS (Fast)',
    'Qwen/Qwen3-TTS-12Hz-0.6B-Base': 'Qwen3 TTS 0.6B (Fast Local)',
    'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice': 'Qwen3 TTS 1.7B (High Quality)',
};

// Load TTS status for settings panel
async function loadTTSStatus() {
    const ttsStatusIcon = document.getElementById('ttsStatusIcon');
    const ttsStatusText = document.getElementById('ttsStatusText');
    const ttsModelDisplay = document.getElementById('ttsModelDisplay');
    const ttsStatusDisplay = document.getElementById('ttsStatusDisplay');

    if (!ttsStatusIcon || !ttsStatusText || !ttsModelDisplay) {
        return;
    }

    try {
        const response = await fetch('/api/tts/available');
        if (response.ok) {
            const data = await response.json();

            if (data.enabled) {
                ttsStatusIcon.textContent = '✅';
                ttsStatusText.textContent = '활성화됨';
                ttsStatusDisplay.style.background = '#ecfdf5';
                ttsStatusDisplay.style.borderColor = '#10b981';
            } else {
                ttsStatusIcon.textContent = '⛔';
                ttsStatusText.textContent = '비활성화됨';
                ttsStatusDisplay.style.background = '#fef2f2';
                ttsStatusDisplay.style.borderColor = '#ef4444';
            }

            // Get model info from the public endpoint
            const modelId = data.model_id || 'edge-tts';
            const modelName = TTS_MODEL_NAMES[modelId] || modelId;
            ttsModelDisplay.textContent = modelName;
            ttsModelDisplay.style.color = data.enabled ? '#059669' : '#6b7280';
        } else {
            ttsStatusIcon.textContent = '❌';
            ttsStatusText.textContent = 'TTS 서비스 오류';
            ttsStatusDisplay.style.background = '#fef2f2';
            ttsStatusDisplay.style.borderColor = '#ef4444';
            ttsModelDisplay.textContent = '확인 불가';
        }
    } catch (error) {
        devLog('Failed to load TTS status:', error);
        ttsStatusIcon.textContent = '❌';
        ttsStatusText.textContent = '연결 실패';
        ttsStatusDisplay.style.background = '#fef2f2';
        ttsStatusDisplay.style.borderColor = '#ef4444';
        ttsModelDisplay.textContent = '확인 불가';
    }
}

// Global reference for current TTS button (for background playback support)
let currentTTSButton = null;

// Safely update TTS button if it still exists in DOM
function safeUpdateTTSButton(button, callback) {
    if (button && document.body.contains(button)) {
        try {
            callback(button);
        } catch (e) {
            devLog('TTS button update skipped (element may have been removed):', e);
        }
    }
}

// Play TTS for given text
async function playTTS(text, button) {
    // Early validation - check if input text exists
    if (!text || typeof text !== 'string' || text.trim().length === 0) {
        showToast('읽을 텍스트가 없습니다.', 'error');
        return;
    }

    // Stop any currently playing audio
    if (ttsAudio) {
        ttsAudio.pause();
        ttsAudio.currentTime = 0;
        ttsAudio = null;
        // Reset previous button if it exists
        safeUpdateTTSButton(currentTTSButton, (btn) => {
            btn.classList.remove('tts-playing');
            resetTTSButton(btn);
        });
        hideTTSIndicator();
    }

    // Check if already playing (toggle off)
    if (button && button.classList.contains('tts-playing')) {
        button.classList.remove('tts-playing');
        resetTTSButton(button);
        currentTTSButton = null;
        hideTTSIndicator();
        return;
    }

    // Store current button reference
    currentTTSButton = button;

    // Update button to loading state
    safeUpdateTTSButton(button, (btn) => {
        btn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" class="tts-loading">
                <circle cx="8" cy="8" r="6" stroke-width="1.5" stroke-dasharray="20" stroke-dashoffset="0">
                    <animate attributeName="stroke-dashoffset" dur="1s" repeatCount="indefinite" values="0;40"/>
                </circle>
            </svg>
        `;
        btn.setAttribute('title', '음성 생성 중...');
        btn.disabled = true;
    });

    try {
        const token = localStorage.getItem('access_token');
        if (!token) {
            throw new Error('로그인이 필요합니다.');
        }

        // Strip markdown and HTML for TTS
        const cleanText = stripMarkdownForTTS(text);

        // Debug log
        devLog('TTS input text length:', text.length, 'clean text length:', cleanText.length);

        // Check if text is empty after stripping
        if (!cleanText || cleanText.trim().length === 0) {
            throw new Error('읽을 수 있는 텍스트가 없습니다.');
        }

        // Truncate text if too long (server limit is typically 1000-5000 chars)
        const maxLength = 4500;  // Leave some margin under 5000 char server limit
        let finalText = cleanText;
        if (cleanText.length > maxLength) {
            // Find a good breaking point (end of sentence)
            let cutPoint = cleanText.lastIndexOf('. ', maxLength);
            if (cutPoint < maxLength * 0.7) {
                cutPoint = maxLength;  // If no good break point, just cut
            }
            finalText = cleanText.substring(0, cutPoint + 1);
            devLog(`TTS text truncated from ${cleanText.length} to ${finalText.length} chars`);
        }

        // Track which session this TTS request belongs to
        const ttsRequestSession = currentSessionId;
        ttsSessionId = ttsRequestSession;

        // Request TTS synthesis with timeout
        // Use global controller so stopAllTTS() can abort this in-flight fetch
        ttsAbortController = new AbortController();
        const timeoutMs = 180000; // 3 minutes (matches backend max)
        const timeoutId = setTimeout(() => {
            if (ttsAbortController) ttsAbortController.abort();
        }, timeoutMs);

        let response;
        let ttsStartTime = Date.now();
        try {
            response = await fetch('/api/tts/synthesize', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: finalText,
                    language: 'ko'
                }),
                signal: ttsAbortController.signal
            });
            clearTimeout(timeoutId);
            devLog(`TTS synthesis completed in ${((Date.now() - ttsStartTime) / 1000).toFixed(1)}s`);
        } catch (fetchError) {
            clearTimeout(timeoutId);
            ttsAbortController = null;
            // If stopAllTTS() triggered this abort, exit silently
            if (ttsStopping) {
                devLog('TTS fetch aborted by stopAllTTS — suppressing error');
                return;
            }
            // Ensure button is reset on timeout/abort
            safeUpdateTTSButton(button, (btn) => {
                btn.classList.remove('tts-playing');
                resetTTSButton(btn);
            });
            if (fetchError.name === 'AbortError') {
                const elapsedTime = ((Date.now() - ttsStartTime) / 1000).toFixed(0);
                devLog(`TTS timeout after ${elapsedTime}s - server may still be processing`);
                throw new Error(`TTS 생성 시간이 초과되었습니다 (${elapsedTime}초). 텍스트가 너무 길거나 서버가 바쁠 수 있습니다. 잠시 후 다시 시도하거나 관리자 설정에서 Edge TTS로 변경해보세요.`);
            }
            throw fetchError;
        }

        // Fetch completed — clear the global abort controller
        ttsAbortController = null;

        // Guard: if user navigated away during synthesis, discard result
        if (currentSessionId !== ttsRequestSession) {
            devLog('TTS discarded: session changed during synthesis');
            return;
        }

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'TTS 생성 실패' }));
            throw new Error(errorData.detail || errorData.error || 'TTS 생성 실패');
        }

        const result = await response.json();

        // Create and play audio
        ttsAudio = new Audio(result.audio_url + '?token=' + encodeURIComponent(token));

        // Update button to playing state (safely)
        safeUpdateTTSButton(button, (btn) => {
            btn.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <rect x="4" y="3" width="3" height="10" rx="1" fill="currentColor"/>
                    <rect x="9" y="3" width="3" height="10" rx="1" fill="currentColor"/>
                </svg>
            `;
            btn.setAttribute('title', '재생 중지');
            btn.classList.add('tts-playing');
            btn.disabled = false;
        });

        // Play audio
        ttsAudio.play();

        // Show floating indicator for background playback
        showTTSIndicator();

        // Handle audio ended - safely update button if it still exists
        ttsAudio.onended = () => {
            safeUpdateTTSButton(currentTTSButton, (btn) => {
                btn.classList.remove('tts-playing');
                resetTTSButton(btn);
            });
            ttsAudio = null;
            currentTTSButton = null;
            hideTTSIndicator();
            devLog('TTS playback completed');
        };

        // Handle audio error - safely update button if it still exists
        ttsAudio.onerror = (e) => {
            devLog('TTS audio error:', e);
            // Suppress error if stopAllTTS() is running or page is navigating away
            if (ttsStopping || window.allowNavigation) {
                devLog('TTS audio error suppressed — stop/navigation in progress');
                return;
            }
            safeUpdateTTSButton(currentTTSButton, (btn) => {
                btn.classList.remove('tts-playing');
                resetTTSButton(btn);
            });
            // Only show error if user is still on the same page
            if (document.body.contains(button)) {
                showError('음성 재생에 실패했습니다.');
            }
            ttsAudio = null;
            currentTTSButton = null;
            hideTTSIndicator();
        };

    } catch (error) {
        devLog('TTS error:', error);
        ttsAbortController = null;
        // If stopAllTTS() is running or page is navigating away,
        // suppress error UI entirely — cleanup is handled by stopAllTTS()
        if (ttsStopping || window.allowNavigation) {
            devLog('TTS error suppressed — stop/navigation in progress');
            return;
        }
        // Always reset button state on error, even if page has changed
        safeUpdateTTSButton(button, (btn) => {
            btn.classList.remove('tts-playing');
            btn.disabled = false;  // Ensure button is re-enabled
            resetTTSButton(btn);
        });
        // Only show error if user is still on same page
        if (document.body.contains(button)) {
            showError(`TTS 오류: ${error.message}`);
        }
        currentTTSButton = null;
        hideTTSIndicator();
    }
}

// Reset TTS button to default state
function resetTTSButton(button) {
    button.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
            <path d="M8 3L4 6H2v4h2l4 3V3z" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M11 5c1.2 1.2 1.2 4.6 0 6" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M13 3c2.4 2.4 2.4 7.6 0 10" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
    `;
    button.setAttribute('title', '음성으로 읽기');
    button.disabled = false;
}

// Global TTS stop function - can be called from anywhere
function stopTTS() {
    if (ttsAudio) {
        ttsAudio.pause();
        ttsAudio.currentTime = 0;
        ttsAudio = null;
    }
    safeUpdateTTSButton(currentTTSButton, (btn) => {
        btn.classList.remove('tts-playing');
        resetTTSButton(btn);
    });
    currentTTSButton = null;
    hideTTSIndicator();
    devLog('TTS stopped globally');
}

// Floating TTS indicator for background playback
function showTTSIndicator() {
    let indicator = document.getElementById('tts-floating-indicator');
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'tts-floating-indicator';
        indicator.innerHTML = `
            <div class="tts-indicator-content">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" class="tts-indicator-icon">
                    <path d="M8 3L4 6H2v4h2l4 3V3z" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M11 5c1.2 1.2 1.2 4.6 0 6" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                <span>재생 중</span>
                <button class="tts-indicator-stop" onclick="stopTTS()" title="중지">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                        <rect x="3" y="3" width="10" height="10" rx="1"/>
                    </svg>
                </button>
            </div>
        `;
        indicator.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 8px 12px;
            border-radius: 20px;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            z-index: 10000;
            font-size: 13px;
            font-weight: 500;
            animation: ttsIndicatorPulse 2s ease-in-out infinite;
            display: none;
        `;

        // Add animation style if not exists
        if (!document.getElementById('tts-indicator-style')) {
            const style = document.createElement('style');
            style.id = 'tts-indicator-style';
            style.textContent = `
                @keyframes ttsIndicatorPulse {
                    0%, 100% { transform: scale(1); opacity: 1; }
                    50% { transform: scale(1.02); opacity: 0.9; }
                }
                .tts-indicator-content {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }
                .tts-indicator-icon {
                    animation: ttsIconBounce 1s ease-in-out infinite;
                }
                @keyframes ttsIconBounce {
                    0%, 100% { transform: translateY(0); }
                    50% { transform: translateY(-2px); }
                }
                .tts-indicator-stop {
                    background: rgba(255,255,255,0.2);
                    border: none;
                    border-radius: 50%;
                    width: 24px;
                    height: 24px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    transition: background 0.2s;
                    color: white;
                }
                .tts-indicator-stop:hover {
                    background: rgba(255,255,255,0.3);
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(indicator);
    }
    indicator.style.display = 'block';
}

function hideTTSIndicator() {
    const indicator = document.getElementById('tts-floating-indicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
}

// Strip markdown formatting for TTS - natural speech conversion (Korean/English)
function stripMarkdownForTTS(text) {
    // Validate input
    if (!text || typeof text !== 'string') {
        devLog('stripMarkdownForTTS: invalid input', text);
        return '내용을 읽을 수 없습니다.';
    }

    try {
        // Korean ordinal number mapping for lists
        const koreanOrdinals = ['첫째', '둘째', '셋째', '넷째', '다섯째', '여섯째', '일곱째', '여덟째', '아홉째', '열째',
            '열한째', '열두째', '열셋째', '열넷째', '열다섯째', '열여섯째', '열일곱째', '열여덟째', '열아홉째', '스무째'];

        // Programming language names for natural reading
        const langNames = {
            'js': '자바스크립트', 'javascript': '자바스크립트', 'jsx': '제이에스엑스',
            'ts': '타입스크립트', 'typescript': '타입스크립트', 'tsx': '티에스엑스',
            'py': '파이썬', 'python': '파이썬', 'python3': '파이썬 3',
            'java': '자바', 'kotlin': '코틀린', 'scala': '스칼라', 'groovy': '그루비',
            'cpp': '씨플러스플러스', 'c++': '씨플러스플러스', 'c': '씨 언어', 'h': '헤더 파일',
            'cs': '씨샵', 'csharp': '씨샵', 'fsharp': '에프샵', 'vb': '비주얼베이직',
            'rb': '루비', 'ruby': '루비', 'rails': '레일즈',
            'go': '고', 'golang': '고랭',
            'rs': '러스트', 'rust': '러스트',
            'php': '피에이치피', 'laravel': '라라벨',
            'swift': '스위프트', 'objc': '오브젝티브씨', 'objective-c': '오브젝티브씨',
            'dart': '다트', 'flutter': '플러터',
            'sql': '에스큐엘', 'mysql': '마이에스큐엘', 'postgresql': '포스트그레스큐엘', 'sqlite': '에스큐엘라이트',
            'mongodb': '몽고디비', 'redis': '레디스', 'elasticsearch': '엘라스틱서치',
            'html': '에이치티엠엘', 'html5': '에이치티엠엘 5', 'xhtml': '엑스에이치티엠엘',
            'css': '씨에스에스', 'css3': '씨에스에스 3', 'scss': '에스씨에스에스', 'sass': '사스', 'less': '레스',
            'json': '제이슨', 'xml': '엑스엠엘', 'yaml': '야믈', 'yml': '야믈', 'toml': '토믈',
            'md': '마크다운', 'markdown': '마크다운', 'rst': '리스트럭처드텍스트',
            'bash': '배쉬', 'shell': '쉘', 'sh': '쉘', 'zsh': '지쉘', 'powershell': '파워쉘', 'ps1': '파워쉘',
            'dockerfile': '도커파일', 'docker': '도커', 'makefile': '메이크파일',
            'nginx': '엔진엑스', 'apache': '아파치',
            'graphql': '그래프큐엘', 'protobuf': '프로토버프',
            'r': '알 언어', 'matlab': '매트랩', 'julia': '줄리아',
            'lua': '루아', 'perl': '펄', 'haskell': '하스켈', 'elixir': '엘릭서', 'erlang': '얼랭',
            'clojure': '클로저', 'lisp': '리스프', 'scheme': '스킴',
            'assembly': '어셈블리', 'asm': '어셈블리', 'wasm': '웹어셈블리',
            'solidity': '솔리디티', 'vyper': '바이퍼',
            'terraform': '테라폼', 'ansible': '앤서블', 'puppet': '퍼핏',
            'vue': '뷰', 'react': '리액트', 'angular': '앵귤러', 'svelte': '스벨트',
            'nextjs': '넥스트제이에스', 'nuxt': '넉스트', 'gatsby': '개츠비',
            'express': '익스프레스', 'fastapi': '패스트에이피아이', 'django': '장고', 'flask': '플라스크',
            'spring': '스프링', 'springboot': '스프링부트'
        };

        // Comprehensive abbreviations dictionary
        const abbreviations = {
            // === 기술 일반 ===
            'API': '에이피아이', 'APIs': '에이피아이들',
            'UI': '유아이', 'UX': '유엑스', 'GUI': '지유아이', 'CLI': '커맨드라인',
            'SDK': '에스디케이', 'IDE': '통합개발환경', 'CDN': '씨디엔',
            'CMS': '콘텐츠관리시스템', 'CRM': '고객관계관리',
            'ERP': '전사적자원관리', 'SCM': '공급망관리',

            // === 데이터베이스 ===
            'DB': '데이터베이스', 'DBMS': '데이터베이스관리시스템',
            'SQL': '에스큐엘', 'NoSQL': '노에스큐엘',
            'ACID': '에이씨아이디', 'CRUD': '크러드',
            'ORM': '오알엠', 'ODM': '오디엠',
            'ETL': '이티엘', 'OLAP': '올랩', 'OLTP': '올티피',

            // === 네트워크/웹 ===
            'HTTP': '에이치티티피', 'HTTPS': '에이치티티피에스',
            'URL': '유알엘', 'URI': '유알아이', 'URN': '유알엔',
            'DNS': '디엔에스', 'IP': '아이피', 'IPv4': '아이피버전4', 'IPv6': '아이피버전6',
            'TCP': '티씨피', 'UDP': '유디피', 'FTP': '에프티피', 'SFTP': '에스에프티피',
            'SSH': '에스에스에이치', 'SSL': '에스에스엘', 'TLS': '티엘에스',
            'SMTP': '에스엠티피', 'IMAP': '아이맵', 'POP3': '팝쓰리',
            'REST': '레스트', 'RESTful': '레스트풀', 'SOAP': '소프',
            'GraphQL': '그래프큐엘', 'gRPC': '지알피씨', 'RPC': '알피씨',
            'WebSocket': '웹소켓', 'WebRTC': '웹알티씨',
            'CORS': '코어스', 'CSRF': '씨에스알에프', 'XSS': '크로스사이트스크립팅',
            'VPN': '브이피엔', 'LAN': '랜', 'WAN': '완', 'WLAN': '더블유랜',
            'NAT': '나트', 'DHCP': '디에이치씨피', 'ARP': '알피',
            'BGP': '비지피', 'OSPF': '오에스피에프',

            // === 데이터 형식 ===
            'JSON': '제이슨', 'XML': '엑스엠엘', 'CSV': '씨에스브이',
            'YAML': '야믈', 'TOML': '토믈', 'INI': '아이엔아이',
            'HTML': '에이치티엠엘', 'CSS': '씨에스에스', 'JS': '자바스크립트',
            'SVG': '에스브이지', 'PDF': '피디에프', 'RTF': '알티에프',
            'ZIP': '집', 'TAR': '타르', 'GZIP': '지집',
            'BASE64': '베이스64', 'UTF8': '유티에프8', 'ASCII': '아스키', 'UNICODE': '유니코드',

            // === 클라우드/인프라 ===
            'AWS': '아마존 웹 서비스', 'GCP': '구글 클라우드', 'Azure': '애저',
            'EC2': '이씨투', 'S3': '에스쓰리', 'RDS': '알디에스', 'Lambda': '람다',
            'ECS': '이씨에스', 'EKS': '이케이에스', 'ECR': '이씨알',
            'VPC': '브이피씨', 'IAM': '아이에이엠', 'KMS': '케이엠에스',
            'SaaS': '사스', 'PaaS': '파스', 'IaaS': '아이아스', 'FaaS': '파스',
            'BaaS': '바스', 'DaaS': '다스', 'MaaS': '마스',
            'VM': '가상머신', 'VPS': '브이피에스', 'Container': '컨테이너',
            'K8s': '쿠버네티스', 'Kubernetes': '쿠버네티스', 'Docker': '도커',
            'Terraform': '테라폼', 'Ansible': '앤서블',
            'CI': '지속적통합', 'CD': '지속적배포', 'CICD': '씨아이씨디',
            'DevOps': '데브옵스', 'MLOps': '엠엘옵스', 'DataOps': '데이터옵스', 'GitOps': '깃옵스',
            'SRE': '사이트신뢰성엔지니어링', 'SLA': '서비스수준협약', 'SLO': '서비스수준목표',

            // === AI/ML ===
            'AI': '인공지능', 'ML': '머신러닝', 'DL': '딥러닝',
            'LLM': '대규모 언어 모델', 'GPT': '지피티', 'BERT': '버트', 'LSTM': '엘에스티엠',
            'NLP': '자연어처리', 'NLU': '자연어이해', 'NLG': '자연어생성',
            'CV': '컴퓨터비전', 'CNN': '씨엔엔', 'RNN': '알엔엔', 'GAN': '갠',
            'RL': '강화학습', 'SL': '지도학습', 'UL': '비지도학습',
            'RAG': '랙', 'LangChain': '랭체인', 'HuggingFace': '허깅페이스',
            'TensorFlow': '텐서플로', 'PyTorch': '파이토치', 'Keras': '케라스',
            'OCR': '광학문자인식', 'TTS': '텍스트투스피치', 'STT': '음성인식', 'ASR': '자동음성인식',

            // === 보안 ===
            'OAuth': '오어스', 'OAuth2': '오어스2', 'OIDC': '오아이디씨',
            'JWT': '제이더블유티', 'JWS': '제이더블유에스', 'JWE': '제이더블유이',
            'SSO': '싱글사인온', 'MFA': '다중인증', '2FA': '이중인증', 'OTP': '일회용비밀번호',
            'SAML': '샘엘', 'LDAP': '엘댑', 'AD': '액티브디렉토리',
            'PKI': '공개키기반구조', 'RSA': '알에스에이', 'AES': '에이이에스', 'SHA': '에스에이치에이',
            'MD5': '엠디파이브', 'HMAC': '에이치맥',
            'RBAC': '역할기반접근제어', 'ABAC': '속성기반접근제어',
            'WAF': '웹방화벽', 'IDS': '침입탐지시스템', 'IPS': '침입방지시스템',
            'DDoS': '디도스', 'DoS': '도스', 'SQLi': '에스큐엘인젝션',
            'OWASP': '오와스프', 'CVE': '씨브이이', 'CVSS': '씨브이에스에스',

            // === 개발방법론 ===
            'TDD': '테스트주도개발', 'BDD': '행위주도개발', 'DDD': '도메인주도설계',
            'MVC': '엠브이씨', 'MVP': '엠브이피', 'MVVM': '엠브이브이엠',
            'OOP': '객체지향프로그래밍', 'FP': '함수형프로그래밍',
            'SOLID': '솔리드', 'DRY': '드라이', 'KISS': '키스', 'YAGNI': '야그니',
            'Agile': '애자일', 'Scrum': '스크럼', 'Kanban': '칸반', 'XP': '익스트림프로그래밍',
            'Waterfall': '워터폴', 'Lean': '린',
            'PR': '풀리퀘스트', 'MR': '머지리퀘스트', 'CR': '코드리뷰',
            'QA': '품질보증', 'UAT': '사용자인수테스트', 'E2E': '엔드투엔드',

            // === 하드웨어/시스템 ===
            'CPU': '씨피유', 'GPU': '지피유', 'TPU': '티피유', 'NPU': '엔피유',
            'RAM': '램', 'ROM': '롬', 'SSD': '에스에스디', 'HDD': '하드디스크',
            'NVMe': '엔브이엠이', 'SATA': '사타', 'SCSI': '스커지',
            'BIOS': '바이오스', 'UEFI': '유이에프아이', 'GRUB': '그럽',
            'USB': '유에스비', 'HDMI': '에이치디엠아이', 'DisplayPort': '디스플레이포트',
            'PCIe': '피씨아이익스프레스', 'NIC': '네트워크카드',
            'OS': '운영체제', 'POSIX': '포직스', 'UNIX': '유닉스', 'Linux': '리눅스',
            'IoT': '사물인터넷', 'RTOS': '실시간운영체제',

            // === 용량/단위 ===
            'KB': '킬로바이트', 'MB': '메가바이트', 'GB': '기가바이트', 'TB': '테라바이트', 'PB': '페타바이트',
            'Kbps': '킬로비트퍼세컨드', 'Mbps': '메가비트퍼세컨드', 'Gbps': '기가비트퍼세컨드',
            'MHz': '메가헤르츠', 'GHz': '기가헤르츠',
            'ms': '밀리초', 'μs': '마이크로초', 'ns': '나노초',
            'px': '픽셀', 'dpi': '디피아이', 'ppi': '피피아이',

            // === 비즈니스/일반 ===
            'B2B': '비투비', 'B2C': '비투씨', 'C2C': '씨투씨', 'D2C': '디투씨',
            'ROI': '투자수익률', 'KPI': '핵심성과지표', 'OKR': '목표및핵심결과',
            'MVP': '최소기능제품', 'POC': '개념증명', 'PoC': '개념증명',
            'SOP': '표준운영절차', 'FAQ': '자주묻는질문', 'Q&A': '질의응답',
            'CEO': '최고경영자', 'CTO': '최고기술책임자', 'CFO': '최고재무책임자', 'COO': '최고운영책임자',
            'PM': '프로젝트매니저', 'PO': '제품책임자', 'SM': '스크럼마스터',
            'HR': '인사', 'R&D': '연구개발', 'M&A': '인수합병',
            'IPO': '기업공개', 'VC': '벤처캐피탈', 'PE': '사모펀드',
            'ASAP': '가능한빨리', 'FYI': '참고로', 'TBD': '미정', 'TBA': '추후공지', 'WIP': '작업중',
            'ETA': '예상도착시간', 'EOD': '오늘업무종료', 'COB': '영업종료',

            // === 일반 약어 ===
            'etc': '등등', 'vs': '대', 'vs.': '대',
            'e.g.': '예를 들어', 'i.e.': '즉', 'cf.': '참고',
            'a.k.a.': '또는', 'aka': '또는',
            'w/': '와 함께', 'w/o': '없이',
            'approx': '대략', 'max': '최대', 'min': '최소', 'avg': '평균',
            'req': '요청', 'res': '응답', 'err': '에러', 'msg': '메시지',
            'src': '소스', 'dest': '목적지', 'tmp': '임시', 'temp': '임시',
            'prev': '이전', 'next': '다음', 'curr': '현재', 'current': '현재',
            'init': '초기화', 'config': '설정', 'cfg': '설정',
            'auth': '인증', 'authz': '인가', 'authn': '인증',
            'admin': '관리자', 'user': '사용자', 'guest': '게스트',
            'dev': '개발', 'prod': '운영', 'stg': '스테이징', 'staging': '스테이징',
            'env': '환경', 'var': '변수', 'const': '상수', 'func': '함수',
            'obj': '객체', 'arr': '배열', 'str': '문자열', 'num': '숫자', 'bool': '불리언',
            'int': '정수', 'float': '실수', 'char': '문자',
            'param': '파라미터', 'arg': '인자', 'prop': '속성', 'attr': '속성',
            'elem': '요소', 'node': '노드', 'idx': '인덱스', 'len': '길이',
            'btn': '버튼', 'img': '이미지', 'vid': '비디오', 'aud': '오디오',
            'doc': '문서', 'docs': '문서들', 'ref': '참조', 'refs': '참조들',
            'repo': '저장소', 'repos': '저장소들', 'pkg': '패키지', 'lib': '라이브러리',
            'deps': '의존성', 'dep': '의존성', 'mod': '모듈', 'mods': '모듈들',
            'ver': '버전', 'vers': '버전들', 'v1': '버전1', 'v2': '버전2', 'v3': '버전3',
            'info': '정보', 'stat': '상태', 'stats': '통계',
            'sync': '동기', 'async': '비동기',
            'pub': '공개', 'priv': '비공개', 'prot': '보호됨',
            'req': '요청', 'resp': '응답', 'ack': '확인',
            'tx': '트랜잭션', 'rx': '수신',
            'io': '입출력', 'stdin': '표준입력', 'stdout': '표준출력', 'stderr': '표준에러'
        };

        // Common English words/phrases with Korean pronunciation guide
        const englishToKorean = {
            // 동사/행위
            'click': '클릭', 'double-click': '더블클릭', 'drag': '드래그', 'drop': '드롭',
            'scroll': '스크롤', 'swipe': '스와이프', 'tap': '탭', 'pinch': '핀치',
            'download': '다운로드', 'upload': '업로드', 'install': '설치', 'uninstall': '삭제',
            'login': '로그인', 'logout': '로그아웃', 'signup': '회원가입', 'signin': '로그인',
            'submit': '제출', 'cancel': '취소', 'confirm': '확인', 'reset': '초기화',
            'save': '저장', 'load': '불러오기', 'delete': '삭제', 'remove': '제거',
            'create': '생성', 'read': '읽기', 'update': '수정', 'edit': '편집',
            'copy': '복사', 'paste': '붙여넣기', 'cut': '잘라내기', 'undo': '실행취소', 'redo': '다시실행',
            'search': '검색', 'find': '찾기', 'filter': '필터', 'sort': '정렬',
            'import': '가져오기', 'export': '내보내기', 'backup': '백업', 'restore': '복원',
            'start': '시작', 'stop': '중지', 'pause': '일시정지', 'resume': '재개',
            'enable': '활성화', 'disable': '비활성화', 'toggle': '토글',
            'open': '열기', 'close': '닫기', 'show': '표시', 'hide': '숨기기',
            'expand': '펼치기', 'collapse': '접기', 'minimize': '최소화', 'maximize': '최대화',
            'zoom in': '확대', 'zoom out': '축소', 'fit': '맞춤',
            'refresh': '새로고침', 'reload': '다시불러오기', 'retry': '재시도',
            'connect': '연결', 'disconnect': '연결해제', 'sync': '동기화',
            'merge': '병합', 'split': '분리', 'join': '결합',
            'compile': '컴파일', 'build': '빌드', 'deploy': '배포', 'release': '릴리스',
            'debug': '디버그', 'test': '테스트', 'run': '실행', 'execute': '실행',
            'commit': '커밋', 'push': '푸시', 'pull': '풀', 'fetch': '패치', 'clone': '클론',
            'branch': '브랜치', 'checkout': '체크아웃', 'rebase': '리베이스', 'cherry-pick': '체리픽',

            // 명사/개념
            'file': '파일', 'folder': '폴더', 'directory': '디렉토리', 'path': '경로',
            'button': '버튼', 'link': '링크', 'icon': '아이콘', 'image': '이미지',
            'menu': '메뉴', 'tab': '탭', 'panel': '패널', 'window': '창', 'dialog': '대화상자',
            'modal': '모달', 'popup': '팝업', 'tooltip': '툴팁', 'dropdown': '드롭다운',
            'checkbox': '체크박스', 'radio': '라디오버튼', 'slider': '슬라이더', 'switch': '스위치',
            'input': '입력', 'output': '출력', 'form': '양식', 'field': '필드',
            'table': '테이블', 'row': '행', 'column': '열', 'cell': '셀',
            'list': '목록', 'grid': '그리드', 'card': '카드', 'item': '항목',
            'header': '헤더', 'footer': '푸터', 'sidebar': '사이드바', 'navbar': '내비게이션바',
            'content': '콘텐츠', 'layout': '레이아웃', 'container': '컨테이너', 'wrapper': '래퍼',
            'component': '컴포넌트', 'element': '요소', 'widget': '위젯', 'plugin': '플러그인',
            'template': '템플릿', 'theme': '테마', 'style': '스타일', 'design': '디자인',
            'font': '폰트', 'color': '색상', 'size': '크기', 'width': '너비', 'height': '높이',
            'margin': '마진', 'padding': '패딩', 'border': '테두리', 'shadow': '그림자',
            'animation': '애니메이션', 'transition': '트랜지션', 'effect': '효과',
            'event': '이벤트', 'handler': '핸들러', 'listener': '리스너', 'callback': '콜백',
            'request': '요청', 'response': '응답', 'status': '상태', 'error': '에러',
            'success': '성공', 'failure': '실패', 'warning': '경고', 'info': '정보',
            'message': '메시지', 'notification': '알림', 'alert': '알림', 'toast': '토스트',
            'log': '로그', 'debug': '디버그', 'trace': '추적', 'stack': '스택',
            'cache': '캐시', 'buffer': '버퍼', 'queue': '큐', 'pool': '풀',
            'thread': '스레드', 'process': '프로세스', 'task': '태스크', 'job': '잡',
            'session': '세션', 'cookie': '쿠키', 'token': '토큰', 'key': '키',
            'value': '값', 'pair': '쌍', 'map': '맵', 'set': '셋', 'array': '배열',
            'object': '객체', 'class': '클래스', 'instance': '인스턴스', 'method': '메서드',
            'function': '함수', 'variable': '변수', 'constant': '상수', 'parameter': '파라미터',
            'argument': '인자', 'return': '반환', 'type': '타입', 'interface': '인터페이스',
            'module': '모듈', 'package': '패키지', 'library': '라이브러리', 'framework': '프레임워크',
            'dependency': '의존성', 'version': '버전', 'release': '릴리스', 'update': '업데이트',
            'feature': '기능', 'bug': '버그', 'issue': '이슈', 'ticket': '티켓',
            'milestone': '마일스톤', 'sprint': '스프린트', 'backlog': '백로그',
            'repository': '저장소', 'branch': '브랜치', 'tag': '태그', 'commit': '커밋',
            'server': '서버', 'client': '클라이언트', 'host': '호스트', 'port': '포트',
            'database': '데이터베이스', 'schema': '스키마', 'query': '쿼리', 'index': '인덱스',
            'network': '네트워크', 'protocol': '프로토콜', 'packet': '패킷', 'payload': '페이로드',
            'endpoint': '엔드포인트', 'route': '라우트', 'middleware': '미들웨어',
            'controller': '컨트롤러', 'service': '서비스', 'model': '모델', 'view': '뷰',
            'frontend': '프론트엔드', 'backend': '백엔드', 'fullstack': '풀스택',
            'mobile': '모바일', 'desktop': '데스크톱', 'web': '웹', 'app': '앱',
            'platform': '플랫폼', 'environment': '환경', 'production': '운영', 'development': '개발',
            'testing': '테스트', 'staging': '스테이징', 'local': '로컬', 'remote': '원격',
            'cloud': '클라우드', 'on-premise': '온프레미스', 'hybrid': '하이브리드',
            'cluster': '클러스터', 'node': '노드', 'instance': '인스턴스', 'replica': '레플리카',
            'load balancer': '로드밸런서', 'proxy': '프록시', 'gateway': '게이트웨이',
            'microservice': '마이크로서비스', 'monolith': '모놀리스', 'serverless': '서버리스',
            'container': '컨테이너', 'orchestration': '오케스트레이션', 'automation': '자동화',
            'pipeline': '파이프라인', 'workflow': '워크플로우', 'process': '프로세스',
            'monitoring': '모니터링', 'logging': '로깅', 'tracing': '트레이싱', 'alerting': '알림',
            'metrics': '메트릭', 'dashboard': '대시보드', 'report': '리포트', 'analytics': '분석',
            'performance': '성능', 'latency': '지연시간', 'throughput': '처리량', 'bandwidth': '대역폭',
            'scalability': '확장성', 'reliability': '신뢰성', 'availability': '가용성',
            'security': '보안', 'privacy': '개인정보보호', 'compliance': '규정준수',
            'encryption': '암호화', 'decryption': '복호화', 'hash': '해시', 'salt': '솔트',
            'authentication': '인증', 'authorization': '인가', 'permission': '권한', 'role': '역할',
            'account': '계정', 'profile': '프로필', 'setting': '설정', 'preference': '환경설정',

            // 형용사/부사
            'default': '기본', 'custom': '사용자정의', 'optional': '선택적', 'required': '필수',
            'public': '공개', 'private': '비공개', 'protected': '보호됨', 'internal': '내부',
            'static': '정적', 'dynamic': '동적', 'readonly': '읽기전용', 'mutable': '가변',
            'sync': '동기', 'async': '비동기', 'parallel': '병렬', 'sequential': '순차',
            'online': '온라인', 'offline': '오프라인', 'active': '활성', 'inactive': '비활성',
            'valid': '유효', 'invalid': '무효', 'enabled': '활성화됨', 'disabled': '비활성화됨',
            'visible': '보임', 'hidden': '숨김', 'collapsed': '접힘', 'expanded': '펼침',
            'loading': '로딩중', 'pending': '대기중', 'processing': '처리중', 'completed': '완료됨',
            'successful': '성공', 'failed': '실패', 'cancelled': '취소됨', 'timeout': '시간초과',
            'deprecated': '더이상사용안함', 'obsolete': '구식', 'legacy': '레거시', 'latest': '최신',
            'stable': '안정', 'beta': '베타', 'alpha': '알파', 'preview': '프리뷰', 'canary': '카나리',
            'major': '메이저', 'minor': '마이너', 'patch': '패치', 'hotfix': '핫픽스',

            // 접속사/전치사
            'and': '그리고', 'or': '또는', 'not': '아님', 'but': '하지만',
            'if': '만약', 'then': '그러면', 'else': '그렇지않으면', 'when': '때',
            'while': '동안', 'for': '위해', 'with': '와함께', 'without': '없이',
            'from': '부터', 'to': '까지', 'in': '안에', 'out': '밖에',
            'before': '전에', 'after': '후에', 'between': '사이에', 'among': '중에',
            'above': '위에', 'below': '아래에', 'inside': '내부에', 'outside': '외부에'
        };

        // Function to convert camelCase/PascalCase to readable format
        const convertCamelCase = (str) => {
            if (/[가-힣]/.test(str) || str.length < 3) return str;
            return str.replace(/([a-z])([A-Z])/g, '$1 $2')
                      .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2');
        };

        // Function to convert snake_case to readable format
        const convertSnakeCase = (str) => {
            if (/[가-힣]/.test(str)) return str;
            return str.replace(/_/g, ' ');
        };

        // Function to convert kebab-case to readable format
        const convertKebabCase = (str) => {
            if (/[가-힣]/.test(str)) return str;
            return str.replace(/-/g, ' ');
        };

        let result = text

        // === PHASE 1: Handle code blocks ===
        .replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
            const langName = lang ? (langNames[lang.toLowerCase()] || lang) : '';
            const lineCount = code.trim().split('\n').length;
            if (langName) {
                return ` ${langName} 코드 ${lineCount}줄이 있습니다. `;
            }
            return ` 코드 ${lineCount}줄이 있습니다. `;
        })

        // Handle inline code - make it readable
        .replace(/`([^`]+)`/g, (match, code) => {
            if (code.length > 50 || /[\n\r]/.test(code)) {
                return ' 코드 ';
            }
            let readable = code;
            readable = convertSnakeCase(readable);
            readable = convertKebabCase(readable);
            readable = convertCamelCase(readable);
            return ` ${readable} `;
        })

        // === PHASE 2: Handle structural elements ===

        // Handle tables - convert to natural speech
        .replace(/^\|(.+)\|$/gm, (match, content) => {
            if (/^[\s\-:|]+$/.test(content)) return '';
            const cells = content.split('|').map(c => c.trim()).filter(c => c && !/^[\s\-:|]+$/.test(c));
            if (cells.length === 0) return '';
            return cells.join(', ') + '. ';
        })

        // Headers - add emphasis pause
        .replace(/^(#{1,6})\s+(.+)$/gm, (match, hashes, title) => {
            const level = hashes.length;
            return level <= 2 ? `${title}. ` : `${title}, `;
        })

        // Numbered lists with Korean ordinals
        .replace(/^(\s*)(\d+)\.\s+(.+)$/gm, (match, indent, num, content) => {
            const index = parseInt(num) - 1;
            const ordinal = koreanOrdinals[index] || `${num}번째`;
            return `${ordinal}, ${content}. `;
        })

        // Bullet points
        .replace(/^(\s*)[-*+]\s+(.+)$/gm, '$2. ')

        // Task lists
        .replace(/^(\s*)[-*+]\s+\[(x|X)\]\s+(.+)$/gm, '완료됨, $3. ')
        .replace(/^(\s*)[-*+]\s+\[\s?\]\s+(.+)$/gm, '미완료, $2. ')

        // Blockquotes
        .replace(/^>\s*(.+)$/gm, '인용, $1. ')

        // === PHASE 3: Handle inline formatting ===

        // Bold - keep content
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/__([^_]+)__/g, '$1')

        // Italic - keep content
        .replace(/\*([^*]+)\*/g, '$1')
        .replace(/_([^_]+)_/g, '$1')

        // Strikethrough - skip
        .replace(/~~([^~]+)~~/g, '')

        // Links - just keep text
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')

        // Images
        .replace(/!\[([^\]]*)\]\([^)]+\)/g, (match, alt) => {
            return alt && alt.trim() ? ` ${alt.trim()} 이미지. ` : ' 이미지가 있습니다. ';
        })

        // Horizontal rules
        .replace(/^[\s]*[-*_]{3,}[\s]*$/gm, '. ')

        // === PHASE 4: Handle special content ===

        // URLs - describe based on domain
        .replace(/https?:\/\/(www\.)?(github\.com|gitlab\.com)[^\s]*/gi, ' 깃허브 링크 ')
        .replace(/https?:\/\/(www\.)?(stackoverflow\.com)[^\s]*/gi, ' 스택오버플로우 링크 ')
        .replace(/https?:\/\/(www\.)?(youtube\.com|youtu\.be)[^\s]*/gi, ' 유튜브 링크 ')
        .replace(/https?:\/\/(www\.)?(google\.com)[^\s]*/gi, ' 구글 링크 ')
        .replace(/https?:\/\/(www\.)?(docs\.)[^\s]*/gi, ' 문서 링크 ')
        .replace(/https?:\/\/[^\s]+/g, ' 링크 ')

        // Email addresses
        .replace(/[\w.-]+@[\w.-]+\.\w+/g, ' 이메일 주소 ')

        // File extensions
        .replace(/\.([a-zA-Z0-9]+)(?=\s|$|[,.])/g, (match, ext) => {
            const extLower = ext.toLowerCase();
            if (langNames[extLower]) return ` ${langNames[extLower]} 파일`;
            return ` 점${ext} 파일`;
        })

        // File paths
        .replace(/(?:\/[\w.-]+)+\/?/g, (match) => {
            const parts = match.split('/').filter(p => p);
            if (parts.length > 2) {
                return ` ${parts[parts.length - 1]} 경로 `;
            }
            return match;
        })

        // HTML tags
        .replace(/<br\s*\/?>/gi, '. ')
        .replace(/<[^>]+>/g, '')

        // Escaped characters
        .replace(/\\([\\`*_{}[\]()#+\-.!])/g, '$1')

        // Footnotes
        .replace(/\[\^[^\]]+\]/g, '')
        .replace(/\[\^[^\]]+\]:\s*.+$/gm, '')

        // Definition lists
        .replace(/^:\s+(.+)$/gm, '$1. ');

        // === PHASE 5: Natural reading improvements ===

        // Expand abbreviations (case-sensitive, whole words)
        Object.entries(abbreviations).forEach(([abbr, expanded]) => {
            const regex = new RegExp(`\\b${abbr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'g');
            result = result.replace(regex, expanded);
        });

        // Note: Technical English terms are kept as-is for natural pronunciation by TTS
        // The englishToKorean dictionary is no longer applied to preserve technical terms in English

        // === PHASE 6: Numbers and units ===
        result = result
            // Percentages
            .replace(/(\d+(?:\.\d+)?)\s*%/g, '$1퍼센트')
            // Temperature
            .replace(/(\d+(?:\.\d+)?)\s*°C/gi, '$1도')
            .replace(/(\d+(?:\.\d+)?)\s*°F/gi, '화씨 $1도')
            .replace(/(\d+(?:\.\d+)?)\s*K\b/g, '$1켈빈')
            // Angles
            .replace(/(\d+(?:\.\d+)?)\s*°(?![CF])/g, '$1도')
            .replace(/(\d+(?:\.\d+)?)\s*rad/gi, '$1라디안')
            // Distance/Length
            .replace(/(\d+(?:\.\d+)?)\s*km/gi, '$1킬로미터')
            .replace(/(\d+(?:\.\d+)?)\s*m(?![a-z])/gi, '$1미터')
            .replace(/(\d+(?:\.\d+)?)\s*cm/gi, '$1센티미터')
            .replace(/(\d+(?:\.\d+)?)\s*mm/gi, '$1밀리미터')
            .replace(/(\d+(?:\.\d+)?)\s*inch(es)?/gi, '$1인치')
            .replace(/(\d+(?:\.\d+)?)\s*ft/gi, '$1피트')
            .replace(/(\d+(?:\.\d+)?)\s*mi(?:le)?s?/gi, '$1마일')
            // Weight
            .replace(/(\d+(?:\.\d+)?)\s*kg/gi, '$1킬로그램')
            .replace(/(\d+(?:\.\d+)?)\s*g(?![a-z])/gi, '$1그램')
            .replace(/(\d+(?:\.\d+)?)\s*mg/gi, '$1밀리그램')
            .replace(/(\d+(?:\.\d+)?)\s*lb/gi, '$1파운드')
            .replace(/(\d+(?:\.\d+)?)\s*oz/gi, '$1온스')
            // Volume
            .replace(/(\d+(?:\.\d+)?)\s*L\b/g, '$1리터')
            .replace(/(\d+(?:\.\d+)?)\s*ml/gi, '$1밀리리터')
            .replace(/(\d+(?:\.\d+)?)\s*gal/gi, '$1갤런')
            // Data size
            .replace(/(\d+(?:\.\d+)?)\s*PB/gi, '$1페타바이트')
            .replace(/(\d+(?:\.\d+)?)\s*TB/gi, '$1테라바이트')
            .replace(/(\d+(?:\.\d+)?)\s*GB/gi, '$1기가바이트')
            .replace(/(\d+(?:\.\d+)?)\s*MB/gi, '$1메가바이트')
            .replace(/(\d+(?:\.\d+)?)\s*KB/gi, '$1킬로바이트')
            .replace(/(\d+(?:\.\d+)?)\s*bytes?/gi, '$1바이트')
            .replace(/(\d+(?:\.\d+)?)\s*bits?/gi, '$1비트')
            // Speed
            .replace(/(\d+(?:\.\d+)?)\s*Gbps/gi, '$1기가비피에스')
            .replace(/(\d+(?:\.\d+)?)\s*Mbps/gi, '$1메가비피에스')
            .replace(/(\d+(?:\.\d+)?)\s*Kbps/gi, '$1킬로비피에스')
            .replace(/(\d+(?:\.\d+)?)\s*bps/gi, '$1비피에스')
            .replace(/(\d+(?:\.\d+)?)\s*km\/h/gi, '$1킬로미터 퍼 아워')
            .replace(/(\d+(?:\.\d+)?)\s*m\/s/gi, '$1미터 퍼 세컨드')
            // Frequency
            .replace(/(\d+(?:\.\d+)?)\s*THz/gi, '$1테라헤르츠')
            .replace(/(\d+(?:\.\d+)?)\s*GHz/gi, '$1기가헤르츠')
            .replace(/(\d+(?:\.\d+)?)\s*MHz/gi, '$1메가헤르츠')
            .replace(/(\d+(?:\.\d+)?)\s*KHz/gi, '$1킬로헤르츠')
            .replace(/(\d+(?:\.\d+)?)\s*Hz/gi, '$1헤르츠')
            // Time
            .replace(/(\d+)\s*h(?:our)?s?(?![a-z])/gi, '$1시간')
            .replace(/(\d+)\s*min(?:ute)?s?(?![a-z])/gi, '$1분')
            .replace(/(\d+)\s*sec(?:ond)?s?(?![a-z])/gi, '$1초')
            .replace(/(\d+(?:\.\d+)?)\s*ms(?![a-z])/gi, '$1밀리초')
            .replace(/(\d+(?:\.\d+)?)\s*μs/gi, '$1마이크로초')
            .replace(/(\d+(?:\.\d+)?)\s*ns/gi, '$1나노초')
            // Money
            .replace(/\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)/g, '$1달러')
            .replace(/₩\s*(\d+(?:,\d{3})*)/g, '$1원')
            .replace(/€\s*(\d+(?:,\d{3})*(?:\.\d{2})?)/g, '$1유로')
            .replace(/£\s*(\d+(?:,\d{3})*(?:\.\d{2})?)/g, '$1파운드')
            .replace(/¥\s*(\d+(?:,\d{3})*)/g, '$1엔')
            // Time formats
            .replace(/(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)/gi, (m, h, min, s, ap) =>
                `${ap.toUpperCase() === 'AM' ? '오전' : '오후'} ${h}시 ${min}분 ${s}초`)
            .replace(/(\d{1,2}):(\d{2})\s*(AM|PM)/gi, (m, h, min, ap) =>
                `${ap.toUpperCase() === 'AM' ? '오전' : '오후'} ${h}시 ${min}분`)
            .replace(/(\d{1,2}):(\d{2}):(\d{2})/g, '$1시 $2분 $3초')
            .replace(/(\d{1,2}):(\d{2})/g, '$1시 $2분')
            // Date formats
            .replace(/(\d{4})-(\d{1,2})-(\d{1,2})/g, '$1년 $2월 $3일')
            .replace(/(\d{1,2})\/(\d{1,2})\/(\d{4})/g, '$3년 $1월 $2일')
            .replace(/(\d{1,2})\/(\d{1,2})\/(\d{2})/g, '20$3년 $1월 $2일')
            // Version numbers
            .replace(/v(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z]+))?/gi, (m, maj, min, pat, pre) =>
                pre ? `버전 ${maj}점${min}점${pat} ${pre}` : `버전 ${maj}점${min}점${pat}`)
            .replace(/v(\d+)\.(\d+)/gi, '버전 $1점$2')
            // Korean won with commas
            .replace(/(\d{1,3}(?:,\d{3})+)\s*원/g, (m, num) => `${num.replace(/,/g, '')}원`)
            // Large numbers with commas (remove commas for TTS)
            .replace(/(\d{1,3}(?:,\d{3})+)/g, (m) => m.replace(/,/g, ''))
            // Decimal numbers (but not IP addresses or versions already handled)
            .replace(/(?<![.\d])(\d+)\.(\d+)(?![.\d])/g, '$1점$2')
            // Ranges
            .replace(/(\d+)\s*[-~]\s*(\d+)/g, '$1에서 $2')
            // Ratios
            .replace(/(\d+)\s*:\s*(\d+)/g, '$1대$2')
            // Powers
            .replace(/(\d+)\s*\^(\d+)/g, '$1의 $2제곱')
            .replace(/10\^(\d+)/g, '10의 $1승')
            // Fractions
            .replace(/(\d+)\s*\/\s*(\d+)(?!\d)/g, '$1분의 $2');

        // === PHASE 7: Handle special symbols ===
        result = result
            // HTML entities
            .replace(/&amp;/g, '그리고')
            .replace(/&lt;/g, '작다')
            .replace(/&gt;/g, '크다')
            .replace(/&nbsp;/g, ' ')
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            // Programming operators
            .replace(/!=/g, ' 같지않다 ')
            .replace(/!==/g, ' 일치하지않는다 ')
            .replace(/===/g, ' 일치한다 ')
            .replace(/==/g, ' 같다 ')
            .replace(/>=/g, ' 크거나같다 ')
            .replace(/<=/g, ' 작거나같다 ')
            .replace(/&&/g, ' 그리고 ')
            .replace(/\|\|/g, ' 또는 ')
            .replace(/\+\+/g, ' 증가 ')
            .replace(/--/g, ' 감소 ')
            .replace(/\+=/g, ' 더하기대입 ')
            .replace(/-=/g, ' 빼기대입 ')
            .replace(/\*=/g, ' 곱하기대입 ')
            .replace(/\/=/g, ' 나누기대입 ')
            // Arrows
            .replace(/->/g, ' 에서 ')
            .replace(/<-/g, ' 로부터 ')
            .replace(/=>/g, ' 화살표 ')
            .replace(/<</g, ' 왼쪽시프트 ')
            .replace(/>>/g, ' 오른쪽시프트 ')
            // Basic operators
            .replace(/(?<!\d)\+(?!\d)/g, ' 더하기 ')
            // Hyphen handling: Korean-hyphen-number → "다시" (e.g., 내부-1 → 내부 다시 1)
            .replace(/([가-힣])-(\d+)/g, '$1 다시 $2')
            // Number-hyphen-number already handled as range above (e.g., 1-10 → 1에서 10)
            // Other standalone hyphens
            .replace(/(?<![가-힣\d])-(?!\d)/g, ' ')
            .replace(/\*/g, ' 곱하기 ')
            .replace(/(?<![a-zA-Z])\/(?![a-zA-Z])/g, ' 나누기 ')
            .replace(/(?<![!=<>])=(?![=<>])/g, ' 는 ')
            // Brackets and parentheses (remove for speech)
            .replace(/[\[\]{}()]/g, ' ')
            // Special characters
            .replace(/&/g, ' 그리고 ')
            .replace(/\|/g, ' 또는 ')
            .replace(/@/g, ' 앳 ')
            .replace(/#(?!\s)/g, ' 해시 ')
            .replace(/\^/g, ' ')
            .replace(/~/g, ' ')
            .replace(/`/g, ' ')
            // Currency and units at end
            .replace(/원(?=\s|$|[,.])/g, '원')
            .replace(/달러(?=\s|$|[,.])/g, '달러')
            // Common emoticons
            .replace(/:D/g, ' ')
            .replace(/:\)/g, ' ')
            .replace(/:\(/g, ' ')
            .replace(/;\)/g, ' ')
            .replace(/:P/g, ' ')
            .replace(/<3/g, ' ')
            // Emojis - just remove them for clean TTS
            .replace(/[\u{1F300}-\u{1F9FF}]/gu, ' ')
            .replace(/[\u{2600}-\u{26FF}]/gu, ' ')
            .replace(/[\u{2700}-\u{27BF}]/gu, ' ');

        // === PHASE 8: Final cleanup ===

        // Clean up punctuation
        result = result
            .replace(/\.{2,}/g, '.')
            .replace(/,{2,}/g, ',')
            .replace(/!{2,}/g, '!')
            .replace(/\?{2,}/g, '?')
            .replace(/\s+\./g, '.')
            .replace(/\.\s*\./g, '.')
            .replace(/,\s*\./g, '.')
            .replace(/!\s*\./g, '!')
            .replace(/\?\s*\./g, '?')
            .replace(/\.+,/g, ',')
            .replace(/,+\s*,+/g, ',');

        // Clean up whitespace
        result = result
            .replace(/[ \t]+/g, ' ')
            .replace(/\n\s*\n\s*\n+/g, '\n\n')
            .replace(/^\s+|\s+$/gm, '')
            .trim();

        // Add natural pauses at sentence boundaries
        result = result
            .replace(/([가-힣a-zA-Z0-9])\n/g, '$1. ')
            .replace(/\n+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();

        // Final punctuation cleanup
        result = result
            .replace(/\s+([.,!?])/g, '$1')
            .replace(/([.,!?])\s*([.,!?])/g, '$1')
            .trim();

        // If result is empty or only punctuation, return a fallback message
        if (!result || result.replace(/[.,!?\s]/g, '').length === 0) {
            devLog('stripMarkdownForTTS: result empty after processing');
            return '내용을 읽을 수 없습니다.';
        }

        return result;
    } catch (error) {
        devLog('stripMarkdownForTTS error:', error);
        return text.replace(/<[^>]+>/g, '').replace(/[#*_`~]/g, '').trim() || '내용을 읽을 수 없습니다.';
    }
}

// Invalidate TTS cache (call when settings change)
function invalidateTTSCache() {
    ttsCacheAvailable = null;
}

// Refresh TTS buttons on all existing messages
async function refreshTTSButtons() {
    invalidateTTSCache();
    const available = await checkTTSAvailability();

    // Find all TTS buttons and update their visibility
    const ttsButtons = document.querySelectorAll('.tts-btn');
    ttsButtons.forEach(btn => {
        btn.style.display = available ? 'inline-flex' : 'none';
    });

    devLog('TTS buttons refreshed, available:', available, 'buttons count:', ttsButtons.length);
}

// Listen for page visibility changes to refresh TTS buttons
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        // Refresh TTS buttons when user comes back to the page
        refreshTTSButtons();
    }
});

// ===== Streaming TTS (Real-time Text-to-Speech) =====
const streamingTTS = {
    enabled: false,
    isActive: false,
    audioQueue: [],
    currentAudio: null,
    currentAudioUrl: null,      // Track URL for proper cleanup
    processedText: '',
    pendingText: '',
    isProcessing: false,
    isPlaying: false,           // Distinguish "playing audio" from "processing queue"
    abortController: null,
    sessionId: null,            // Track which session this TTS belongs to
    consecutiveErrors: 0,       // Track consecutive fetch errors
    pendingFetches: 0,          // Track in-flight fetch requests

    // Limits
    MAX_QUEUE_SIZE: 30,         // Max queued audio blobs to prevent memory bloat
    MAX_CONSECUTIVE_ERRORS: 3,  // Stop after this many consecutive failures
    FETCH_TIMEOUT_MS: 60000,    // Per-sentence fetch timeout (60s)

    // Sentence-ending patterns for Korean and English
    sentenceEndPattern: /[.!?。！？]\s*$|[.!?。！？](?=\s)|다\.\s*$|요\.\s*$|니다\.\s*$|세요\.\s*$/,

    // Initialize streaming TTS for a new response
    start() {
        if (!this.enabled) return;

        // Stop any previous streaming TTS
        this.stop();

        this.isActive = true;
        this.audioQueue = [];
        this.processedText = '';
        this.pendingText = '';
        this.isProcessing = false;
        this.isPlaying = false;
        this.consecutiveErrors = 0;
        this.pendingFetches = 0;
        this.abortController = new AbortController();
        this.sessionId = currentSessionId;

        devLog('🔊 Streaming TTS started');
        showNotification('실시간 음성 읽기가 시작됩니다', 'info');
    },

    // Add text chunk from streaming response
    addChunk(text) {
        if (!this.enabled || !this.isActive) return;

        // Guard: stop if session changed
        if (this.sessionId !== currentSessionId) {
            this.stop();
            return;
        }

        this.pendingText += text;
        this.processPendingText();
    },

    // Process pending text and extract complete sentences
    processPendingText() {
        if (this.isProcessing) return;

        // Look for complete sentences
        const sentences = this.extractSentences(this.pendingText);

        if (sentences.complete.length > 0) {
            sentences.complete.forEach(sentence => {
                const cleanSentence = sentence.trim();
                if (cleanSentence.length > 0) {
                    this.queueSentence(cleanSentence);
                }
            });
            this.pendingText = sentences.remaining;
        }
    },

    // Extract complete sentences from text
    extractSentences(text) {
        const complete = [];
        let remaining = text;

        // Split by sentence-ending punctuation
        const sentenceRegex = /([^.!?。！？]*[.!?。！？]+\s*)/g;
        let match;
        let lastIndex = 0;

        while ((match = sentenceRegex.exec(text)) !== null) {
            const sentence = match[1];
            // Only consider it complete if it has meaningful content
            if (sentence.replace(/[.!?。！？\s]/g, '').length > 3) {
                complete.push(sentence);
                lastIndex = sentenceRegex.lastIndex;
            }
        }

        remaining = text.substring(lastIndex);

        // Also check for Korean sentence endings without standard punctuation
        if (remaining.length > 50) {
            // If remaining text is long, try to find a natural break
            const koreanBreak = remaining.match(/^(.{20,}?)(다|요|니다|세요)\s+/);
            if (koreanBreak) {
                complete.push(koreanBreak[1] + koreanBreak[2]);
                remaining = remaining.substring(koreanBreak[0].length);
            }
        }

        return { complete, remaining };
    },

    // Queue a sentence for TTS
    async queueSentence(sentence) {
        if (!this.isActive) return;

        // Guard: queue size limit to prevent memory bloat
        if (this.audioQueue.length >= this.MAX_QUEUE_SIZE) {
            devLog('🔊 Streaming TTS queue full, skipping sentence');
            return;
        }

        // Guard: stop after too many consecutive errors
        if (this.consecutiveErrors >= this.MAX_CONSECUTIVE_ERRORS) {
            devLog('🔊 Streaming TTS stopped: too many consecutive errors');
            if (this.consecutiveErrors === this.MAX_CONSECUTIVE_ERRORS) {
                showNotification('실시간 음성 생성이 반복적으로 실패하여 중단되었습니다.', 'warning');
                this.consecutiveErrors++; // Prevent repeated notifications
            }
            return;
        }

        this.processedText += sentence + ' ';

        try {
            // Clean the sentence for TTS
            const cleanText = stripMarkdownForTTS(sentence);
            if (!cleanText || cleanText.length < 2) return;

            devLog('🔊 Queueing TTS sentence:', cleanText.substring(0, 50) + '...');

            // Fetch audio
            this.pendingFetches++;
            const audioBlob = await this.fetchTTSAudio(cleanText);
            this.pendingFetches = Math.max(0, this.pendingFetches - 1);

            if (audioBlob && this.isActive) {
                this.consecutiveErrors = 0; // Reset on success
                this.audioQueue.push(audioBlob);
                this.playNext();
            }
        } catch (error) {
            this.pendingFetches = Math.max(0, this.pendingFetches - 1);
            devLog('Streaming TTS error:', error);
        }
    },

    // Fetch TTS audio for text
    async fetchTTSAudio(text) {
        if (!this.isActive) return null;

        try {
            // Per-sentence timeout via AbortController race
            const fetchController = new AbortController();
            const timeoutId = setTimeout(() => fetchController.abort(), this.FETCH_TIMEOUT_MS);

            // Abort if either the global controller or per-fetch controller fires
            const onGlobalAbort = () => fetchController.abort();
            this.abortController?.signal.addEventListener('abort', onGlobalAbort, { once: true });

            let response;
            try {
                const headers = { 'Content-Type': 'application/json' };
                const token = localStorage.getItem('access_token');
                if (token) {
                    headers['Authorization'] = `Bearer ${token}`;
                }
                response = await fetch('/api/tts/synthesize', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ text, use_cache: true }),
                    signal: fetchController.signal
                });
            } finally {
                clearTimeout(timeoutId);
                this.abortController?.signal.removeEventListener('abort', onGlobalAbort);
            }

            if (!response.ok) {
                this.consecutiveErrors++;
                throw new Error(`TTS request failed: ${response.status}`);
            }

            // Guard: check if still active after async operation
            if (!this.isActive) return null;

            return await response.blob();
        } catch (error) {
            if (error.name === 'AbortError') {
                devLog('Streaming TTS request aborted');
            } else {
                this.consecutiveErrors++;
                devLog('Streaming TTS fetch error:', error);
            }
            return null;
        }
    },

    // Play next audio in queue
    playNext() {
        if (!this.isActive || this.isPlaying || this.audioQueue.length === 0) {
            return;
        }

        this.isPlaying = true;
        const audioBlob = this.audioQueue.shift();
        const audioUrl = URL.createObjectURL(audioBlob);
        this.currentAudioUrl = audioUrl;

        this.currentAudio = new Audio(audioUrl);

        this.currentAudio.onended = () => {
            this._cleanupCurrentAudio();
            this.playNext();
        };

        this.currentAudio.onerror = (e) => {
            devLog('Streaming TTS playback error:', e);
            this._cleanupCurrentAudio();
            this.playNext();
        };

        this.currentAudio.play().catch(error => {
            devLog('Streaming TTS play() rejected:', error);
            this._cleanupCurrentAudio();
            this.playNext();
        });
    },

    // Clean up current audio element and revoke blob URL
    _cleanupCurrentAudio() {
        if (this.currentAudioUrl) {
            URL.revokeObjectURL(this.currentAudioUrl);
            this.currentAudioUrl = null;
        }
        this.currentAudio = null;
        this.isPlaying = false;
    },

    // Called when streaming response is complete
    finish() {
        if (!this.enabled || !this.isActive) return;

        // Process any remaining text
        if (this.pendingText.trim().length > 0) {
            const cleanText = stripMarkdownForTTS(this.pendingText.trim());
            if (cleanText && cleanText.length > 2) {
                this.queueSentence(this.pendingText.trim());
            }
        }

        devLog('🔊 Streaming TTS finishing, remaining queue:', this.audioQueue.length, 'pending fetches:', this.pendingFetches);
    },

    // Stop streaming TTS and clean up all resources
    stop() {
        const wasActive = this.isActive;
        this.isActive = false;

        // Abort all in-flight fetch requests
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }

        // Stop and clean up current audio
        if (this.currentAudio) {
            try {
                this.currentAudio.pause();
                this.currentAudio.src = '';
            } catch (e) { /* ignore */ }
        }
        this._cleanupCurrentAudio();

        // Clean up queued blobs (no URLs to revoke, they're still Blob objects)
        this.audioQueue = [];
        this.pendingText = '';
        this.isProcessing = false;
        this.isPlaying = false;
        this.consecutiveErrors = 0;
        this.pendingFetches = 0;
        this.sessionId = null;

        if (wasActive) {
            devLog('🔊 Streaming TTS stopped and cleaned up');
        }
    },

    // Toggle streaming TTS on/off
    toggle() {
        this.enabled = !this.enabled;
        localStorage.setItem('streamingTTSEnabled', this.enabled);

        if (this.enabled) {
            showNotification('실시간 음성 읽기 활성화됨', 'success');
        } else {
            this.stop();
            showNotification('실시간 음성 읽기 비활성화됨', 'info');
        }

        return this.enabled;
    },

    // Load setting from localStorage
    loadSetting() {
        this.enabled = localStorage.getItem('streamingTTSEnabled') === 'true';
        return this.enabled;
    }
};

// Initialize streaming TTS setting
streamingTTS.loadSetting();

// Clean up all TTS on page hide (mobile: tab switch, app background)
window.addEventListener('pagehide', () => {
    stopAllTTS();
});

// ===== Voice Input (Speech-to-Text) =====
let speechRecognition = null;
let isListening = false;

// Initialize speech recognition
function initSpeechRecognition() {
    // Check browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        devLog('Speech recognition not supported');
        if (voiceBtn) {
            voiceBtn.style.display = 'none';
        }
        return false;
    }

    speechRecognition = new SpeechRecognition();
    speechRecognition.continuous = false;
    speechRecognition.interimResults = true;
    speechRecognition.lang = 'ko-KR'; // Korean
    speechRecognition.maxAlternatives = 1;

    // Event handlers
    speechRecognition.onstart = () => {
        isListening = true;
        if (voiceBtn) {
            voiceBtn.classList.add('listening');
            voiceBtn.title = '음성 인식 중... (클릭하여 중지)';
        }
        devLog('Voice recognition started');
    };

    speechRecognition.onend = () => {
        isListening = false;
        if (voiceBtn) {
            voiceBtn.classList.remove('listening');
            voiceBtn.title = '음성으로 입력 (클릭하여 시작)';
        }
        devLog('Voice recognition ended');
    };

    speechRecognition.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }

        // Update input field
        if (userInput) {
            if (finalTranscript) {
                // Append final result to existing text
                const currentText = userInput.value;
                const newText = currentText ? currentText + ' ' + finalTranscript : finalTranscript;
                userInput.value = newText.trim();

                // Trigger input event for send button state update
                userInput.dispatchEvent(new Event('input', { bubbles: true }));

                // Auto-resize textarea
                userInput.style.height = 'auto';
                userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';

                devLog('Voice input final:', finalTranscript);
            }
        }
    };

    speechRecognition.onerror = (event) => {
        devLog('Voice recognition error:', event.error);
        isListening = false;
        if (voiceBtn) {
            voiceBtn.classList.remove('listening');
            voiceBtn.title = '음성으로 입력 (클릭하여 시작)';
        }

        // Detect browser
        const isChrome = /Chrome/.test(navigator.userAgent) && !/Edge|Edg/.test(navigator.userAgent);
        const isHTTP = window.location.protocol === 'http:';

        // Show user-friendly error messages
        let errorMessage = '';
        switch (event.error) {
            case 'no-speech':
                errorMessage = '음성이 감지되지 않았습니다. 다시 시도해주세요.';
                break;
            case 'audio-capture':
                errorMessage = '마이크를 찾을 수 없습니다. 마이크를 연결해주세요.';
                break;
            case 'not-allowed':
                if (isChrome && isHTTP) {
                    // Chrome on HTTP localhost needs special flag - use dynamic origin
                    errorMessage = 'Chrome에서 HTTP 연결 시 음성 인식이 제한됩니다. Safari를 사용하거나, Chrome 주소창에 chrome://flags/#unsafely-treat-insecure-origin-as-secure 를 입력하고 ' + window.location.origin + ' 을 추가한 후 Chrome을 재시작해주세요.';
                } else {
                    errorMessage = '마이크 사용 권한이 필요합니다. 브라우저 설정에서 허용해주세요.';
                }
                break;
            case 'network':
                if (isChrome && isHTTP) {
                    errorMessage = 'Chrome에서 HTTP 연결 시 음성 인식 네트워크 오류가 발생할 수 있습니다. Safari를 사용하거나 HTTPS 연결을 사용해주세요.';
                } else {
                    errorMessage = '네트워크 오류가 발생했습니다. 인터넷 연결을 확인해주세요.';
                }
                break;
            case 'aborted':
                // User cancelled, no need to show error
                return;
            default:
                errorMessage = '음성 인식 중 오류가 발생했습니다.';
        }

        if (errorMessage) {
            showNotification(errorMessage, 'warning');
        }
    };

    devLog('Speech recognition initialized');
    return true;
}

// Toggle voice recognition
async function toggleVoiceRecognition() {
    if (!speechRecognition) {
        if (!initSpeechRecognition()) {
            showNotification('이 브라우저는 음성 인식을 지원하지 않습니다.', 'error');
            return;
        }
    }

    if (isListening) {
        speechRecognition.stop();
        devLog('Voice recognition stopped by user');
    } else {
        // Detect Chrome on HTTP - show proactive warning
        const isChrome = /Chrome/.test(navigator.userAgent) && !/Edge|Edg/.test(navigator.userAgent);
        const isHTTP = window.location.protocol === 'http:';

        try {
            // First, explicitly request microphone permission using getUserMedia
            // This ensures Chrome properly grants microphone access before SpeechRecognition
            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    // Stop the stream immediately - we just needed to trigger permission
                    stream.getTracks().forEach(track => track.stop());
                    devLog('Microphone permission granted via getUserMedia');
                } catch (mediaError) {
                    devLog('getUserMedia error:', mediaError);
                    if (mediaError.name === 'NotAllowedError' || mediaError.name === 'PermissionDeniedError') {
                        if (isChrome && isHTTP) {
                            showNotification('Chrome에서 HTTP 연결 시 음성 인식이 제한됩니다. Safari를 사용하거나, Chrome 주소창에 chrome://flags/#unsafely-treat-insecure-origin-as-secure 를 입력하고 ' + window.location.origin + ' 을 추가한 후 Chrome을 재시작해주세요.', 'warning');
                        } else {
                            showNotification('마이크 사용 권한이 필요합니다. 브라우저 설정에서 허용해주세요.', 'warning');
                        }
                        return;
                    } else if (mediaError.name === 'NotFoundError') {
                        showNotification('마이크를 찾을 수 없습니다. 마이크를 연결해주세요.', 'warning');
                        return;
                    }
                    // For other errors, try to proceed with speech recognition anyway
                }
            }

            speechRecognition.start();
            devLog('Voice recognition started by user');
        } catch (error) {
            devLog('Voice recognition start error:', error);
            // If already started, stop and restart
            if (error.message && error.message.includes('already started')) {
                speechRecognition.stop();
                setTimeout(() => {
                    try {
                        speechRecognition.start();
                    } catch (e) {
                        devLog('Voice recognition restart error:', e);
                    }
                }, 100);
            } else {
                if (isChrome && isHTTP) {
                    showNotification('Chrome에서 HTTP 연결 시 음성 인식이 제한됩니다. Safari를 사용하거나 Chrome 플래그 설정을 확인해주세요.', 'warning');
                } else {
                    showNotification('음성 인식을 시작할 수 없습니다. 다시 시도해주세요.', 'warning');
                }
            }
        }
    }
}

// Initialize voice button event listener
function initVoiceButton() {
    if (voiceBtn) {
        voiceBtn.addEventListener('click', toggleVoiceRecognition);

        // Check if speech recognition is supported
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            voiceBtn.style.display = 'none';
            devLog('Voice button hidden - speech recognition not supported');
        } else {
            devLog('Voice button initialized');
        }
    }
}

// Copy text to clipboard
async function copyToClipboard(text, button) {
    try {
        await navigator.clipboard.writeText(text);

        // Visual feedback with animation
        const originalHTML = button.innerHTML;
        const originalTooltip = button.getAttribute('data-tooltip');

        button.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                <path d="M3 8L6 11L13 4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        `;
        button.style.color = '#10b981';
        button.style.borderColor = '#10b981';
        button.style.background = 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0.15) 100%)';
        button.setAttribute('title', '✓ 복사되었습니다');

        // Add success animation class
        button.style.transform = 'scale(1.05)';

        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.style.color = '';
            button.style.borderColor = '';
            button.style.background = '';
            button.style.transform = '';
            button.setAttribute('title', originalTooltip);
        }, 2000);
    } catch (error) {
        logger.error('Copy failed:', error);

        // Show error feedback
        const originalHTML = button.innerHTML;
        button.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                <path d="M4 4L12 12M12 4L4 12" stroke-width="2" stroke-linecap="round"/>
            </svg>
        `;
        button.style.color = '#ef4444';

        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.style.color = '';
        }, 2000);
    }
}

// Download answer in various formats
async function downloadAnswer(text, format, button) {
    try {
        let content, filename, mimeType;
        const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');

        switch (format) {
            case 'json':
                content = JSON.stringify({
                    answer: text,
                    timestamp: new Date().toISOString(),
                    format: 'markdown'
                }, null, 2);
                filename = `answer-${timestamp}.json`;
                mimeType = 'application/json';
                break;

            case 'markdown':
                content = text;
                filename = `answer-${timestamp}.md`;
                mimeType = 'text/markdown';
                break;

            case 'html':
                // Convert markdown to HTML
                const htmlContent = marked.parse(text);
                content = `<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 답변 - ${timestamp}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            color: #333;
        }
        pre {
            background: #f5f5f5;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
        }
        code {
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Consolas', 'Monaco', monospace;
        }
        pre code {
            background: none;
            padding: 0;
        }
        blockquote {
            border-left: 4px solid #667eea;
            padding-left: 16px;
            margin-left: 0;
            color: #666;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th {
            background: #667eea;
            color: white;
        }
        img {
            max-width: 100%;
            height: auto;
        }
        .timestamp {
            color: #999;
            font-size: 0.9em;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
    </style>
</head>
<body>
    ${htmlContent}
    <div class="timestamp">생성일시: ${new Date().toLocaleString('ko-KR')}</div>
</body>
</html>`;
                filename = `answer-${timestamp}.html`;
                mimeType = 'text/html';
                break;

            case 'txt':
                // Remove markdown formatting for plain text
                content = text
                    .replace(/#{1,6}\s/g, '') // Remove headers
                    .replace(/\*\*(.+?)\*\*/g, '$1') // Remove bold
                    .replace(/\*(.+?)\*/g, '$1') // Remove italic
                    .replace(/\[(.+?)\]\(.+?\)/g, '$1') // Remove links
                    .replace(/`(.+?)`/g, '$1') // Remove inline code
                    .replace(/```[\s\S]*?```/g, '[코드 블록]'); // Replace code blocks
                filename = `answer-${timestamp}.txt`;
                mimeType = 'text/plain';
                break;

            case 'pdf':
                // Generate PDF using html2pdf.js
                filename = `answer-${timestamp}.pdf`;
                await generateAnswerPdf(text, filename, button);
                return; // Early return for async pdf generation

            case 'docx':
                // Generate Word document using docx library
                filename = `answer-${timestamp}.docx`;
                await generateDocx(text, filename, button);
                return; // Early return for async docx generation

            case 'hwpx':
                // Generate HWPX document via server API
                filename = `answer-${timestamp}.hwpx`;
                await generateHwpx(text, filename, button);
                return; // Early return for async hwpx generation

            default:
                logger.error('Unknown format:', format);
                return;
        }

        // Create blob and download
        const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        // Visual feedback
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <path d="M3 8L6 11L13 4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
            button.style.color = '#10b981';

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
            }, 2000);
        }
    } catch (error) {
        logger.error('Download failed:', error);

        // Show error feedback
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <path d="M4 4L12 12M12 4L4 12" stroke-width="2" stroke-linecap="round"/>
                </svg>
            `;
            button.style.color = '#ef4444';

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
            }, 2000);
        }
    }
}

// Generate PDF from markdown text using html2pdf.js
async function generateAnswerPdf(text, filename, button) {
    try {
        // Convert markdown to HTML
        const htmlContent = marked.parse(text);

        // Create complete HTML document
        const fullHTML = `<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>AI 답변 - ${new Date().toLocaleDateString('ko-KR')}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', 'Malgun Gothic', sans-serif;
            line-height: 1.8;
            color: #1a1a1a;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #2c3e50;
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
        }
        p {
            margin: 12px 0;
        }
        pre {
            background: #f6f8fa;
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            padding: 16px;
            overflow-x: auto;
            font-size: 14px;
        }
        code {
            background: #f6f8fa;
            border: 1px solid #e1e4e8;
            border-radius: 3px;
            padding: 2px 6px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 0.9em;
        }
        pre code {
            background: none;
            border: none;
            padding: 0;
        }
        blockquote {
            border-left: 4px solid #667eea;
            margin: 16px 0;
            padding: 12px 20px;
            background: #f8f9fa;
            color: #555;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th {
            background: #667eea;
            color: white;
            font-weight: 600;
        }
        .timestamp {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #e1e4e8;
            color: #6c757d;
            font-size: 0.9em;
            text-align: center;
        }
    </style>
</head>
<body>
    ${htmlContent}
    <div class="timestamp">
        생성일시: ${new Date().toLocaleString('ko-KR')}
    </div>
</body>
</html>`;

        // Parse HTML to extract styles and content (same as exportAsPDF)
        const parser = new DOMParser();
        const doc = parser.parseFromString(fullHTML, 'text/html');

        // Extract styles from head
        const styles = doc.querySelector('style');
        const styleText = styles ? styles.textContent : '';

        // Get body content
        const bodyContent = doc.body.innerHTML;

        // Create temporary container with styles applied
        const container = document.createElement('div');
        container.style.position = 'absolute';
        container.style.left = '-9999px';

        // Add styles
        const styleElement = document.createElement('style');
        styleElement.textContent = styleText;
        container.appendChild(styleElement);

        // Add content
        const contentDiv = document.createElement('div');
        contentDiv.innerHTML = bodyContent;
        container.appendChild(contentDiv);

        document.body.appendChild(container);

        // PDF generation options
        const opt = {
            margin: 10,
            filename: filename,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2, useCORS: true },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
        };

        // Generate PDF from content div with styles
        await html2pdf().set(opt).from(contentDiv).save();

        // Clean up
        document.body.removeChild(container);

        // Visual feedback
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <path d="M3 8L6 11L13 4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
            button.style.color = '#10b981';

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
            }, 2000);
        }
    } catch (error) {
        logger.error('PDF generation failed:', error);

        // Show error feedback
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <path d="M4 4L12 12M12 4L4 12" stroke-width="2" stroke-linecap="round"/>
                </svg>
            `;
            button.style.color = '#ef4444';

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
            }, 2000);
        }
    }
}

// Generate Word document (.docx) from markdown text
async function generateDocx(text, filename, button) {
    try {
        const { Document, Paragraph, TextRun, HeadingLevel, AlignmentType, TabStopType, TabStopPosition, convertInchesToTwip } = docx;

        // Parse markdown into structured content
        const lines = text.split('\n');
        const documentChildren = [];

        let currentList = null;
        let inCodeBlock = false;
        let codeBlockContent = [];
        let codeBlockLanguage = '';

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Handle code blocks
            if (line.startsWith('```')) {
                if (!inCodeBlock) {
                    inCodeBlock = true;
                    codeBlockLanguage = line.slice(3).trim();
                    codeBlockContent = [];
                } else {
                    inCodeBlock = false;
                    // Add code block as gray background paragraph
                    if (codeBlockContent.length > 0) {
                        documentChildren.push(
                            new Paragraph({
                                text: codeBlockContent.join('\n'),
                                shading: {
                                    fill: 'F5F5F5',
                                },
                                spacing: {
                                    before: 200,
                                    after: 200,
                                },
                                style: 'code',
                            })
                        );
                    }
                    codeBlockContent = [];
                }
                continue;
            }

            if (inCodeBlock) {
                codeBlockContent.push(line);
                continue;
            }

            // Handle headings
            if (line.startsWith('#')) {
                const level = line.match(/^#+/)[0].length;
                const headingText = line.replace(/^#+\s*/, '');

                const headingLevels = {
                    1: HeadingLevel.HEADING_1,
                    2: HeadingLevel.HEADING_2,
                    3: HeadingLevel.HEADING_3,
                    4: HeadingLevel.HEADING_4,
                    5: HeadingLevel.HEADING_5,
                    6: HeadingLevel.HEADING_6,
                };

                documentChildren.push(
                    new Paragraph({
                        text: headingText,
                        heading: headingLevels[level] || HeadingLevel.HEADING_1,
                        spacing: {
                            before: 240,
                            after: 120,
                        },
                    })
                );
                currentList = null;
                continue;
            }

            // Handle unordered lists
            if (line.match(/^\s*[-*+]\s+/)) {
                const text = line.replace(/^\s*[-*+]\s+/, '');
                const textRuns = parseInlineFormatting(text);

                documentChildren.push(
                    new Paragraph({
                        children: textRuns,
                        bullet: {
                            level: 0,
                        },
                        spacing: {
                            before: 100,
                            after: 100,
                        },
                    })
                );
                continue;
            }

            // Handle ordered lists
            if (line.match(/^\s*\d+\.\s+/)) {
                const text = line.replace(/^\s*\d+\.\s+/, '');
                const textRuns = parseInlineFormatting(text);

                documentChildren.push(
                    new Paragraph({
                        children: textRuns,
                        numbering: {
                            reference: 'my-numbering',
                            level: 0,
                        },
                        spacing: {
                            before: 100,
                            after: 100,
                        },
                    })
                );
                continue;
            }

            // Handle blockquotes
            if (line.startsWith('>')) {
                const text = line.replace(/^>\s*/, '');
                const textRuns = parseInlineFormatting(text);

                documentChildren.push(
                    new Paragraph({
                        children: textRuns,
                        indent: {
                            left: convertInchesToTwip(0.5),
                        },
                        border: {
                            left: {
                                color: '667EEA',
                                space: 1,
                                size: 24,
                                style: 'single',
                            },
                        },
                        spacing: {
                            before: 100,
                            after: 100,
                        },
                    })
                );
                continue;
            }

            // Handle empty lines
            if (line.trim() === '') {
                documentChildren.push(
                    new Paragraph({
                        text: '',
                        spacing: {
                            before: 100,
                            after: 100,
                        },
                    })
                );
                currentList = null;
                continue;
            }

            // Regular paragraphs with inline formatting
            const textRuns = parseInlineFormatting(line);
            documentChildren.push(
                new Paragraph({
                    children: textRuns,
                    spacing: {
                        before: 100,
                        after: 100,
                    },
                })
            );
            currentList = null;
        }

        // Add timestamp at the end
        documentChildren.push(
            new Paragraph({
                text: '',
                spacing: { before: 400 },
            })
        );
        documentChildren.push(
            new Paragraph({
                children: [
                    new TextRun({
                        text: `생성일시: ${new Date().toLocaleString('ko-KR')}`,
                        size: 18,
                        color: '999999',
                    }),
                ],
                border: {
                    top: {
                        color: 'EEEEEE',
                        space: 1,
                        size: 6,
                        style: 'single',
                    },
                },
                spacing: {
                    before: 200,
                },
            })
        );

        // Create document
        const doc = new Document({
            sections: [{
                properties: {},
                children: documentChildren,
            }],
            numbering: {
                config: [{
                    reference: 'my-numbering',
                    levels: [{
                        level: 0,
                        format: 'decimal',
                        text: '%1.',
                        alignment: AlignmentType.LEFT,
                    }],
                }],
            },
            styles: {
                paragraphStyles: [{
                    id: 'code',
                    name: 'Code',
                    basedOn: 'Normal',
                    next: 'Normal',
                    run: {
                        font: 'Consolas',
                        size: 20,
                    },
                    paragraph: {
                        spacing: {
                            line: 276,
                            before: 200,
                            after: 200,
                        },
                    },
                }],
            },
        });

        // Generate blob and download
        const blob = await docx.Packer.toBlob(doc);

        // Create proper Blob with MIME type
        const docxBlob = new Blob([blob], {
            type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        });

        // Use FileSaver.js if available, otherwise use createElement method
        if (typeof saveAs === 'function') {
            saveAs(docxBlob, filename);
        } else {
            const url = URL.createObjectURL(docxBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 100);
        }

        // Visual feedback
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <path d="M3 8L6 11L13 4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
            button.style.color = '#10b981';

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
            }, 2000);
        }
    } catch (error) {
        logger.error('Word document generation failed:', error);

        // Show error feedback
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <path d="M4 4L12 12M12 4L4 12" stroke-width="2" stroke-linecap="round"/>
                </svg>
            `;
            button.style.color = '#ef4444';

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
            }, 2000);
        }
    }
}

// Generate HWPX document via server API
async function generateHwpx(text, filename, button) {
    try {
        // Convert markdown to HTML
        const htmlContent = marked.parse(text);

        // Call server API to convert HTML to HWPX
        const token = localStorage.getItem('access_token');
        const headers = {
            'Content-Type': 'application/json'
        };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch('/api/convert/hwpx', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                content: htmlContent,
                content_type: 'html',
                filename: filename
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'HWPX 변환 실패');
        }

        // Download the HWPX file
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        // Visual feedback
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <path d="M3 8L6 11L13 4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
            button.style.color = '#10b981';

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
            }, 2000);
        }
    } catch (error) {
        logger.error('HWPX 생성 실패:', error);

        // Show error feedback
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <circle cx="8" cy="8" r="7" stroke-width="2"/>
                    <line x1="8" y1="4" x2="8" y2="8" stroke-width="2" stroke-linecap="round"/>
                    <circle cx="8" cy="11" r="0.5" fill="currentColor"/>
                </svg>
            `;
            button.style.color = '#ef4444';

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
            }, 2000);
        }

        // Show toast notification
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #ef4444;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 10000;
            font-size: 14px;
        `;
        toast.textContent = `HWPX 생성 실패: ${error.message}`;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}

// Helper function to parse inline markdown formatting (bold, italic, code)
function parseInlineFormatting(text) {
    const textRuns = [];
    let currentPos = 0;

    // Regex patterns for inline formatting
    const patterns = [
        { regex: /\*\*(.+?)\*\*/g, bold: true },           // **bold**
        { regex: /\*(.+?)\*/g, italic: true },             // *italic*
        { regex: /__(.+?)__/g, bold: true },               // __bold__
        { regex: /_(.+?)_/g, italic: true },               // _italic_
        { regex: /`(.+?)`/g, code: true },                 // `code`
    ];

    // Find all matches
    const matches = [];
    patterns.forEach(pattern => {
        let match;
        const regex = new RegExp(pattern.regex);
        while ((match = regex.exec(text)) !== null) {
            matches.push({
                start: match.index,
                end: regex.lastIndex,
                text: match[1],
                bold: pattern.bold,
                italic: pattern.italic,
                code: pattern.code,
            });
        }
    });

    // Sort matches by position
    matches.sort((a, b) => a.start - b.start);

    // Build text runs
    if (matches.length === 0) {
        return [new docx.TextRun({ text })];
    }

    matches.forEach(match => {
        // Add text before match
        if (match.start > currentPos) {
            textRuns.push(new docx.TextRun({
                text: text.substring(currentPos, match.start),
            }));
        }

        // Add formatted text
        const runOptions = { text: match.text };
        if (match.bold) runOptions.bold = true;
        if (match.italic) runOptions.italics = true;
        if (match.code) {
            runOptions.font = 'Consolas';
            runOptions.shading = { fill: 'F0F0F0' };
        }
        textRuns.push(new docx.TextRun(runOptions));

        currentPos = match.end;
    });

    // Add remaining text
    if (currentPos < text.length) {
        textRuns.push(new docx.TextRun({
            text: text.substring(currentPos),
        }));
    }

    return textRuns.length > 0 ? textRuns : [new docx.TextRun({ text })];
}

// Submit feedback (👍/👎)
async function submitFeedback(button, feedbackType) {
    try {
        // Check if already submitted
        if (button.classList.contains('feedback-submitted')) {
            return;
        }

        // Get conversation_id and generate message_id
        const conversationId = currentSessionId || 'anonymous';
        const messageId = Date.now().toString(); // Use timestamp as message_id

        // Send feedback to server
        const data = await Auth.apiCall('/api/feedback', {
            method: 'POST',
            body: JSON.stringify({
                conversation_id: conversationId,
                message_id: messageId,
                feedback_type: feedbackType
            })
        });

        if (!data) {
            throw new Error('피드백 전송 실패');
        }

        // Mark as submitted
        button.classList.add('feedback-submitted');

        // Disable both buttons in this feedback group
        const feedbackDiv = button.parentElement;
        const allButtons = feedbackDiv.querySelectorAll('.feedback-btn');
        allButtons.forEach(btn => {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
        });

        // Highlight selected button
        button.style.opacity = '1';
        button.style.transform = 'scale(1.2)';
        button.style.filter = 'drop-shadow(0 0 8px rgba(59, 130, 246, 0.5))';

        // Show success message
        const originalTitle = button.getAttribute('title');
        button.setAttribute('title', '✓ 피드백 감사합니다!');

        setTimeout(() => {
            button.style.transform = 'scale(1)';
            button.style.filter = '';
        }, 300);

        devLog(`✅ Feedback submitted: ${feedbackType}`);

    } catch (error) {
        logger.error('Feedback submission failed:', error);

        // Show error feedback
        button.style.color = '#ef4444';
        button.style.borderColor = '#ef4444';

        setTimeout(() => {
            button.style.color = '';
            button.style.borderColor = '';
        }, 2000);
    }
}

// Add response time indicator
function addResponseTime(messageDiv, elapsed, cached = false, stats = null) {
    const timeDiv = document.createElement('div');
    timeDiv.className = 'response-time';

    const icon = cached ? '⚡' : '⏱️';
    const label = cached ? '캐시 응답' : '응답 시간';

    // Build statistics text if available (only for non-cached responses)
    let statsText = '';
    if (stats && !cached) {
        statsText = ` • 초당 ${stats.tokens_per_second}토큰 • ${stats.total_tokens}개 토큰 • 첫 토큰까지 ${stats.time_to_first_token}초`;
    }

    timeDiv.innerHTML = `
        <span class="time-icon">${icon}</span>
        <span class="time-text">${label}: ${elapsed}초${statsText}</span>
    `;

    // Add special styling for cached responses
    if (cached) {
        timeDiv.classList.add('cached');
    }

    messageDiv.appendChild(timeDiv);
}

// Add error message with retry button
function addErrorMessageWithRetry(errorText, question, errorDetail = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot error';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    // Create error display
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-details';

    // Main error message
    const errorTitle = document.createElement('div');
    errorTitle.className = 'error-title';
    errorTitle.textContent = errorText;
    errorDiv.appendChild(errorTitle);

    // Error details if provided
    if (errorDetail) {
        if (errorDetail.detail) {
            const detailDiv = document.createElement('div');
            detailDiv.className = 'error-detail';
            detailDiv.textContent = errorDetail.detail;
            errorDiv.appendChild(detailDiv);
        }

        if (errorDetail.solution) {
            const solutionDiv = document.createElement('div');
            solutionDiv.className = 'error-solution';
            solutionDiv.innerHTML = `<strong>💡 해결 방법:</strong> ${escapeHtml(errorDetail.solution)}`;
            errorDiv.appendChild(solutionDiv);
        }
    }

    contentDiv.appendChild(errorDiv);

    // Action buttons container
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'error-actions';

    // Retry button
    const retryBtn = document.createElement('button');
    retryBtn.className = 'retry-btn';
    retryBtn.textContent = '🔄 다시 시도';
    retryBtn.onclick = () => {
        // Remove error message
        messageDiv.remove();
        // Remove last user message from history (will be re-added)
        if (conversationHistory.length > 0 && conversationHistory[conversationHistory.length - 1].role === 'user') {
            conversationHistory.pop();
        }
        // Set input and send again
        userInput.value = question;
        sendMessage();
    };

    // Cancel button
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'cancel-btn';
    cancelBtn.textContent = '취소';
    cancelBtn.onclick = () => {
        messageDiv.remove();
    };

    actionsDiv.appendChild(retryBtn);
    actionsDiv.appendChild(cancelBtn);
    contentDiv.appendChild(actionsDiv);

    messageDiv.appendChild(contentDiv);
    chatContainer.appendChild(messageDiv);

    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// ===== Document Management =====
// Note: Document management has been moved to admin page
// Keep the code for backwards compatibility but check if elements exist
const docsBtn = document.getElementById('docsBtn');
const docsModal = document.getElementById('docsModal');
const closeDocsModal = document.getElementById('closeDocsModal');
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const uploadStatus = document.getElementById('uploadStatus');
const docsList = document.getElementById('docsList');
const refreshDocsBtn = document.getElementById('refreshDocsBtn');

// Only initialize if elements exist (admin page has these features)
if (docsBtn && docsModal) {
    // Open modal
    docsBtn.addEventListener('click', () => {
        docsModal.classList.add('active');
        pushModal(docsModal, 'docs');
        loadDocuments();
    });
}

if (closeDocsModal && docsModal) {
    // Close modal
    closeDocsModal.addEventListener('click', () => {
        docsModal.classList.remove('active');
        popModal(docsModal);
    });
}

if (docsModal) {
    // Close modal when clicking outside
    docsModal.addEventListener('click', (e) => {
        if (e.target === docsModal) {
            docsModal.classList.remove('active');
            popModal(docsModal);
        }
    });
}

if (uploadArea && fileInput) {
    // Upload area click
    uploadArea.addEventListener('click', () => {
        fileInput.click();
    });
}

// Validate file type
function isValidDocumentFile(file) {
    const fileName = file.name.toLowerCase();
    const validExtensions = ['.pdf', '.hwp', '.hwpx', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'];
    return validExtensions.some(ext => fileName.endsWith(ext));
}

if (fileInput) {
    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            if (isValidDocumentFile(file)) {
                uploadFile(file);
            } else {
                showUploadStatus('지원되지 않는 파일 형식입니다. 지원 형식: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT', 'error');
            }
        }
    });
}

if (uploadArea) {
    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');

        if (e.dataTransfer.files.length > 0) {
            const file = e.dataTransfer.files[0];
            if (isValidDocumentFile(file)) {
                uploadFile(file);
            } else {
                showUploadStatus('지원되지 않는 파일 형식입니다. 지원 형식: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT', 'error');
            }
        }
    });
}

if (refreshDocsBtn) {
    // Refresh documents
    refreshDocsBtn.addEventListener('click', loadDocuments);
}

// Upload file
async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    // 파일 정보 표시
    const fileSizeMB = (file.size / 1024 / 1024).toFixed(2);
    showUploadStatus(`📤 업로드 중: ${file.name} (${fileSizeMB}MB)`, 'uploading');

    try {
        const authToken = Auth.getAccessToken();
        const headers = {};
        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        const response = await fetch('/api/documents/upload', {
            method: 'POST',
            headers: headers,
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            // Check if it's a duplicate upload
            if (result.is_duplicate) {
                showUploadStatus(
                    `✓ ${file.name} - 동일한 파일이 이미 존재합니다 (버전 ${result.current_version}, ${result.chunk_count} 청크)`,
                    'success'
                );
            } else {
                showUploadStatus(
                    `✓ ${file.name} 업로드 및 색인 완료! (${result.chunk_count} 청크 생성)`,
                    'success'
                );
            }
            fileInput.value = '';
            // Reload documents and filter list in parallel
            setTimeout(async () => {
                const refreshTasks = [
                    loadDocuments(),
                    loadFilterDocuments(),
                    checkStatus(),
                    loadGroupTree()
                ];

                // If group management modal is open and a group is selected, refresh its documents
                if (selectedGroupForEdit) {
                    refreshTasks.push(loadGroupDocuments(selectedGroupForEdit));
                }

                await Promise.all(refreshTasks);
            }, 1000);
        } else {
            // 상세한 에러 메시지 표시 (파일명 포함)
            let errorMsg = `✗ ${file.name} 업로드 실패`;
            if (result.detail) {
                errorMsg += `\n사유: ${result.detail}`;
            }
            if (response.status === 413) {
                errorMsg += '\n💡 파일 크기를 줄이거나 분할하여 업로드하세요.';
            } else if (response.status === 400) {
                errorMsg += '\n💡 지원되는 파일 형식인지 확인하세요.';
            } else if (response.status === 409) {
                errorMsg += '\n💡 기존 파일을 삭제하거나 다른 이름으로 업로드하세요.';
            }
            showUploadStatus(errorMsg, 'error');
        }
    } catch (error) {
        // 네트워크 또는 기타 에러
        let errorMsg = `✗ ${file.name} 업로드 실패\n사유: ${error.message}`;
        if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
            errorMsg += '\n💡 네트워크 연결을 확인하거나 서버 상태를 확인하세요.';
        }
        showUploadStatus(errorMsg, 'error');
    }
}

// Show upload status
function showUploadStatus(message, type) {
    uploadStatus.textContent = message;
    uploadStatus.className = `upload-status ${type}`;

    if (type !== 'uploading') {
        setTimeout(() => {
            uploadStatus.className = 'upload-status';
        }, 5000);
    }
}

// Load documents
async function loadDocuments() {
    docsList.innerHTML = '<div class="loading">문서 목록을 불러오는 중...</div>';

    try {
        const data = await Auth.apiCall('/api/documents');

        if (data.documents.length === 0) {
            docsList.innerHTML = `
                <div class="empty-state">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        <polyline points="13 2 13 9 20 9" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <p>업로드된 문서가 없습니다</p>
                    <p class="hint-text">위에서 PDF 파일을 업로드해보세요</p>
                </div>
            `;
            return;
        }

        docsList.innerHTML = data.documents.map(doc => `
            <div class="doc-item">
                <div class="doc-info">
                    <div class="doc-name" onclick="viewDocumentChunks('${doc.filename.replace(/'/g, "\\'")}')">
                        ${doc.filename}
                    </div>
                    <div class="doc-meta">
                        <span class="doc-meta-item">📊 ${doc.size_mb} MB</span>
                        <span class="doc-meta-item">📦 ${doc.chunk_count} 청크</span>
                        <span class="doc-meta-item">📅 ${formatDate(doc.modified)}</span>
                    </div>
                </div>
                <div class="doc-actions">
                    <span class="doc-status ${doc.indexed ? 'indexed' : 'not-indexed'}">
                        ${doc.indexed ? '✓ 색인됨' : '✗ 미색인'}
                    </span>
                    <button class="version-btn" onclick="showVersionModal('${doc.filename.replace(/'/g, "\\'")}')">
                        🔄 버전
                    </button>
                    <button class="delete-btn" onclick="deleteDocument('${doc.filename}')">
                        🗑️ 삭제
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        docsList.innerHTML = `
            <div class="empty-state">
                <p>문서 목록을 불러오지 못했습니다</p>
                <p class="hint-text">${error.message}</p>
            </div>
        `;
    }
}

// View document chunks
async function viewDocumentChunks(filename) {
    // Show modal
    chunkViewerModal.classList.add('active');
    pushModal(chunkViewerModal, 'chunkViewer');

    // Set filename
    chunkViewerFilename.textContent = filename;

    // Show loading state
    chunkViewerList.innerHTML = '<div class="loading">청크를 불러오는 중...</div>';
    chunkViewerCount.textContent = '';

    try {
        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/chunks`);

        if (!response.ok) {
            throw new Error(`Failed to fetch chunks: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.chunks || data.chunks.length === 0) {
            chunkViewerList.innerHTML = `
                <div class="empty-state">
                    <p>이 문서에는 청크가 없습니다</p>
                </div>
            `;
            chunkViewerCount.textContent = '청크 0개';
            return;
        }

        // Update count badge
        chunkViewerCount.textContent = `총 ${data.total_count}개 청크`;

        // Render chunks
        chunkViewerList.innerHTML = data.chunks.map(chunk => `
            <div class="chunk-item">
                <div class="chunk-header">
                    <span class="chunk-index">청크 #${chunk.index}</span>
                    <span class="chunk-page">📄 ${chunk.page || 'N/A'}</span>
                </div>
                <div class="chunk-text">${escapeHtml(chunk.text)}</div>
            </div>
        `).join('');

    } catch (error) {
        logger.error('Error loading chunks:', error);
        chunkViewerList.innerHTML = `
            <div class="empty-state">
                <p>청크를 불러오는데 실패했습니다</p>
                <p class="hint-text">${error.message}</p>
            </div>
        `;
        chunkViewerCount.textContent = '';
    }
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Delete document
async function deleteDocument(filename) {
    // Check authentication (required to delete documents)
    const token = localStorage.getItem('access_token');
    if (!token) {
        showUploadStatus('✗ 로그인이 필요합니다', 'error');
        return;
    }

    if (!confirm(`"${filename}" 문서를 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없으며, 벡터 DB에서도 함께 삭제됩니다.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();

        if (response.ok) {
            showUploadStatus(`✓ ${filename} 삭제 완료`, 'success');
            // Parallel refresh of documents, filter, and status
            await Promise.all([
                loadDocuments(),
                loadFilterDocuments(),
                checkStatus()
            ]);
        } else {
            showUploadStatus(`✗ 삭제 실패: ${result.detail}`, 'error');
        }
    } catch (error) {
        showUploadStatus(`✗ 삭제 실패: ${error.message}`, 'error');
    }
}

// Format date
function formatDate(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
        return '오늘';
    } else if (diffDays === 1) {
        return '어제';
    } else if (diffDays < 7) {
        return `${diffDays}일 전`;
    } else {
        return date.toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
}

// Format date with time for version management (precise timestamp)
function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

// ===== Settings Management =====
const settingsBtn = document.getElementById('settingsBtn');
const settingsPanel = document.getElementById('settingsPanel');
const settingsOverlay = document.getElementById('settingsOverlay');
const closeSettingsBtn = document.getElementById('closeSettingsBtn');

// Settings controls
const topKSlider = document.getElementById('topKSlider');
const topKValue = document.getElementById('topKValue');
const searchModeSelect = document.getElementById('searchModeSelect');
const temperatureSlider = document.getElementById('temperatureSlider');
const temperatureValue = document.getElementById('temperatureValue');
const maxTokensSlider = document.getElementById('maxTokensSlider');
const maxTokensValue = document.getElementById('maxTokensValue');
const cacheThresholdSlider = document.getElementById('cacheThresholdSlider');
const cacheThresholdValue = document.getElementById('cacheThresholdValue');
const cacheTTLSlider = document.getElementById('cacheTTLSlider');
const cacheTTLValue = document.getElementById('cacheTTLValue');
const systemPrompt = document.getElementById('systemPrompt');
const clearCacheBtn = document.getElementById('clearCacheBtn');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');
const resetSettingsBtn = document.getElementById('resetSettingsBtn');

// Default settings
const defaultSettings = {
    top_k: 5,
    temperature: 0.7,
    max_tokens: 2048,
    cache_threshold: 0.95,
    cache_ttl: 60,
    searchMode: 'smart',  // 검색 모드 (smart, local-only, web-enhanced, comprehensive, tools-only)
    llm_model: 'mlx-community/Qwen3-30B-A3B-4bit',
    embedding_model: 'nlpai-lab/KURE-v1',
    system_prompt: `당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다. 업로드된 다양한 형식의 문서들(PDF, HWP, DOCX, TXT 등)을 정확히 분석하여 사용자의 질문에 유용한 답변을 제공합니다.

**핵심 원칙:**
1. **제공된 컨텍스트 활용**: 검색된 문서 내용을 꼼꼼히 살펴보고 관련 정보를 찾아 답변합니다
2. **정확한 정보 전달**: 문서에서 찾은 정보를 정확하게 전달하며, 필요시 해당 부분을 인용합니다
3. **적극적인 분석**: 직접적인 답이 없어도 문서 내용을 종합하여 유용한 답변을 제공합니다
4. **맥락 이해**: 이전 대화 내용을 참고하여 자연스럽고 일관된 대화를 유지합니다
5. **명확한 구조화**: 복잡한 내용은 단계별로 나누어 이해하기 쉽게 설명합니다

**응답 방법:**
1. **핵심 답변**: 질문에 대한 직접적인 답을 먼저 제시합니다
2. **근거 제시**: 문서의 관련 내용을 인용하거나 요약하여 제시합니다
3. **상세 설명**: 필요시 배경 정보, 예시, 관련 내용을 추가합니다
4. **추가 정보**: 관련된 유용한 정보가 있다면 함께 안내합니다

**특별 지침:**
- 표, 그래프, 수치 데이터는 정확히 인용하고 맥락과 함께 설명합니다
- 여러 문서에서 관련 정보가 있을 경우 통합하여 제시합니다
- 모순되는 정보가 있다면 명확히 지적하고 각 출처를 밝힙니다
- 전문 용어는 필요시 쉬운 말로 풀어 설명합니다
- 목록, 단계, 비교 등이 필요한 경우 마크다운 형식을 활용합니다
- 문서에 직접적인 답이 없어도 관련 내용을 종합하여 도움이 되는 답변을 제공합니다`
};

// Load settings from localStorage
let currentSettings = { ...defaultSettings };

function loadSettings() {
    const saved = localStorage.getItem('chatSettings');
    if (saved) {
        try {
            currentSettings = { ...defaultSettings, ...JSON.parse(saved) };
        } catch (e) {
            logger.error('Failed to load settings:', e);
        }
    }
    applySettings();
}

/**
 * Load system prompt from server (admin-configured)
 * This ensures the admin page's system prompt is actually used
 */
async function loadSystemPromptFromServer() {
    try {
        // Check if user is authenticated
        const token = localStorage.getItem('access_token');

        if (!token) {
            // Not authenticated - use default system prompt
            devLog('Not authenticated, using default system prompt');
            return;
        }

        // Use Auth.apiCall for automatic retry logic
        const data = await Auth.apiCall('/api/system-prompt');

        if (data.system_prompt) {
            // Update current settings with server's system prompt
            currentSettings.system_prompt = data.system_prompt;

            // Also update the UI if the element exists
            if (systemPrompt) {
                systemPrompt.value = data.system_prompt;
            }

            logger.info('✅ System prompt loaded from server');
            devLog('System prompt loaded:', data.system_prompt.substring(0, 100) + '...');
        }
    } catch (error) {
        // Silent fail - use default system prompt from localStorage/defaultSettings
        devLog('Failed to load system prompt from server, using default:', error.message);
    }
}

/**
 * 하이브리드 RAG 활성화 상태 확인 및 검색 모드 UI 제어
 */
async function checkHybridRAGStatus() {
    try {
        // Check if user is authenticated first
        if (!Auth.isAuthenticated()) {
            logger.debug('Skipping Hybrid RAG status check - user not authenticated');
            return;
        }

        const data = await Auth.apiCall('/api/hybrid-rag/status');

        if (searchModeSelect) {
            if (!data.enabled) {
                // 하이브리드 RAG 비활성화 상태
                // 검색 모드를 'local-only'로 강제 설정
                searchModeSelect.value = 'local-only';
                currentSettings.searchMode = 'local-only';

                // 드롭다운 비활성화 및 스타일 변경
                searchModeSelect.disabled = true;
                searchModeSelect.style.cursor = 'not-allowed';
                searchModeSelect.style.opacity = '0.6';

                // 다른 옵션들 비활성화
                Array.from(searchModeSelect.options).forEach(option => {
                    if (option.value !== 'local-only') {
                        option.disabled = true;
                    }
                });

                logger.info('⚠️ 하이브리드 RAG 비활성화 - 검색 모드를 로컬 문서만으로 고정');
            } else {
                // 하이브리드 RAG 활성화 상태 - 정상 동작
                searchModeSelect.disabled = false;
                searchModeSelect.style.cursor = 'pointer';
                searchModeSelect.style.opacity = '1';

                // 모든 옵션 활성화
                Array.from(searchModeSelect.options).forEach(option => {
                    option.disabled = false;
                });

                logger.info('✅ 하이브리드 RAG 활성화 - 모든 검색 모드 사용 가능');
            }
        }
    } catch (error) {
        logger.error('하이브리드 RAG 상태 확인 실패:', error);
        // 에러 시 안전하게 local-only로 고정
        if (searchModeSelect) {
            searchModeSelect.value = 'local-only';
            currentSettings.searchMode = 'local-only';
            searchModeSelect.disabled = true;
        }
    }
}

function applySettings() {
    if (topKSlider && topKValue) {
        topKSlider.value = currentSettings.top_k;
        topKValue.textContent = currentSettings.top_k;
    }

    if (searchModeSelect) {
        searchModeSelect.value = currentSettings.searchMode || 'smart';
    }

    // 하이브리드 RAG 상태 확인 및 검색 모드 UI 제어
    checkHybridRAGStatus();

    if (temperatureSlider && temperatureValue) {
        temperatureSlider.value = currentSettings.temperature;
        temperatureValue.textContent = currentSettings.temperature.toFixed(1);
    }

    if (maxTokensSlider && maxTokensValue) {
        maxTokensSlider.value = currentSettings.max_tokens;
        maxTokensValue.textContent = currentSettings.max_tokens;
    }

    if (cacheThresholdSlider && cacheThresholdValue) {
        cacheThresholdSlider.value = currentSettings.cache_threshold;
        cacheThresholdValue.textContent = currentSettings.cache_threshold.toFixed(2);
    }

    if (cacheTTLSlider && cacheTTLValue) {
        cacheTTLSlider.value = currentSettings.cache_ttl;
        cacheTTLValue.textContent = currentSettings.cache_ttl;
    }

    const llmModelDisplay = document.getElementById('llmModelDisplay');
    if (llmModelDisplay) {
        llmModelDisplay.textContent = currentSettings.llm_model || '설정되지 않음';
    }

    const embeddingModelDisplay = document.getElementById('embeddingModelDisplay');
    if (embeddingModelDisplay) {
        embeddingModelDisplay.textContent = currentSettings.embedding_model || '설정되지 않음';
    }

    if (systemPrompt) {
        systemPrompt.value = currentSettings.system_prompt;
    }

    // Apply streaming TTS setting
    const streamingTTSToggle = document.getElementById('streamingTTSToggle');
    if (streamingTTSToggle) {
        streamingTTSToggle.checked = streamingTTS.loadSetting();
        streamingTTSToggle.addEventListener('change', (e) => {
            streamingTTS.enabled = e.target.checked;
            localStorage.setItem('streamingTTSEnabled', e.target.checked);
            if (e.target.checked) {
                showNotification('실시간 음성 읽기가 활성화되었습니다', 'success');
            } else {
                streamingTTS.stop();
                showNotification('실시간 음성 읽기가 비활성화되었습니다', 'info');
            }
        });
    }
}

// Display current LLM, Embedding, and Reranker models
async function loadAvailableModels() {
    const llmModelDisplay = document.getElementById('llmModelDisplay');
    const embeddingModelDisplay = document.getElementById('embeddingModelDisplay');
    const rerankerModelDisplay = document.getElementById('rerankerModelDisplay');

    if (!llmModelDisplay || !embeddingModelDisplay) {
        logger.error('Model display elements not found');
        return;
    }

    // Simply display the current models from settings
    llmModelDisplay.textContent = currentSettings.llm_model || '설정되지 않음';
    embeddingModelDisplay.textContent = currentSettings.embedding_model || '설정되지 않음';

    // Load reranker model from RAG quality settings
    if (rerankerModelDisplay) {
        try {
            const data = await Auth.apiCall('/api/hybrid-rag/status');

            if (data.quality_features && data.quality_features.reranking_enabled) {
                rerankerModelDisplay.textContent = data.quality_features.reranker_model || 'dengcao/Qwen3-Reranker-8B:Q4_K_M';
                rerankerModelDisplay.style.color = '#166534';
            } else {
                rerankerModelDisplay.textContent = '비활성화됨';
                rerankerModelDisplay.style.color = '#9ca3af';
            }
        } catch (error) {
            logger.error('Failed to load reranker model:', error);
            rerankerModelDisplay.textContent = '로드 실패';
            rerankerModelDisplay.style.color = '#dc2626';
        }
    }
}

// Open settings panel (called from dropdown menu)
async function openSettingsPanel() {
    settingsPanel.classList.add('active');
    settingsOverlay.classList.add('active');
    pushModal(settingsPanel, 'settings');

    // Fetch latest status to get current model info
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        if (data.llm_model) currentSettings.llm_model = data.llm_model;
        if (data.embedding_model) currentSettings.embedding_model = data.embedding_model;

        // Update max tokens slider based on model
        updateMaxTokensSlider(data.llm_model);
    } catch (error) {
        logger.error('Failed to fetch latest model info:', error);
    }

    // Fetch reranker model from RAG quality settings
    try {
        const ragData = await Auth.apiCall('/api/hybrid-rag/status');
        if (ragData.quality_features && ragData.quality_features.reranker_model) {
            currentSettings.reranker_model = ragData.quality_features.reranker_model;
        }
    } catch (error) {
        logger.error('Failed to fetch reranker model info:', error);
    }

    // Fetch TTS status
    await loadTTSStatus();

    // Load latest system prompt from server (admin-configured)
    await loadSystemPromptFromServer();

    // 하이브리드 RAG 상태 확인 및 검색 모드 UI 제어
    await checkHybridRAGStatus();

    await loadAvailableModels();  // Load available models when opening settings
    loadCacheStats();
    loadCacheEnabled();

    // Apply current settings to UI elements (refresh UI with latest values)
    applySettings();
}

// Note: settingsBtn now uses toggleSettingsDropdown() from index.html onclick attribute

// Close settings
function closeSettings() {
    settingsPanel.classList.remove('active');
    settingsOverlay.classList.remove('active');
    popModal(settingsPanel);
    // Remove focus from settings button to clear outline
    settingsBtn.blur();
}

if (closeSettingsBtn) {
    closeSettingsBtn.addEventListener('click', closeSettings);
}

if (settingsOverlay) {
    settingsOverlay.addEventListener('click', closeSettings);
}

// Update slider values in real-time (only if elements exist)
if (topKSlider && topKValue) {
    // 실시간 화면 업데이트
    topKSlider.addEventListener('input', (e) => {
        topKValue.textContent = e.target.value;
    });

    // 값 변경 완료 시 자동 저장
    topKSlider.addEventListener('change', (e) => {
        currentSettings.top_k = parseInt(e.target.value);
        localStorage.setItem('chatSettings', JSON.stringify(currentSettings));
        logger.info('✅ Top K 저장됨:', e.target.value);
    });
}

// 검색 모드 변경 시 자동 저장
if (searchModeSelect) {
    searchModeSelect.addEventListener('change', async (e) => {
        // 하이브리드 RAG 상태 재확인
        try {
            // Check if user is authenticated
            if (!Auth.isAuthenticated()) {
                return;
            }

            const data = await Auth.apiCall('/api/hybrid-rag/status');

            // 하이브리드 RAG가 비활성화 상태이고, local-only가 아닌 값으로 변경하려는 경우
            if (!data.enabled && e.target.value !== 'local-only') {
                alert('⚠️ 하이브리드 RAG 기능이 비활성화되어 있습니다.\n로컬 문서만 사용 가능합니다.');
                e.target.value = 'local-only';
                currentSettings.searchMode = 'local-only';
                localStorage.setItem('chatSettings', JSON.stringify(currentSettings));
                return;
            }
        } catch (error) {
            logger.error('하이브리드 RAG 상태 확인 실패:', error);
        }

        // 현재 설정 업데이트
        currentSettings.searchMode = e.target.value;

        // localStorage에 즉시 저장
        localStorage.setItem('chatSettings', JSON.stringify(currentSettings));

        logger.info('✅ 검색 모드 저장됨:', e.target.value);
    });
}

if (temperatureSlider && temperatureValue) {
    // 실시간 화면 업데이트
    temperatureSlider.addEventListener('input', (e) => {
        temperatureValue.textContent = parseFloat(e.target.value).toFixed(1);
    });

    // 값 변경 완료 시 자동 저장
    temperatureSlider.addEventListener('change', (e) => {
        currentSettings.temperature = parseFloat(e.target.value);
        localStorage.setItem('chatSettings', JSON.stringify(currentSettings));
        logger.info('✅ Temperature 저장됨:', e.target.value);
    });
}

// Model-specific max token limits (output tokens)
// Note: These are OUTPUT token limits, not context window sizes
// Order matters: more specific patterns should come first
const MODEL_MAX_TOKENS = {
    // GLM models (ZhipuAI) - high output capacity
    'glm-4-flash': 16384,
    'glm-4.7-flash': 16384,
    'glm-4-plus': 16384,
    'glm-4': 16384,
    // Qwen models
    'qwen3': 32768,
    'qwen2.5': 32768,
    'qwen2': 32768,
    'qwen': 32768,
    // Llama models - specific versions first
    'llama3.2': 131072,
    'llama3.1': 131072,
    'llama3': 8192,
    'llama2': 4096,
    'llama': 8192,
    // Gemma models
    'gemma2': 8192,
    'gemma': 8192,
    // Mistral models
    'mixtral': 32768,
    'mistral': 32768,
    // Claude models
    'claude-3': 16384,
    'claude': 8192,
    // GPT models
    'gpt-4o': 16384,
    'gpt-4-turbo': 16384,
    'gpt-4': 8192,
    'gpt-3.5': 4096,
    // Gemini models
    'gemini-pro': 8192,
    'gemini': 8192,
    // DeepSeek models
    'deepseek': 16384,
    // Default
    'default': 8192
};

/**
 * Update max tokens slider based on current LLM model
 * @param {string} modelName - Current LLM model name
 */
function updateMaxTokensSlider(modelName) {
    if (!maxTokensSlider || !maxTokensValue) return;

    const modelLower = (modelName || '').toLowerCase();
    let maxTokens = MODEL_MAX_TOKENS['default'];

    // Find matching model max tokens
    for (const [key, value] of Object.entries(MODEL_MAX_TOKENS)) {
        if (modelLower.includes(key)) {
            maxTokens = value;
            break;
        }
    }

    // Cap at reasonable UI limit (32768 for usability)
    const uiMaxTokens = Math.min(maxTokens, 32768);

    // Update slider attributes
    maxTokensSlider.max = uiMaxTokens;

    // Adjust current value if exceeds new max
    if (parseInt(maxTokensSlider.value) > uiMaxTokens) {
        maxTokensSlider.value = uiMaxTokens;
        maxTokensValue.textContent = uiMaxTokens;
        currentSettings.max_tokens = uiMaxTokens;
    }

    // Update slider step for larger ranges
    if (uiMaxTokens > 8192) {
        maxTokensSlider.step = 512;
    } else {
        maxTokensSlider.step = 256;
    }

    logger.info(`✅ Max tokens slider updated for ${modelName}: max=${uiMaxTokens}`);
}

if (maxTokensSlider && maxTokensValue) {
    // 실시간 화면 업데이트
    maxTokensSlider.addEventListener('input', (e) => {
        maxTokensValue.textContent = e.target.value;
    });

    // 값 변경 완료 시 자동 저장
    maxTokensSlider.addEventListener('change', (e) => {
        currentSettings.max_tokens = parseInt(e.target.value);
        localStorage.setItem('chatSettings', JSON.stringify(currentSettings));
        logger.info('✅ Max Tokens 저장됨:', e.target.value);
    });
}

if (cacheThresholdSlider && cacheThresholdValue) {
    // 실시간 화면 업데이트
    cacheThresholdSlider.addEventListener('input', (e) => {
        cacheThresholdValue.textContent = parseFloat(e.target.value).toFixed(2);
    });

    // 값 변경 완료 시 자동 저장
    cacheThresholdSlider.addEventListener('change', (e) => {
        currentSettings.cache_threshold = parseFloat(e.target.value);
        localStorage.setItem('chatSettings', JSON.stringify(currentSettings));
        logger.info('✅ Cache Threshold 저장됨:', e.target.value);
    });
}

if (cacheTTLSlider && cacheTTLValue) {
    // 실시간 화면 업데이트
    cacheTTLSlider.addEventListener('input', (e) => {
        cacheTTLValue.textContent = e.target.value;
    });

    // 값 변경 완료 시 자동 저장
    cacheTTLSlider.addEventListener('change', (e) => {
        currentSettings.cache_ttl = parseInt(e.target.value);
        localStorage.setItem('chatSettings', JSON.stringify(currentSettings));
        logger.info('✅ Cache TTL 저장됨:', e.target.value);
    });
}

// Save settings
if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', async () => {
        // 모델 설정은 관리자 페이지에서만 변경 가능하므로 현재 값 유지
        // 시스템 프롬프트도 관리자 페이지에서만 변경 가능 (서버에서 항상 로드)
        currentSettings = {
            top_k: topKSlider ? parseInt(topKSlider.value) : defaultSettings.top_k,
            searchMode: searchModeSelect ? searchModeSelect.value : defaultSettings.searchMode,
            temperature: temperatureSlider ? parseFloat(temperatureSlider.value) : defaultSettings.temperature,
            max_tokens: maxTokensSlider ? parseInt(maxTokensSlider.value) : defaultSettings.max_tokens,
            cache_threshold: cacheThresholdSlider ? parseFloat(cacheThresholdSlider.value) : defaultSettings.cache_threshold,
            cache_ttl: cacheTTLSlider ? parseInt(cacheTTLSlider.value) : defaultSettings.cache_ttl,
            llm_model: currentSettings.llm_model,  // 현재 모델 유지 (읽기 전용)
            embedding_model: currentSettings.embedding_model,  // 현재 모델 유지 (읽기 전용)
            system_prompt: currentSettings.system_prompt  // 서버에서 로드된 값 유지 (읽기 전용)
        };

        localStorage.setItem('chatSettings', JSON.stringify(currentSettings));

        // Show success message
        const originalText = saveSettingsBtn.textContent;
        saveSettingsBtn.textContent = '✓ 저장됨!';
        saveSettingsBtn.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';

        setTimeout(() => {
            saveSettingsBtn.textContent = originalText;
        }, 2000);

        // Close settings panel
        setTimeout(() => {
            closeSettings();
        }, 1000);
    });
}

// Reset settings
if (resetSettingsBtn) {
    resetSettingsBtn.addEventListener('click', async () => {
        if (confirm('모든 설정을 기본값으로 복원하시겠습니까?')) {
            try {
                // Fetch current admin-configured models and system prompt from server
                const response = await fetch('/api/status');
                const data = await response.json();

                // Reset to defaults, but use admin-configured models
                currentSettings = {
                    ...defaultSettings,
                    llm_model: data.llm_model || defaultSettings.llm_model,
                    embedding_model: data.embedding_model || defaultSettings.embedding_model
                };

                // Reload system prompt from server
                await loadSystemPromptFromServer();

                applySettings();
                localStorage.removeItem('chatSettings');

                // Show success message
                const originalText = resetSettingsBtn.textContent;
                resetSettingsBtn.textContent = '✓ 복원됨!';

                setTimeout(() => {
                    resetSettingsBtn.textContent = originalText;
                }, 2000);
            } catch (error) {
                logger.error('Failed to fetch current models:', error);
                // Fallback to complete defaults if fetch fails
                currentSettings = { ...defaultSettings };

                // Try to reload system prompt even on error
                try {
                    await loadSystemPromptFromServer();
                } catch (e) {
                    logger.error('Failed to load system prompt:', e);
                }

                applySettings();
                localStorage.removeItem('chatSettings');

                alert('기본값으로 복원되었습니다.\n(서버에서 현재 모델 정보를 가져오지 못했습니다)');
            }
        }
    });
}

// Load cache statistics
async function loadCacheStats() {
    try {
        // Get DOM elements
        const statTotalEntries = document.getElementById('statTotalEntries');
        const statTotalQueries = document.getElementById('statTotalQueries');
        const statCacheHits = document.getElementById('statCacheHits');
        const statHitRate = document.getElementById('statHitRate');

        // Check if elements exist (might not be on this page)
        if (!statTotalEntries || !statTotalQueries || !statCacheHits || !statHitRate) {
            return; // Elements don't exist, skip silently
        }

        // Check authentication (required for cache stats)
        const token = localStorage.getItem('access_token');
        if (!token) {
            // Set default values for unauthenticated users
            statTotalEntries.textContent = '-';
            statTotalQueries.textContent = '-';
            statCacheHits.textContent = '-';
            statHitRate.textContent = '-';
            return;
        }

        const response = await fetch('/api/cache/stats', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        const stats = await response.json();

        if (response.ok) {
            statTotalEntries.textContent = stats.total_entries || 0;
            statTotalQueries.textContent = stats.total_queries || 0;
            statCacheHits.textContent = stats.cache_hits || 0;

            // Calculate hit rate
            const hitRate = stats.total_queries > 0
                ? ((stats.cache_hits / stats.total_queries) * 100).toFixed(1) + '%'
                : '0%';
            statHitRate.textContent = hitRate;

            // Update hit rate color based on percentage
            const hitRateValue = parseFloat(hitRate);
            if (hitRateValue >= 70) {
                statHitRate.style.color = '#059669'; // Green
            } else if (hitRateValue >= 40) {
                statHitRate.style.color = '#d97706'; // Orange
            } else {
                statHitRate.style.color = '#dc2626'; // Red
            }
        }
    } catch (error) {
        logger.error('Failed to load cache stats:', error);
        // Safe error handling - only set if elements exist
        const statTotalEntries = document.getElementById('statTotalEntries');
        const statTotalQueries = document.getElementById('statTotalQueries');
        const statCacheHits = document.getElementById('statCacheHits');
        const statHitRate = document.getElementById('statHitRate');

        if (statTotalEntries) statTotalEntries.textContent = 'Error';
        if (statTotalQueries) statTotalQueries.textContent = 'Error';
        if (statCacheHits) statCacheHits.textContent = 'Error';
        if (statHitRate) statHitRate.textContent = 'Error';
    }
}

// Refresh stats button
const refreshStatsBtn = document.getElementById('refreshStatsBtn');
if (refreshStatsBtn) {
    refreshStatsBtn.addEventListener('click', loadCacheStats);
}

// Clear cache button
if (clearCacheBtn) {
    clearCacheBtn.addEventListener('click', async () => {
        if (!confirm('모든 캐시를 삭제하시겠습니까?')) {
            return;
        }

        try {
            const response = await fetch('/api/cache/clear', {
                method: 'POST'
            });

            const result = await response.json();

            if (response.ok) {
                const originalText = clearCacheBtn.textContent;
                clearCacheBtn.textContent = `✓ ${result.entries_cleared}개 삭제됨`;

                // Reload stats after clearing
                setTimeout(() => {
                    clearCacheBtn.textContent = originalText;
                    loadCacheStats();
                }, 1000);
            } else {
                alert(`캐시 삭제 실패: ${result.detail}`);
            }
        } catch (error) {
            alert(`캐시 삭제 실패: ${error.message}`);
        }
    });
}

// Load cache enabled status
async function loadCacheEnabled() {
    try {
        // Check authentication (required for cache settings)
        const token = localStorage.getItem('access_token');
        const toggle = document.getElementById('cacheEnabledToggle');

        if (!token) {
            // Disable toggle for unauthenticated users
            if (toggle) {
                toggle.checked = false;
                toggle.disabled = true;
            }
            return;
        }

        const response = await fetch('/api/cache/enabled', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        const result = await response.json();

        if (response.ok) {
            if (toggle) {
                toggle.checked = result.enabled;
                toggle.disabled = false;
            }
        }
    } catch (error) {
        logger.error('Failed to load cache enabled status:', error);
    }
}

// Cache enabled toggle
const cacheEnabledToggle = document.getElementById('cacheEnabledToggle');
if (cacheEnabledToggle) {
    cacheEnabledToggle.addEventListener('change', async (e) => {
        const enabled = e.target.checked;

        try {
            const response = await fetch('/api/cache/enabled', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ enabled: enabled })
            });

            const result = await response.json();

            if (response.ok) {
                // Show success feedback (briefly change appearance)
                const message = enabled ? '✓ 캐시 활성화됨' : '✓ 캐시 비활성화됨';
                const notification = document.createElement('div');
                notification.textContent = message;
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 12px 24px;
                    border-radius: 8px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                    z-index: 10000;
                    font-weight: 500;
                `;
                document.body.appendChild(notification);
                setTimeout(() => notification.remove(), 2000);

                // Reload stats
                loadCacheStats();
            } else {
                alert(`캐시 설정 실패: ${result.detail}`);
                // Revert toggle state
                e.target.checked = !enabled;
            }
        } catch (error) {
            alert(`캐시 설정 실패: ${error.message}`);
            // Revert toggle state
            e.target.checked = !enabled;
        }
    });
}

// ===== Source Details Modal =====
async function showSourceDetails(filename) {
    devLog('[showSourceDetails] Called for filename:', filename);
    devLog('[showSourceDetails] currentContextData length:', currentContextData.length);

    // Find all context items for this filename in cache
    let sourceContexts = currentContextData.filter(ctx => ctx.filename === filename);

    devLog('[showSourceDetails] Found in cache:', sourceContexts.length, 'items');

    // If not found in cache, fetch from server
    if (sourceContexts.length === 0) {
        devLog('[showSourceDetails] Not in cache, fetching from server...');
        devLog('[showSourceDetails] API URL:', `/api/documents/${encodeURIComponent(filename)}/chunks`);

        // Show loading indicator
        sourceFilename.textContent = filename;
        sourceScore.textContent = '로딩 중...';
        sourceText.textContent = '📥 문서 내용을 불러오는 중입니다...\n잠시만 기다려주세요.';
        sourceModal.classList.add('active');
        pushModal(sourceModal, 'source');

        try {
            const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/chunks`);
            devLog('[showSourceDetails] Response status:', response.status, response.statusText);

            if (!response.ok) {
                const errorText = await response.text();
                logger.error('[showSourceDetails] Server error:', errorText);
                throw new Error(`Server returned ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            devLog('[showSourceDetails] Received data:', {
                filename: data.filename,
                total_count: data.total_count,
                chunks_count: data.chunks?.length
            });

            if (!data.chunks || data.chunks.length === 0) {
                devLog('[showSourceDetails] No chunks in response');
                sourceModal.classList.remove('active');
                alert(`출처 정보를 찾을 수 없습니다.\n파일명: ${filename}`);
                return;
            }

            // Convert server chunks to context format
            sourceContexts = data.chunks.map(chunk => ({
                filename: filename,
                text: chunk.text,
                score: 1.0  // Default score for loaded chunks
            }));

            devLog('[showSourceDetails] Successfully loaded', sourceContexts.length, 'chunks from server');
        } catch (error) {
            logger.error('[showSourceDetails] Error:', error);
            logger.error('[showSourceDetails] Error stack:', error.stack);
            sourceModal.classList.remove('active');
            alert(`출처 정보를 불러오는데 실패했습니다.\n파일명: ${filename}\n에러: ${error.message}`);
            return;
        }
    }

    // Use the first context item (or combine all if multiple)
    const context = sourceContexts[0];

    // Populate modal
    sourceFilename.textContent = filename;
    sourceScore.textContent = `${(context.score * 100).toFixed(1)}%`;

    // Show all matching text snippets
    if (sourceContexts.length > 1) {
        const allTexts = sourceContexts.map((ctx, idx) =>
            `[발췌 ${idx + 1}]\n${ctx.text}`
        ).join('\n\n' + '='.repeat(50) + '\n\n');
        sourceText.textContent = allTexts;
    } else {
        sourceText.textContent = context.text;
    }

    // Show modal
    sourceModal.classList.add('active');
    pushModal(sourceModal, 'source');
}

// ===== Draft Auto-Save =====
const DRAFT_KEY = 'chatDraft';

// Save draft to localStorage (with debouncing)
let draftSaveTimeout = null;
function saveDraft() {
    clearTimeout(draftSaveTimeout);
    draftSaveTimeout = setTimeout(() => {
        const draft = userInput.value.trim();
        if (draft) {
            localStorage.setItem(DRAFT_KEY, draft);
        } else {
            localStorage.removeItem(DRAFT_KEY);
        }
    }, 500); // Debounce 500ms
}

// Load draft from localStorage
function loadDraft() {
    try {
        const draft = localStorage.getItem(DRAFT_KEY);
        if (draft) {
            userInput.value = draft;
            autoResize();
            updateSendButton();

            // Show notification
            const notification = document.createElement('div');
            notification.className = 'draft-notification';
            notification.textContent = '💾 저장된 입력 내용을 복구했습니다';
            document.body.appendChild(notification);

            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => notification.remove(), 300);
            }, 3000);
        }
    } catch (e) {
        logger.error('Failed to load draft:', e);
    }
}

// Clear draft after sending
function clearDraft() {
    localStorage.removeItem(DRAFT_KEY);
}

// Flag to allow navigation without warning
window.allowNavigation = false;

// Warn before leaving with unsaved draft
window.addEventListener('beforeunload', (e) => {
    // Clean up all TTS resources before page unload
    stopAllTTS();

    // Skip warning if navigation is explicitly allowed
    if (window.allowNavigation) {
        return;
    }

    const draft = userInput.value.trim();
    if (draft && !isLoading) {
        e.preventDefault();
        e.returnValue = '입력 중인 내용이 있습니다. 페이지를 나가시겠습니까?';
    }
});

// ===== Conversation History Management =====
const HISTORY_KEY = 'chatHistory';
const MAX_HISTORY_ITEMS = 100; // Limit history size

// Save conversation history to localStorage
function saveHistory() {
    try {
        // Limit history size to prevent localStorage overflow
        const limitedHistory = conversationHistory.slice(-MAX_HISTORY_ITEMS);
        localStorage.setItem(HISTORY_KEY, JSON.stringify(limitedHistory));
    } catch (e) {
        logger.error('Failed to save history:', e);
    }
}

// Load conversation history from localStorage
function loadHistory() {
    try {
        const saved = localStorage.getItem(HISTORY_KEY);
        if (saved) {
            conversationHistory = JSON.parse(saved);

            // Restore chat UI
            if (conversationHistory.length > 0) {
                restoreChatUI();
            }
        }
    } catch (e) {
        logger.error('Failed to load history:', e);
        conversationHistory = [];
    }
}

// Restore chat UI from conversation history
function restoreChatUI() {
    // Clear welcome message
    chatContainer.innerHTML = '';

    // Rebuild currentContextData from all saved messages
    currentContextData = [];
    conversationHistory.forEach(msg => {
        if (msg.context && Array.isArray(msg.context)) {
            currentContextData.push(...msg.context);
        }
    });

    // Find last user question for regenerate function
    for (let i = conversationHistory.length - 1; i >= 0; i--) {
        if (conversationHistory[i].role === 'user') {
            lastUserQuestion = conversationHistory[i].content;
            break;
        }
    }

    conversationHistory.forEach(msg => {
        if (msg.role === 'user') {
            // Add user message
            addMessage(msg.content, 'user');
        } else if (msg.role === 'assistant') {
            // Add assistant message
            const messageDiv = addMessage('', 'assistant');
            const contentDiv = messageDiv.querySelector('.message-content');

            // Render markdown
            contentDiv.innerHTML = sanitizeHTML(marked.parse(msg.content);

            // Apply syntax highlighting
            contentDiv.querySelectorAll('pre code').forEach((block) => {
                if (!block.dataset.highlighted) {
                    normalizeLanguageClass(block);
                    hljs.highlightElement(block);
                }
            });

            // Render special content (math, diagrams, music, charts)
            renderSpecialContent(contentDiv);

            // Add action buttons first (to contentDiv, not messageDiv)
            addActionButtons(contentDiv, msg.content);

            // Restore sources if available (after action buttons)
            if (msg.sources && msg.sources.length > 0) {
                // Add HR separator before sources
                const hr = document.createElement('hr');
                hr.className = 'sources-separator';
                contentDiv.appendChild(hr);

                // Create sources section
                const sourcesDiv = document.createElement('div');
                sourcesDiv.className = 'sources';
                sourcesDiv.innerHTML = '<strong>📚 참고 문서:</strong><br>';

                msg.sources.forEach(source => {
                    const sourceTag = document.createElement('span');
                    sourceTag.className = 'source-tag';
                    sourceTag.textContent = source;

                    // Add click handler to show source details
                    sourceTag.addEventListener('click', () => {
                        showSourceDetails(source);
                    });

                    sourcesDiv.appendChild(sourceTag);
                });

                contentDiv.appendChild(sourcesDiv);
            }
        }
    });

    // Scroll to bottom
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Clear conversation history (both in memory and localStorage)
function clearHistory() {
    conversationHistory = [];
    localStorage.removeItem(HISTORY_KEY);
}

// Export conversation history - show format selection modal
function exportHistory() {
    if (conversationHistory.length === 0) {
        alert('저장할 대화 내용이 없습니다.');
        return;
    }

    const modal = document.getElementById('exportModal');
    const messageCount = document.getElementById('exportMessageCount');

    if (!modal || !messageCount) {
        logger.error('Export modal elements not found');
        return;
    }

    // Update message count
    messageCount.textContent = conversationHistory.length;

    // Show modal
    modal.classList.add('active');
    pushModal(modal, 'export');
}

// Export as specific format
async function exportAsFormat(format) {
    const date = new Date().toISOString().slice(0, 10);
    let content, mimeType, extension;

    try {
        switch (format) {
            case 'json':
                content = JSON.stringify(conversationHistory, null, 2);
                mimeType = 'application/json';
                extension = 'json';
                break;

            case 'txt':
                content = conversationHistoryToText();
                mimeType = 'text/plain';
                extension = 'txt';
                break;

            case 'markdown':
                content = conversationHistoryToMarkdown();
                mimeType = 'text/markdown';
                extension = 'md';
                break;

            case 'html':
                content = conversationHistoryToHTML();
                mimeType = 'text/html';
                extension = 'html';
                break;

            case 'pdf':
                await exportAsPDF(date);
                return; // PDF export handles modal closing internally

            case 'docx':
                await exportAsDocx(date);
                return; // DOCX export handles modal closing internally

            case 'hwpx':
                await exportAsHwpx(date);
                return; // HWPX export handles modal closing internally

            default:
                logger.error('Unknown format:', format);
                return;
        }

        // Create and download file (for simple formats)
        const blob = new Blob([content], { type: mimeType + ';charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `chat-history-${date}.${extension}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        // Close modal
        const modal = document.getElementById('exportModal');
        modal.classList.remove('active');
        popModal(modal);

        logger.info(`✅ 대화 내용을 ${format.toUpperCase()} 형식으로 내보냈습니다.`);
    } catch (error) {
        logger.error('Export error:', error);
        showError(`내보내기 실패: ${error.message}`);
    }
}

// Convert conversation history to plain text
function conversationHistoryToText() {
    const lines = [];
    lines.push('='.repeat(60));
    lines.push('📋 대화 내역');
    lines.push(`📅 내보낸 날짜: ${new Date().toLocaleString('ko-KR')}`);
    lines.push(`💬 총 메시지 수: ${conversationHistory.length}개`);
    lines.push('='.repeat(60));
    lines.push('');

    conversationHistory.forEach((msg, index) => {
        const role = msg.role === 'user' ? '👤 사용자' : '🤖 AI';
        const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleString('ko-KR') : '';

        lines.push(`[${index + 1}] ${role}`);
        if (timestamp) {
            lines.push(`⏰ ${timestamp}`);
        }
        lines.push('-'.repeat(60));
        lines.push(msg.content);
        lines.push('');
    });

    return lines.join('\n');
}

// Convert conversation history to Markdown
function conversationHistoryToMarkdown() {
    const lines = [];
    lines.push('# 📋 대화 내역\n');
    lines.push(`> **내보낸 날짜**: ${new Date().toLocaleString('ko-KR')}  `);
    lines.push(`> **총 메시지 수**: ${conversationHistory.length}개\n`);
    lines.push('---\n');

    conversationHistory.forEach((msg, index) => {
        const role = msg.role === 'user' ? '👤 **사용자**' : '🤖 **AI**';
        const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleString('ko-KR') : '';

        lines.push(`## ${index + 1}. ${role}\n`);
        if (timestamp) {
            lines.push(`*⏰ ${timestamp}*\n`);
        }

        // Format content with proper markdown
        const content = msg.content
            .replace(/```/g, '\n```')  // Ensure code blocks have line breaks
            .trim();

        lines.push(content + '\n');
        lines.push('---\n');
    });

    return lines.join('\n');
}

// Convert conversation history to HTML
function conversationHistoryToHTML() {
    const html = [];
    html.push('<!DOCTYPE html>');
    html.push('<html lang="ko">');
    html.push('<head>');
    html.push('    <meta charset="UTF-8">');
    html.push('    <meta name="viewport" content="width=device-width, initial-scale=1.0">');
    html.push('    <title>대화 내역</title>');
    html.push('    <style>');
    html.push('        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #f5f5f5; }');
    html.push('        .header { background: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }');
    html.push('        .header h1 { margin: 0 0 15px 0; color: #333; }');
    html.push('        .header p { margin: 5px 0; color: #666; font-size: 14px; }');
    html.push('        .message { background: white; padding: 20px; border-radius: 12px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }');
    html.push('        .message.user { border-left: 4px solid #667eea; }');
    html.push('        .message.assistant { border-left: 4px solid #22c55e; }');
    html.push('        .message-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #eee; }');
    html.push('        .role { font-weight: bold; font-size: 16px; }');
    html.push('        .role.user { color: #667eea; }');
    html.push('        .role.assistant { color: #22c55e; }');
    html.push('        .timestamp { color: #999; font-size: 13px; }');
    html.push('        .content { line-height: 1.6; color: #333; white-space: pre-wrap; word-wrap: break-word; }');
    html.push('        pre { background: #f8f9fa; padding: 15px; border-radius: 8px; overflow-x: auto; }');
    html.push('        code { font-family: "Consolas", "Monaco", monospace; font-size: 13px; }');
    html.push('    </style>');
    html.push('</head>');
    html.push('<body>');
    html.push('    <div class="header">');
    html.push('        <h1>📋 대화 내역</h1>');
    html.push(`        <p><strong>내보낸 날짜:</strong> ${new Date().toLocaleString('ko-KR')}</p>`);
    html.push(`        <p><strong>총 메시지 수:</strong> ${conversationHistory.length}개</p>`);
    html.push('    </div>');

    conversationHistory.forEach((msg, index) => {
        const roleClass = msg.role === 'user' ? 'user' : 'assistant';
        const roleName = msg.role === 'user' ? '👤 사용자' : '🤖 AI';
        const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleString('ko-KR') : '';
        const escapedContent = msg.content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');

        html.push(`    <div class="message ${roleClass}">`);
        html.push('        <div class="message-header">');
        html.push(`            <div class="role ${roleClass}">${roleName}</div>`);
        if (timestamp) {
            html.push(`            <div class="timestamp">⏰ ${timestamp}</div>`);
        }
        html.push('        </div>');
        html.push(`        <div class="content">${escapedContent}</div>`);
        html.push('    </div>');
    });

    html.push('</body>');
    html.push('</html>');

    return html.join('\n');
}

// Export as PDF using html2pdf.js
async function exportAsPDF(date) {
    try {
        showInfo('PDF 생성 중...');

        // Parse HTML to extract styles and content
        const fullHTML = conversationHistoryToHTML();
        const parser = new DOMParser();
        const doc = parser.parseFromString(fullHTML, 'text/html');

        // Extract styles from head
        const styles = doc.querySelector('style');
        const styleText = styles ? styles.textContent : '';

        // Get body content
        const bodyContent = doc.body.innerHTML;

        // Create temporary container with styles applied
        const container = document.createElement('div');
        container.style.position = 'absolute';
        container.style.left = '-9999px';

        // Add styles
        const styleElement = document.createElement('style');
        styleElement.textContent = styleText;
        container.appendChild(styleElement);

        // Add content
        const contentDiv = document.createElement('div');
        contentDiv.innerHTML = bodyContent;
        container.appendChild(contentDiv);

        document.body.appendChild(container);

        // Configure html2pdf options
        const opt = {
            margin: 10,
            filename: `chat-history-${date}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2, useCORS: true },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
        };

        // Generate PDF from content div with styles
        await html2pdf().set(opt).from(contentDiv).save();

        // Clean up
        document.body.removeChild(container);

        // Close modal
        const modal = document.getElementById('exportModal');
        modal.classList.remove('active');
        popModal(modal);

        showSuccess('PDF 내보내기 완료');
        logger.info('✅ 대화 내용을 PDF 형식으로 내보냈습니다.');
    } catch (error) {
        logger.error('PDF export error:', error);
        showError(`PDF 내보내기 실패: ${error.message}`);
    }
}

// Export as DOCX using docx library
async function exportAsDocx(date) {
    try {
        showInfo('Word 문서 생성 중...');

        const { Document, Packer, Paragraph, TextRun, HeadingLevel } = docx;

        // Create document sections
        const sections = [];

        // Header
        sections.push(
            new Paragraph({
                text: '📋 대화 내역',
                heading: HeadingLevel.HEADING_1,
            }),
            new Paragraph({
                children: [
                    new TextRun({
                        text: `내보낸 날짜: ${new Date().toLocaleString('ko-KR')}`,
                    }),
                ],
            }),
            new Paragraph({
                children: [
                    new TextRun({
                        text: `총 메시지 수: ${conversationHistory.length}개`,
                    }),
                ],
            }),
            new Paragraph({ text: '' }) // Empty line
        );

        // Add messages
        conversationHistory.forEach((msg, index) => {
            const roleName = msg.role === 'user' ? '👤 사용자' : '🤖 AI';
            const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleString('ko-KR') : '';

            sections.push(
                new Paragraph({
                    text: `${index + 1}. ${roleName}`,
                    heading: HeadingLevel.HEADING_2,
                }),
            );

            if (timestamp) {
                sections.push(
                    new Paragraph({
                        children: [
                            new TextRun({
                                text: `⏰ ${timestamp}`,
                                italics: true,
                            }),
                        ],
                    })
                );
            }

            sections.push(
                new Paragraph({
                    children: [
                        new TextRun({
                            text: msg.content,
                        }),
                    ],
                }),
                new Paragraph({ text: '' }) // Empty line
            );
        });

        // Create document
        const doc = new Document({
            sections: [{
                properties: {},
                children: sections,
            }],
        });

        // Generate and save
        const blob = await Packer.toBlob(doc);
        saveAs(blob, `chat-history-${date}.docx`);

        // Close modal
        const modal = document.getElementById('exportModal');
        modal.classList.remove('active');
        popModal(modal);

        showSuccess('Word 문서 내보내기 완료');
        logger.info('✅ 대화 내용을 DOCX 형식으로 내보냈습니다.');
    } catch (error) {
        logger.error('DOCX export error:', error);
        showError(`Word 문서 내보내기 실패: ${error.message}`);
    }
}

// Export as HWPX using backend conversion API
async function exportAsHwpx(date) {
    try {
        showInfo('한글 문서 변환 중...');

        // Create HTML content
        const htmlContent = conversationHistoryToHTML();

        // Call backend conversion API
        const token = localStorage.getItem('access_token');
        if (!token) {
            throw new Error('로그인이 필요합니다.');
        }

        const response = await fetch('/api/convert/hwpx', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: htmlContent,
                content_type: 'html',
                filename: `chat-history-${date}`
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: '변환 실패' }));
            throw new Error(errorData.detail || '한글 문서 변환 실패');
        }

        // Download the HWPX file
        const blob = await response.blob();
        saveAs(blob, `chat-history-${date}.hwpx`);

        // Close modal
        const modal = document.getElementById('exportModal');
        modal.classList.remove('active');
        popModal(modal);

        showSuccess('한글 문서 내보내기 완료');
        logger.info('✅ 대화 내용을 HWPX 형식으로 내보냈습니다.');
    } catch (error) {
        logger.error('HWPX export error:', error);
        showError(`한글 문서 내보내기 실패: ${error.message}`);
    }
}

// Import conversation history from JSON file
function importHistory() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,.txt,.md';

    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        try {
            const text = await file.text();
            const fileName = file.name.toLowerCase();
            let imported;

            // Parse based on file extension
            if (fileName.endsWith('.json')) {
                imported = parseJsonHistory(text);
            } else if (fileName.endsWith('.txt')) {
                imported = parseTextHistory(text);
            } else if (fileName.endsWith('.md')) {
                imported = parseMarkdownHistory(text);
            } else {
                throw new Error('지원하지 않는 파일 형식입니다. JSON, TXT, MD 파일만 가능합니다.');
            }

            // Validate imported data
            if (!Array.isArray(imported) || imported.length === 0) {
                throw new Error('올바른 대화 내용을 찾을 수 없습니다.');
            }

            // Confirm overwrite
            if (conversationHistory.length > 0) {
                if (!confirm('현재 대화 내용을 덮어쓰시겠습니까?')) {
                    return;
                }
            }

            // Load imported history
            conversationHistory = imported;
            saveHistory();
            restoreChatUI();

            alert(`대화 내용을 불러왔습니다. (${imported.length}개 메시지)`);
        } catch (err) {
            logger.error('Import error:', err);
            alert(`파일을 불러오는데 실패했습니다: ${err.message}`);
        }
    };

    input.click();
}

// Parse JSON format
function parseJsonHistory(text) {
    const imported = JSON.parse(text);
    if (!Array.isArray(imported)) {
        throw new Error('Invalid JSON format: expected an array');
    }
    return imported;
}

// Parse TXT format
function parseTextHistory(text) {
    const messages = [];
    const lines = text.split('\n');
    let currentMessage = null;
    let contentLines = [];
    let inContent = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Detect message start: [N] 👤 사용자 or [N] 🤖 AI
        const messageMatch = line.match(/^\[(\d+)\] (👤 사용자|🤖 AI)$/);
        if (messageMatch) {
            // Save previous message
            if (currentMessage && contentLines.length > 0) {
                currentMessage.content = contentLines.join('\n').trim();
                messages.push(currentMessage);
            }

            // Start new message
            const role = messageMatch[2] === '👤 사용자' ? 'user' : 'assistant';
            currentMessage = { role, content: '' };
            contentLines = [];
            inContent = false;
            continue;
        }

        // Skip separator lines
        if (line.match(/^[-=]{10,}$/)) {
            if (!inContent) {
                inContent = true; // Content starts after separator
            }
            continue;
        }

        // Skip timestamp lines
        if (line.match(/^⏰ /)) {
            continue;
        }

        // Skip header lines
        if (line.match(/^(📋 대화 내역|📅 내보낸 날짜|💬 총 메시지 수)/)) {
            continue;
        }

        // Collect content lines
        if (inContent && currentMessage) {
            contentLines.push(line);
        }
    }

    // Save last message
    if (currentMessage && contentLines.length > 0) {
        currentMessage.content = contentLines.join('\n').trim();
        messages.push(currentMessage);
    }

    return messages;
}

// Parse Markdown format
function parseMarkdownHistory(text) {
    const messages = [];
    const lines = text.split('\n');
    let currentMessage = null;
    let contentLines = [];
    let inContent = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Detect message start: ## N. 👤 **사용자** or ## N. 🤖 **AI**
        const messageMatch = line.match(/^## \d+\. (👤 \*\*사용자\*\*|🤖 \*\*AI\*\*)$/);
        if (messageMatch) {
            // Save previous message
            if (currentMessage && contentLines.length > 0) {
                currentMessage.content = contentLines.join('\n').trim();
                messages.push(currentMessage);
            }

            // Start new message
            const role = messageMatch[1].includes('사용자') ? 'user' : 'assistant';
            currentMessage = { role, content: '' };
            contentLines = [];
            inContent = false;
            continue;
        }

        // Skip timestamp lines
        if (line.match(/^\*⏰ /)) {
            inContent = true; // Content starts after timestamp
            continue;
        }

        // Skip separator lines
        if (line.match(/^---$/)) {
            continue;
        }

        // Skip header lines
        if (line.match(/^(# 📋 대화 내역|> \*\*내보낸 날짜|> \*\*총 메시지 수)/)) {
            continue;
        }

        // Collect content lines
        if (currentMessage) {
            if (inContent || line.trim() !== '') {
                inContent = true;
                contentLines.push(line);
            }
        }
    }

    // Save last message
    if (currentMessage && contentLines.length > 0) {
        currentMessage.content = contentLines.join('\n').trim();
        messages.push(currentMessage);
    }

    return messages;
}

// Copy to clipboard function
async function copyToClipboard(text, button) {
    try {
        await navigator.clipboard.writeText(text);

        // Show feedback
        const originalHTML = button.innerHTML;
        button.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                <path d="M3 8L6 11L13 4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        `;
        button.classList.add('copied');

        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.classList.remove('copied');
        }, 2000);
    } catch (err) {
        logger.error('Failed to copy:', err);
        alert('복사에 실패했습니다');
    }
}

// Stop generation function
function stopGeneration() {
    if (currentAbortController) {
        currentAbortController.abort();
        // Note: The cancelled message will be added by the catch block in sendMessage()
        // We only need to clean up UI elements here
    }
}

// Scroll to bottom function
function scrollToBottom() {
    chatContainer.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
    });
}

// Update scroll button visibility based on scroll position
function updateScrollButtonVisibility() {
    const scrollBtn = document.getElementById('scrollToBottomBtn');
    if (!scrollBtn) return;

    const threshold = 20;  // Reduced from 100 to 20 for better responsiveness
    const atBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < threshold;

    if (atBottom) {
        scrollBtn.classList.remove('visible');
    } else {
        scrollBtn.classList.add('visible');
    }
}

// Setup scroll to bottom button
function setupScrollButton() {
    const scrollBtn = document.getElementById('scrollToBottomBtn');
    if (!scrollBtn) return;

    // Show/hide button based on scroll position
    chatContainer.addEventListener('scroll', updateScrollButtonVisibility);

    // Click handler
    scrollBtn.addEventListener('click', scrollToBottom);

    // Initial check
    updateScrollButtonVisibility();
}

// Show stop button during generation
function showStopButton() {
    // Check if stop button already exists
    if (document.getElementById('stopBtn')) return;

    const inputArea = document.querySelector('.input-area');
    const stopBtn = document.createElement('button');
    stopBtn.id = 'stopBtn';
    stopBtn.className = 'stop-btn';
    stopBtn.title = '응답 생성 중단';
    stopBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
            <rect x="4" y="4" width="8" height="8" rx="1"/>
        </svg>
    `;
    stopBtn.onclick = stopGeneration;

    inputArea.appendChild(stopBtn);
}

// Hide stop button
function hideStopButton() {
    const stopBtn = document.getElementById('stopBtn');
    if (stopBtn) {
        stopBtn.remove();
    }
}

// ===== Theme Management =====
let isTogglingTheme = false;  // Prevent concurrent theme switches

function initTheme() {
    // Get saved theme or default to light
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme, true);  // Skip animation on init
}

function toggleTheme() {
    // Prevent concurrent toggles
    if (isTogglingTheme) {
        return;
    }

    isTogglingTheme = true;

    try {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
    } finally {
        // Release lock after a short delay to prevent rapid clicking
        setTimeout(() => {
            isTogglingTheme = false;
        }, 100);
    }
}

function setTheme(theme, skipTransition = false) {
    // Validate theme value
    if (theme !== 'light' && theme !== 'dark') {
        theme = 'light';
    }

    // Set theme attribute on root element
    document.documentElement.setAttribute('data-theme', theme);

    // Force reflow to ensure CSS variables are applied immediately
    void document.documentElement.offsetHeight;

    // Save to localStorage
    try {
        localStorage.setItem('theme', theme);
    } catch (error) {
        logger.error('Failed to save theme to localStorage:', error);
    }

    // Update theme toggle button icons with null checks
    if (themeToggle) {
        const sunIcon = themeToggle.querySelector('.sun-icon');
        const moonIcon = themeToggle.querySelector('.moon-icon');

        if (sunIcon && moonIcon) {
            if (theme === 'dark') {
                // Show moon icon, hide sun icon
                if (skipTransition) {
                    // Instant change on init
                    sunIcon.style.display = 'none';
                    sunIcon.style.opacity = '0';
                    moonIcon.style.display = 'block';
                    moonIcon.style.opacity = '1';
                    moonIcon.style.transform = 'rotate(0deg) scale(1)';
                } else {
                    // Smooth transition on toggle
                    sunIcon.style.opacity = '0';
                    sunIcon.style.transform = 'rotate(-90deg) scale(0.8)';
                    moonIcon.style.display = 'block';
                    moonIcon.style.opacity = '1';
                    moonIcon.style.transform = 'rotate(0deg) scale(1)';
                    // Hide sun icon after transition
                    setTimeout(() => {
                        sunIcon.style.display = 'none';
                    }, 300);
                }
            } else {
                // Show sun icon, hide moon icon
                if (skipTransition) {
                    // Instant change on init
                    moonIcon.style.display = 'none';
                    moonIcon.style.opacity = '0';
                    sunIcon.style.display = 'block';
                    sunIcon.style.opacity = '1';
                    sunIcon.style.transform = 'rotate(0deg) scale(1)';
                } else {
                    // Smooth transition on toggle
                    moonIcon.style.opacity = '0';
                    moonIcon.style.transform = 'rotate(90deg) scale(0.8)';
                    sunIcon.style.display = 'block';
                    sunIcon.style.opacity = '1';
                    sunIcon.style.transform = 'rotate(0deg) scale(1)';
                    // Hide moon icon after transition
                    setTimeout(() => {
                        moonIcon.style.display = 'none';
                    }, 300);
                }
            }
        }
    }

    // Add visual feedback
    if (!skipTransition && themeToggle) {
        themeToggle.style.transform = 'rotate(360deg)';
        themeToggle.style.transition = 'transform 0.3s ease';
        setTimeout(() => {
            themeToggle.style.transform = '';
            themeToggle.style.transition = '';
        }, 300);
    }
}

// Initialize settings on load
loadSettings();

// Load conversation history on startup
// loadHistory();  // Disabled: Now using Redis-based conversation history instead of localStorage

// Load draft on startup
loadDraft();

// Show validation error
function showValidationError(message) {
    // Create error notification
    const errorDiv = document.createElement('div');
    errorDiv.className = 'validation-error';
    errorDiv.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor" style="flex-shrink: 0;">
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zM7 4h2v5H7V4zm0 6h2v2H7v-2z"/>
        </svg>
        <span>${message}</span>
    `;

    // Add to page
    document.body.appendChild(errorDiv);

    // Shake animation for input
    userInput.style.animation = 'shake 0.3s ease-in-out';
    userInput.style.borderColor = '#ef4444';

    // Remove after 3 seconds
    setTimeout(() => {
        errorDiv.style.opacity = '0';
        setTimeout(() => errorDiv.remove(), 300);
        userInput.style.animation = '';
        userInput.style.borderColor = '';
    }, 3000);

    // Focus input
    userInput.focus();
}

// Update character count display
function updateCharCount() {
    const length = userInput.value.length;
    const maxLength = INPUT_VALIDATION.MAX_LENGTH;

    // Find or create char count element
    let charCount = document.getElementById('charCount');
    if (!charCount) {
        charCount = document.createElement('div');
        charCount.id = 'charCount';
        charCount.className = 'char-count';
        userInput.parentElement.appendChild(charCount);
    }

    // Update text and color
    charCount.textContent = `${length} / ${maxLength}`;

    // Color coding
    if (length > maxLength) {
        charCount.style.color = '#ef4444'; // Red - over limit
    } else if (length > maxLength * 0.9) {
        charCount.style.color = '#f59e0b'; // Orange - warning
    } else {
        charCount.style.color = 'var(--text-secondary)'; // Gray - normal
    }

    // Show only when typing
    if (length > 0) {
        charCount.style.opacity = '1';
    } else {
        charCount.style.opacity = '0';
    }
}

// ===== Document Filter Functionality =====
let availableDocuments = [];
window.selectedDocumentIds = new Set();

// Toggle filter panel expansion/collapse
function toggleFilterPanel() {
    const filterContent = document.getElementById('filterContent');

    if (!filterContent) return;

    // Toggle collapsed state - CSS handles arrow rotation automatically
    filterContent.classList.toggle('collapsed');
}

// Load available documents for filter from server
async function loadFilterDocuments() {
    const documentList = document.getElementById('filterDocumentList');

    if (!documentList) {
        logger.warn('filterDocumentList element not found');
        return;
    }

    try {
        // Check if user is authenticated (required for documents API)
        const token = localStorage.getItem('access_token');
        if (!token) {
            documentList.innerHTML = '<div class="loading-documents">로그인 후 문서 목록을 확인할 수 있습니다</div>';
            return;
        }

        // Show loading state
        documentList.innerHTML = '<div class="loading-documents">문서 목록을 불러오는 중...</div>';

        // Use Auth.apiCall for automatic retry logic
        // Note: Retry logic will handle transient failures better than timeout
        const data = await Auth.apiCall('/api/documents?filter_scope=user', {
            signal: AbortSignal.timeout(10000) // 10 second timeout
        });

        availableDocuments = data.documents || [];
        renderFilterDocumentList();
    } catch (error) {
        logger.error('Error loading filter documents:', error);
        if (error.name === 'TimeoutError') {
            documentList.innerHTML = '<div class="loading-documents" style="color: #ef4444;">⏱️ 시간 초과: 서버 응답이 없습니다.</div>';
        } else if (error.message.includes('인증')) {
            documentList.innerHTML = '<div class="loading-documents" style="color: #666;">🔒 로그인 후 이용 가능합니다.</div>';
        } else {
            documentList.innerHTML = '<div class="loading-documents" style="color: #ef4444;">❌ 문서 목록을 불러오는데 실패했습니다.<br><small>' + escapeHtml(error.message) + '</small></div>';
        }
    }
}

// Render filter document list with checkboxes
function renderFilterDocumentList() {
    const documentList = document.getElementById('filterDocumentList');

    if (!documentList) {
        logger.warn('filterDocumentList element not found');
        return;
    }

    if (availableDocuments.length === 0) {
        documentList.innerHTML = '<div class="loading-documents">📭 등록된 문서가 없습니다.</div>';
        updateFilterTabCounts();
        return;
    }

    documentList.innerHTML = availableDocuments.map(doc => `
        <div class="document-item">
            <input type="checkbox"
                   id="doc-${doc.id}"
                   value="${doc.id}"
                   onchange="handleDocumentSelection(this)">
            <label for="doc-${doc.id}">
                <div class="document-name">${doc.name}</div>
                <div class="document-meta">
                    <span>📄 ${doc.chunk_count || 0}개 청크</span>
                    <span>📅 ${formatDate(doc.created_at)}</span>
                </div>
            </label>
            <div class="document-actions">
                <button class="doc-action-btn" onclick="downloadDocument('${doc.name}', event)" title="원본 파일 다운로드">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8 12l-4-4h2.5V4h3v4H12l-4 4z"/>
                        <path d="M14 13v1H2v-1h12z"/>
                    </svg>
                </button>
                <button class="doc-action-btn" onclick="downloadDocumentAsPDF('${doc.name}', event)" title="PDF로 다운로드">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M2 2h12v12H2V2zm1 1v10h10V3H3z"/>
                        <path d="M4 5h8v1H4V5zm0 2h8v1H4V7zm0 2h5v1H4V9z"/>
                    </svg>
                </button>
            </div>
        </div>
    `).join('');

    // Update counts after rendering
    updateFilterTabCounts();
}

// Handle document checkbox selection
function handleDocumentSelection(checkbox) {
    if (checkbox.checked) {
        window.selectedDocumentIds.add(checkbox.value);
    } else {
        window.selectedDocumentIds.delete(checkbox.value);
    }

    // Auto-switch to "selected documents" mode if any document is selected
    const selectedMode = document.querySelector('input[name="filterMode"][value="selected"]');
    const allMode = document.querySelector('input[name="filterMode"][value="all"]');

    if (window.selectedDocumentIds.size > 0 && selectedMode) {
        selectedMode.checked = true;
    } else if (window.selectedDocumentIds.size === 0 && allMode) {
        // Auto-switch to "all documents" mode if no document is selected
        allMode.checked = true;
    }

    // Update tab counts
    updateFilterTabCounts();
}

// Handle filter mode change (all vs selected)
function handleFilterModeChange(mode) {
    if (mode === 'all') {
        // Uncheck all document checkboxes
        document.querySelectorAll('.document-item input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
        window.selectedDocumentIds.clear();
        updateFilterTabCounts();
    }
}

// Get selected document IDs for query
function getSelectedDocumentIds() {
    const filterMode = document.querySelector('input[name="filterMode"]:checked')?.value;

    if (filterMode === 'all') {
        return null; // null means search all documents
    }

    if (window.selectedDocumentIds.size === 0) {
        return null; // If no documents selected, default to all
    }

    return Array.from(window.selectedDocumentIds);
}

/**
 * Get active filter data based on the currently selected tab
 * Returns object with documentIds and groupIds
 */
function getActiveFilterData() {
    // Check which filter tab is active
    const activeTab = document.querySelector('.filter-tab.active')?.dataset.tab;

    let documentIds = null;
    let groupIds = null;

    if (activeTab === 'documents') {
        // Document filter is active
        const filterMode = document.querySelector('input[name="filterMode"]:checked')?.value;
        if (filterMode === 'selected') {
            if (window.selectedDocumentIds && window.selectedDocumentIds.size > 0) {
                documentIds = Array.from(window.selectedDocumentIds);
            } else {
                // If "selected" mode but no documents selected, use empty array to prevent any search
                documentIds = [];
            }
        }
    } else if (activeTab === 'groups') {
        // Group filter is active
        const groupFilterMode = document.querySelector('input[name="groupFilterMode"]:checked')?.value;
        if (groupFilterMode === 'selected' && groupFilter) {
            const selectedGroups = groupFilter.getSelectedGroups();
            if (selectedGroups && selectedGroups.length > 0) {
                groupIds = selectedGroups;
            } else {
                // If "selected" mode but no groups selected, use empty array to prevent any search
                groupIds = [];
            }
        }
    }

    return { documentIds, groupIds };
}

// Initialize document filter
function initDocumentFilter() {
    // Set initial state to collapsed (closed)
    const filterContent = document.getElementById('filterContent');
    if (filterContent) {
        filterContent.classList.add('collapsed');
    }

    // Set up filter header click handler
    const filterHeader = document.querySelector('.filter-header');
    if (filterHeader) {
        filterHeader.addEventListener('click', toggleFilterPanel);
    }

    // Set up filter mode radio button handlers
    const filterModeRadios = document.querySelectorAll('input[name="filterMode"]');
    filterModeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            handleFilterModeChange(e.target.value);
        });
    });

    // Load organization info and documents from server for filter
    loadFilterOrgInfo();
    loadFilterDocuments();
}

// ===== Suggested Questions =====

/**
 * Load suggested questions from server
 */
async function loadSuggestedQuestions() {
    try {
        // Add cache-busting parameter to get fresh questions
        const data = await Auth.apiCall(`/api/suggested-questions?t=${Date.now()}`);
        if (!data) {
            devWarn('Failed to load suggested questions');
            return;
        }

        if (data.questions && data.questions.length > 0) {
            try {
                displaySuggestedQuestions(data.questions);
            } catch (err) {
                devWarn('Could not display suggested questions panel:', err);
            }

            // Update AutoComplete with new questions
            if (questionAutoComplete) {
                questionAutoComplete.updateSuggestions(data.questions);
            }
        }
    } catch (error) {
        logger.error('Error loading suggested questions:', error);
    }
}

/**
 * Refresh suggested questions with animation
 */
async function refreshSuggestedQuestions() {
    const btn = refreshSuggestionsBtn;
    if (!btn) return;

    // Add rotating animation
    btn.classList.add('rotating');
    btn.disabled = true;

    try {
        // Clear current suggestions
        const listElement = document.getElementById('suggestedQuestionsList');
        if (listElement) {
            listElement.style.opacity = '0.5';
        }

        // Load new suggestions
        await loadSuggestedQuestions();

        // Restore opacity
        if (listElement) {
            listElement.style.opacity = '1';
        }
    } catch (error) {
        logger.error('Error refreshing suggested questions:', error);
    } finally {
        // Remove animation after it completes
        setTimeout(() => {
            btn.classList.remove('rotating');
            btn.disabled = false;
        }, 600);
    }
}

/**
 * Display suggested questions in the UI
 */
function displaySuggestedQuestions(questions) {
    const container = document.getElementById('suggestedQuestions');
    const listElement = document.getElementById('suggestedQuestionsList');

    if (!container || !listElement) {
        // Silently skip if elements are not in DOM (not an error condition)
        devWarn('Suggested questions panel elements not found - skipping display');
        return;
    }

    if (!questions || questions.length === 0) {
        return;
    }

    // Clear existing questions
    listElement.innerHTML = '';

    // Create question elements
    questions.forEach((question, index) => {
        const questionItem = document.createElement('div');
        questionItem.className = 'suggested-question-item';
        questionItem.setAttribute('data-question', question);

        const questionText = document.createElement('div');
        questionText.className = 'suggested-question-text';
        questionText.textContent = question;

        questionItem.appendChild(questionText);

        // Add click handler
        questionItem.addEventListener('click', () => handleQuestionClick(question));

        listElement.appendChild(questionItem);
    });

    // ALWAYS show the suggestions container when questions are added
    container.style.display = 'block';
}

/**
 * Handle click on suggested question
 */
function handleQuestionClick(question) {
    // Set question in input
    userInput.value = question;

    // Hide suggested questions
    const container = document.getElementById('suggestedQuestions');
    if (container) {
        container.style.display = 'none';
    }

    // Auto-send the question
    sendMessage();

    // Focus back on input
    userInput.focus();
}

/**
 * Hide suggested questions (called after first user message)
 */
function hideSuggestedQuestions() {
    const container = document.getElementById('suggestedQuestions');
    if (container) {
        container.style.display = 'none';
    }
}

// ============================================================================
// Group Management Integration
// ============================================================================

let groupManager = null;
let groupFilter = null;
let selectedGroupForEdit = null;

/**
 * Initialize group management UI
 */
async function initGroupManagement() {
    try {
        // Initialize group manager and filter
        const result = await initializeGroupManagement();
        groupManager = result.groupManager;
        groupFilter = result.groupFilter;

        // Setup modal event handlers
        setupGroupModalHandlers();

        // Setup filter tab handlers
        setupGroupFilterHandlers();

        // Load groups into filter
        await loadGroupsIntoFilter();

        // Update initial tab counts
        updateFilterTabCounts();

    } catch (error) {
        logger.error('Failed to initialize group management:', error);
    }
}

/**
 * Setup group management modal handlers
 */
function setupGroupModalHandlers() {
    // Group management button - open modal
    const groupManageBtn = document.getElementById('groupManageBtn');
    const groupModal = document.getElementById('groupManagementModal');
    const closeGroupModal = document.getElementById('closeGroupModal');

    if (groupManageBtn && groupModal) {
        groupManageBtn.addEventListener('click', async () => {
            groupModal.classList.add('active');
            pushModal(groupModal, 'group');

            // Parallel loading of group data, selected group docs, and assignable docs
            const loadTasks = [
                loadGroupTree(),
                loadAllDocumentsForAssign()
            ];

            // Conditionally add selected group documents loading
            if (selectedGroupForEdit) {
                loadTasks.push(loadGroupDocuments(selectedGroupForEdit));
            }

            await Promise.all(loadTasks);
        });
    }

    if (closeGroupModal && groupModal) {
        closeGroupModal.addEventListener('click', () => {
            groupModal.classList.remove('active');
            popModal(groupModal);
        });
    }

    // Close modal when clicking outside
    if (groupModal) {
        groupModal.addEventListener('click', (e) => {
            if (e.target === groupModal) {
                groupModal.classList.remove('active');
                popModal(groupModal);
            }
        });
    }

    // Create group button - open create modal
    const createGroupBtn = document.getElementById('createGroupBtn');
    const groupCreateModal = document.getElementById('groupCreateModal');
    const closeGroupCreateModal = document.getElementById('closeGroupCreateModal');
    const cancelGroupCreate = document.getElementById('cancelGroupCreate');

    if (createGroupBtn && groupCreateModal) {
        createGroupBtn.addEventListener('click', () => {
            groupCreateModal.classList.add('active');
            pushModal(groupCreateModal, 'groupCreate');
            populateParentGroupSelect();
        });
    }

    if (closeGroupCreateModal && groupCreateModal) {
        closeGroupCreateModal.addEventListener('click', () => {
            groupCreateModal.classList.remove('active');
            popModal(groupCreateModal);
        });
    }

    if (cancelGroupCreate && groupCreateModal) {
        cancelGroupCreate.addEventListener('click', () => {
            groupCreateModal.classList.remove('active');
            popModal(groupCreateModal);
        });
    }

    // Group creation form submit
    const groupCreateForm = document.getElementById('groupCreateForm');
    if (groupCreateForm) {
        groupCreateForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await handleGroupCreate();
        });
    }

    // Group info form submit
    const groupInfoForm = document.getElementById('groupInfoForm');
    if (groupInfoForm) {
        groupInfoForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await handleGroupUpdate();
        });
    }

    // Delete group button
    const deleteGroupBtn = document.getElementById('deleteGroupBtn');
    if (deleteGroupBtn) {
        deleteGroupBtn.addEventListener('click', async () => {
            await handleGroupDelete();
        });
    }

    // Assign documents button
    const assignDocumentsBtn = document.getElementById('assignDocumentsBtn');
    if (assignDocumentsBtn) {
        assignDocumentsBtn.addEventListener('click', async () => {
            await handleDocumentAssign();
        });
    }
}

/**
 * Setup filter tab handlers
 */
function setupGroupFilterHandlers() {
    const filterTabs = document.querySelectorAll('.filter-tab');
    const documentPanel = document.getElementById('documentFilterPanel');
    const groupPanel = document.getElementById('groupFilterPanel');

    filterTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Update active tab
            filterTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Show corresponding panel
            const tabType = tab.dataset.tab;
            if (tabType === 'documents') {
                documentPanel.style.display = 'block';
                groupPanel.style.display = 'none';
            } else if (tabType === 'groups') {
                documentPanel.style.display = 'none';
                groupPanel.style.display = 'block';
            }
        });
    });
}

/**
 * Update filter tab counts to show selected items
 */
function updateFilterTabCounts() {
    const documentTab = document.querySelector('.filter-tab[data-tab="documents"]');
    const groupTab = document.querySelector('.filter-tab[data-tab="groups"]');

    if (documentTab) {
        const docCount = window.selectedDocumentIds ? window.selectedDocumentIds.size : 0;
        const baseText = '문서별';
        documentTab.textContent = docCount > 0 ? `${baseText} (${docCount})` : baseText;
    }

    if (groupTab && groupFilter) {
        const groupCount = groupFilter.getSelectedGroups().length;
        const baseText = '그룹별';
        groupTab.textContent = groupCount > 0 ? `${baseText} (${groupCount})` : baseText;
    }

    // Update document counts in filter options
    const totalDocCount = document.getElementById('totalDocCount');
    const selectedDocCount = document.getElementById('selectedDocCount');
    if (totalDocCount && availableDocuments) {
        totalDocCount.textContent = `(${availableDocuments.length}개)`;
    }
    if (selectedDocCount && window.selectedDocumentIds) {
        const count = window.selectedDocumentIds.size;
        selectedDocCount.textContent = count > 0 ? `(${count}개)` : '';
    }

    // Update group counts in filter options
    const totalGroupCount = document.getElementById('totalGroupCount');
    const selectedGroupCount = document.getElementById('selectedGroupCount');
    if (totalGroupCount && groupManager && groupManager.groups) {
        totalGroupCount.textContent = `(${groupManager.groups.length}개)`;
    }
    if (selectedGroupCount && groupFilter) {
        const count = groupFilter.getSelectedGroups().length;
        selectedGroupCount.textContent = count > 0 ? `(${count}개)` : '';
    }
}

/**
 * Load and display user organization info in filter header
 */
async function loadFilterOrgInfo() {
    const filterOrgName = document.getElementById('filterOrgName');

    if (!filterOrgName) {
        return;
    }

    try {
        const token = localStorage.getItem('access_token');
        if (!token) {
            filterOrgName.textContent = '로그인 필요';
            return;
        }

        // Get current user info using Auth.apiCall for retry logic
        const userData = await Auth.apiCall('/api/auth/me');
        const user = userData.user;

        // Get organization info
        if (user.org_id) {
            try {
                const orgData = await Auth.apiCall(`/api/organizations/${user.org_id}`);
                // API returns {success: true, organization: {name: "..."}}
                const orgName = orgData.organization?.name || user.org_id;
                filterOrgName.textContent = orgName;
            } catch (orgError) {
                // If org fetch fails, fall back to org_id
                filterOrgName.textContent = user.org_id;
            }
        } else {
            filterOrgName.textContent = '조직 없음';
        }
    } catch (error) {
        logger.error('Failed to load organization info:', error);
        filterOrgName.textContent = '로드 실패';
    }
}

/**
 * Load Hybrid RAG status
 */
async function loadHybridRagStatus() {
    try {
        // Check if user is authenticated first
        if (!Auth.isAuthenticated()) {
            logger.debug('Skipping Hybrid RAG status load - user not authenticated');
            isHybridRagEnabled = false;
            return;
        }

        const data = await Auth.apiCall('/api/hybrid-rag/status');
        if (data.success) {
            isHybridRagEnabled = data.enabled;
            logger.info(`✅ Hybrid RAG status loaded: ${isHybridRagEnabled ? 'enabled' : 'disabled'}`);
        }
    } catch (error) {
        logger.error('Failed to load Hybrid RAG status:', error);
        // Default to false on error
        isHybridRagEnabled = false;
    }
}

/**
 * Load groups into filter panel
 */
async function loadGroupsIntoFilter() {
    try {
        // Check if groupManager exists (may not be initialized if elements are missing)
        if (!groupManager) {
            logger.warn('Group manager not initialized - skipping group filter load');
            return;
        }

        // Load groups with user filter scope to enforce organization filtering
        await groupManager.loadGroups('user');
        const groupFilterList = document.getElementById('groupFilterList');

        if (groupFilterList && groupFilter) {
            groupFilter.renderGroupSelector(groupFilterList);

            // Setup filter change handler
            groupFilter.onFilterChanged = (selectedGroupIds) => {
                // Auto-select appropriate radio button based on group selection
                const selectedRadio = document.querySelector('input[name="groupFilterMode"][value="selected"]');
                const allRadio = document.querySelector('input[name="groupFilterMode"][value="all"]');

                if (selectedGroupIds && selectedGroupIds.length > 0) {
                    // Groups are selected -> auto-select "선택한 그룹만"
                    if (selectedRadio) selectedRadio.checked = true;
                } else {
                    // No groups selected -> auto-select "전체 그룹"
                    if (allRadio) allRadio.checked = true;
                }

                // Update tab counts
                updateFilterTabCounts();
                // Filter will be applied when user sends a query
            };

            // Update counts after loading groups
            updateFilterTabCounts();
        }
    } catch (error) {
        logger.error('Failed to load groups into filter:', error);
    }
}

/**
 * Load group tree in management modal
 */
async function loadGroupTree() {
    try {
        await groupManager.loadGroups();
        const groupTree = document.getElementById('groupTree');

        if (groupTree) {
            groupManager.renderTree(groupTree, {
                onSelect: handleGroupSelect,
                onEdit: handleGroupEdit,
                onDelete: handleGroupDelete,
                selectedGroupId: selectedGroupForEdit,
                showDocumentCount: true
            });
        }
    } catch (error) {
        logger.error('Failed to load group tree:', error);
    }
}

/**
 * Handle group selection in tree
 */
function handleGroupSelect(groupId) {
    selectedGroupForEdit = groupId;
    const group = groupManager.findGroup(groupId);

    if (group) {
        // Show group details panel
        document.getElementById('groupDetailsEmpty').style.display = 'none';
        document.getElementById('groupDetailsContent').style.display = 'block';

        // Populate form fields
        document.getElementById('groupNameInput').value = group.name;
        document.getElementById('groupDescInput').value = group.description || '';
        document.getElementById('groupColorInput').value = group.color;
        document.getElementById('groupIconInput').value = group.icon;
        document.getElementById('groupDocCount').textContent = group.document_count || 0;

        // Load documents for this group
        loadGroupDocuments(groupId);

        // Reload tree to show selection
        loadGroupTree();
    }
}

/**
 * Handle group edit button click
 */
function handleGroupEdit(groupId) {
    handleGroupSelect(groupId);
}

/**
 * Handle group update form submit
 */
async function handleGroupUpdate() {
    if (!selectedGroupForEdit) return;

    try {
        const updates = {
            name: document.getElementById('groupNameInput').value,
            description: document.getElementById('groupDescInput').value,
            color: document.getElementById('groupColorInput').value,
            icon: document.getElementById('groupIconInput').value
        };

        await groupManager.updateGroup(selectedGroupForEdit, updates);
        await loadGroupTree();
        await loadGroupsIntoFilter();

        alert('그룹이 업데이트되었습니다.');
    } catch (error) {
        logger.error('Failed to update group:', error);
        alert('그룹 업데이트 실패: ' + error.message);
    }
}

/**
 * Handle group deletion
 */
async function handleGroupDelete() {
    if (!selectedGroupForEdit) return;

    const group = groupManager.findGroup(selectedGroupForEdit);
    if (!group) return;

    if (!confirm(`"${group.name}" 그룹을 삭제하시겠습니까?\n그룹의 문서는 부모 그룹으로 이동됩니다.`)) {
        return;
    }

    try {
        await groupManager.deleteGroup(selectedGroupForEdit);

        // Reset selection
        selectedGroupForEdit = null;
        document.getElementById('groupDetailsEmpty').style.display = 'block';
        document.getElementById('groupDetailsContent').style.display = 'none';

        await loadGroupTree();
        await loadGroupsIntoFilter();

        alert('그룹이 삭제되었습니다.');
    } catch (error) {
        logger.error('Failed to delete group:', error);
        alert('그룹 삭제 실패: ' + error.message);
    }
}

/**
 * Handle group creation
 */
async function handleGroupCreate() {
    try {
        const groupData = {
            name: document.getElementById('newGroupName').value,
            description: document.getElementById('newGroupDesc').value,
            color: document.getElementById('newGroupColor').value,
            icon: document.getElementById('newGroupIcon').value,
            parent_id: document.getElementById('newGroupParent').value || null
        };

        await groupManager.createGroup(groupData);

        // Close modal and reset form
        const createModal = document.getElementById('groupCreateModal');
        createModal.classList.remove('active');
        popModal(createModal);
        document.getElementById('groupCreateForm').reset();

        // Reload trees
        await loadGroupTree();
        await loadGroupsIntoFilter();

        alert('그룹이 생성되었습니다.');
    } catch (error) {
        logger.error('Failed to create group:', error);
        alert('그룹 생성 실패: ' + error.message);
    }
}

/**
 * Populate parent group select dropdown
 */
function populateParentGroupSelect() {
    const select = document.getElementById('newGroupParent');
    if (!select) return;

    // Clear existing options except first
    while (select.options.length > 1) {
        select.remove(1);
    }

    // Add all groups as options
    groupManager.groups.forEach(group => {
        const option = document.createElement('option');
        option.value = group.id;
        option.textContent = `${group.icon} ${group.name}`;
        select.appendChild(option);
    });
}

/**
 * Load documents for a group
 */
async function loadGroupDocuments(groupId) {
    try {
        const documents = await groupManager.getGroupDocuments(groupId);
        const listContainer = document.getElementById('groupDocumentsList');

        if (!listContainer) return;

        if (documents.length === 0) {
            listContainer.innerHTML = '<div class="empty-state">할당된 문서가 없습니다</div>';
        } else {
            listContainer.innerHTML = documents.map(doc => `
                <div class="assigned-document-item">
                    <span class="assigned-document-name">${doc}</span>
                    <button class="remove-document-btn" data-filename="${doc}" data-group-id="${groupId}" title="그룹에서 제거">🗑️</button>
                </div>
            `).join('');

            // Add event listeners to remove buttons
            listContainer.querySelectorAll('.remove-document-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const filename = e.target.dataset.filename;
                    const groupId = e.target.dataset.groupId;

                    if (confirm(`"${filename}" 문서를 이 그룹에서 제거하시겠습니까?\n(문서는 기본 그룹으로 이동됩니다)`)) {
                        try {
                            await groupManager.removeDocumentFromGroup(filename, groupId);
                            // Reload group documents and update count
                            await loadGroupDocuments(groupId);
                            updateGroupDocCount(groupId);

                            // Reload group tree to update document counts in group list
                            await loadGroupTree();

                            // Reload the assignable document list to prevent duplicates
                            await loadAllDocumentsForAssign();

                            // Update search filter to reflect document count changes
                            await loadGroupsIntoFilter();

                            showNotification('문서가 기본 그룹으로 이동되었습니다.', 'success');
                        } catch (error) {
                            showNotification('문서 제거에 실패했습니다: ' + error.message, 'error');
                        }
                    }
                });
            });
        }

        // Load all documents into the assign select
        await loadAllDocumentsForAssign();
    } catch (error) {
        logger.error('Failed to load group documents:', error);
    }
}

/**
 * Update group document count in UI
 */
async function updateGroupDocCount(groupId) {
    try {
        const group = groupManager.findGroup(groupId);
        if (group) {
            const countElement = document.getElementById('groupDocCount');
            if (countElement) {
                countElement.textContent = group.document_count || 0;
            }
        }
    } catch (error) {
        logger.error('Failed to update group doc count:', error);
    }
}

/**
 * Load all documents for assignment dropdown
 */
async function loadAllDocumentsForAssign() {
    try {
        const data = await Auth.apiCall('/api/documents');

        const select = document.getElementById('documentSelectForAssign');
        if (!select) return;

        select.innerHTML = '';

        // Get currently assigned documents for the selected group
        let assignedDocs = [];
        if (selectedGroupForEdit) {
            try {
                assignedDocs = await groupManager.getGroupDocuments(selectedGroupForEdit);
            } catch (error) {
                logger.error('Failed to load assigned documents:', error);
            }
        }

        if (data.documents && data.documents.length > 0) {
            // Filter out documents already assigned to the current group
            const availableDocs = data.documents.filter(doc => !assignedDocs.includes(doc.filename));

            if (availableDocs.length > 0) {
                availableDocs.forEach(doc => {
                    const option = document.createElement('option');
                    option.value = doc.filename;
                    option.textContent = doc.filename;
                    select.appendChild(option);
                });
            } else {
                select.innerHTML = '<option>할당 가능한 문서가 없습니다</option>';
            }
        } else {
            select.innerHTML = '<option>문서가 없습니다</option>';
        }
    } catch (error) {
        logger.error('Failed to load documents:', error);
    }
}

/**
 * Handle document assignment
 */
async function handleDocumentAssign() {
    if (!selectedGroupForEdit) {
        alert('그룹을 먼저 선택해주세요.');
        return;
    }

    const select = document.getElementById('documentSelectForAssign');
    const selectedDocs = Array.from(select.selectedOptions).map(opt => opt.value);

    if (selectedDocs.length === 0) {
        alert('할당할 문서를 선택해주세요.');
        return;
    }

    try {
        await groupManager.batchAssignDocuments(selectedDocs, selectedGroupForEdit);
        await loadGroupDocuments(selectedGroupForEdit);
        await loadGroupTree(); // Refresh to update document counts

        // Reload the assignable document list to update available documents
        await loadAllDocumentsForAssign();

        // Update search filter to reflect document count changes
        await loadGroupsIntoFilter();

        alert(`${selectedDocs.length}개 문서가 할당되었습니다.`);
    } catch (error) {
        logger.error('Failed to assign documents:', error);
        alert('문서 할당 실패: ' + error.message);
    }
}

// ============================================
// Admin Dashboard - Security Logs
// ============================================

let currentLogsPage = 0;
const logsPerPage = 50;
let currentLogFilters = {
    level: '',
    event_type: ''
};

// ============================================================================
// v2.3.0: Document Version Management
// ============================================================================

// Show version management modal
async function showVersionModal(filename) {
    const modal = document.getElementById('versionModal');
    const filenameElement = document.getElementById('versionFilename');
    const versionsList = document.getElementById('versionsList');

    if (!modal || !filenameElement || !versionsList) {
        logger.error('Version modal elements not found');
        return;
    }

    // Set filename
    filenameElement.textContent = filename;

    // Show modal
    modal.classList.add('active');
    pushModal(modal, 'version');

    // Load versions
    await loadVersions(filename);
}

// Load versions for a document
async function loadVersions(filename) {
    const versionsList = document.getElementById('versionsList');
    const versionsCount = document.getElementById('versionsCount');

    versionsList.innerHTML = '<div class="loading">버전 목록을 불러오는 중...</div>';

    try {
        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/versions`);

        if (!response.ok) {
            throw new Error(`Failed to fetch versions: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.versions || data.versions.length === 0) {
            versionsList.innerHTML = `
                <div class="empty-state">
                    <p>버전 이력이 없습니다</p>
                    <p class="hint-text">파일을 업로드하면 첫 번째 버전이 생성됩니다</p>
                </div>
            `;
            versionsCount.textContent = '버전 0개';
            return;
        }

        // Update count
        versionsCount.textContent = `총 ${data.total_count}개 버전`;

        // Render versions (newest first)
        versionsList.innerHTML = data.versions.map((ver, index) => `
            <div class="version-item ${index === 0 ? 'latest-version' : ''}">
                <div class="version-header">
                    <div class="version-info">
                        <span class="version-number">v${ver.version}</span>
                        ${index === 0 ? '<span class="version-badge">최신</span>' : ''}
                        <span class="version-date">${formatDateTime(ver.created_at)}</span>
                    </div>
                    <div class="version-actions">
                        ${index !== 0 ? `
                            <button class="version-action-btn" onclick="restoreVersion('${filename.replace(/'/g, "\\'")}', ${ver.version})" title="이 버전으로 복원">
                                ↩️ 복원
                            </button>
                            <button class="version-action-btn" onclick="compareVersions('${filename.replace(/'/g, "\\'")}', ${ver.version}, ${data.versions[0].version})" title="최신 버전과 비교">
                                🔍 비교
                            </button>
                        ` : `
                            <span class="version-action-placeholder"></span>
                            <span class="version-action-placeholder"></span>
                        `}
                        ${data.versions.length > 1 ? `
                            <button class="version-action-btn delete" onclick="deleteVersion('${filename.replace(/'/g, "\\'")}', ${ver.version})" title="이 버전 삭제">
                                🗑️ 삭제
                            </button>
                        ` : ''}
                    </div>
                </div>
                <div class="version-meta">
                    <span class="version-meta-item">📊 ${(ver.file_size / 1024 / 1024).toFixed(2)} MB</span>
                    <span class="version-meta-item">📦 ${ver.chunk_count} 청크</span>
                    <span class="version-meta-item">👤 ${ver.created_by === 'system' ? '시스템' : ver.created_by}</span>
                    ${ver.comment ? `<span class="version-meta-item">💬 ${ver.comment}</span>` : ''}
                </div>
            </div>
        `).join('');

    } catch (error) {
        logger.error('Error loading versions:', error);
        versionsList.innerHTML = `
            <div class="empty-state">
                <p>버전 목록을 불러오는데 실패했습니다</p>
                <p class="hint-text">${error.message}</p>
            </div>
        `;
        versionsCount.textContent = '';
    }
}

// Restore a specific version
async function restoreVersion(filename, version) {
    if (!confirm(`"${filename}" 파일을 버전 ${version}으로 복원하시겠습니까?\n\n현재 파일이 이 버전의 내용으로 대체되며, 새로운 버전이 생성됩니다.`)) {
        return;
    }

    const modal = document.getElementById('versionModal');
    const versionsList = document.getElementById('versionsList');

    // Show loading state
    versionsList.innerHTML = '<div class="loading">버전을 복원하는 중...</div>';

    try {
        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/versions/${version}/restore`, {
            method: 'POST'
        });

        const result = await response.json();

        if (response.ok) {
            showUploadStatus(`✓ 버전 ${version}으로 복원 완료`, 'success');

            // Close modal
            modal.classList.remove('active');

            // Reload documents list
            loadDocuments();
            checkStatus();
        } else {
            showUploadStatus(`✗ 복원 실패: ${result.detail}`, 'error');
            // Reload versions to reset UI
            await loadVersions(filename);
        }
    } catch (error) {
        showUploadStatus(`✗ 복원 실패: ${error.message}`, 'error');
        await loadVersions(filename);
    }
}

// Compare two versions
async function compareVersions(filename, version1, version2) {
    try {
        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/versions/compare?version1=${version1}&version2=${version2}`);

        if (!response.ok) {
            throw new Error(`Failed to compare versions: ${response.statusText}`);
        }

        const comparison = await response.json();

        // Show comparison modal
        showComparisonModal(comparison);

    } catch (error) {
        logger.error('Error comparing versions:', error);
        showUploadStatus(`✗ 비교 실패: ${error.message}`, 'error');
    }
}

// Show version comparison modal
function showComparisonModal(comparison) {
    const modal = document.getElementById('comparisonModal');
    const content = document.getElementById('comparisonContent');

    if (!modal || !content) {
        logger.error('Comparison modal elements not found');
        return;
    }

    const v1 = comparison.version1;
    const v2 = comparison.version2;
    const diff = comparison.differences;

    content.innerHTML = `
        <div class="comparison-header">
            <h3>${comparison.filename} 버전 비교</h3>
        </div>

        <div class="comparison-grid">
            <div class="comparison-column">
                <h4>버전 ${v1.version}</h4>
                <div class="version-details">
                    <div class="detail-row">
                        <span class="detail-label">생성일:</span>
                        <span class="detail-value">${formatDateTime(v1.created_at)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">파일 크기:</span>
                        <span class="detail-value">${(v1.file_size / 1024 / 1024).toFixed(2)} MB</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">청크 수:</span>
                        <span class="detail-value">${v1.chunk_count}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">해시:</span>
                        <span class="detail-value mono">${v1.file_hash.substring(0, 16)}...</span>
                    </div>
                    ${v1.comment ? `
                    <div class="detail-row">
                        <span class="detail-label">설명:</span>
                        <span class="detail-value">${v1.comment}</span>
                    </div>
                    ` : ''}
                </div>
            </div>

            <div class="comparison-column">
                <h4>버전 ${v2.version}</h4>
                <div class="version-details">
                    <div class="detail-row">
                        <span class="detail-label">생성일:</span>
                        <span class="detail-value">${formatDateTime(v2.created_at)}</span>
                    </div>
                    <div class="detail-row ${diff.size_changed ? 'changed' : ''}">
                        <span class="detail-label">파일 크기:</span>
                        <span class="detail-value">
                            ${(v2.file_size / 1024 / 1024).toFixed(2)} MB
                            ${diff.size_changed ? `<span class="diff-badge">${diff.size_diff > 0 ? '+' : ''}${(diff.size_diff / 1024 / 1024).toFixed(2)} MB</span>` : ''}
                        </span>
                    </div>
                    <div class="detail-row ${diff.chunk_count_diff !== 0 ? 'changed' : ''}">
                        <span class="detail-label">청크 수:</span>
                        <span class="detail-value">
                            ${v2.chunk_count}
                            ${diff.chunk_count_diff !== 0 ? `<span class="diff-badge">${diff.chunk_count_diff > 0 ? '+' : ''}${diff.chunk_count_diff}</span>` : ''}
                        </span>
                    </div>
                    <div class="detail-row ${diff.content_changed ? 'changed' : ''}">
                        <span class="detail-label">해시:</span>
                        <span class="detail-value mono">
                            ${v2.file_hash.substring(0, 16)}...
                            ${diff.content_changed ? '<span class="diff-badge">변경됨</span>' : '<span class="diff-badge same">동일</span>'}
                        </span>
                    </div>
                    ${v2.comment ? `
                    <div class="detail-row">
                        <span class="detail-label">설명:</span>
                        <span class="detail-value">${v2.comment}</span>
                    </div>
                    ` : ''}
                </div>
            </div>
        </div>

        <div class="comparison-summary">
            <h4>변경 사항 요약</h4>
            <div class="summary-list">
                <div class="summary-item ${diff.content_changed ? 'changed' : 'unchanged'}">
                    <span class="summary-label">파일 내용</span>
                    <span class="summary-value">${diff.content_changed ? '변경됨' : '동일함'}</span>
                </div>
                ${diff.size_changed ? `
                <div class="summary-item changed">
                    <span class="summary-label">파일 크기</span>
                    <span class="summary-value">${diff.size_diff > 0 ? '↗' : '↘'} ${diff.size_diff > 0 ? '+' : ''}${(diff.size_diff / 1024 / 1024).toFixed(2)} MB</span>
                </div>` : ''}
                ${diff.chunk_count_diff !== 0 ? `
                <div class="summary-item changed">
                    <span class="summary-label">청크 수</span>
                    <span class="summary-value">${diff.chunk_count_diff > 0 ? '↗' : '↘'} ${diff.chunk_count_diff > 0 ? '+' : ''}${diff.chunk_count_diff}</span>
                </div>` : ''}
            </div>
        </div>
    `;

    modal.classList.add('active');
    pushModal(modal, 'comparison');
}

// Delete a specific version
async function deleteVersion(filename, version) {
    // Check authentication (required to delete versions)
    const token = localStorage.getItem('access_token');
    if (!token) {
        showUploadStatus('✗ 로그인이 필요합니다', 'error');
        return;
    }

    if (!confirm(`"${filename}" 파일의 버전 ${version}을 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/versions/${version}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const result = await response.json();

        if (response.ok) {
            showUploadStatus(`✓ 버전 ${version} 삭제 완료`, 'success');
            // Reload versions
            await loadVersions(filename);
        } else {
            showUploadStatus(`✗ 삭제 실패: ${result.detail}`, 'error');
        }
    } catch (error) {
        showUploadStatus(`✗ 삭제 실패: ${error.message}`, 'error');
    }
}

// Initialize version management and export modals
function initVersionManagement() {
    const versionModal = document.getElementById('versionModal');
    const closeVersionModal = document.getElementById('closeVersionModal');
    const comparisonModal = document.getElementById('comparisonModal');
    const closeComparisonModal = document.getElementById('closeComparisonModal');
    const exportModal = document.getElementById('exportModal');
    const closeExportModal = document.getElementById('closeExportModal');

    // Close version modal handlers
    if (closeVersionModal) {
        closeVersionModal.addEventListener('click', () => {
            versionModal.classList.remove('active');
            popModal(versionModal);
        });
    }

    if (versionModal) {
        versionModal.addEventListener('click', (e) => {
            if (e.target === versionModal) {
                versionModal.classList.remove('active');
                popModal(versionModal);
            }
        });
    }

    // Close comparison modal handlers
    if (closeComparisonModal) {
        closeComparisonModal.addEventListener('click', () => {
            comparisonModal.classList.remove('active');
            popModal(comparisonModal);
        });
    }

    if (comparisonModal) {
        comparisonModal.addEventListener('click', (e) => {
            if (e.target === comparisonModal) {
                comparisonModal.classList.remove('active');
                popModal(comparisonModal);
            }
        });
    }

    // Close export modal handlers
    if (closeExportModal) {
        closeExportModal.addEventListener('click', () => {
            exportModal.classList.remove('active');
            popModal(exportModal);
        });
    }

    if (exportModal) {
        exportModal.addEventListener('click', (e) => {
            if (e.target === exportModal) {
                exportModal.classList.remove('active');
                popModal(exportModal);
            }
        });
    }
}

// Initialize admin dashboard
function initAdminDashboard() {
    const adminModal = document.getElementById('adminModal');
    const closeAdminModal = document.getElementById('closeAdminModal');
    const applyLogFilters = document.getElementById('applyLogFilters');
    const refreshLogs = document.getElementById('refreshLogs');
    const prevLogsPage = document.getElementById('prevLogsPage');
    const nextLogsPage = document.getElementById('nextLogsPage');

    if (!adminModal) return;

    // Close modal handlers
    closeAdminModal?.addEventListener('click', () => {
        adminModal.classList.remove('active');
        popModal(adminModal);
    });

    adminModal.addEventListener('click', (e) => {
        if (e.target === adminModal) {
            adminModal.classList.remove('active');
            popModal(adminModal);
        }
    });

    // Filter handlers
    applyLogFilters?.addEventListener('click', () => {
        currentLogFilters.level = document.getElementById('logLevelFilter').value;
        currentLogFilters.event_type = document.getElementById('logEventTypeFilter').value;
        currentLogsPage = 0;
        loadSecurityLogs();
    });

    refreshLogs?.addEventListener('click', () => {
        loadSecurityLogs();
    });

    // Pagination handlers
    prevLogsPage?.addEventListener('click', () => {
        if (currentLogsPage > 0) {
            currentLogsPage--;
            loadSecurityLogs();
        }
    });

    nextLogsPage?.addEventListener('click', () => {
        currentLogsPage++;
        loadSecurityLogs();
    });
}

// Open admin dashboard
async function goToAdmin() {
    const adminModal = document.getElementById('adminModal');
    if (!adminModal) return;

    adminModal.classList.add('active');
    pushModal(adminModal, 'admin');
    await loadSecurityLogs();
}

// Load security logs
async function loadSecurityLogs() {
    const logsTableBody = document.getElementById('logsTableBody');
    const prevBtn = document.getElementById('prevLogsPage');
    const nextBtn = document.getElementById('nextLogsPage');
    const paginationInfo = document.getElementById('logsPaginationInfo');

    if (!logsTableBody) return;

    logsTableBody.innerHTML = '<tr><td colspan="6" class="loading">로그를 불러오는 중...</td></tr>';

    try {
        const params = new URLSearchParams({
            limit: logsPerPage.toString(),
            offset: (currentLogsPage * logsPerPage).toString()
        });

        if (currentLogFilters.level) {
            params.append('level', currentLogFilters.level);
        }
        if (currentLogFilters.event_type) {
            params.append('event_type', currentLogFilters.event_type);
        }

        const token = sessionStorage.getItem('access_token');
        const response = await fetch(`/api/auth/admin/security-logs?${params}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to load security logs');
        }

        const data = await response.json();

        if (!data.logs || data.logs.length === 0) {
            logsTableBody.innerHTML = '<tr><td colspan="6" class="loading">로그가 없습니다.</td></tr>';
            prevBtn.disabled = true;
            nextBtn.disabled = true;
            paginationInfo.textContent = '페이지 1';
            return;
        }

        // Render logs
        logsTableBody.innerHTML = '';
        data.logs.forEach(log => {
            const row = document.createElement('tr');

            // Format timestamp
            const timestamp = new Date(log.timestamp).toLocaleString('ko-KR');

            // Event type translation
            const eventTypeMap = {
                'AUTH_LOGIN_SUCCESS': '로그인 성공',
                'AUTH_LOGIN_FAILED': '로그인 실패',
                'AUTH_LOGOUT': '로그아웃',
                'RATE_LIMIT_EXCEEDED': 'Rate Limit 초과',
                'BRUTE_FORCE_ATTEMPT': 'Brute Force 시도',
                'UNAUTHORIZED_ACCESS': '무단 접근',
                'TOKEN_ISSUED': '토큰 발급',
                'TOKEN_INVALID': '유효하지 않은 토큰',
                'TOKEN_EXPIRED': '토큰 만료',
                'ACCOUNT_LOCKED': '계정 잠금',
                'PERMISSION_DENIED': '권한 거부'
            };
            const eventTypeText = eventTypeMap[log.event_type] || log.event_type;

            row.innerHTML = `
                <td>${timestamp}</td>
                <td><span class="log-level ${log.level}">${log.level}</span></td>
                <td>${eventTypeText}</td>
                <td>${log.user_id === 'anonymous' ? '익명' : log.user_id.substring(0, 8) + '...'}</td>
                <td>${log.ip_address}</td>
                <td>${log.message}</td>
            `;

            logsTableBody.appendChild(row);
        });

        // Update pagination
        const currentPageNum = currentLogsPage + 1;
        const totalPages = Math.ceil(data.total_count / logsPerPage);
        paginationInfo.textContent = `페이지 ${currentPageNum} / ${totalPages} (총 ${data.total_count}개)`;

        prevBtn.disabled = currentLogsPage === 0;
        nextBtn.disabled = (currentLogsPage + 1) * logsPerPage >= data.total_count;

    } catch (error) {
        logger.error('Failed to load security logs:', error);
        logsTableBody.innerHTML = '<tr><td colspan="6" class="loading">로그 로딩 실패: ' + escapeHtml(error.message) + '</td></tr>';
    }
}

// Start application when DOM is ready
// ===== User Preferences Management =====

/**
 * Load user preferences from server
 */
async function loadUserPreferences() {
    // Check if user is authenticated
    if (!Auth || !Auth.isAuthenticated()) {
        devLog('⏭️ 로그인하지 않음 - 설정 로드 건너뛰기');
        return null;
    }

    try {
        const result = await Auth.apiCall('/api/user/preferences', {
            method: 'GET'
        });

        if (result && result.data) {
            const preferences = result.data;
            devLog('📋 사용자 설정 로드:', preferences);

            // Apply preferences to UI
            applyUserPreferences(preferences);

            return preferences;
        }
    } catch (error) {
        // Silently ignore preference loading errors (non-critical)
        // This can happen during page navigation or token expiration
        devLog('⚠️ 사용자 설정 로드 실패 (무시됨):', error.message);
    }
    return null;
}

/**
 * Apply loaded preferences to UI
 */
function applyUserPreferences(preferences) {
    if (!preferences) return;

    // Apply active filter tab
    if (preferences.active_filter_tab) {
        const tabButton = document.querySelector(`.filter-tab[data-tab="${preferences.active_filter_tab}"]`);
        if (tabButton) {
            tabButton.click();
        }
    }

    // Apply group filter mode
    if (preferences.group_filter_mode) {
        const radioButton = document.querySelector(`input[name="groupFilterMode"][value="${preferences.group_filter_mode}"]`);
        if (radioButton) {
            radioButton.checked = true;
        }
    }

    // Apply selected document IDs
    if (preferences.selected_document_ids && preferences.selected_document_ids.length > 0) {
        // Wait for document filter to be initialized
        setTimeout(() => {
            if (window.selectedDocumentIds) {
                window.selectedDocumentIds.clear();
                preferences.selected_document_ids.forEach(id => {
                    window.selectedDocumentIds.add(id);
                });

                // Update UI checkboxes
                preferences.selected_document_ids.forEach(id => {
                    const checkbox = document.querySelector(`input[type="checkbox"][value="${id}"]`);
                    if (checkbox) {
                        checkbox.checked = true;
                    }
                });

                // Update filter mode radio to "selected" if documents are selected
                if (preferences.selected_document_ids.length > 0) {
                    const selectedModeRadio = document.querySelector('input[name="filterMode"][value="selected"]');
                    if (selectedModeRadio) {
                        selectedModeRadio.checked = true;
                    }
                }

                updateFilterTabCounts();
                devLog('✅ 선택된 문서 복원:', preferences.selected_document_ids.length);
            }
        }, 500);
    }

    // Apply selected group IDs
    if (preferences.selected_group_ids && preferences.selected_group_ids.length > 0) {
        // Wait for group filter to be initialized
        setTimeout(() => {
            if (groupFilter && typeof groupFilter.selectGroups === 'function') {
                groupFilter.selectGroups(preferences.selected_group_ids);
                devLog('✅ 선택된 그룹 복원:', preferences.selected_group_ids.length);
            }
        }, 1000);
    }
}

/**
 * Save user preferences to server
 */
async function saveUserPreferences() {
    // Check if user is authenticated
    if (!Auth || !Auth.isAuthenticated()) {
        return false;
    }

    try {
        // Gather current preferences
        const activeTab = document.querySelector('.filter-tab.active')?.dataset.tab || 'documents';
        const groupFilterMode = document.querySelector('input[name="groupFilterMode"]:checked')?.value || 'all';

        const selectedDocIds = window.selectedDocumentIds ? Array.from(window.selectedDocumentIds) : [];
        const selectedGrpIds = groupFilter && typeof groupFilter.getSelectedGroups === 'function'
            ? groupFilter.getSelectedGroups()
            : [];

        const preferences = {
            search_scope: "all",  // Legacy field
            selected_document_ids: selectedDocIds,
            selected_group_ids: selectedGrpIds,
            active_filter_tab: activeTab,
            group_filter_mode: groupFilterMode
        };

        const result = await Auth.apiCall('/api/user/preferences', {
            method: 'PUT',
            body: JSON.stringify(preferences)
        });

        if (result && result.success) {
            devLog('✅ 사용자 설정 저장 완료');
            return true;
        }
    } catch (error) {
        logger.error('사용자 설정 저장 실패:', error);
    }
    return false;
}

/**
 * Setup auto-save for preferences
 */
function setupPreferencesAutoSave() {
    // Save preferences when filter changes
    const filterTabButtons = document.querySelectorAll('.filter-tab');
    filterTabButtons.forEach(button => {
        button.addEventListener('click', () => {
            setTimeout(saveUserPreferences, 500);
        });
    });

    // Save when document filter mode changes (전체 문서 / 선택한 문서만)
    const documentFilterRadios = document.querySelectorAll('input[name="filterMode"]');
    documentFilterRadios.forEach(radio => {
        radio.addEventListener('change', saveUserPreferences);
    });

    // Save when group filter mode changes
    const groupFilterRadios = document.querySelectorAll('input[name="groupFilterMode"]');
    groupFilterRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            // When "전체 그룹" (all) is selected, clear all individual group selections
            if (e.target.value === 'all' && groupFilter) {
                // Clear selected group IDs in the filter
                groupFilter.clearSelection();

                // Uncheck all group checkboxes in the UI
                const groupCheckboxes = document.querySelectorAll('.filter-group-checkbox');
                groupCheckboxes.forEach(checkbox => {
                    checkbox.checked = false;
                });

                devLog('✅ 전체 그룹 선택 - 개별 그룹 선택 해제');
            }

            saveUserPreferences();
        });
    });

    // Save when document selection changes
    // (Will be triggered by document filter checkbox changes)
    const documentFilterPanel = document.getElementById('filterDocumentList');
    if (documentFilterPanel) {
        documentFilterPanel.addEventListener('change', (e) => {
            if (e.target.type === 'checkbox') {
                setTimeout(saveUserPreferences, 300);
            }
        });
    }

    devLog('✅ 설정 자동 저장 설정 완료');
}

// ============================================================================
// Document Download Functions
// ============================================================================

/**
 * Download original document file
 */
async function downloadDocument(filename, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    try {
        const token = localStorage.getItem('access_token');
        if (!token) {
            showError('로그인이 필요합니다.');
            return;
        }

        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/download`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: '다운로드 실패' }));
            throw new Error(errorData.detail || '다운로드 실패');
        }

        // Create blob and download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showSuccess(`${filename} 다운로드 완료`);
    } catch (error) {
        logger.error('Download error:', error);
        showError(error.message || '파일 다운로드 중 오류가 발생했습니다.');
    }
}

/**
 * Download document as PDF (convert if needed)
 */
async function downloadDocumentAsPDF(filename, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    try {
        const token = localStorage.getItem('access_token');
        if (!token) {
            showError('로그인이 필요합니다.');
            return;
        }

        // Show loading indicator
        const originalFilename = filename;
        const pdfFilename = filename.replace(/\.[^.]+$/, '.pdf');

        showInfo(`${originalFilename} PDF 변환 중...`);

        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/download-pdf`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'PDF 다운로드 실패' }));

            // If PDF conversion not available, suggest original download
            if (response.status === 400) {
                const shouldDownloadOriginal = confirm(
                    `${errorData.detail || 'PDF 변환이 지원되지 않습니다.'}\n\n원본 파일을 다운로드하시겠습니까?`
                );
                if (shouldDownloadOriginal) {
                    await downloadDocument(filename, event);
                }
                return;
            }

            throw new Error(errorData.detail || 'PDF 다운로드 실패');
        }

        // Create blob and download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = pdfFilename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showSuccess(`${pdfFilename} 다운로드 완료`);
    } catch (error) {
        logger.error('PDF download error:', error);
        showError(error.message || 'PDF 다운로드 중 오류가 발생했습니다.');
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', async () => {
        const startTime = performance.now();

        // Phase 1: Core initialization (must complete first)
        await init();

        // Phase 2: Parallel initialization of independent modules
        const results = await Promise.allSettled([
            initDocumentFilter(),
            initGroupManagement(),
            initConversationHistory(),
            initAdminDashboard(),
            initVersionManagement(),
            loadHybridRagStatus()
        ]);

        // Log initialization results
        const moduleNames = ['DocumentFilter', 'GroupManagement', 'ConversationHistory', 'AdminDashboard', 'VersionManagement', 'HybridRagStatus'];
        results.forEach((result, index) => {
            if (result.status === 'rejected') {
                logger.error(`❌ ${moduleNames[index]} initialization failed:`, result.reason);
            } else {
                logger.info(`✅ ${moduleNames[index]} initialized successfully`);
            }
        });

        const initTime = performance.now() - startTime;
        logger.info(`✅ Initialization complete in ${initTime.toFixed(2)}ms`);

        // Load and setup user preferences (after other init)
        // Wait a bit longer to ensure all filters are fully loaded
        setTimeout(async () => {
            await loadUserPreferences();
            setupPreferencesAutoSave();
        }, 1500);
    });
} else {
    // DOM already loaded
    (async () => {
        const startTime = performance.now();

        // Phase 1: Core initialization (must complete first)
        await init();

        // Phase 2: Parallel initialization of independent modules
        const results = await Promise.allSettled([
            initDocumentFilter(),
            initGroupManagement(),
            initConversationHistory(),
            initAdminDashboard(),
            initVersionManagement(),
            loadHybridRagStatus()
        ]);

        // Log initialization results
        const moduleNames = ['DocumentFilter', 'GroupManagement', 'ConversationHistory', 'AdminDashboard', 'VersionManagement', 'HybridRagStatus'];
        results.forEach((result, index) => {
            if (result.status === 'rejected') {
                logger.error(`❌ ${moduleNames[index]} initialization failed:`, result.reason);
            } else {
                logger.info(`✅ ${moduleNames[index]} initialized successfully`);
            }
        });

        const initTime = performance.now() - startTime;
        logger.info(`✅ Initialization complete in ${initTime.toFixed(2)}ms`);

        // Load and setup user preferences (after other init)
        // Wait a bit longer to ensure all filters are fully loaded
        setTimeout(async () => {
            await loadUserPreferences();
            setupPreferencesAutoSave();
        }, 1500);
    })();
}
