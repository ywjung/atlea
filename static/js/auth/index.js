/**
 * Auth Module Index
 * 
 * Central export for all authentication modules.
 */

// Re-export all auth functions
export * from './session.js';
export * from './login.js';
export * from './register.js';
export * from './password.js';

// Named exports for convenience
export {
    setTokens, getAccessToken, getRefreshToken, clearTokens,
    setUser, getUser, clearUser,
    setSessionId, getSessionId, clearSessionId,
    isAuthenticated, isAdmin, getUserRole, getUserId,
    clearAuth,
    redirectToLogin, redirectToHome, requireAuth, requireAdmin
} from './session.js';

export {
    login, logout, refreshToken, validateSession
} from './login.js';

export {
    register, generateCaptcha
} from './register.js';

export {
    changePassword, requestPasswordReset, confirmPasswordReset
} from './password.js';
