import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
    formatTimestamp,
    formatDate,
    formatDateTime,
    formatFileSize,
    formatNumber,
} from '../../../static/js/utils/formatters.js';

describe('utils/formatters', () => {
    beforeEach(() => {
        // Mock system time for consistent test results
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2024-01-15T12:00:00.000Z'));
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    describe('formatTimestamp', () => {
        it('should format recent timestamp as "방금 전"', () => {
            const timestamp = new Date('2024-01-15T11:59:30.000Z');
            expect(formatTimestamp(timestamp)).toBe('방금 전');
        });

        it('should format minutes ago', () => {
            const timestamp = new Date('2024-01-15T11:55:00.000Z');
            expect(formatTimestamp(timestamp)).toBe('5분 전');
        });

        it('should format hours ago', () => {
            const timestamp = new Date('2024-01-15T10:00:00.000Z');
            expect(formatTimestamp(timestamp)).toBe('2시간 전');
        });

        it('should format days ago', () => {
            const timestamp = new Date('2024-01-13T12:00:00.000Z');
            expect(formatTimestamp(timestamp)).toBe('2일 전');
        });

        it('should format full date for old timestamps', () => {
            const timestamp = new Date('2024-01-01T12:00:00.000Z');
            const result = formatTimestamp(timestamp);
            expect(result).toMatch(/2024/);
            expect(result).toMatch(/01/);
        });

        it('should handle string timestamps', () => {
            const timestamp = '2024-01-15T11:55:00.000Z';
            expect(formatTimestamp(timestamp)).toBe('5분 전');
        });
    });

    describe('formatDate', () => {
        it('should format today as "오늘"', () => {
            const isoString = '2024-01-15T10:00:00.000Z';
            expect(formatDate(isoString)).toBe('오늘');
        });

        it('should format yesterday as "어제"', () => {
            const isoString = '2024-01-14T10:00:00.000Z';
            expect(formatDate(isoString)).toBe('어제');
        });

        it('should format recent days', () => {
            const isoString = '2024-01-13T10:00:00.000Z';
            expect(formatDate(isoString)).toBe('2일 전');
        });

        it('should format old dates with full format', () => {
            const isoString = '2024-01-01T10:00:00.000Z';
            const result = formatDate(isoString);
            expect(result).toMatch(/2024/);
            expect(result).toMatch(/1월/);
        });
    });

    describe('formatDateTime', () => {
        it('should format datetime with Korean locale', () => {
            const isoString = '2024-01-15T14:30:45.000Z';
            const result = formatDateTime(isoString);
            expect(result).toMatch(/2024/);
            expect(result).toMatch(/01/);
            expect(result).toMatch(/15/);
        });

        it('should use 24-hour format', () => {
            const isoString = '2024-01-15T23:30:45.000Z';
            const result = formatDateTime(isoString);
            // Should not contain AM/PM indicators
            expect(result).not.toMatch(/오전|오후|AM|PM/);
        });
    });

    describe('formatFileSize', () => {
        it('should format zero bytes', () => {
            expect(formatFileSize(0)).toBe('0 Bytes');
        });

        it('should format bytes', () => {
            expect(formatFileSize(500)).toBe('500 Bytes');
        });

        it('should format kilobytes', () => {
            expect(formatFileSize(1024)).toBe('1 KB');
            expect(formatFileSize(1536)).toBe('1.5 KB');
        });

        it('should format megabytes', () => {
            expect(formatFileSize(1048576)).toBe('1 MB');
            expect(formatFileSize(1572864)).toBe('1.5 MB');
        });

        it('should format gigabytes', () => {
            expect(formatFileSize(1073741824)).toBe('1 GB');
            expect(formatFileSize(1610612736)).toBe('1.5 GB');
        });

        it('should format large files', () => {
            expect(formatFileSize(1099511627776)).toBe('1 TB');
        });

        it('should round to 2 decimal places', () => {
            expect(formatFileSize(1234567)).toBe('1.18 MB');
        });
    });

    describe('formatNumber', () => {
        it('should format numbers with thousand separators', () => {
            expect(formatNumber(1000)).toBe('1,000');
            expect(formatNumber(1234567)).toBe('1,234,567');
        });

        it('should handle small numbers', () => {
            expect(formatNumber(100)).toBe('100');
            expect(formatNumber(999)).toBe('999');
        });

        it('should handle zero', () => {
            expect(formatNumber(0)).toBe('0');
        });

        it('should handle negative numbers', () => {
            expect(formatNumber(-1234)).toBe('-1,234');
        });

        it('should handle decimal numbers', () => {
            const result = formatNumber(1234.56);
            expect(result).toMatch(/1,234/);
        });
    });
});
