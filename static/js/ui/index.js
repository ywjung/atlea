/**
 * UI Module Index
 *
 * Central export for all UI components.
 */

// Re-export all UI modules
export * from './toast.js';
export * from './loading.js';
export * from './theme.js';
export * from './modal.js';

// Named exports for convenience
export {
    showToast,
    showNotification
} from './toast.js';

export {
    showLoading,
    updateLoadingMessage,
    hideLoading,
    createSpinner
} from './loading.js';

export {
    initTheme,
    toggleTheme,
    setTheme,
    getCurrentTheme,
    isDarkTheme
} from './theme.js';

export {
    pushModal,
    popModal,
    getTopmostModal,
    isAnyModalOpen,
    closeTopmostModal,
    closeAllModals,
    showModal,
    hideModal,
    setupModalBackdropClose,
    setupModalEscHandler
} from './modal.js';
