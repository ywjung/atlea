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
