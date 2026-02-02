/**
 * Session Management
 * 
 * Token storage and authentication state management.
 */

import { getItem, setItem, removeItem } from '../utils/storage.js';

// Storage keys
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_KEY = 'user_data';
const SESSION_ID_KEY = 'session_id';

/**
 * Token Management
 */

export function setTokens(accessToken, refreshToken) {
    setItem(ACCESS_TOKEN_KEY, accessToken);
    if (refreshToken) {
        setItem(REFRESH_TOKEN_KEY, refreshToken);
    }
}

export function getAccessToken() {
    return getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
    return getItem(REFRESH_TOKEN_KEY);
}

export function clearTokens() {
    removeItem(ACCESS_TOKEN_KEY);
    removeItem(REFRESH_TOKEN_KEY);
}

/**
 * User Management
 */

export function setUser(user) {
    setItem(USER_KEY, user);
}

export function getUser() {
    return getItem(USER_KEY);
}

export function clearUser() {
    removeItem(USER_KEY);
}

/**
 * Session Management
 */

export function setSessionId(sessionId) {
    setItem(SESSION_ID_KEY, sessionId);
}

export function getSessionId() {
    return getItem(SESSION_ID_KEY);
}

export function clearSessionId() {
    removeItem(SESSION_ID_KEY);
}

/**
 * Authentication State
 */

export function isAuthenticated() {
    return !!getAccessToken();
}

export function isAdmin() {
    const user = getUser();
    return user && user.role === 'admin';
}

export function getUserRole() {
    const user = getUser();
    return user ? user.role : null;
}

export function getUserId() {
    const user = getUser();
    return user ? user.user_id : null;
}

/**
 * Get current user info from server
 * @returns {Promise<Object>} - User object
 */
export async function getCurrentUser() {
    const response = await fetch('/api/users/me', {
        headers: {
            'Authorization': 'Bearer ' + getAccessToken()
        }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch user info');
    }

    const data = await response.json();
    setUser(data.user);
    return data.user;
}

/**
 * Get active sessions
 * @returns {Promise<Object>} - Sessions data
 */
export async function getSessions() {
    const response = await fetch('/api/auth/sessions', {
        headers: {
            'Authorization': 'Bearer ' + getAccessToken()
        }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch sessions');
    }

    return await response.json();
}

/**
 * Revoke specific session
 * @param {string} sessionId - Session ID to revoke
 * @returns {Promise<Object>} - Result
 */
export async function revokeSession(sessionId) {
    const response = await fetch('/api/auth/sessions/' + sessionId, {
        method: 'DELETE',
        headers: {
            'Authorization': 'Bearer ' + getAccessToken()
        }
    });

    if (!response.ok) {
        throw new Error('Failed to revoke session');
    }

    return await response.json();
}

/**
 * Revoke all sessions
 * @returns {Promise<Object>} - Result with revoked_count
 */
export async function revokeAllSessions() {
    const response = await fetch('/api/auth/sessions', {
        method: 'DELETE',
        headers: {
            'Authorization': 'Bearer ' + getAccessToken()
        }
    });

    if (!response.ok) {
        throw new Error('Failed to revoke all sessions');
    }

    return await response.json();
}

/**
 * Update user profile
 * @param {string} username - New username
 * @returns {Promise<Object>} - Updated user
 */
export async function updateProfile(username) {
    const response = await fetch('/api/users/profile', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + getAccessToken()
        },
        body: JSON.stringify({ username })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to update profile');
    }

    const data = await response.json();
    setUser(data.user);
    return data.user;
}

/**
 * Initialize activity monitoring (placeholder for compatibility)
 */
export function initActivityMonitor() {
    // Activity monitoring implementation
    // This is a placeholder for compatibility with legacy code
    console.log('Activity monitor initialized');
}

/**
 * Start session validation (placeholder for compatibility)
 */
export function startSessionValidation() {
    // Session validation implementation
    // This is a placeholder for compatibility with legacy code
    console.log('Session validation started');
}

/**
 * Clear All Auth Data
 */

export function clearAuth() {
    clearTokens();
    clearUser();
    clearSessionId();
}

/**
 * Redirect Helpers
 */

export function redirectToLogin(returnUrl = null) {
    const url = returnUrl 
        ? '/login.html?return=' + encodeURIComponent(returnUrl)
        : '/login.html';
    window.location.href = url;
}

export function redirectToHome() {
    window.location.href = '/';
}

export function requireAuth() {
    if (!isAuthenticated()) {
        redirectToLogin(window.location.pathname);
        return false;
    }
    return true;
}

export function requireAdmin() {
    if (!isAuthenticated()) {
        redirectToLogin(window.location.pathname);
        return false;
    }
    if (!isAdmin()) {
        alert('관리자 권한이 필요합니다.');
        redirectToHome();
        return false;
    }
    return true;
}
