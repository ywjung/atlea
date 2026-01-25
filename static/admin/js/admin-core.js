/**
 * Admin Dashboard Core Module
 * - Tab management
 * - Dropdown handling
 * - Utility functions
 * - Event delegation
 * - Toast notifications
 */

// =============================================================================
// Global State
// =============================================================================
const AdminCore = {
    state: {
        currentTab: 'dashboard',
        isLoading: false,
        lastUpdate: null,
        openDropdowns: new Set()
    },
    cache: new Map(),
    eventBus: new EventTarget()
};

// =============================================================================
// Initialization
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
    AdminCore.init();
});

AdminCore.init = function() {
    // Initialize tabs
    this.initTabs();

    // Initialize dropdowns
    this.initDropdowns();

    // Initialize global event listeners
    this.initEventListeners();

    // Initialize tooltips
    this.initTooltips();

    // Load initial tab
    const hash = window.location.hash.slice(1);
    if (hash) {
        this.switchTab(hash);
    }

    console.log('[AdminCore] Initialized');
};

// =============================================================================
// Tab Management
// =============================================================================
AdminCore.initTabs = function() {
    // Add click handlers to all tab buttons
    document.querySelectorAll('.tab[onclick*="switchTab"]').forEach(tab => {
        const match = tab.getAttribute('onclick').match(/switchTab\('([^']+)'\)/);
        if (match) {
            tab.setAttribute('data-tab', match[1]);
        }
    });
};

AdminCore.switchTab = function(tabName) {
    // Update state
    this.state.currentTab = tabName;

    // Close all dropdowns
    this.closeAllDropdowns();

    // Remove active class from all tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });

    // Remove active class from all dropdown toggles
    document.querySelectorAll('.tab-dropdown').forEach(dropdown => {
        dropdown.classList.remove('active');
    });

    // Add active class to current tab
    const activeTab = document.querySelector(`.tab[data-tab="${tabName}"]`);
    if (activeTab) {
        activeTab.classList.add('active');
    }

    // Check if tab is in a dropdown
    const dropdownItem = document.querySelector(`.tab-dropdown-item[data-tab="${tabName}"]`);
    if (dropdownItem) {
        const dropdown = dropdownItem.closest('.tab-dropdown');
        if (dropdown) {
            dropdown.classList.add('active');
            dropdownItem.classList.add('active');
        }
    }

    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });

    // Show current tab content
    const tabContent = document.getElementById(`${tabName}-tab`);
    if (tabContent) {
        tabContent.classList.add('active');
    }

    // Update URL hash
    history.replaceState(null, null, `#${tabName}`);

    // Emit tab change event
    this.emit('tabChange', { tabName });

    // Tab-specific load function mapping (for backward compatibility with existing function names)
    const tabLoadFunctions = {
        'dashboard': () => { if (typeof loadDashboard === 'function') loadDashboard(true); },
        'users': 'loadUsers',
        'documents': 'adminLoadDocuments',
        'groups': 'adminLoadGroups',
        'sessions': 'loadSessions',
        'prompts': 'loadPrompts',
        'login-history': () => {
            if (typeof populateLoginHistoryUserFilter === 'function') populateLoginHistoryUserFilter();
            if (typeof loadLoginhistory === 'function') loadLoginhistory();
        },
        'logs': 'loadLogs',
        'audit': 'loadAudit',
        'webhooks': 'loadWebhooks',
        'models': 'loadModels',
        'settings': 'loadSettings',
        'reindex': 'checkReindexStatus',
        'performance-metrics': 'loadPerformancemetrics'
    };

    // Call tab-specific load function if exists
    const loadHandler = tabLoadFunctions[tabName];
    if (typeof loadHandler === 'function') {
        // Direct function call (for complex handlers like login-history)
        loadHandler();
    } else if (typeof loadHandler === 'string' && typeof window[loadHandler] === 'function') {
        // Function name string
        window[loadHandler]();
    } else {
        // Fallback to auto-generated function name
        const loadFunction = `load${this.capitalize(tabName.replace(/-/g, ''))}`;
        if (typeof window[loadFunction] === 'function') {
            window[loadFunction]();
        }
    }
};

// =============================================================================
// Dropdown Management
// =============================================================================
AdminCore.initDropdowns = function() {
    // Handle dropdown toggle clicks
    document.querySelectorAll('.tab-dropdown-toggle').forEach(toggle => {
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const dropdown = toggle.closest('.tab-dropdown');
            this.toggleDropdown(dropdown);
        });
    });

    // Handle dropdown item clicks
    document.querySelectorAll('.tab-dropdown-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            const tabName = item.getAttribute('data-tab');
            if (tabName) {
                this.switchTab(tabName);
            }
            this.closeAllDropdowns();
        });
    });

    // Close dropdowns on outside click
    document.addEventListener('click', () => {
        this.closeAllDropdowns();
    });

    // Close dropdowns on escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            this.closeAllDropdowns();
        }
    });
};

