/**
 * Login Module
 * 
 * Login and logout functionality.
 */

import { post } from '../utils/http.js';
import { setTokens, setUser, clearAuth } from './session.js';

/**
 * Login with email and password
 * @param {string} email - User email
 * @param {string} password - User password
 * @param {string} totpToken - Optional TOTP token for 2FA
 * @returns {Promise<Object>} - Login response
 */
export async function login(email, password, totpToken = null) {
    try {
        const response = await post('/auth/login', {
            email,
            password,
            totp_token: totpToken
        });

        // Store tokens and user data
        if (response.tokens) {
            setTokens(response.tokens.access_token, response.tokens.refresh_token);
        }
        
        if (response.user) {
            setUser(response.user);
        }

        return response;
    } catch (error) {
        console.error('Login failed:', error);
        throw error;
    }
}

/**
 * Logout current user
 * @returns {Promise<void>}
 */
export async function logout() {
    try {
        await post('/auth/logout');
    } catch (error) {
        console.error('Logout API failed:', error);
    } finally {
        clearAuth();
        window.location.href = '/login.html';
    }
}

/**
 * Refresh access token
 * @returns {Promise<Object>} - New tokens
 */
export async function refreshToken() {
    try {
        const response = await post('/auth/refresh');
        
        if (response.tokens) {
            setTokens(response.tokens.access_token, response.tokens.refresh_token);
        }
        
        return response;
    } catch (error) {
        console.error('Token refresh failed:', error);
        clearAuth();
        throw error;
    }
}

/**
 * Validate current session
 * @returns {Promise<boolean>} - True if session is valid
 */
export async function validateSession() {
    try {
        const response = await post('/auth/validate');
        return response.valid === true;
    } catch (error) {
        return false;
    }
}
