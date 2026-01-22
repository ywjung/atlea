// ASCII art detection function (shared between renderer and highlighter)
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

// DOM elements
const chatContainer = document.getElementById('chatContainer');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
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
            max_tokens: Math.max(1, Math.min(8192, parseInt(currentSettings.max_tokens) || 2048)),
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
            60000 // 60 second timeout (increased for LLM response generation)
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

        let sources = null;
        let fullText = '';
        let tokenCount = 0;
        let tokenStats = null;  // Store token generation statistics
        let isFirstChunk = true;  // Track first chunk to hide progress indicator

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

                            // Update token count (approximate by splitting on spaces)
                            tokenCount = fullText.split(/\s+/).filter(w => w.length > 0).length;

                            // Server already filters <think> tags, so just render
                            try {
                                contentDiv.innerHTML = marked.parse(fullText);

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
                        } else if (data.type === 'done') {
                            // Calculate response time
                            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

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

                            // Generate and display follow-up questions
                            try {
                                const followUpQs = await followUpQuestions.generate(question, fullText, [], currentSessionId);
                                if (followUpQs && followUpQs.length > 0) {
                                    followUpQuestions.display(contentDiv, followUpQs, (selectedQuestion) => {
                                        // When user clicks a follow-up question, populate input and send
                                        userInput.value = selectedQuestion;
                                        autoResize();
                                        updateSendButton();
                                        sendMessage();
                                    });
                                }
                            } catch (error) {
                                logger.error('Failed to generate/display follow-up questions:', error);
                            }
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
        } else {
            // Show error message with retry option if available
            errorHandler.showErrorMessage(errorInfo, errorInfo.canRetry);
        }
    } finally {
        isLoading = false;
        currentAbortController = null;
        hideStopButton();
        updateSendButton();

        // Reset StreamingVisualizer
        streamingVisualizer.reset();

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
    searchInfoDiv.style.cssText = `
        margin: 8px 0 12px 0;
        padding: 8px 12px;
        background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
        border-left: 3px solid #0ea5e9;
        border-radius: 6px;
        font-size: 13px;
        color: #0c4a6e;
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
    separator.style.cssText = 'color: #94a3b8; font-weight: 300;';
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
    sourcesText.style.cssText = 'color: #0369a1; font-size: 12px;';
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
        contentDiv.innerHTML = marked.parse(text);

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

    actionsDiv.appendChild(feedbackDiv);
    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(regenerateBtn);
    actionsDiv.appendChild(downloadContainer);
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

    actionsDiv.appendChild(feedbackDiv);
    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(regenerateBtn);
    actionsDiv.appendChild(downloadContainer);
    wrapperDiv.appendChild(actionsDiv);
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
}

// Display current LLM and Embedding models
async function loadAvailableModels() {
    const llmModelDisplay = document.getElementById('llmModelDisplay');
    const embeddingModelDisplay = document.getElementById('embeddingModelDisplay');

    if (!llmModelDisplay || !embeddingModelDisplay) {
        logger.error('Model display elements not found');
        return;
    }

    // Simply display the current models from settings
    llmModelDisplay.textContent = currentSettings.llm_model || '설정되지 않음';
    embeddingModelDisplay.textContent = currentSettings.embedding_model || '설정되지 않음';
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
    } catch (error) {
        logger.error('Failed to fetch latest model info:', error);
    }

    // Load latest system prompt from server (admin-configured)
    await loadSystemPromptFromServer();

    // 하이브리드 RAG 상태 확인 및 검색 모드 UI 제어
    await checkHybridRAGStatus();

    await loadAvailableModels();  // Load available models when opening settings
    loadCacheStats();
    loadCacheEnabled();
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
            contentDiv.innerHTML = marked.parse(msg.content);

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
