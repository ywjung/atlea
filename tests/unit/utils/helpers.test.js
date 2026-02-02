import { describe, it, expect, vi } from 'vitest';
import {
    formatTimestamp,
    formatFileSize,
    formatNumber,
    debounce,
    throttle,
    generateId,
    generateUUID,
    sleep,
} from '../../../static/js/utils/helpers.js';

describe('utils/helpers', () => {
    describe('formatTimestamp', () => {
        it('should format ISO timestamp to readable date', () => {
            const timestamp = '2024-01-15T10:30:00Z';
            const result = formatTimestamp(timestamp);
            expect(result).toContain('2024');
            expect(result).toContain('Jan');
        });

        it('should handle invalid timestamps', () => {
            expect(formatTimestamp('')).toBe('');
            expect(formatTimestamp(null)).toBe('');
            expect(formatTimestamp('invalid')).toBe('Invalid Date');
        });
    });

    describe('formatFileSize', () => {
        it('should format bytes correctly', () => {
            expect(formatFileSize(500)).toBe('500 B');
            expect(formatFileSize(1024)).toBe('1.00 KB');
            expect(formatFileSize(1048576)).toBe('1.00 MB');
            expect(formatFileSize(1073741824)).toBe('1.00 GB');
        });

        it('should handle zero and negative values', () => {
            expect(formatFileSize(0)).toBe('0 B');
            expect(formatFileSize(-100)).toBe('0 B');
        });

        it('should handle decimal precision', () => {
            expect(formatFileSize(1536)).toBe('1.50 KB');
            expect(formatFileSize(2621440)).toBe('2.50 MB');
        });
    });

    describe('formatNumber', () => {
        it('should format numbers with thousands separator', () => {
            expect(formatNumber(1000)).toBe('1,000');
            expect(formatNumber(1000000)).toBe('1,000,000');
        });

        it('should handle small numbers', () => {
            expect(formatNumber(100)).toBe('100');
            expect(formatNumber(0)).toBe('0');
        });

        it('should handle negative numbers', () => {
            expect(formatNumber(-1000)).toBe('-1,000');
        });
    });

    describe('debounce', () => {
        it('should delay function execution', async () => {
            let counter = 0;
            const increment = () => counter++;
            const debounced = debounce(increment, 100);

            debounced();
            debounced();
            debounced();

            expect(counter).toBe(0); // Should not execute immediately

            await sleep(150);
            expect(counter).toBe(1); // Should execute once after delay
        });

        it('should cancel previous calls', async () => {
            let counter = 0;
            const increment = () => counter++;
            const debounced = debounce(increment, 100);

            debounced();
            await sleep(50);
            debounced(); // Resets the timer
            await sleep(50);

            expect(counter).toBe(0); // First call cancelled

            await sleep(100);
            expect(counter).toBe(1); // Only second call executes
        });
    });

    describe('throttle', () => {
        it('should limit function execution rate', async () => {
            let counter = 0;
            const increment = () => counter++;
            const throttled = throttle(increment, 100);

            throttled();
            throttled();
            throttled();

            expect(counter).toBe(1); // Should execute immediately once

            await sleep(150);
            throttled();

            expect(counter).toBe(2); // Should execute again after delay
        });

        it('should maintain execution rate', async () => {
            let counter = 0;
            const increment = () => counter++;
            const throttled = throttle(increment, 100);

            for (let i = 0; i < 10; i++) {
                throttled();
                await sleep(20);
            }

            // Should execute roughly every 100ms
            expect(counter).toBeGreaterThanOrEqual(2);
            expect(counter).toBeLessThanOrEqual(3);
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

        it('should generate IDs of correct length', () => {
            const id = generateId();
            expect(id.length).toBeGreaterThan(8);
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
    });

    describe('sleep', () => {
        it('should delay execution', async () => {
            const start = Date.now();
            await sleep(100);
            const duration = Date.now() - start;

            expect(duration).toBeGreaterThanOrEqual(90); // Allow some timing variance
        });

        it('should return a promise', () => {
            const result = sleep(10);
            expect(result).toBeInstanceOf(Promise);
        });
    });
});
