import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get, post, put, del, apiCall, uploadFile } from '../../../static/js/utils/http.js';

describe('utils/http', () => {
    beforeEach(() => {
        localStorage.clear();
        // Reset fetch mock
        global.fetch = vi.fn();
    });

    describe('apiCall', () => {
        it('should make successful API call', async () => {
            const mockResponse = { data: 'test' };
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => mockResponse,
            });

            const result = await apiCall('/test');
            expect(result).toEqual(mockResponse);
            expect(global.fetch).toHaveBeenCalledWith(
                '/api/test',
                expect.objectContaining({
                    headers: expect.objectContaining({
                        'Content-Type': 'application/json',
                    }),
                })
            );
        });

        it('should add Authorization header when token exists', async () => {
            localStorage.setItem('access_token', 'test-token');

            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => ({}),
            });

            await apiCall('/test');

            expect(global.fetch).toHaveBeenCalledWith(
                '/api/test',
                expect.objectContaining({
                    headers: expect.objectContaining({
                        'Authorization': 'Bearer test-token',
                    }),
                })
            );
        });

        it('should handle endpoints that already have /api prefix', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => ({}),
            });

            await apiCall('/api/test');

            expect(global.fetch).toHaveBeenCalledWith(
                '/api/test',
                expect.any(Object)
            );
        });

        it('should handle non-JSON responses', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'text/plain']]),
                text: async () => 'plain text response',
            });

            const result = await apiCall('/test');
            expect(result).toBe('plain text response');
        });

        it('should handle 401 unauthorized', async () => {
            localStorage.setItem('access_token', 'expired-token');
            localStorage.setItem('user_id', '123');

            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 401,
                statusText: 'Unauthorized',
            });

            // Mock window.location
            delete window.location;
            window.location = { href: '' };

            await expect(apiCall('/test')).rejects.toThrow('Authentication required');
            expect(localStorage.getItem('access_token')).toBeNull();
            expect(localStorage.getItem('user_id')).toBeNull();
        });

        it('should handle HTTP errors', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 500,
                statusText: 'Internal Server Error',
                json: async () => ({ error: 'Server error occurred' }),
            });

            await expect(apiCall('/test')).rejects.toThrow('Server error occurred');
        });

        it('should handle HTTP errors without JSON response', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 404,
                statusText: 'Not Found',
                json: async () => {
                    throw new Error('Not JSON');
                },
            });

            await expect(apiCall('/test')).rejects.toThrow('Not Found');
        });

        it('should handle network errors', async () => {
            global.fetch = vi.fn().mockRejectedValue(new Error('Network failure'));

            await expect(apiCall('/test')).rejects.toThrow('Network failure');
        });
    });

    describe('get', () => {
        it('should make GET request', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => ({ result: 'success' }),
            });

            const result = await get('/users');
            expect(result).toEqual({ result: 'success' });
            expect(global.fetch).toHaveBeenCalledWith(
                '/api/users',
                expect.objectContaining({ method: 'GET' })
            );
        });

        it('should handle query parameters', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => ({}),
            });

            await get('/users', { page: 1, limit: 10 });

            expect(global.fetch).toHaveBeenCalledWith(
                '/api/users?page=1&limit=10',
                expect.any(Object)
            );
        });

        it('should handle empty params', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => ({}),
            });

            await get('/users', {});

            expect(global.fetch).toHaveBeenCalledWith('/api/users', expect.any(Object));
        });
    });

    describe('post', () => {
        it('should make POST request with data', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 201,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => ({ id: 1, created: true }),
            });

            const data = { name: 'Test User', email: 'test@example.com' };
            const result = await post('/users', data);

            expect(result).toEqual({ id: 1, created: true });
            expect(global.fetch).toHaveBeenCalledWith(
                '/api/users',
                expect.objectContaining({
                    method: 'POST',
                    body: JSON.stringify(data),
                })
            );
        });

        it('should handle empty data', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => ({}),
            });

            await post('/endpoint');

            expect(global.fetch).toHaveBeenCalledWith(
                '/api/endpoint',
                expect.objectContaining({
                    method: 'POST',
                })
            );
        });
    });

    describe('put', () => {
        it('should make PUT request', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                headers: new Map([['content-type', 'application/json']]),
                json: async () => ({ updated: true }),
            });

            const data = { name: 'Updated Name' };
            const result = await put('/users/1', data);

            expect(result).toEqual({ updated: true });
            expect(global.fetch).toHaveBeenCalledWith(
                '/api/users/1',
                expect.objectContaining({
                    method: 'PUT',
                    body: JSON.stringify(data),
                })
            );
        });
    });

    describe('del', () => {
        it('should make DELETE request', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 204,
                headers: new Map(),
                text: async () => '',
            });

            await del('/users/1');

            expect(global.fetch).toHaveBeenCalledWith(
                '/api/users/1',
                expect.objectContaining({ method: 'DELETE' })
            );
        });
    });

    // uploadFile uses XMLHttpRequest which is difficult to test in jsdom
    // These tests would be better as E2E tests
    describe.skip('uploadFile', () => {
        it('should be tested in E2E tests', () => {
            // uploadFile uses XMLHttpRequest for progress tracking
            // Better tested with real browser in E2E tests
            expect(true).toBe(true);
        });
    });

    describe('Error Handling', () => {
        it('should preserve error messages', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 400,
                statusText: 'Bad Request',
                json: async () => ({ message: 'Custom error message' }),
            });

            await expect(apiCall('/test')).rejects.toThrow('Custom error message');
        });

        it('should handle errors without message field', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 500,
                statusText: 'Internal Server Error',
                json: async () => ({}),
            });

            await expect(apiCall('/test')).rejects.toThrow('HTTP 500');
        });
    });
});
