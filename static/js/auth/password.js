/**
 * Password Management Module
 * 
 * Password change and reset functionality.
 */

import { post } from '../utils/http.js';

/**
 * Change password for current user
 * @param {string} oldPassword - Current password
 * @param {string} newPassword - New password
 * @returns {Promise<Object>} - Response
 */
export async function changePassword(oldPassword, newPassword) {
    try {
        const response = await post('/auth/change-password', {
            old_password: oldPassword,
            new_password: newPassword
        });
        return response;
    } catch (error) {
        console.error('Password change failed:', error);
        throw error;
    }
}

/**
 * Request password reset email
 * @param {string} email - User email
 * @returns {Promise<Object>} - Response
 */
export async function requestPasswordReset(email) {
    try {
        const response = await post('/auth/password-reset/request', { email });
        return response;
    } catch (error) {
        console.error('Password reset request failed:', error);
        throw error;
    }
}

/**
 * Confirm password reset with token
 * @param {string} token - Reset token from email
 * @param {string} newPassword - New password
 * @returns {Promise<Object>} - Response
 */
export async function confirmPasswordReset(token, newPassword) {
    try {
        const response = await post('/auth/password-reset/confirm', {
            token,
            new_password: newPassword
        });
        return response;
    } catch (error) {
        console.error('Password reset confirmation failed:', error);
        throw error;
    }
}
