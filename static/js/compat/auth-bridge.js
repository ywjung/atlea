/**
 * Auth Compatibility Bridge
 *
 * Bridges legacy Auth object interface with new ES6 auth modules.
 * Allows existing pages to work with new modular code without changes.
 */

import * as authSession from '../auth/session.js';
import * as authLogin from '../auth/login.js';
import * as authRegister from '../auth/register.js';
import * as authPassword from '../auth/password.js';
import { showToast } from '../ui/toast.js';
import { apiCall, post } from '../utils/http.js';
import { validatePassword, validateEmail, validateUsername } from '../utils/validation.js';

/**
 * Legacy Auth object for backward compatibility
 * Wraps ES6 module functions as object methods
 */
window.Auth = {
    // Session management
    setTokens: authSession.setTokens,
    getAccessToken: authSession.getAccessToken,
    getRefreshToken: authSession.getRefreshToken,
    clearTokens: authSession.clearTokens,

    setUser: authSession.setUser,
    getUser: authSession.getUser,
    clearUser: authSession.clearUser,

    setSessionId: authSession.setSessionId,
    getSessionId: authSession.getSessionId,
    clearSessionId: authSession.clearSessionId,

    isAuthenticated: authSession.isAuthenticated,
    isAdmin: authSession.isAdmin,
    getUserRole: authSession.getUserRole,
    getUserId: authSession.getUserId,

    // Extended session methods
    getCurrentUser: authSession.getCurrentUser,
    getSessions: authSession.getSessions,
    revokeSession: authSession.revokeSession,
    revokeAllSessions: authSession.revokeAllSessions,
    updateProfile: authSession.updateProfile,
    initActivityMonitor: authSession.initActivityMonitor,
    startSessionValidation: authSession.startSessionValidation,

    clearAuth: authSession.clearAuth,

    redirectToLogin: authSession.redirectToLogin,
    redirectToHome: authSession.redirectToHome,
    requireAuth: authSession.requireAuth,
    requireAdmin: authSession.requireAdmin,

    // Login/Logout
    login: authLogin.login,
    logout: authLogin.logout,
    refreshToken: authLogin.refreshToken,
    validateSession: authLogin.validateSession,

    // Registration
    register: authRegister.register,
    generateCaptcha: authRegister.generateCaptcha,

    // Password management
    changePassword: authPassword.changePassword,
    requestPasswordReset: authPassword.requestPasswordReset,
    confirmPasswordReset: authPassword.confirmPasswordReset,

    // UI feedback methods (mapped to toast)
    showError: (message, elementId) => {
        // elementId parameter for backward compatibility (ignored - using toast instead)
        showToast(message, 'error');
    },

    showSuccess: (message, elementId) => {
        // elementId parameter for backward compatibility (ignored - using toast instead)
        showToast(message, 'success');
    },

    showInfo: (message, elementId) => {
        // elementId parameter for backward compatibility (ignored - using toast instead)
        showToast(message, 'info');
    },

    showWarning: (message, elementId) => {
        // elementId parameter for backward compatibility (ignored - using toast instead)
        showToast(message, 'warning');
    },

    hideError: (elementId) => {
        // elementId parameter for backward compatibility
        // Toast auto-hides, no action needed
        // Kept for compatibility
    },

    hideSuccess: (elementId) => {
        // elementId parameter for backward compatibility
        // Toast auto-hides, no action needed
        // Kept for compatibility
    },

    // API call wrapper
    apiCall: apiCall,

    // Direct HTTP methods for compatibility
    post: post,

    // Validation methods
    validatePassword: validatePassword,
    validateEmail: validateEmail,
    validateUsername: validateUsername,

    // Utility methods
    isTokenExpired: (token) => {
        if (!token) return true;
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            return payload.exp * 1000 < Date.now();
        } catch {
            return true;
        }
    }
};

// Export for module usage
export default window.Auth;
