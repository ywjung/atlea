/**
 * Registration Module
 * 
 * User registration functionality.
 */

import { post } from '../utils/http.js';
import { setTokens, setUser } from './session.js';

/**
 * Register new user
 * @param {string} email - User email
 * @param {string} username - Username
 * @param {string} password - Password
 * @param {string} captchaId - Optional captcha ID
 * @param {string} captchaAnswer - Optional captcha answer
 * @returns {Promise<Object>} - Registration response
 */
export async function register(email, username, password, captchaId = null, captchaAnswer = null) {
    try {
        const data = {
            email,
            username,
            password
        };

        if (captchaId && captchaAnswer) {
            data.captcha_id = captchaId;
            data.captcha_answer = captchaAnswer;
        }

        const response = await post('/auth/register', data);

        // Auto-login after registration
        if (response.tokens) {
            setTokens(response.tokens.access_token, response.tokens.refresh_token);
        }
        
        if (response.user) {
            setUser(response.user);
        }

        return response;
    } catch (error) {
        console.error('Registration failed:', error);
        throw error;
    }
}

/**
 * Generate captcha for registration
 * @param {string} action - Action type (default: 'register')
 * @returns {Promise<Object>} - Captcha data with ID and image
 */
export async function generateCaptcha(action = 'register') {
    try {
        const response = await post('/auth/captcha/generate', { action });
        return response;
    } catch (error) {
        console.error('Captcha generation failed:', error);
        throw error;
    }
}
