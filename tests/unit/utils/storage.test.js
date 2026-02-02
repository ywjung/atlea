import { describe, it, expect, beforeEach } from 'vitest';
import { getItem, setItem, removeItem, session } from '../../../static/js/utils/storage.js';

describe('utils/storage', () => {
    beforeEach(() => {
        localStorage.clear();
        sessionStorage.clear();
    });

    describe('localStorage operations', () => {
        it('should set and get items', () => {
            setItem('testKey', 'testValue');
            expect(getItem('testKey')).toBe('testValue');
        });

        it('should handle JSON objects', () => {
            const testObj = { name: 'Test', value: 123 };
            setItem('testObj', testObj);

            const retrieved = getItem('testObj');
            expect(retrieved).toEqual(testObj);
        });

        it('should remove items', () => {
            setItem('testKey', 'testValue');
            removeItem('testKey');

            expect(getItem('testKey')).toBeNull();
        });

        it('should return null for non-existent keys', () => {
            expect(getItem('nonExistent')).toBeNull();
        });

        it('should handle arrays', () => {
            const testArray = [1, 2, 3, 'four', { five: 5 }];
            setItem('testArray', testArray);

            const retrieved = getItem('testArray');
            expect(retrieved).toEqual(testArray);
        });

        it('should overwrite existing values', () => {
            setItem('testKey', 'oldValue');
            setItem('testKey', 'newValue');

            expect(getItem('testKey')).toBe('newValue');
        });
    });

    describe('sessionStorage operations', () => {
        it('should set and get session items', () => {
            session.setItem('sessionKey', 'sessionValue');
            expect(session.getItem('sessionKey')).toBe('sessionValue');
        });

        it('should handle JSON objects in session', () => {
            const testObj = { temp: 'data' };
            session.setItem('sessionObj', testObj);

            const retrieved = session.getItem('sessionObj');
            expect(retrieved).toEqual(testObj);
        });

        it('should remove session items', () => {
            session.setItem('sessionKey', 'sessionValue');
            session.removeItem('sessionKey');

            expect(session.getItem('sessionKey')).toBeNull();
        });

        it('should be independent from localStorage', () => {
            setItem('key', 'localStorage');
            session.setItem('key', 'sessionStorage');

            expect(getItem('key')).toBe('localStorage');
            expect(session.getItem('key')).toBe('sessionStorage');
        });
    });

    describe('error handling', () => {
        it('should handle invalid JSON gracefully', () => {
            localStorage.setItem('invalidJSON', 'not json {');
            const result = getItem('invalidJSON');

            expect(result).toBe('not json {'); // Returns as string
        });

        it('should handle null values', () => {
            setItem('nullKey', null);
            expect(getItem('nullKey')).toBeNull();
        });

        it('should handle undefined values', () => {
            setItem('undefinedKey', undefined);
            const result = getItem('undefinedKey');

            expect(result).toBeNull();
        });
    });

    describe('data persistence', () => {
        it('should persist primitive types correctly', () => {
            setItem('string', 'text');
            setItem('number', 42);
            setItem('boolean', true);

            expect(getItem('string')).toBe('text');
            expect(getItem('number')).toBe(42);
            expect(getItem('boolean')).toBe(true);
        });

        it('should persist nested objects', () => {
            const nested = {
                level1: {
                    level2: {
                        level3: 'deep value',
                    },
                },
            };

            setItem('nested', nested);
            const retrieved = getItem('nested');

            expect(retrieved.level1.level2.level3).toBe('deep value');
        });
    });
});
