/**
 * Vitest Test Setup
 *
 * Global test configuration and mocks
 */

// Mock browser APIs
global.localStorage = {
    data: {},
    getItem(key) {
        return this.data[key] || null;
    },
    setItem(key, value) {
        this.data[key] = value.toString();
    },
    removeItem(key) {
        delete this.data[key];
    },
    clear() {
        this.data = {};
    },
};

global.sessionStorage = {
    data: {},
    getItem(key) {
        return this.data[key] || null;
    },
    setItem(key, value) {
        this.data[key] = value.toString();
    },
    removeItem(key) {
        delete this.data[key];
    },
    clear() {
        this.data = {};
    },
};

// Mock fetch for API calls
global.fetch = async (url, options = {}) => {
    // Return mock response
    return {
        ok: true,
        status: 200,
        json: async () => ({}),
        text: async () => '',
        headers: new Map(),
    };
};

// Mock DOMPurify
global.DOMPurify = {
    sanitize: (html) => html,
};

// Mock marked
global.marked = {
    parse: (markdown) => markdown,
    setOptions: () => {},
};

// Clear storage before each test
beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
});
