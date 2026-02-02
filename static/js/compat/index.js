/**
 * Compatibility Layer Index
 *
 * Provides backward compatibility bridges for legacy code.
 */

export { default as Auth } from './auth-bridge.js';

/**
 * Initialize all compatibility bridges
 * Call this to setup global objects for legacy code
 */
export function initCompatibilityLayer() {
    // Auth bridge is auto-initialized via window.Auth
    // Add other compatibility layers here as needed
    console.log('✅ Compatibility layer initialized');
}
