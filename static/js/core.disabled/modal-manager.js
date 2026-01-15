/**
 * Modal Stack Manager
 * Manages modal display order and ESC key handling
 */

class ModalManager {
    constructor() {
        this.modalStack = [];
        this.setupKeyboardShortcuts();
    }

    /**
     * Push a modal to the stack (when opening)
     */
    push(modalElement, modalName) {
        // Remove if already in stack (prevent duplicates)
        this.modalStack = this.modalStack.filter(item => item.element !== modalElement);
        // Add to end of stack (most recent)
        this.modalStack.push({ element: modalElement, name: modalName });
    }

    /**
     * Remove a modal from the stack (when closing)
     */
    pop(modalElement) {
        this.modalStack = this.modalStack.filter(item => item.element !== modalElement);
    }

    /**
     * Get the topmost (most recently opened) modal
     */
    getTopmost() {
        if (this.modalStack.length === 0) return null;
        return this.modalStack[this.modalStack.length - 1];
    }

    /**
     * Close the topmost modal
     */
    closeTopmost() {
        const topModal = this.getTopmost();
        if (topModal) {
            topModal.element.classList.remove('active');
            this.pop(topModal.element);

            // Special handling for specific modals
            if (topModal.name === 'settings') {
                // Settings panel has overlay and close function
                const settingsOverlay = document.getElementById('settingsOverlay');
                if (settingsOverlay) {
                    settingsOverlay.classList.remove('active');
                }
                const settingsBtn = document.getElementById('settingsBtn');
                if (settingsBtn) {
                    settingsBtn.blur();
                }
            } else if (topModal.name === 'sidebar') {
                // Conversation sidebar has additional classes
                const container = document.querySelector('.container');
                const historyToggleBtn = document.getElementById('historyToggleBtn');
                if (container) container.classList.remove('sidebar-active');
                if (historyToggleBtn) historyToggleBtn.classList.remove('active');
            }

            return true;
        }
        return false;
    }

    /**
     * Setup global keyboard shortcuts
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Esc - Close only the topmost modal
            if (e.key === 'Escape') {
                this.closeTopmost();
            }
        });
    }

    /**
     * Check if any modals are open
     */
    hasOpenModals() {
        return this.modalStack.length > 0;
    }

    /**
     * Close all modals
     */
    closeAll() {
        while (this.modalStack.length > 0) {
            this.closeTopmost();
        }
    }
}

// Create singleton instance
const modalManager = new ModalManager();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = modalManager;
}
