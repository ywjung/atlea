// Configure marked.js
marked.setOptions({
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    },
    breaks: true,
    gfm: true
});

// Debug mode control
const DEBUG_MODE = false; // Set to true for development, false for production

// Console wrapper for production
const devLog = (...args) => DEBUG_MODE && console.log(...args);
const devWarn = (...args) => DEBUG_MODE && console.warn(...args);
// Keep console.error for production errors

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

// Initialize feature modules
const errorHandler = new ErrorHandler();
const streamingVisualizer = new StreamingVisualizer();
let questionAutoComplete = null;  // Will be initialized after fetching questions
let currentContextData = [];  // Store context data for source details
const followUpQuestions = new FollowUpQuestions();  // Initialize follow-up questions feature

// Initialize
async function init() {
    initTheme();
    await checkStatus();
    setupEventListeners();
    setupScrollButton();
    await loadSuggestedQuestions();  // Load suggested questions after status check

    // Initialize AutoComplete after loading suggested questions
    await initializeAutoComplete();

    userInput.focus();
}

// Initialize AutoComplete
async function initializeAutoComplete() {
    try {
        const response = await fetch('/api/suggested-questions');
        if (response.ok) {
            const data = await response.json();
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
    clearBtn.addEventListener('click', clearChat);
    exportBtn.addEventListener('click', exportHistory);
    importBtn.addEventListener('click', importHistory);
    reindexBtn.addEventListener('click', reindexDocuments);
    themeToggle.addEventListener('click', toggleTheme);

    // Help modal event listeners
    helpBtn.addEventListener('click', () => {
        helpModal.classList.add('active');
    });

    closeHelpModal.addEventListener('click', () => {
        helpModal.classList.remove('active');
    });

    // Close help modal when clicking outside
    helpModal.addEventListener('click', (e) => {
        if (e.target === helpModal) {
            helpModal.classList.remove('active');
        }
    });

    // Source modal event listeners
    closeSourceModal.addEventListener('click', () => {
        sourceModal.classList.remove('active');
    });

    // Close modal when clicking outside
    sourceModal.addEventListener('click', (e) => {
        if (e.target === sourceModal) {
            sourceModal.classList.remove('active');
        }
    });

    // Chunk viewer modal event listeners
    closeChunkViewerModal.addEventListener('click', () => {
        chunkViewerModal.classList.remove('active');
    });

    // Close modal when clicking outside
    chunkViewerModal.addEventListener('click', (e) => {
        if (e.target === chunkViewerModal) {
            chunkViewerModal.classList.remove('active');
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

    userInput.addEventListener('input', () => {
        autoResize();
        updateSendButton();
        updateCharCount();
        saveDraft(); // Auto-save draft
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
            } else {
                helpModal.classList.add('active');
            }
            return;
        }

        // Esc - Close any open modal or panel
        if (e.key === 'Escape') {
            // Close help modal
            if (helpModal.classList.contains('active')) {
                helpModal.classList.remove('active');
                return;
            }
            // Close settings panel
            if (settingsPanel.classList.contains('active')) {
                closeSettings();
                return;
            }
            // Close docs modal
            if (docsModal.classList.contains('active')) {
                docsModal.classList.remove('active');
                return;
            }
            // Close source modal
            if (sourceModal.classList.contains('active')) {
                sourceModal.classList.remove('active');
                return;
            }
            // Close chunk viewer modal
            if (chunkViewerModal.classList.contains('active')) {
                chunkViewerModal.classList.remove('active');
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
            }
        }

        // Ctrl/Cmd + E - Export history
        if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
            e.preventDefault();
            exportHistory();
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
        const response = await fetch('/api/status');
        const data = await response.json();

        if (data.status === 'ready') {
            statusEl.textContent = '준비됨';
            statusEl.style.color = '#4ade80';
            docCountEl.textContent = `📄 문서 ${data.pdf_count}개 (청크 ${data.chunk_count}개)`;
            sendBtn.disabled = false;
        } else {
            statusEl.textContent = '초기화 중...';
            statusEl.style.color = '#fbbf24';
            setTimeout(checkStatus, 2000);
        }
    } catch (error) {
        console.error('Status check failed:', error);
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

// Send message with streaming
async function sendMessage(regenerate = false) {
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

    // Scroll to bottom to show typing indicator
    scrollToBottom();

    // Track response time
    const startTime = Date.now();

    // Abort any previous request before starting a new one
    if (currentAbortController) {
        console.log('Aborting previous request');
        currentAbortController.abort();
    }

    // Create AbortController for this request
    currentAbortController = new AbortController();

    try {
        // Get selected document IDs from filter
        const documentIds = getSelectedDocumentIds();

        // Wrap fetch with ErrorHandler retry and timeout
        const response = await errorHandler.withTimeout(
            () => errorHandler.withRetry(
                async () => {
                    const res = await fetch('/api/query/stream', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            question: question,
                            top_k: currentSettings.top_k,
                            temperature: currentSettings.temperature,
                            max_tokens: currentSettings.max_tokens,
                            system_prompt: currentSettings.system_prompt,
                            cache_threshold: currentSettings.cache_threshold,
                            cache_ttl: currentSettings.cache_ttl,
                            document_ids: documentIds,  // Add selected document IDs
                            history: conversationHistory.slice(0, -1)  // Send history without current question
                        }),
                        signal: currentAbortController.signal
                    });

                    if (!res.ok) {
                        throw new Error(`HTTP error! status: ${res.status}`);
                    }

                    return res;
                }
            ),
            60000 // 60 second timeout (increased for LLM response generation)
        );

        // Show streaming progress (StreamingVisualizer)
        streamingVisualizer.showStreamingProgress(chatContainer);

        // Create message container for streaming
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot';
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        messageDiv.appendChild(contentDiv);
        chatContainer.appendChild(messageDiv);

        let sources = null;
        let fullText = '';
        let tokenCount = 0;

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

                            devLog('🔍 [METADATA] Received metadata:', {
                                sources: sources,
                                sourcesLength: sources ? sources.length : 0,
                                sourcesType: typeof sources,
                                sourcesIsArray: Array.isArray(sources),
                                contextLength: currentContextData.length,
                                cached: data.data.cached
                            });
                        } else if (data.type === 'chunk') {
                            fullText += data.data;

                            // Update token count (approximate by splitting on spaces)
                            tokenCount = fullText.split(/\s+/).filter(w => w.length > 0).length;
                            streamingVisualizer.updateTokenCount(tokenCount);

                            // Server already filters <think> tags, so just render
                            try {
                                contentDiv.innerHTML = marked.parse(fullText);

                                // Highlight code blocks
                                contentDiv.querySelectorAll('pre code').forEach((block) => {
                                    hljs.highlightElement(block);
                                });

                                // Scroll to bottom
                                chatContainer.scrollTop = chatContainer.scrollHeight;
                            } catch (renderError) {
                                console.error('Render error:', renderError);
                                // Continue streaming even if rendering fails
                            }
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

                            // Add timestamp
                            addResponseTime(messageDiv, elapsed, data.data?.cached);

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
                                const followUpQs = await followUpQuestions.generate(question, fullText);
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
                                console.error('Failed to generate/display follow-up questions:', error);
                            }
                        }
                    } catch (parseError) {
                        console.error('JSON parse error:', parseError, 'Line:', line);
                    }
                }
            }
        }

    } catch (error) {
        console.error('Query failed:', error);

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

        // Highlight code blocks
        contentDiv.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
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

// Clear chat
function clearChat() {
    if (confirm('대화 내용을 모두 삭제하시겠습니까?')) {
        // Clear conversation history (both in memory and localStorage)
        clearHistory();

        // Clear AutoComplete
        if (questionAutoComplete) {
            questionAutoComplete.clear();
        }

        // Clear chat UI and recreate suggested questions section
        chatContainer.innerHTML = `
            <div class="welcome-message">
                <h2>안녕하세요! 👋</h2>
                <p>PDF 문서 내용에 대해 무엇이든 질문해주세요.</p>
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

        // Reattach event listener for refresh button
        const refreshBtn = document.getElementById('refreshSuggestionsBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadSuggestedQuestions);
        }

        // Show and load suggested questions
        const suggestedQuestionsContainer = document.getElementById('suggestedQuestions');
        if (suggestedQuestionsContainer) {
            suggestedQuestionsContainer.style.display = 'block';
        }
        loadSuggestedQuestions();
    }
}

// Reindex documents
async function reindexDocuments() {
    if (!confirm('문서를 재색인하시겠습니까? 시간이 걸릴 수 있습니다.')) {
        return;
    }

    reindexBtn.disabled = true;
    reindexBtn.textContent = '재색인 중...';
    statusEl.textContent = '재색인 중...';
    statusEl.style.color = '#fbbf24';

    try {
        const response = await fetch('/api/reindex', {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        alert(data.message);
        await checkStatus();

    } catch (error) {
        console.error('Reindex failed:', error);
        alert('재색인에 실패했습니다.');
    } finally {
        reindexBtn.disabled = false;
        reindexBtn.textContent = '문서 재색인';
    }
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

    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(regenerateBtn);
    contentDiv.appendChild(actionsDiv);
}

// Add action buttons to sources wrapper (positioned on the right side)
function addActionButtonsToWrapper(wrapperDiv, text) {
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions-inline';

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

    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(regenerateBtn);
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
        console.error('Copy failed:', error);

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

// Add response time indicator
function addResponseTime(messageDiv, elapsed, cached = false) {
    const timeDiv = document.createElement('div');
    timeDiv.className = 'response-time';

    const icon = cached ? '⚡' : '⏱️';
    const label = cached ? '캐시 응답' : '응답 시간';

    timeDiv.innerHTML = `
        <span class="time-icon">${icon}</span>
        <span class="time-text">${label}: ${elapsed}초</span>
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
            solutionDiv.innerHTML = `<strong>💡 해결 방법:</strong> ${errorDetail.solution}`;
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
const docsBtn = document.getElementById('docsBtn');
const docsModal = document.getElementById('docsModal');
const closeDocsModal = document.getElementById('closeDocsModal');
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const uploadStatus = document.getElementById('uploadStatus');
const docsList = document.getElementById('docsList');
const refreshDocsBtn = document.getElementById('refreshDocsBtn');

// Open modal
docsBtn.addEventListener('click', () => {
    docsModal.classList.add('active');
    loadDocuments();
});

// Close modal
closeDocsModal.addEventListener('click', () => {
    docsModal.classList.remove('active');
});

// Close modal when clicking outside
docsModal.addEventListener('click', (e) => {
    if (e.target === docsModal) {
        docsModal.classList.remove('active');
    }
});

// Upload area click
uploadArea.addEventListener('click', () => {
    fileInput.click();
});

// File input change
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        uploadFile(e.target.files[0]);
    }
});

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
        const fileName = file.name.toLowerCase();
        const isPDF = file.type === 'application/pdf' || fileName.endsWith('.pdf');
        const isHWP = fileName.endsWith('.hwp');

        if (isPDF || isHWP) {
            uploadFile(file);
        } else {
            showUploadStatus('PDF 또는 HWP 파일만 업로드 가능합니다.', 'error');
        }
    }
});

