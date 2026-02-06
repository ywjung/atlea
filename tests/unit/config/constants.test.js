import { describe, it, expect } from 'vitest';
import {
    MODEL_MAX_TOKENS,
    TTS_MODEL_NAMES,
    STORAGE_KEYS,
    HISTORY_CONFIG,
    API_ENDPOINTS,
    UI_CONFIG,
    FEATURES,
    getModelMaxTokens,
    getTTSModelName,
} from '../../../static/js/config/constants.js';

describe('config/constants', () => {
    describe('MODEL_MAX_TOKENS', () => {
        it('should have GLM model token limits', () => {
            expect(MODEL_MAX_TOKENS['glm-4-flash']).toBe(16384);
            expect(MODEL_MAX_TOKENS['glm-4-plus']).toBe(16384);
        });

        it('should have Qwen model token limits', () => {
            expect(MODEL_MAX_TOKENS['qwen3']).toBe(32768);
            expect(MODEL_MAX_TOKENS['qwen2.5']).toBe(32768);
        });

        it('should have Llama model token limits', () => {
            expect(MODEL_MAX_TOKENS['llama3.2']).toBe(131072);
            expect(MODEL_MAX_TOKENS['llama3.1']).toBe(131072);
            expect(MODEL_MAX_TOKENS['llama3']).toBe(8192);
        });

        it('should have default token limit', () => {
            expect(MODEL_MAX_TOKENS['default']).toBe(8192);
        });
    });

    describe('TTS_MODEL_NAMES', () => {
        it('should have model display names', () => {
            expect(TTS_MODEL_NAMES['edge-tts']).toBe('Edge TTS (Fast)');
            expect(TTS_MODEL_NAMES['Qwen/Qwen3-TTS-12Hz-0.6B-Base']).toBe('Qwen3 TTS 0.6B (Fast Local)');
        });
    });

    describe('STORAGE_KEYS', () => {
        it('should have storage key definitions', () => {
            expect(STORAGE_KEYS.DRAFT).toBe('chatDraft');
            expect(STORAGE_KEYS.THEME).toBe('theme');
            expect(STORAGE_KEYS.ACCESS_TOKEN).toBe('access_token');
            expect(STORAGE_KEYS.SESSION_ID).toBe('session_id');
        });
    });

    describe('HISTORY_CONFIG', () => {
        it('should have history configuration', () => {
            expect(HISTORY_CONFIG.MAX_ITEMS).toBe(100);
            expect(HISTORY_CONFIG.SAVE_DEBOUNCE_MS).toBe(500);
        });
    });

    describe('API_ENDPOINTS', () => {
        it('should have auth endpoints', () => {
            expect(API_ENDPOINTS.AUTH.LOGIN).toBe('/api/auth/login');
            expect(API_ENDPOINTS.AUTH.LOGOUT).toBe('/api/auth/logout');
            expect(API_ENDPOINTS.AUTH.REGISTER).toBe('/api/auth/register');
        });

        it('should have chat endpoints', () => {
            expect(API_ENDPOINTS.CHAT.SEND).toBe('/api/chat');
            expect(API_ENDPOINTS.CHAT.STREAM).toBe('/api/chat/stream');
        });

        it('should have conversation endpoints', () => {
            expect(API_ENDPOINTS.CONVERSATIONS.LIST).toBe('/api/conversations');
            expect(API_ENDPOINTS.CONVERSATIONS.CREATE).toBe('/api/conversations');
        });

        it('should have document endpoints', () => {
            expect(API_ENDPOINTS.DOCUMENTS.LIST).toBe('/api/documents');
            expect(API_ENDPOINTS.DOCUMENTS.UPLOAD).toBe('/api/upload');
        });

        it('should have TTS endpoints', () => {
            expect(API_ENDPOINTS.TTS.AVAILABLE).toBe('/api/tts/available');
            expect(API_ENDPOINTS.TTS.SYNTHESIZE).toBe('/api/tts/synthesize');
        });
    });

    describe('UI_CONFIG', () => {
        it('should have UI timing configurations', () => {
            expect(UI_CONFIG.TOAST_DURATION).toBe(3000);
            expect(UI_CONFIG.DEBOUNCE_DELAY).toBe(300);
            expect(UI_CONFIG.THROTTLE_DELAY).toBe(300);
            expect(UI_CONFIG.ANIMATION_DURATION).toBe(300);
        });
    });

    describe('FEATURES', () => {
        it('should have feature flags', () => {
            expect(FEATURES.HYBRID_RAG).toBe(true);
            expect(FEATURES.TTS).toBe(true);
            expect(FEATURES.MARKDOWN).toBe(true);
        });
    });

    describe('getModelMaxTokens', () => {
        it('should return exact match', () => {
            expect(getModelMaxTokens('glm-4-flash')).toBe(16384);
            expect(getModelMaxTokens('qwen3')).toBe(32768);
            expect(getModelMaxTokens('llama3.2')).toBe(131072);
        });

        it('should return prefix match', () => {
            expect(getModelMaxTokens('glm-4-flash-preview')).toBe(16384);
            expect(getModelMaxTokens('qwen3-chat')).toBe(32768);
            expect(getModelMaxTokens('llama3.2-vision')).toBe(131072);
        });

        it('should be case insensitive', () => {
            expect(getModelMaxTokens('GLM-4-Flash')).toBe(16384);
            expect(getModelMaxTokens('QWEN3')).toBe(32768);
        });

        it('should return default for unknown models', () => {
            expect(getModelMaxTokens('unknown-model')).toBe(8192);
            expect(getModelMaxTokens('')).toBe(8192);
            expect(getModelMaxTokens(null)).toBe(8192);
            expect(getModelMaxTokens(undefined)).toBe(8192);
        });

        it('should match longer prefixes first', () => {
            // llama3.2 should match before llama3
            expect(getModelMaxTokens('llama3.2')).toBe(131072);
            expect(getModelMaxTokens('llama3')).toBe(8192);
        });
    });

    describe('getTTSModelName', () => {
        it('should return display name for known models', () => {
            expect(getTTSModelName('edge-tts')).toBe('Edge TTS (Fast)');
            expect(getTTSModelName('Qwen/Qwen3-TTS-12Hz-0.6B-Base')).toBe('Qwen3 TTS 0.6B (Fast Local)');
        });

        it('should return model ID for unknown models', () => {
            expect(getTTSModelName('unknown-model')).toBe('unknown-model');
            expect(getTTSModelName('custom-tts')).toBe('custom-tts');
        });
    });
});
