import { describe, it, expect, vi } from 'vitest';
import {
    generateSessionId,
    generateId,
    generateUUID,
    sleep,
    retry,
    copyToClipboard,
    downloadAsFile,
    parseQueryString,
    buildQueryString,
    getUrlParams,
    isInViewport,
    scrollIntoView,
    getBrowserInfo,
    isFeatureSupported,
} from '../../../static/js/utils/helpers.js';

describe('utils/helpers', () => {
    describe('generateSessionId', () => {
        it('should generate unique session IDs', () => {
            const id1 = generateSessionId();
            const id2 = generateSessionId();

            expect(id1).toBeTruthy();
            expect(id2).toBeTruthy();
            expect(id1).not.toBe(id2);
            expect(id1).toMatch(/^session_/);
        });

        it('should include timestamp', () => {
            const id = generateSessionId();
            expect(id).toMatch(/^session_\d+_/);
        });
    });

    describe('generateId', () => {
        it('should generate unique IDs', () => {
            const id1 = generateId();
            const id2 = generateId();

            expect(id1).toBeTruthy();
            expect(id2).toBeTruthy();
            expect(id1).not.toBe(id2);
        });

        it('should use default prefix', () => {
            const id = generateId();
            expect(id).toMatch(/^id_/);
        });

        it('should use custom prefix', () => {
            const id = generateId('custom');
            expect(id).toMatch(/^custom_/);
        });

        it('should generate IDs of correct length', () => {
            const id = generateId();
            expect(id.length).toBeGreaterThan(15);
        });
    });

    describe('generateUUID', () => {
        it('should generate valid UUIDs', () => {
            const uuid = generateUUID();
            const uuidRegex =
                /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

            expect(uuid).toMatch(uuidRegex);
        });

        it('should generate unique UUIDs', () => {
            const uuid1 = generateUUID();
            const uuid2 = generateUUID();

            expect(uuid1).not.toBe(uuid2);
        });

        it('should have correct UUID v4 format', () => {
            const uuid = generateUUID();
            const parts = uuid.split('-');

            expect(parts).toHaveLength(5);
            expect(parts[2][0]).toBe('4'); // Version 4
        });
    });

    describe('sleep', () => {
        it('should delay execution', async () => {
            const start = Date.now();
            await sleep(100);
            const duration = Date.now() - start;

            expect(duration).toBeGreaterThanOrEqual(90);
        });

        it('should return a promise', () => {
            const result = sleep(10);
            expect(result).toBeInstanceOf(Promise);
        });
    });

    describe('retry', () => {
        it('should retry on failure', async () => {
            let attempts = 0;
            const fn = async () => {
                attempts++;
                if (attempts < 3) {
                    throw new Error('Failed');
                }
                return 'success';
            };

            const result = await retry(fn, 3, 10);
            expect(result).toBe('success');
            expect(attempts).toBe(3);
        });

        it('should throw after max retries', async () => {
            const fn = async () => {
                throw new Error('Always fails');
            };

            await expect(retry(fn, 2, 10)).rejects.toThrow('Always fails');
        });

        it('should succeed on first try', async () => {
            const fn = async () => 'immediate success';
            const result = await retry(fn, 3, 10);

            expect(result).toBe('immediate success');
        });
    });

    describe('parseQueryString', () => {
        it('should parse query string', () => {
            const result = parseQueryString('?name=test&age=25');
            expect(result).toEqual({ name: 'test', age: '25' });
        });

        it('should handle query string without ?', () => {
            const result = parseQueryString('name=test&age=25');
            expect(result).toEqual({ name: 'test', age: '25' });
        });

        it('should decode URL encoding', () => {
            const result = parseQueryString('name=John%20Doe');
            expect(result).toEqual({ name: 'John Doe' });
        });

        it('should handle empty query string', () => {
            const result = parseQueryString('');
            expect(result).toEqual({});
        });

        it('should handle missing values', () => {
            const result = parseQueryString('key1=&key2=value');
            expect(result).toEqual({ key1: '', key2: 'value' });
        });
    });

    describe('buildQueryString', () => {
        it('should build query string from object', () => {
            const params = { name: 'test', age: 25 };
            const result = buildQueryString(params);

            expect(result).toBe('name=test&age=25');
        });

        it('should encode special characters', () => {
            const params = { name: 'John Doe' };
            const result = buildQueryString(params);

            expect(result).toBe('name=John%20Doe');
        });

        it('should skip null and undefined values', () => {
            const params = { name: 'test', age: null, city: undefined };
            const result = buildQueryString(params);

            expect(result).toBe('name=test');
        });

        it('should handle empty object', () => {
            const result = buildQueryString({});
            expect(result).toBe('');
        });
    });

    describe('getBrowserInfo', () => {
        it('should return browser information', () => {
            const info = getBrowserInfo();

            expect(info).toHaveProperty('name');
            expect(info).toHaveProperty('version');
            expect(info).toHaveProperty('os');
        });

        it('should have string values', () => {
            const info = getBrowserInfo();

            expect(typeof info.name).toBe('string');
            expect(typeof info.version).toBe('string');
            expect(typeof info.os).toBe('string');
        });
    });

    describe('isFeatureSupported', () => {
        it('should check for localStorage', () => {
            const supported = isFeatureSupported('localStorage');
            expect(typeof supported).toBe('boolean');
        });

        it('should check for sessionStorage', () => {
            const supported = isFeatureSupported('sessionStorage');
            expect(typeof supported).toBe('boolean');
        });

        it('should return false for unknown features', () => {
            const supported = isFeatureSupported('nonExistentFeature');
            expect(supported).toBe(false);
        });

        it('should support multiple feature checks', () => {
            const features = [
                'localStorage',
                'sessionStorage',
                'webWorker',
                'serviceWorker',
            ];

            features.forEach((feature) => {
                const supported = isFeatureSupported(feature);
                expect(typeof supported).toBe('boolean');
            });
        });
    });
});
