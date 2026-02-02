/**
 * Main JavaScript Module Index
 *
 * Central export point for all modular JavaScript code.
 * Import from this file to access any module in the application.
 *
 * Usage:
 *   import { initApp, showToast, login } from '/static/js/index.js';
 */

// Application initialization
export * from './app/index.js';

// Authentication
export * from './auth/index.js';

// Chat functionality
export * from './chat/index.js';

// UI components
export * from './ui/index.js';

// Utilities
export * from './utils/index.js';

// Markdown processing
export * from './markdown/index.js';

// Named exports for convenience
export {
    initApp,
    initFeatures
} from './app/index.js';

export {
    setTokens, getAccessToken, getRefreshToken, clearTokens,
    setUser, getUser, clearUser,
    setSessionId, getSessionId, clearSessionId,
    isAuthenticated, isAdmin, getUserRole, getUserId,
    clearAuth,
    redirectToLogin, redirectToHome, requireAuth, requireAdmin,
    login, logout, refreshToken, validateSession,
    register, generateCaptcha,
    changePassword, requestPasswordReset, confirmPasswordReset
} from './auth/index.js';

export {
    getCurrentConversationId, setCurrentConversationId,
    loadConversations, createConversation, loadConversation,
    deleteConversation, updateConversationTitle, toggleBookmark,
    renderUserMessage, renderAssistantMessage, renderSystemMessage,
    createLoadingIndicator, updateMessageContent, addMessageActions,
    streamChatResponse, sendMessageWithStreaming, cancelStream
} from './chat/index.js';

export {
    showToast, showNotification,
    showLoading, updateLoadingMessage, hideLoading, createSpinner,
    initTheme, toggleTheme, setTheme, getCurrentTheme, isDarkTheme,
    pushModal, popModal, getTopmostModal, isAnyModalOpen,
    closeTopmostModal, closeAllModals, showModal, hideModal,
    setupModalBackdropClose, setupModalEscHandler
} from './ui/index.js';

export {
    sanitizeHTML, safeSetInnerHTML,
    formatTimestamp, formatFileSize, formatNumber,
    get, post, put, del, patch, apiCall, uploadFile,
    getItem, setItem, removeItem, session,
    createElement, addClass, removeClass, toggleClass,
    show, hide, toggle, debounce, throttle,
    INPUT_VALIDATION, validateInput, validateEmail, validatePassword,
    validateUsername, sanitizeFilename
} from './utils/index.js';

export {
    initMarked, parseMarkdown,
    isAsciiArt, normalizeLanguageClass, renderMath, highlightCodeBlocks
} from './markdown/index.js';
