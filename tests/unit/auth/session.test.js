import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    setTokens,
    getAccessToken,
    getRefreshToken,
    clearTokens,
    setUser,
    getUser,
    clearUser,
    setSessionId,
    getSessionId,
    clearSessionId,
    isAuthenticated,
    isAdmin,
    getUserRole,
    getUserId,
    clearAuth,
} from '../../../static/js/auth/session.js';

describe('auth/session', () => {
    beforeEach(() => {
        localStorage.clear();
        sessionStorage.clear();
    });

    describe('Token Management', () => {
        it('should set and get access token', () => {
            setTokens('access123', 'refresh456');
            expect(getAccessToken()).toBe('access123');
        });

        it('should set and get refresh token', () => {
            setTokens('access123', 'refresh456');
            expect(getRefreshToken()).toBe('refresh456');
        });

        it('should clear tokens', () => {
            setTokens('access123', 'refresh456');
            clearTokens();

            expect(getAccessToken()).toBeNull();
            expect(getRefreshToken()).toBeNull();
        });

        it('should handle null tokens', () => {
            setTokens(null, null);
            expect(getAccessToken()).toBeNull();
            expect(getRefreshToken()).toBeNull();
        });
    });

    describe('User Management', () => {
        it('should set and get user', () => {
            const user = {
                id: 1,
                username: 'testuser',
                email: 'test@example.com',
                role: 'user',
            };

            setUser(user);
            const retrieved = getUser();

            expect(retrieved).toEqual(user);
        });

        it('should clear user', () => {
            const user = { id: 1, username: 'testuser' };
            setUser(user);
            clearUser();

            expect(getUser()).toBeNull();
        });

        it('should get user ID', () => {
            const user = { id: 42, username: 'testuser' };
            setUser(user);

            expect(getUserId()).toBe(42);
        });

        it('should get user role', () => {
            const user = { id: 1, username: 'testuser', role: 'admin' };
            setUser(user);

            expect(getUserRole()).toBe('admin');
        });

        it('should return null for missing user data', () => {
            expect(getUserId()).toBeNull();
            expect(getUserRole()).toBeNull();
        });
    });

    describe('Session ID Management', () => {
        it('should set and get session ID', () => {
            setSessionId('session-123-abc');
            expect(getSessionId()).toBe('session-123-abc');
        });

        it('should clear session ID', () => {
            setSessionId('session-123-abc');
            clearSessionId();

            expect(getSessionId()).toBeNull();
        });
    });

    describe('Authentication Status', () => {
        it('should return true when authenticated', () => {
            setTokens('access123', 'refresh456');
            setUser({ id: 1, username: 'testuser' });

            expect(isAuthenticated()).toBe(true);
        });

        it('should return false when not authenticated (no token)', () => {
            setUser({ id: 1, username: 'testuser' });
            expect(isAuthenticated()).toBe(false);
        });

        it('should return false when not authenticated (no user)', () => {
            setTokens('access123', 'refresh456');
            expect(isAuthenticated()).toBe(false);
        });

        it('should return false when nothing is set', () => {
            expect(isAuthenticated()).toBe(false);
        });
    });

    describe('Admin Check', () => {
        it('should return true for admin users', () => {
            setUser({ id: 1, username: 'admin', role: 'admin' });
            expect(isAdmin()).toBe(true);
        });

        it('should return false for non-admin users', () => {
            setUser({ id: 2, username: 'user', role: 'user' });
            expect(isAdmin()).toBe(false);
        });

        it('should return false when no user is set', () => {
            expect(isAdmin()).toBe(false);
        });

        it('should handle case-insensitive role check', () => {
            setUser({ id: 1, username: 'admin', role: 'Admin' });
            expect(isAdmin()).toBe(true);
        });
    });

    describe('Clear All Auth Data', () => {
        it('should clear all authentication data', () => {
            setTokens('access123', 'refresh456');
            setUser({ id: 1, username: 'testuser' });
            setSessionId('session-123');

            clearAuth();

            expect(getAccessToken()).toBeNull();
            expect(getRefreshToken()).toBeNull();
            expect(getUser()).toBeNull();
            expect(getSessionId()).toBeNull();
            expect(isAuthenticated()).toBe(false);
        });
    });

    describe('Edge Cases', () => {
        it('should handle malformed user data', () => {
            localStorage.setItem('user', 'not valid json {');
            expect(getUser()).toBeNull();
        });

        it('should handle empty strings', () => {
            setTokens('', '');
            expect(getAccessToken()).toBeNull();
            expect(getRefreshToken()).toBeNull();
        });

        it('should handle user without role', () => {
            setUser({ id: 1, username: 'testuser' });
            expect(getUserRole()).toBeNull();
            expect(isAdmin()).toBe(false);
        });

        it('should handle user without id', () => {
            setUser({ username: 'testuser' });
            expect(getUserId()).toBeNull();
        });
    });
});
