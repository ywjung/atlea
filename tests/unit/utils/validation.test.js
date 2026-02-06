import { describe, it, expect } from 'vitest';
import {
    validateEmail,
    validatePassword,
    validateUsername,
    sanitizeFilename,
    validateInput,
    INPUT_VALIDATION,
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
            const result1 = validateUsername('user123');
            expect(result1.valid).toBe(true);

            const result2 = validateUsername('test_user');
            expect(result2.valid).toBe(true);

            const result3 = validateUsername('user-name');
            expect(result3.valid).toBe(true);
        });

        it('should reject usernames that are too short', () => {
            const result = validateUsername('ab');
            expect(result.valid).toBe(false);
            expect(result.error).toContain('최소 3자');
        });

        it('should reject usernames with invalid characters', () => {
            const result1 = validateUsername('user@name');
            expect(result1.valid).toBe(false);
            expect(result1.error).toContain('영문자, 숫자, -, _');

            const result2 = validateUsername('user name');
            expect(result2.valid).toBe(false);

            const result3 = validateUsername('user!name');
            expect(result3.valid).toBe(false);
        });

        it('should handle edge cases', () => {
            // Too long
            const longUsername = 'a'.repeat(51);
            const result1 = validateUsername(longUsername);
            expect(result1.valid).toBe(false);
            expect(result1.error).toContain('최대 50자');
        });
    });

    describe('validateInput', () => {
        it('should accept valid input', () => {
            const result = validateInput('This is a valid question');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('This is a valid question');
        });

        it('should reject empty input', () => {
            const result = validateInput('');
            expect(result.valid).toBe(false);
            expect(result.error).toContain('질문을 입력해주세요');
        });

        it('should reject whitespace-only input', () => {
            const result = validateInput('   ');
            expect(result.valid).toBe(false);
            expect(result.error).toContain('질문을 입력해주세요');
        });

        it('should reject input that is too long', () => {
            const longInput = 'a'.repeat(INPUT_VALIDATION.MAX_LENGTH + 1);
            const result = validateInput(longInput);

            expect(result.valid).toBe(false);
            expect(result.error).toContain('최대');
        });

        it('should reject input with script tags', () => {
            const result = validateInput('<script>alert("xss")</script>');
            expect(result.valid).toBe(false);
            expect(result.error).toContain('허용되지 않는');
        });

        it('should reject input with iframe tags', () => {
            const result = validateInput('<iframe src="evil.com"></iframe>');
            expect(result.valid).toBe(false);
            expect(result.error).toContain('허용되지 않는');
        });

        it('should reject input with javascript protocol', () => {
            const result = validateInput('javascript:alert("xss")');
            expect(result.valid).toBe(false);
            expect(result.error).toContain('허용되지 않는');
        });

        it('should reject input with event handlers', () => {
            const result = validateInput('<div onclick="alert()">test</div>');
            expect(result.valid).toBe(false);
            expect(result.error).toContain('허용되지 않는');
        });

        it('should normalize consecutive whitespace', () => {
            const result = validateInput('This   has    multiple    spaces');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('This has multiple spaces');
        });

        it('should trim leading and trailing whitespace', () => {
            const result = validateInput('  test  ');
            expect(result.valid).toBe(true);
            expect(result.normalized).toBe('test');
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
