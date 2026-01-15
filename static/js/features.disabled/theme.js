/**
 * Theme Manager
 * Handles dark/light theme switching and persistence
 */

class ThemeManager {
    constructor() {
        this.currentTheme = 'light';
        this.initElements();
        this.initTheme();
        this.initEventListeners();
    }

    initElements() {
        this.themeToggle = document.getElementById('themeToggle');
    }

    initEventListeners() {
        this.themeToggle?.addEventListener('click', () => this.toggle());
    }

    initTheme() {
        // Load saved theme or use system preference
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme) {
            this.setTheme(savedTheme);
        } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            this.setTheme('dark');
        } else {
            this.setTheme('light');
        }
    }

    setTheme(theme) {
        this.currentTheme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        this.updateToggleIcon();
    }

    toggle() {
        const newTheme = this.currentTheme === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    }

    updateToggleIcon() {
        if (!this.themeToggle) return;

        const sunIcon = this.themeToggle.querySelector('.sun-icon');
        const moonIcon = this.themeToggle.querySelector('.moon-icon');

        if (this.currentTheme === 'dark') {
            sunIcon?.style.setProperty('display', 'none');
            moonIcon?.style.setProperty('display', 'block');
        } else {
            moonIcon?.style.setProperty('display', 'none');
            sunIcon?.style.setProperty('display', 'block');
        }
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = ThemeManager;
}
