/**
 * Session Manager
 * Handles localStorage-based session persistence
 */

class SessionManager {
    constructor() {
        this.SESSION_KEY = 'chatbot_session';
        this.SESSION_EXPIRY_HOURS = 24;
        this.version = '1.0';
    }

    /**
     * Save current session to localStorage
     * @param {Array} conversationHistory - Chat history
     */
    saveSession(conversationHistory) {
        try {
            const session = {
                history: conversationHistory,
                timestamp: Date.now(),
                version: this.version
            };

            localStorage.setItem(this.SESSION_KEY, JSON.stringify(session));
            console.log('Session saved successfully');
            return true;
        } catch (error) {
            console.error('Failed to save session:', error);

            // Handle quota exceeded error
            if (error.name === 'QuotaExceededError') {
                this.clearOldSessions();
                console.warn('localStorage quota exceeded, cleared old sessions');
            }
            return false;
        }
    }

    /**
     * Load session from localStorage
     * @returns {Array|null} - Conversation history or null if expired/invalid
     */
    loadSession() {
        try {
            const saved = localStorage.getItem(this.SESSION_KEY);

            if (!saved) {
                console.log('No saved session found');
                return null;
            }

            const session = JSON.parse(saved);

            // Check version compatibility
            if (session.version !== this.version) {
                console.warn('Session version mismatch, clearing old session');
                this.clearSession();
                return null;
            }

            // Check expiry (24 hours)
            const expiryTime = this.SESSION_EXPIRY_HOURS * 60 * 60 * 1000;
            const now = Date.now();

            if (now - session.timestamp > expiryTime) {
                console.log('Session expired, clearing');
                this.clearSession();
                return null;
            }

            console.log('Session loaded successfully', session.history.length, 'messages');
            return session.history;

        } catch (error) {
            console.error('Failed to load session:', error);
            this.clearSession(); // Clear corrupted session
            return null;
        }
    }

    /**
     * Clear current session
     */
    clearSession() {
        try {
            localStorage.removeItem(this.SESSION_KEY);
            console.log('Session cleared');
            return true;
        } catch (error) {
            console.error('Failed to clear session:', error);
            return false;
        }
    }

    /**
     * Check if session exists
     * @returns {boolean}
     */
    hasSession() {
        return localStorage.getItem(this.SESSION_KEY) !== null;
    }

    /**
     * Get session info without loading
     * @returns {Object|null} - Session metadata
     */
    getSessionInfo() {
        try {
            const saved = localStorage.getItem(this.SESSION_KEY);
            if (!saved) return null;

            const session = JSON.parse(saved);
            const age = Date.now() - session.timestamp;
            const ageHours = Math.floor(age / (60 * 60 * 1000));
            const ageMinutes = Math.floor((age % (60 * 60 * 1000)) / (60 * 1000));

            return {
                messageCount: session.history.length,
                age: `${ageHours}시간 ${ageMinutes}분 전`,
                timestamp: new Date(session.timestamp).toLocaleString('ko-KR'),
                isExpired: age > (this.SESSION_EXPIRY_HOURS * 60 * 60 * 1000)
            };
        } catch (error) {
            console.error('Failed to get session info:', error);
            return null;
        }
    }

    /**
     * Clear old/corrupted sessions
     */
    clearOldSessions() {
        try {
            // Get all localStorage keys
            const keys = Object.keys(localStorage);

            // Find and clear chatbot-related keys
            keys.forEach(key => {
                if (key.startsWith('chatbot_')) {
                    try {
                        const item = localStorage.getItem(key);
                        const data = JSON.parse(item);

                        // Clear if old or corrupted
                        if (!data.timestamp ||
                            Date.now() - data.timestamp > (this.SESSION_EXPIRY_HOURS * 60 * 60 * 1000)) {
                            localStorage.removeItem(key);
                            console.log('Cleared old session:', key);
                        }
                    } catch (e) {
                        // Clear corrupted data
                        localStorage.removeItem(key);
                        console.log('Cleared corrupted session:', key);
                    }
                }
            });
        } catch (error) {
            console.error('Failed to clear old sessions:', error);
        }
    }

    /**
     * Auto-save with debouncing
     * @param {Array} conversationHistory
     * @param {number} delay - Delay in ms (default 1000)
     */
    autoSave(conversationHistory, delay = 1000) {
        // Clear existing timeout
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }

        // Set new timeout
        this.saveTimeout = setTimeout(() => {
            this.saveSession(conversationHistory);
        }, delay);
    }
}

// Export for use in main script
window.SessionManager = SessionManager;
