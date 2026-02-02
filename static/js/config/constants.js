/**
 * Application Constants
 *
 * Central configuration and constants for the application.
 */

/**
 * Model maximum token configurations
 * Maps model names to their maximum token limits
 */
export const MODEL_MAX_TOKENS = {
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
 * TTS model name mappings for display
 */
export const TTS_MODEL_NAMES = {
    'edge-tts': 'Edge TTS (Fast)',
    'Qwen/Qwen3-TTS-12Hz-0.6B-Base': 'Qwen3 TTS 0.6B (Fast Local)',
    'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice': 'Qwen3 TTS 1.7B (High Quality)'
};

/**
 * Storage keys
 */
export const STORAGE_KEYS = {
    DRAFT: 'chatDraft',
    HISTORY: 'chatHistory',
    THEME: 'theme',
    ACCESS_TOKEN: 'access_token',
    REFRESH_TOKEN: 'refresh_token',
    USER_DATA: 'user_data',
    SESSION_ID: 'session_id',
    CURRENT_CONVERSATION: 'current_conversation_id'
};

/**
 * History configuration
 */
export const HISTORY_CONFIG = {
    MAX_ITEMS: 100, // Maximum number of history items to store
    SAVE_DEBOUNCE_MS: 500 // Debounce time for saving history
};

/**
 * API endpoints
 */
export const API_ENDPOINTS = {
    AUTH: {
        LOGIN: '/api/auth/login',
        LOGOUT: '/api/auth/logout',
        REGISTER: '/api/auth/register',
        REFRESH: '/api/auth/refresh',
        PASSWORD_RESET_REQUEST: '/api/auth/password-reset/request',
        PASSWORD_RESET_CONFIRM: '/api/auth/password-reset/confirm',
        CHANGE_PASSWORD: '/api/auth/change-password'
    },
    CHAT: {
        SEND: '/api/chat',
        STREAM: '/api/chat/stream',
        SUGGESTIONS: '/api/suggestions'
    },
    CONVERSATIONS: {
        LIST: '/api/conversations',
        GET: '/api/conversations/:id',
        CREATE: '/api/conversations',
        UPDATE: '/api/conversations/:id',
        DELETE: '/api/conversations/:id',
        BOOKMARK: '/api/conversations/:id/bookmark'
    },
    DOCUMENTS: {
        LIST: '/api/documents',
        UPLOAD: '/api/upload',
        DELETE: '/api/documents/:filename',
        CHUNKS: '/api/documents/:filename/chunks'
    },
    TTS: {
        AVAILABLE: '/api/tts/available',
        SYNTHESIZE: '/api/tts/synthesize'
    }
};

/**
 * UI configuration
 */
export const UI_CONFIG = {
    TOAST_DURATION: 3000, // Default toast display duration (ms)
    DEBOUNCE_DELAY: 300, // Default debounce delay (ms)
    THROTTLE_DELAY: 300, // Default throttle delay (ms)
    ANIMATION_DURATION: 300 // Default animation duration (ms)
};

/**
 * Feature flags
 */
export const FEATURES = {
    HYBRID_RAG: true,
    TTS: true,
    VOICE_INPUT: true,
    MARKDOWN: true,
    CODE_HIGHLIGHTING: true,
    MATH_RENDERING: true
};

/**
 * Get model max tokens by model name
 * @param {string} modelName - Model name or prefix
 * @returns {number} - Maximum tokens for the model
 */
export function getModelMaxTokens(modelName) {
    if (!modelName) return MODEL_MAX_TOKENS.default;

    const lowerName = modelName.toLowerCase();

    // Try exact match first
    if (MODEL_MAX_TOKENS[lowerName]) {
        return MODEL_MAX_TOKENS[lowerName];
    }

    // Try prefix match
    for (const [key, value] of Object.entries(MODEL_MAX_TOKENS)) {
        if (lowerName.startsWith(key)) {
            return value;
        }
    }

    return MODEL_MAX_TOKENS.default;
}

/**
 * Get TTS model display name
 * @param {string} modelId - TTS model ID
 * @returns {string} - Display name
 */
export function getTTSModelName(modelId) {
    return TTS_MODEL_NAMES[modelId] || modelId;
}
