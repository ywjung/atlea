/**
 * Settings Manager
 * Handles application settings and configuration
 */

class SettingsManager {
    constructor() {
        this.initElements();
        this.initEventListeners();
    }

    initElements() {
        this.settingsPanel = document.getElementById('settingsPanel');
        this.settingsOverlay = document.getElementById('settingsOverlay');
        this.closeSettingsBtn = document.getElementById('closeSettingsBtn');
        this.settingsBtn = document.getElementById('settingsBtn');
    }

    initEventListeners() {
        this.closeSettingsBtn?.addEventListener('click', () => this.close());
        this.settingsOverlay?.addEventListener('click', () => this.close());
    }

    async open() {
        this.settingsPanel?.classList.add('active');
        this.settingsOverlay?.classList.add('active');
        modalManager.push(this.settingsPanel, 'settings');
        await this.loadAvailableModels();
        this.loadCacheStats();
    }

    close() {
        this.settingsPanel?.classList.remove('active');
        this.settingsOverlay?.classList.remove('active');
        modalManager.pop(this.settingsPanel);
        this.settingsBtn?.blur();
    }

    async loadAvailableModels() {
        console.log('SettingsManager: loadAvailableModels called');
    }

    loadCacheStats() {
        console.log('SettingsManager: loadCacheStats called');
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = SettingsManager;
}