AdminCore.toggleDropdown = function(arg1, arg2) {
    // Support both signatures:
    // Old: toggleDropdown(event, dropdownId) - from inline onclick handlers
    // New: toggleDropdown(dropdownElement, event) - from AdminCore

    let dropdown, event;

    if (typeof arg2 === 'string') {
        // Old signature: toggleDropdown(event, dropdownId)
        event = arg1;
        const dropdownId = arg2;
        const menu = document.getElementById('dropdown-' + dropdownId);
        if (menu) {
            dropdown = menu.parentElement;
        } else {
            console.error('[AdminCore] Dropdown not found:', 'dropdown-' + dropdownId);
            return;
        }
    } else {
        // New signature: toggleDropdown(dropdown, event)
        dropdown = arg1;
        event = arg2;
    }

    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }

    if (!dropdown) return;

    const isOpen = dropdown.classList.contains('open');

    // Close all other dropdowns
    this.closeAllDropdowns();

    if (!isOpen) {
        dropdown.classList.add('open');
        this.state.openDropdowns.add(dropdown);

        // Position dropdown menu
        this.positionDropdownMenu(dropdown);
    }
};

AdminCore.closeAllDropdowns = function() {
    document.querySelectorAll('.tab-dropdown.open').forEach(dropdown => {
        dropdown.classList.remove('open');
    });
    this.state.openDropdowns.clear();
};

AdminCore.positionDropdownMenu = function(dropdown) {
    const menu = dropdown.querySelector('.tab-dropdown-menu');
    // Support both .tab-dropdown-toggle and .tab (for backward compatibility with existing HTML)
    const toggle = dropdown.querySelector('.tab-dropdown-toggle') || dropdown.querySelector('.tab');

    if (!menu || !toggle) return;

    // Get toggle button position (for fixed positioning)
    const toggleRect = toggle.getBoundingClientRect();
    const viewportWidth = window.innerWidth;

    // Position directly below the toggle button
    let left = toggleRect.left;
    const top = toggleRect.bottom + 2;

    // Set initial position
    menu.style.top = `${top}px`;
    menu.style.left = `${left}px`;
    menu.style.right = '';

    // Check if menu would overflow right edge of viewport
    const menuRect = menu.getBoundingClientRect();
    if (menuRect.right > viewportWidth - 16) {
        // Align menu's right edge to toggle's right edge
        menu.style.left = `${toggleRect.right - menuRect.width}px`;
    }
};

// =============================================================================
// Event System
// =============================================================================
AdminCore.initEventListeners = function() {
    // Window resize handler
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            this.emit('resize');
            this.positionAllDropdowns();
        }, 100);
    });

    // Hash change handler
    window.addEventListener('hashchange', () => {
        const hash = window.location.hash.slice(1);
        if (hash && hash !== this.state.currentTab) {
            this.switchTab(hash);
        }
    });
};

AdminCore.on = function(event, callback) {
    this.eventBus.addEventListener(event, callback);
};

AdminCore.off = function(event, callback) {
    this.eventBus.removeEventListener(event, callback);
};

AdminCore.emit = function(event, data = {}) {
    this.eventBus.dispatchEvent(new CustomEvent(event, { detail: data }));
};

AdminCore.positionAllDropdowns = function() {
    this.state.openDropdowns.forEach(dropdown => {
        this.positionDropdownMenu(dropdown);
    });
};

// =============================================================================
// Toast Notifications
// =============================================================================
AdminCore.toast = function(message, type = 'info', duration = 4000) {
    // Create container if not exists
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${this.escapeHtml(message)}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    // Auto remove
    if (duration > 0) {
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    return toast;
};

// =============================================================================
// Loading State
// =============================================================================
AdminCore.setLoading = function(loading, target = null) {
    this.state.isLoading = loading;

    if (target) {
        const element = typeof target === 'string' ? document.querySelector(target) : target;
        if (element) {
            if (loading) {
                element.classList.add('loading');
                element.setAttribute('data-loading', 'true');
            } else {
                element.classList.remove('loading');
                element.removeAttribute('data-loading');
            }
        }
    }

    // Update global loading indicator if exists
    const globalLoader = document.getElementById('global-loader');
    if (globalLoader) {
        globalLoader.style.display = loading ? 'flex' : 'none';
    }

    this.emit('loadingChange', { loading });
};

// =============================================================================
// Tooltips
// =============================================================================
AdminCore.initTooltips = function() {
    // Tooltips are handled via CSS [data-tooltip]
    // This function can be used for dynamic tooltip initialization
};

// =============================================================================
// Modal Management
// =============================================================================
AdminCore.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Focus first input
        const firstInput = modal.querySelector('input, textarea, select');
        if (firstInput) {
            setTimeout(() => firstInput.focus(), 100);
        }

        this.emit('modalOpen', { modalId });
    }
};