// Refresh documents
refreshDocsBtn.addEventListener('click', loadDocuments);

// Upload file
async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    showUploadStatus(`업로드 중: ${file.name}`, 'uploading');

    try {
        const response = await fetch('/api/documents/upload', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            showUploadStatus(
                `✓ ${file.name} 업로드 및 색인 완료! (${result.chunk_count} 청크 생성)`,
                'success'
            );
            fileInput.value = '';
            // Reload documents and filter list
            setTimeout(() => {
                loadDocuments();
                loadFilterDocuments();  // Refresh search scope filter
                checkStatus();
            }, 1000);
        } else {
            showUploadStatus(`✗ 업로드 실패: ${result.detail}`, 'error');
        }
    } catch (error) {
        showUploadStatus(`✗ 업로드 실패: ${error.message}`, 'error');
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
        const response = await fetch('/api/documents');
        const data = await response.json();

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
        console.error('Error loading chunks:', error);
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
    if (!confirm(`"${filename}" 문서를 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없으며, 벡터 DB에서도 함께 삭제됩니다.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok) {
            showUploadStatus(`✓ ${filename} 삭제 완료`, 'success');
            loadDocuments();
            loadFilterDocuments();  // Refresh search scope filter
            checkStatus();
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

// ===== Settings Management =====
const settingsBtn = document.getElementById('settingsBtn');
const settingsPanel = document.getElementById('settingsPanel');
const settingsOverlay = document.getElementById('settingsOverlay');
const closeSettingsBtn = document.getElementById('closeSettingsBtn');

// Settings controls
const topKSlider = document.getElementById('topKSlider');
const topKValue = document.getElementById('topKValue');
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
            console.error('Failed to load settings:', e);
        }
    }
    applySettings();
}

function applySettings() {
    topKSlider.value = currentSettings.top_k;
    topKValue.textContent = currentSettings.top_k;

    temperatureSlider.value = currentSettings.temperature;
    temperatureValue.textContent = currentSettings.temperature.toFixed(1);

    maxTokensSlider.value = currentSettings.max_tokens;
    maxTokensValue.textContent = currentSettings.max_tokens;

    cacheThresholdSlider.value = currentSettings.cache_threshold;
    cacheThresholdValue.textContent = currentSettings.cache_threshold.toFixed(2);

    cacheTTLSlider.value = currentSettings.cache_ttl;
    cacheTTLValue.textContent = currentSettings.cache_ttl;

    const llmSelect = document.getElementById('llmSelect');
    if (llmSelect) {
        llmSelect.value = currentSettings.llm_model;
    }

    const embeddingSelect = document.getElementById('embeddingSelect');
    if (embeddingSelect) {
        embeddingSelect.value = currentSettings.embedding_model;
    }

    systemPrompt.value = currentSettings.system_prompt;
}

// Load available LLM and Embedding models from server
async function loadAvailableModels() {
    const llmSelect = document.getElementById('llmSelect');
    const embeddingSelect = document.getElementById('embeddingSelect');

    if (!llmSelect || !embeddingSelect) {
        console.error('Model select elements not found');
        return;
    }

    console.log('Loading available models...');

    try {
        const response = await fetch('/api/models');
        console.log('Models API response status:', response.status);

        if (!response.ok) {
            throw new Error(`Failed to load models: ${response.status}`);
        }

        const data = await response.json();
        console.log('Models data:', data);
        const llmModels = data.llm_models || [];
        const embeddingModels = data.embedding_models || [];
        console.log('Found LLM models:', llmModels.length, 'Embedding models:', embeddingModels.length);

        // Load LLM models
        llmSelect.innerHTML = '';
        if (llmModels.length === 0) {
            console.warn('No LLM models available');
            llmSelect.innerHTML = '<option value="">다운로드된 LLM 모델이 없습니다</option>';
            llmSelect.disabled = true;
        } else {
            llmModels.forEach(model => {
                console.log('Adding LLM model:', model.label, '=', model.value);
                const option = document.createElement('option');
                option.value = model.value;
                option.textContent = model.label;
                llmSelect.appendChild(option);
            });

            if (currentSettings.llm_model) {
                llmSelect.value = currentSettings.llm_model;
            }
            llmSelect.disabled = false;
        }

        // Load Embedding models
        embeddingSelect.innerHTML = '';
        if (embeddingModels.length === 0) {
            console.warn('No embedding models available');
            embeddingSelect.innerHTML = '<option value="">다운로드된 Embedding 모델이 없습니다</option>';
            embeddingSelect.disabled = true;
        } else {
            embeddingModels.forEach(model => {
                console.log('Adding Embedding model:', model.label, '=', model.value);
                const option = document.createElement('option');
                option.value = model.value;
                option.textContent = model.label;
                embeddingSelect.appendChild(option);
            });

            if (currentSettings.embedding_model) {
                embeddingSelect.value = currentSettings.embedding_model;
            }
            embeddingSelect.disabled = false;
        }

        console.log('Models loaded successfully');

    } catch (error) {
        console.error('Failed to load available models:', error);
        llmSelect.innerHTML = '<option value="">모델 로드 실패</option>';
        llmSelect.disabled = true;
        embeddingSelect.innerHTML = '<option value="">모델 로드 실패</option>';
        embeddingSelect.disabled = true;
    }
}

// Open settings (with cache stats loading)
settingsBtn.addEventListener('click', async () => {
    settingsPanel.classList.add('active');
    settingsOverlay.classList.add('active');
    await loadAvailableModels();  // Load available models when opening settings
    loadCacheStats();
});

// Close settings
function closeSettings() {
    settingsPanel.classList.remove('active');
    settingsOverlay.classList.remove('active');
}

closeSettingsBtn.addEventListener('click', closeSettings);
settingsOverlay.addEventListener('click', closeSettings);

// Update slider values in real-time
topKSlider.addEventListener('input', (e) => {
    topKValue.textContent = e.target.value;
});

temperatureSlider.addEventListener('input', (e) => {
    temperatureValue.textContent = parseFloat(e.target.value).toFixed(1);
});

maxTokensSlider.addEventListener('input', (e) => {
    maxTokensValue.textContent = e.target.value;
});

cacheThresholdSlider.addEventListener('input', (e) => {
    cacheThresholdValue.textContent = parseFloat(e.target.value).toFixed(2);
});

cacheTTLSlider.addEventListener('input', (e) => {
    cacheTTLValue.textContent = e.target.value;
});

// Save settings
saveSettingsBtn.addEventListener('click', async () => {
    const llmSelect = document.getElementById('llmSelect');
    const embeddingSelect = document.getElementById('embeddingSelect');
    const oldLLM = currentSettings.llm_model;
    const newLLM = llmSelect.value;
    const oldEmbedding = currentSettings.embedding_model;
    const newEmbedding = embeddingSelect.value;

    currentSettings = {
        top_k: parseInt(topKSlider.value),
        temperature: parseFloat(temperatureSlider.value),
        max_tokens: parseInt(maxTokensSlider.value),
        cache_threshold: parseFloat(cacheThresholdSlider.value),
        cache_ttl: parseInt(cacheTTLSlider.value),
        llm_model: newLLM,
        embedding_model: newEmbedding,
        system_prompt: systemPrompt.value
    };

    localStorage.setItem('chatSettings', JSON.stringify(currentSettings));

    // Check if LLM model changed
    if (oldLLM !== newLLM) {
        try {
            const response = await fetch('/api/change-llm', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ llm_model: newLLM })
            });

            if (!response.ok) {
                throw new Error('Failed to change LLM model');
            }

            const result = await response.json();
            alert(`LLM 모델이 ${result.llm_model}으로 변경되었습니다.`);
        } catch (error) {
            console.error('LLM model change failed:', error);
            alert('LLM 모델 변경에 실패했습니다.');
            return;
        }
    }

    // Check if Embedding model changed
    if (oldEmbedding !== newEmbedding) {
        try {
            const response = await fetch('/api/change-embedding', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ embedding_model: newEmbedding })
            });

            if (!response.ok) {
                throw new Error('Failed to change Embedding model');
            }

            const result = await response.json();
            alert(`Embedding 모델이 ${result.embedding_model}으로 변경되었습니다.\n\n⚠️ ${result.warning}`);
        } catch (error) {
            console.error('Embedding model change failed:', error);
            alert('Embedding 모델 변경에 실패했습니다.');
            return;
        }
    }

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

// Reset settings
resetSettingsBtn.addEventListener('click', () => {
    if (confirm('모든 설정을 기본값으로 복원하시겠습니까?')) {
        currentSettings = { ...defaultSettings };
        applySettings();
        localStorage.removeItem('chatSettings');

        // Show success message
        const originalText = resetSettingsBtn.textContent;
        resetSettingsBtn.textContent = '✓ 복원됨!';

        setTimeout(() => {
            resetSettingsBtn.textContent = originalText;
        }, 2000);
    }
});

// Load cache statistics
async function loadCacheStats() {
    try {
        const response = await fetch('/api/cache/stats');
        const stats = await response.json();

        if (response.ok) {
            document.getElementById('statTotalEntries').textContent = stats.total_entries || 0;
            document.getElementById('statTotalQueries').textContent = stats.total_queries || 0;
            document.getElementById('statCacheHits').textContent = stats.cache_hits || 0;

            // Calculate hit rate
            const hitRate = stats.total_queries > 0
                ? ((stats.cache_hits / stats.total_queries) * 100).toFixed(1) + '%'
                : '0%';
            document.getElementById('statHitRate').textContent = hitRate;

            // Update hit rate color based on percentage
            const hitRateElement = document.getElementById('statHitRate');
            const hitRateValue = parseFloat(hitRate);
            if (hitRateValue >= 70) {
                hitRateElement.style.color = '#059669'; // Green
            } else if (hitRateValue >= 40) {
                hitRateElement.style.color = '#d97706'; // Orange
            } else {
                hitRateElement.style.color = '#dc2626'; // Red
            }
        }
    } catch (error) {
        console.error('Failed to load cache stats:', error);
        document.getElementById('statTotalEntries').textContent = 'Error';
        document.getElementById('statHitRate').textContent = 'Error';
        document.getElementById('statTotalQueries').textContent = 'Error';
        document.getElementById('statCacheHits').textContent = 'Error';
    }
}

// Refresh stats button
document.getElementById('refreshStatsBtn').addEventListener('click', loadCacheStats);

// Clear cache button
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

// ===== Source Details Modal =====
function showSourceDetails(filename) {
    devLog('showSourceDetails called for:', filename);
    devLog('currentContextData:', currentContextData);

    // Find all context items for this filename
    const sourceContexts = currentContextData.filter(ctx => ctx.filename === filename);

    devLog('sourceContexts found:', sourceContexts);

    if (sourceContexts.length === 0) {
        console.error('No context found for filename:', filename);
        console.error('Available filenames in currentContextData:',
            currentContextData.map(ctx => ctx.filename));
        alert('출처 정보를 찾을 수 없습니다.');
        return;
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
        console.error('Failed to load draft:', e);
    }
}

// Clear draft after sending
function clearDraft() {
    localStorage.removeItem(DRAFT_KEY);
}

// Warn before leaving with unsaved draft
window.addEventListener('beforeunload', (e) => {
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
        console.error('Failed to save history:', e);
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
        console.error('Failed to load history:', e);
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
                hljs.highlightElement(block);
            });

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

// Export conversation history as JSON file
function exportHistory() {
    if (conversationHistory.length === 0) {
        alert('저장할 대화 내용이 없습니다.');
        return;
    }

    const dataStr = JSON.stringify(conversationHistory, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = `chat-history-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

// Import conversation history from JSON file
function importHistory() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/json';

    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        try {
            const text = await file.text();
            const imported = JSON.parse(text);

            // Validate imported data
            if (!Array.isArray(imported)) {
                throw new Error('Invalid format: expected an array');
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

            alert('대화 내용을 불러왔습니다.');
        } catch (err) {
            alert(`파일을 불러오는데 실패했습니다: ${err.message}`);
        }
    };

    input.click();
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
        console.error('Failed to copy:', err);
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
        console.error('Failed to save theme to localStorage:', error);
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
loadHistory();

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
let selectedDocumentIds = new Set();

// Toggle filter panel expansion/collapse
function toggleFilterPanel() {
    const filterContent = document.getElementById('filterContent');
    const toggleBtn = document.querySelector('.toggle-filter-btn');
    const toggleIcon = toggleBtn.querySelector('svg');

    if (filterContent.classList.contains('collapsed')) {
        filterContent.classList.remove('collapsed');
        toggleIcon.style.transform = 'rotate(180deg)';
    } else {
        filterContent.classList.add('collapsed');
        toggleIcon.style.transform = 'rotate(0deg)';
    }
}

// Load available documents for filter from server
async function loadFilterDocuments() {
    try {
        const response = await fetch('/api/documents');
        if (!response.ok) {
            throw new Error('Failed to fetch documents');
        }

        const data = await response.json();
        availableDocuments = data.documents || [];
        renderFilterDocumentList();
    } catch (error) {
        console.error('Error loading filter documents:', error);
        const documentList = document.getElementById('filterDocumentList');
        documentList.innerHTML = '<div class="loading-documents" style="color: #ef4444;">문서 목록을 불러오는데 실패했습니다.</div>';
    }
}

// Render filter document list with checkboxes
function renderFilterDocumentList() {
    const documentList = document.getElementById('filterDocumentList');

    if (availableDocuments.length === 0) {
        documentList.innerHTML = '<div class="loading-documents">등록된 문서가 없습니다.</div>';
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
        </div>
    `).join('');
}

// Handle document checkbox selection
function handleDocumentSelection(checkbox) {
    if (checkbox.checked) {
        selectedDocumentIds.add(checkbox.value);
    } else {
        selectedDocumentIds.delete(checkbox.value);
    }

    // Auto-switch to "selected documents" mode if any document is selected
    const selectedMode = document.querySelector('input[name="filterMode"][value="selected"]');
    if (selectedDocumentIds.size > 0 && selectedMode) {
        selectedMode.checked = true;
    }
}

// Handle filter mode change (all vs selected)
function handleFilterModeChange(mode) {
    if (mode === 'all') {
        // Uncheck all document checkboxes
        document.querySelectorAll('.document-item input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
        selectedDocumentIds.clear();
    }
}

// Get selected document IDs for query
function getSelectedDocumentIds() {
    const filterMode = document.querySelector('input[name="filterMode"]:checked')?.value;

    if (filterMode === 'all') {
        return null; // null means search all documents
    }

    if (selectedDocumentIds.size === 0) {
        return null; // If no documents selected, default to all
    }

    return Array.from(selectedDocumentIds);
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

    // Load documents from server for filter
    loadFilterDocuments();
}

// ===== Suggested Questions =====

/**
 * Load suggested questions from server
 */
async function loadSuggestedQuestions() {
    try {
        const response = await fetch('/api/suggested-questions');
        if (!response.ok) {
            devWarn('Failed to load suggested questions');
            return;
        }

        const data = await response.json();
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
        console.error('Error loading suggested questions:', error);
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
        console.error('Error refreshing suggested questions:', error);
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

// Start application when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        init();
        initDocumentFilter();
    });
} else {
    // DOM already loaded
    init();
    initDocumentFilter();
}
