/**
 * Input Validation
 *
 * Validates user input for security and constraints.
 */

/**
 * Input validation configuration
 */
export const INPUT_VALIDATION = {
    MIN_LENGTH: 1,
    MAX_LENGTH: 5000,
    FORBIDDEN_PATTERNS: [
        /<script[^>]*>.*?<\/script>/gi,  // Script tags
        /<iframe[^>]*>.*?<\/iframe>/gi,  // Iframe tags
        /javascript:/gi,                  // JavaScript protocol
        /on\w+\s*=/gi                     // Event handlers (onclick, onload, etc.)
    ]
};

/**
 * Validate user input
 * @param {string} text - Input text to validate
 * @returns {Object} - Validation result {valid: boolean, error?: string, normalized?: string}
 */
export function validateInput(text) {
    // Remove leading/trailing whitespace
    const trimmed = text.trim();

    // Check if empty
    if (trimmed.length === 0) {
        return { valid: false, error: '질문을 입력해주세요.' };
    }

    // Check minimum length
    if (trimmed.length < INPUT_VALIDATION.MIN_LENGTH) {
        return { valid: false, error: `최소 ${INPUT_VALIDATION.MIN_LENGTH}자 이상 입력해주세요.` };
    }

    // Check maximum length
    if (trimmed.length > INPUT_VALIDATION.MAX_LENGTH) {
        return { valid: false, error: `최대 ${INPUT_VALIDATION.MAX_LENGTH}자까지 입력 가능합니다. (현재: ${trimmed.length}자)` };
    }

    // Check for forbidden patterns (XSS prevention)
    for (const pattern of INPUT_VALIDATION.FORBIDDEN_PATTERNS) {
        if (pattern.test(trimmed)) {
            return { valid: false, error: '허용되지 않는 문자나 태그가 포함되어 있습니다.' };
        }
    }

    // Normalize consecutive whitespace
    const normalized = trimmed.replace(/\s+/g, ' ');

    return { valid: true, normalized };
}

/**
 * Validate email format
 * @param {string} email - Email address to validate
 * @returns {boolean} - True if valid email format
 */
export function validateEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Validate password strength with detailed requirements
 * @param {string} password - Password to validate
 * @returns {Object} - Validation result {valid: boolean, errors?: string[], strength?: string}
 */
export function validatePassword(password) {
    const errors = [];

    // Check length
    if (password.length < 8) {
        errors.push('비밀번호는 최소 8자 이상이어야 합니다.');
    }

    if (password.length > 128) {
        errors.push('비밀번호는 최대 128자까지 가능합니다.');
    }

    // Check for uppercase
    if (!/[A-Z]/.test(password)) {
        errors.push('대문자를 최소 1개 포함해야 합니다.');
    }

    // Check for lowercase
    if (!/[a-z]/.test(password)) {
        errors.push('소문자를 최소 1개 포함해야 합니다.');
    }

    // Check for digit
    if (!/[0-9]/.test(password)) {
        errors.push('숫자를 최소 1개 포함해야 합니다.');
    }

    // Check for special character
    if (!/[!@#$%^&*()_+\-=\[\]{}|;:',.<>?/~`]/.test(password)) {
        errors.push('특수문자를 최소 1개 포함해야 합니다.');
    }

    // Check for no whitespace
    if (/\s/.test(password)) {
        errors.push('공백을 포함할 수 없습니다.');
    }

    // If there are errors, return invalid
    if (errors.length > 0) {
        return { valid: false, errors };
    }

    // Determine strength for valid passwords
    const hasUpperCase = /[A-Z]/.test(password);
    const hasLowerCase = /[a-z]/.test(password);
    const hasNumber = /[0-9]/.test(password);
    const hasSpecial = /[!@#$%^&*()_+\-=\[\]{}|;:',.<>?/~`]/.test(password);

    let strength = 'weak';
    const criteria = [hasUpperCase, hasLowerCase, hasNumber, hasSpecial].filter(Boolean).length;

    if (password.length >= 12 && criteria >= 4) {
        strength = 'strong';
    } else if (password.length >= 10 && criteria >= 3) {
        strength = 'medium';
    }

    return { valid: true, strength };
}

/**
 * Validate username
 * @param {string} username - Username to validate
 * @returns {Object} - Validation result {valid: boolean, error?: string}
 */
export function validateUsername(username) {
    if (username.length < 3) {
        return { valid: false, error: '사용자 이름은 최소 3자 이상이어야 합니다.' };
    }

    if (username.length > 50) {
        return { valid: false, error: '사용자 이름은 최대 50자까지 가능합니다.' };
    }

    // Allow letters, numbers, underscore, hyphen
    const usernameRegex = /^[a-zA-Z0-9_-]+$/;
    if (!usernameRegex.test(username)) {
        return { valid: false, error: '사용자 이름은 영문자, 숫자, -, _만 사용 가능합니다.' };
    }

    return { valid: true };
}

/**
 * Sanitize filename
 * @param {string} filename - Filename to sanitize
 * @returns {string} - Sanitized filename
 */
export function sanitizeFilename(filename) {
    // Remove path separators and dangerous characters
    return filename
        .replace(/[/\\]/g, '_')
        .replace(/\.\./g, '_')
        .replace(/[<>:"|?*]/g, '_')
        .trim();
}