AdminCore.closeModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
        this.emit('modalClose', { modalId });
    }
};

// Close modal on backdrop click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal') && e.target.classList.contains('active')) {
        const modalId = e.target.id;
        AdminCore.closeModal(modalId);
    }
});

// Close modal on escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const activeModal = document.querySelector('.modal.active');
        if (activeModal) {
            AdminCore.closeModal(activeModal.id);
        }
    }
});

// =============================================================================
// Utility Functions
// =============================================================================
AdminCore.escapeHtml = function(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
};

AdminCore.capitalize = function(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
};

AdminCore.formatNumber = function(num, locale = 'ko-KR') {
    return new Intl.NumberFormat(locale).format(num);
};

AdminCore.formatDate = function(date, options = {}) {
    const defaultOptions = {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    };
    return new Intl.DateTimeFormat('ko-KR', { ...defaultOptions, ...options }).format(new Date(date));
};

AdminCore.formatRelativeTime = function(date) {
    const now = new Date();
    const then = new Date(date);
    const diffMs = now - then;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return '방금 전';
    if (diffMin < 60) return `${diffMin}분 전`;
    if (diffHour < 24) return `${diffHour}시간 전`;
    if (diffDay < 7) return `${diffDay}일 전`;

    return this.formatDate(date);
};

AdminCore.debounce = function(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

AdminCore.throttle = function(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
};

// =============================================================================
// Cache Management
// =============================================================================
AdminCore.setCache = function(key, value, ttl = 60000) {
    this.cache.set(key, {
        value,
        expiry: Date.now() + ttl
    });
};

AdminCore.getCache = function(key) {
    const cached = this.cache.get(key);
    if (cached && cached.expiry > Date.now()) {
        return cached.value;
    }
    this.cache.delete(key);
    return null;
};

AdminCore.clearCache = function(keyPattern = null) {
    if (keyPattern) {
        for (const key of this.cache.keys()) {
            if (key.includes(keyPattern)) {
                this.cache.delete(key);
            }
        }
    } else {
        this.cache.clear();
    }
};

// =============================================================================
// Counter Animation
// =============================================================================
AdminCore.animateCounter = function(element, target, duration = 1000, options = {}) {
    const { isPercentage = false, decimals = 0, suffix = '' } = options;

    if (!element) return;

    const start = parseInt(element.textContent.replace(/[^\d.-]/g, '')) || 0;
    const startTime = performance.now();

    const update = (currentTime) => {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Easing function (easeOutCubic)
        const easeProgress = 1 - Math.pow(1 - progress, 3);

        const current = start + (target - start) * easeProgress;
        const displayValue = decimals > 0 ? current.toFixed(decimals) : Math.floor(current);

        element.textContent = `${this.formatNumber(displayValue)}${isPercentage ? '%' : ''}${suffix}`;

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    };

    requestAnimationFrame(update);
};

// =============================================================================
// Progress Bar Animation
// =============================================================================
AdminCore.animateProgressBar = function(elementId, percentage) {
    const element = document.getElementById(elementId);
    if (element) {
        // Reset width first for animation
        element.style.width = '0%';

        // Animate to target
        requestAnimationFrame(() => {
            element.style.width = `${Math.min(100, Math.max(0, percentage))}%`;
        });
    }
};

// =============================================================================
// API Helper
// =============================================================================
AdminCore.apiCall = async function(url, options = {}) {
    try {
        this.setLoading(true);

        const response = await Auth.apiCall(url, options);

        this.setLoading(false);
        return response;
    } catch (error) {
        this.setLoading(false);
        console.error('[AdminCore] API Error:', error);
        throw error;
    }
};

// =============================================================================
// Export for global access (compatibility with existing code)
// =============================================================================
window.switchTab = AdminCore.switchTab.bind(AdminCore);
window.toggleDropdown = AdminCore.toggleDropdown.bind(AdminCore);
window.AdminCore = AdminCore;
