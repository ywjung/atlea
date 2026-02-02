import { describe, it, expect } from 'vitest';
import {
    validateEmail,
    validatePassword,
    validateUsername,
    sanitizeFilename,
} from '../../../static/js/utils/validation.js';

describe('utils/validation', () => {
    describe('validateEmail', () => {
        it('should validate correct email addresses', () => {
            expect(validateEmail('user@example.com')).toBe(true);
            expect(validateEmail('test.user@domain.co.uk')).toBe(true);
            expect(validateEmail('user+tag@example.com')).toBe(true);
        });

        it('should reject invalid email addresses', () => {
            expect(validateEmail('invalid')).toBe(false);
            expect(validateEmail('invalid@')).toBe(false);
            expect(validateEmail('@example.com')).toBe(false);
            expect(validateEmail('user@')).toBe(false);
            expect(validateEmail('')).toBe(false);
        });

        it('should handle edge cases', () => {
            expect(validateEmail(null)).toBe(false);
            expect(validateEmail(undefined)).toBe(false);
            expect(validateEmail('user @example.com')).toBe(false); // Space in email
        });
    });

    describe('validatePassword', () => {
        it('should accept strong passwords', () => {
            const result = validatePassword('StrongPass123!');
            expect(result.valid).toBe(true);
            expect(result.strength).toBe('strong');
        });

        it('should reject passwords without uppercase', () => {
            const result = validatePassword('weakpass123!');
            expect(result.valid).toBe(false);
            expect(result.errors).toContain('대문자를 최소 1개 포함해야 합니다.');
        });

        it('should reject passwords without lowercase', () => {
            const result = validatePassword('WEAKPASS123!');
            expect(result.valid).toBe(false);
            expect(result.errors).toContain('소문자를 최소 1개 포함해야 합니다.');
        });

        it('should reject passwords without numbers', () => {
            const result = validatePassword('WeakPass!');
            expect(result.valid).toBe(false);
            expect(result.errors).toContain('숫자를 최소 1개 포함해야 합니다.');
        });

        it('should reject passwords without special characters', () => {
            const result = validatePassword('WeakPass123');
            expect(result.valid).toBe(false);
            expect(result.errors).toContain('특수문자를 최소 1개 포함해야 합니다.');
        });

        it('should reject passwords shorter than 8 characters', () => {
            const result = validatePassword('Weak1!');
            expect(result.valid).toBe(false);
            expect(result.errors).toContain('비밀번호는 최소 8자 이상이어야 합니다.');
        });

        it('should reject passwords with spaces', () => {
            const result = validatePassword('Weak Pass123!');
            expect(result.valid).toBe(false);
            expect(result.errors).toContain('공백을 포함할 수 없습니다.');
        });

        it('should return all errors for very weak passwords', () => {
            const result = validatePassword('weak');
            expect(result.valid).toBe(false);
            expect(result.errors.length).toBeGreaterThan(3);
        });
    });

    describe('validateUsername', () => {
        it('should accept valid usernames', () => {
            expect(validateUsername('user123')).toBe(true);
            expect(validateUsername('test_user')).toBe(true);
            expect(validateUsername('user-name')).toBe(true);
        });

        it('should reject usernames that are too short', () => {
            expect(validateUsername('ab')).toBe(false);
        });

        it('should reject usernames with invalid characters', () => {
            expect(validateUsername('user@name')).toBe(false);
            expect(validateUsername('user name')).toBe(false); // Space
            expect(validateUsername('user!name')).toBe(false);
        });

        it('should reject empty or null usernames', () => {
            expect(validateUsername('')).toBe(false);
            expect(validateUsername(null)).toBe(false);
            expect(validateUsername(undefined)).toBe(false);
        });
    });

    describe('sanitizeFilename', () => {
        it('should remove dangerous characters', () => {
            expect(sanitizeFilename('../../../etc/passwd')).not.toContain('..');
            expect(sanitizeFilename('file<script>.txt')).not.toContain('<');
            expect(sanitizeFilename('file>script.txt')).not.toContain('>');
        });

        it('should preserve safe characters', () => {
            expect(sanitizeFilename('my-file_name.txt')).toBe('my-file_name.txt');
            expect(sanitizeFilename('document_v2.pdf')).toBe('document_v2.pdf');
        });

        it('should handle edge cases', () => {
            expect(sanitizeFilename('')).toBe('');
            expect(sanitizeFilename('   ')).toBe('');
        });
    });
});
