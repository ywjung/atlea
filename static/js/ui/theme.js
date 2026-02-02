/**
 * Theme Management
 *
 * Handles light/dark theme toggling and persistence.
 */

import { getItem, setItem } from '../utils/storage.js';

let isTogglingTheme = false;  // Prevent concurrent theme switches

/**
 * Initialize theme from localStorage
 */
export function initTheme() {
    // Get saved theme or default to light
    const savedTheme = getItem('theme', 'light');
    setTheme(savedTheme, true);  // Skip animation on init
}

/**
 * Toggle between light and dark themes
 */
export function toggleTheme() {
    // Prevent concurrent toggles
    if (isTogglingTheme) {
        return;
    }

    isTogglingTheme = true;

    try {
        const currentTheme = getCurrentTheme();
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
    } finally {
        // Release lock after a short delay to prevent rapid clicking
        setTimeout(() => {
            isTogglingTheme = false;
        }, 100);
    }
}

/**
 * Set theme
 * @param {string} theme - Theme name ('light' or 'dark')
 * @param {boolean} skipTransition - Skip animation
 */
export function setTheme(theme, skipTransition = false) {
    // Validate theme value
    if (theme !== 'light' && theme !== 'dark') {
        theme = 'light';
    }

    // Set theme attribute on root element
    document.documentElement.setAttribute('data-theme', theme);

    // Force reflow to ensure CSS variables are applied immediately
    void document.documentElement.offsetHeight;

    // Save to localStorage
    setItem('theme', theme);

    // Update theme toggle button
    updateThemeToggleButton(theme, skipTransition);
}

/**
 * Get current theme
 * @returns {string} - Current theme ('light' or 'dark')
 */
export function getCurrentTheme() {
    return document.documentElement.getAttribute('data-theme') || 'light';
}

/**
 * Update theme toggle button icons
 * @param {string} theme - Theme name
 * @param {boolean} skipTransition - Skip animation
 */
function updateThemeToggleButton(theme, skipTransition = false) {
    const themeToggle = document.getElementById('themeToggle');
    if (!themeToggle) return;

    const sunIcon = themeToggle.querySelector('.sun-icon');
    const moonIcon = themeToggle.querySelector('.moon-icon');

    if (sunIcon && moonIcon) {
        if (theme === 'dark') {
            // Show moon icon, hide sun icon
            if (skipTransition) {
                // Instant change on init
                sunIcon.style.display = 'none';
                sunIcon.style.opacity = '0';
                moonIcon.style.display = 'block';
                moonIcon.style.opacity = '1';
                moonIcon.style.transform = 'rotate(0deg) scale(1)';
            } else {
                // Smooth transition on toggle
                sunIcon.style.opacity = '0';
                sunIcon.style.transform = 'rotate(-90deg) scale(0.8)';
                moonIcon.style.display = 'block';
                moonIcon.style.opacity = '1';
                moonIcon.style.transform = 'rotate(0deg) scale(1)';
                // Hide sun icon after transition
                setTimeout(() => {
                    sunIcon.style.display = 'none';
                }, 300);
            }
        } else {
            // Show sun icon, hide moon icon
            if (skipTransition) {
                // Instant change on init
                moonIcon.style.display = 'none';
                moonIcon.style.opacity = '0';
                sunIcon.style.display = 'block';
                sunIcon.style.opacity = '1';
                sunIcon.style.transform = 'rotate(0deg) scale(1)';
            } else {
                // Smooth transition on toggle
                moonIcon.style.opacity = '0';
                moonIcon.style.transform = 'rotate(90deg) scale(0.8)';
                sunIcon.style.display = 'block';
                sunIcon.style.opacity = '1';
                sunIcon.style.transform = 'rotate(0deg) scale(1)';
                // Hide moon icon after transition
                setTimeout(() => {
                    moonIcon.style.display = 'none';
                }, 300);
            }
        }
    }

    // Add visual feedback
    if (!skipTransition) {
        themeToggle.style.transform = 'rotate(360deg)';
        themeToggle.style.transition = 'transform 0.3s ease';
        setTimeout(() => {
            themeToggle.style.transform = '';
            themeToggle.style.transition = '';
        }, 300);
    }
}

/**
 * Check if dark theme is active
 * @returns {boolean}
 */
export function isDarkTheme() {
    return getCurrentTheme() === 'dark';
}
