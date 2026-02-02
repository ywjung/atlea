/**
 * Application Initialization
 *
 * Main initialization and coordination for the chat application.
 */

import { initTheme } from '../ui/theme.js';
import { setupModalEscHandler } from '../ui/modal.js';
import { initMarked } from '../markdown/config.js';
import { isAuthenticated, redirectToLogin } from '../auth/session.js';

/**
 * Initialize application
 */
export async function initApp() {
    // Initialize theme before anything else to prevent flash
    initTheme();

    // Setup global modal ESC key handler
    setupModalEscHandler();

    // Initialize markdown renderer
    initMarked();

    // Check authentication
    if (!isAuthenticated()) {
        redirectToLogin(window.location.pathname);
        return false;
    }

    return true;
}

/**
 * Initialize page-specific features
 * @param {Object} options - Initialization options
 * @param {boolean} options.chat - Initialize chat features
 * @param {boolean} options.admin - Initialize admin features
 * @param {boolean} options.documents - Initialize document features
 */
export async function initFeatures(options = {}) {
    const { chat = false, admin = false, documents = false } = options;

    if (chat) {
        await initChatFeatures();
    }

    if (admin) {
        await initAdminFeatures();
    }

    if (documents) {
        await initDocumentFeatures();
    }
}

/**
 * Initialize chat-specific features
 */
async function initChatFeatures() {
    // Chat initialization will be implemented as modules are integrated
    // This is a placeholder for progressive migration
    console.log('Chat features initialized');
}

/**
 * Initialize admin-specific features
 */
async function initAdminFeatures() {
    // Admin initialization placeholder
    console.log('Admin features initialized');
}

/**
 * Initialize document-specific features
 */
async function initDocumentFeatures() {
    // Document initialization placeholder
    console.log('Document features initialized');
}
