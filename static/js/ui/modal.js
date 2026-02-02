/**
 * Modal Stack Management
 *
 * Manages multiple modals with proper stacking and ESC key handling.
 */

let modalStack = [];  // Track which modals are open in order

/**
 * Push modal to stack (open modal)
 * @param {HTMLElement} modalElement - Modal DOM element
 * @param {string} modalName - Modal identifier name
 */
export function pushModal(modalElement, modalName) {
    // Remove if already in stack (prevent duplicates)
    modalStack = modalStack.filter(item => item.element !== modalElement);

    // Add to end of stack (most recent)
    modalStack.push({ element: modalElement, name: modalName });
}

/**
 * Pop modal from stack (close modal)
 * @param {HTMLElement} modalElement - Modal DOM element
 */
export function popModal(modalElement) {
    modalStack = modalStack.filter(item => item.element !== modalElement);
}

/**
 * Get topmost (most recent) modal
 * @returns {Object|null} - Modal object {element, name} or null
 */
export function getTopmostModal() {
    if (modalStack.length === 0) return null;
    return modalStack[modalStack.length - 1];
}

/**
 * Check if any modal is open
 * @returns {boolean}
 */
export function isAnyModalOpen() {
    return modalStack.length > 0;
}

/**
 * Close topmost modal
 */
export function closeTopmostModal() {
    const topModal = getTopmostModal();
    if (topModal && topModal.element) {
        topModal.element.classList.remove('active');
        popModal(topModal.element);
    }
}

/**
 * Close all modals
 */
export function closeAllModals() {
    while (modalStack.length > 0) {
        closeTopmostModal();
    }
}

/**
 * Get modal count
 * @returns {number}
 */
export function getModalCount() {
    return modalStack.length;
}

/**
 * Show modal
 * @param {HTMLElement} modalElement - Modal DOM element
 * @param {string} modalName - Modal identifier name
 */
export function showModal(modalElement, modalName) {
    if (!modalElement) return;

    modalElement.classList.add('active');
    pushModal(modalElement, modalName);
}

/**
 * Hide modal
 * @param {HTMLElement} modalElement - Modal DOM element
 */
export function hideModal(modalElement) {
    if (!modalElement) return;

    modalElement.classList.remove('active');
    popModal(modalElement);
}

/**
 * Setup modal close on backdrop click
 * @param {HTMLElement} modalElement - Modal DOM element
 */
export function setupModalBackdropClose(modalElement) {
    if (!modalElement) return;

    modalElement.addEventListener('click', (e) => {
        if (e.target === modalElement) {
            hideModal(modalElement);
        }
    });
}

/**
 * Setup ESC key handler for modals
 */
export function setupModalEscHandler() {
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeTopmostModal();
        }
    });
}
