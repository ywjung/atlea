/**
 * Admin Dashboard Themes Module
 * - Theme toggle (light/dark)
 * - System preference detection
 * - Theme persistence
 */

// =============================================================================
// Theme Manager
// =============================================================================
const AdminThemes = {
    STORAGE_KEY: 'admin-theme',
    themes: ['light', 'dark'],
    currentTheme: 'light'
};

// =============================================================================
// Initialization
// =============================================================================
AdminThemes.init = function() {
    // Get saved theme or system preference
    const savedTheme = localStorage.getItem(this.STORAGE_KEY);
    const systemTheme = this.getSystemTheme();

    // Priority: saved > system > default (light)
    const initialTheme = savedTheme || systemTheme || 'light';
    this.setTheme(initialTheme, false);

    // Listen for system theme changes
    this.watchSystemTheme();

    // Initialize toggle buttons
    this.initToggleButtons();

    console.log('[AdminThemes] Initialized with theme:', this.currentTheme);
};

// =============================================================================
// Theme Operations
// =============================================================================
AdminThemes.setTheme = function(theme, save = true) {
    if (!this.themes.includes(theme)) {
        console.warn(`[AdminThemes] Invalid theme: ${theme}`);
        return;
    }

    console.log('[AdminThemes] setTheme called:', theme);
    this.currentTheme = theme;

    // Save preference first
    if (save) {
        localStorage.setItem(this.STORAGE_KEY, theme);
    }

    const html = document.documentElement;
    const body = document.body;

    // Update data-attribute on both html and body
    html.setAttribute('data-theme', theme);
    body.setAttribute('data-theme', theme);

    // Update meta theme-color for mobile browsers
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
        metaThemeColor.content = theme === 'dark' ? '#0f172a' : '#667eea';
    }

    // Update toggle button icons
    this.updateToggleButtons();

    // FORCE REPAINT: Nuclear option - hide and show body
    // This guarantees a repaint by forcing layout recalculation
    body.style.display = 'none';
    // Force synchronous reflow
    void body.offsetHeight;
    body.style.display = '';

    // Emit theme change event
    if (typeof AdminCore !== 'undefined') {
        AdminCore.emit('themeChange', { theme });
    }
    console.log('[AdminThemes] Theme change complete:', theme);
};

AdminThemes.toggle = function() {
    console.log('[AdminThemes] Toggle called, current theme:', this.currentTheme);
    const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
    console.log('[AdminThemes] Switching to:', newTheme);
    this.setTheme(newTheme);

    // Show toast notification
    if (typeof AdminCore !== 'undefined') {
        AdminCore.toast(
            newTheme === 'dark' ? '다크 모드가 활성화되었습니다.' : '라이트 모드가 활성화되었습니다.',
            'info',
            2000
        );
    }
};

AdminThemes.getTheme = function() {
    return this.currentTheme;
};

AdminThemes.isDark = function() {
    return this.currentTheme === 'dark';
};

// =============================================================================
// System Theme Detection
// =============================================================================
AdminThemes.getSystemTheme = function() {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
    }
    return 'light';
};

AdminThemes.watchSystemTheme = function() {
    if (!window.matchMedia) return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    mediaQuery.addEventListener('change', (e) => {
        // Only auto-switch if user hasn't manually set a preference
        const savedTheme = localStorage.getItem(this.STORAGE_KEY);
        if (!savedTheme) {
            this.setTheme(e.matches ? 'dark' : 'light', false);
        }
    });
};

// =============================================================================
// Toggle Button Management
// =============================================================================
AdminThemes.initToggleButtons = function() {
    // Just update the toggle button icons - click handler is attached inline in HTML
    this.updateToggleButtons();
    console.log('[AdminThemes] Toggle buttons initialized');
};

AdminThemes.updateToggleButtons = function() {
    document.querySelectorAll('.theme-toggle, [data-theme-toggle]').forEach(button => {
        const sunIcon = button.querySelector('.icon-sun');
        const moonIcon = button.querySelector('.icon-moon');

        if (sunIcon && moonIcon) {
            if (this.currentTheme === 'dark') {
                sunIcon.style.display = 'none';
                moonIcon.style.display = 'block';
            } else {
                sunIcon.style.display = 'block';
                moonIcon.style.display = 'none';
            }
        }

        // Update aria-label for accessibility
        button.setAttribute('aria-label',
            this.currentTheme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'
        );

        // Update title
        button.setAttribute('title',
            this.currentTheme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'
        );
    });
};

// =============================================================================
// Theme Toggle Button Component
// =============================================================================
AdminThemes.createToggleButton = function(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const button = document.createElement('button');
    button.className = 'theme-toggle';
    button.setAttribute('aria-label', '테마 전환');
    button.setAttribute('title', '테마 전환');

    button.innerHTML = `
        <span class="icon-sun">☀️</span>
        <span class="icon-moon">🌙</span>
    `;

    button.addEventListener('click', () => this.toggle());

    container.appendChild(button);
    this.updateToggleButtons();

    return button;
};

// =============================================================================
// CSS Variable Access
// =============================================================================
AdminThemes.getCSSVariable = function(variableName) {
    return getComputedStyle(document.documentElement).getPropertyValue(variableName).trim();
};

AdminThemes.setCSSVariable = function(variableName, value) {
    document.documentElement.style.setProperty(variableName, value);
};

// =============================================================================
// Color Utilities for Charts
// =============================================================================
AdminThemes.getChartColors = function() {
    const isDark = this.isDark();

    return {
        text: isDark ? '#94a3b8' : '#64748b',
        textPrimary: isDark ? '#f1f5f9' : '#1e293b',
        grid: isDark ? 'rgba(51, 65, 85, 0.5)' : 'rgba(226, 232, 240, 0.8)',
        background: isDark ? '#1e293b' : '#ffffff',
        border: isDark ? '#334155' : '#e2e8f0',
        tooltipBg: isDark ? '#1e293b' : '#ffffff',
        tooltipText: isDark ? '#f1f5f9' : '#1e293b'
    };
};

// =============================================================================
// Theme Presets (for future customization)
// =============================================================================
AdminThemes.presets = {
    light: {
        name: '라이트',
        variables: {}  // Uses default CSS variables
    },
    dark: {
        name: '다크',
        variables: {}  // Uses dark theme CSS variables
    }
    // Additional themes can be added here
};

AdminThemes.applyPreset = function(presetName) {
    const preset = this.presets[presetName];
    if (!preset) return;

    // Apply custom variables if any
    Object.entries(preset.variables).forEach(([name, value]) => {
        this.setCSSVariable(name, value);
    });
};

// =============================================================================
// Reset Theme
// =============================================================================
AdminThemes.reset = function() {
    localStorage.removeItem(this.STORAGE_KEY);
    const systemTheme = this.getSystemTheme();
    this.setTheme(systemTheme, false);
};

// =============================================================================
// Export
// =============================================================================
window.AdminThemes = AdminThemes;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    AdminThemes.init();
});

// Also initialize immediately if DOM is already loaded
if (document.readyState === 'interactive' || document.readyState === 'complete') {
    AdminThemes.init();
}
