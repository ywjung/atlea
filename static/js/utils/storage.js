/**
 * Local Storage Utilities
 * 
 * Safe wrappers for localStorage operations.
 */

/**
 * Get item from localStorage
 * @param {string} key - Storage key
 * @param {any} defaultValue - Default value if key doesn't exist
 * @returns {any} - Stored value or default
 */
export function getItem(key, defaultValue = null) {
    try {
        const value = localStorage.getItem(key);
        if (value === null) return defaultValue;
        
        // Try to parse JSON
        try {
            return JSON.parse(value);
        } catch {
            return value;
        }
    } catch (error) {
        console.error(`Failed to get item from localStorage: ${key}`, error);
        return defaultValue;
    }
}

/**
 * Set item in localStorage
 * @param {string} key - Storage key
 * @param {any} value - Value to store
 * @returns {boolean} - Success status
 */
export function setItem(key, value) {
    try {
        const serialized = typeof value === 'string' ? value : JSON.stringify(value);
        localStorage.setItem(key, serialized);
        return true;
    } catch (error) {
        console.error(`Failed to set item in localStorage: ${key}`, error);
        return false;
    }
}

/**
 * Remove item from localStorage
 * @param {string} key - Storage key
 * @returns {boolean} - Success status
 */
export function removeItem(key) {
    try {
        localStorage.removeItem(key);
        return true;
    } catch (error) {
        console.error(`Failed to remove item from localStorage: ${key}`, error);
        return false;
    }
}

/**
 * Clear all items from localStorage
 * @returns {boolean} - Success status
 */
export function clear() {
    try {
        localStorage.clear();
        return true;
    } catch (error) {
        console.error('Failed to clear localStorage', error);
        return false;
    }
}

/**
 * Check if key exists in localStorage
 * @param {string} key - Storage key
 * @returns {boolean} - True if key exists
 */
export function hasItem(key) {
    try {
        return localStorage.getItem(key) !== null;
    } catch (error) {
        console.error(`Failed to check item in localStorage: ${key}`, error);
        return false;
    }
}

/**
 * Get all keys in localStorage
 * @returns {string[]} - Array of keys
 */
export function getAllKeys() {
    try {
        return Object.keys(localStorage);
    } catch (error) {
        console.error('Failed to get localStorage keys', error);
        return [];
    }
}

/**
 * Session storage wrapper
 */
export const session = {
    getItem(key, defaultValue = null) {
        try {
            const value = sessionStorage.getItem(key);
            if (value === null) return defaultValue;
            try {
                return JSON.parse(value);
            } catch {
                return value;
            }
        } catch (error) {
            console.error(`Failed to get session item: ${key}`, error);
            return defaultValue;
        }
    },

    setItem(key, value) {
        try {
            const serialized = typeof value === 'string' ? value : JSON.stringify(value);
            sessionStorage.setItem(key, serialized);
            return true;
        } catch (error) {
            console.error(`Failed to set session item: ${key}`, error);
            return false;
        }
    },

    removeItem(key) {
        try {
            sessionStorage.removeItem(key);
            return true;
        } catch (error) {
            console.error(`Failed to remove session item: ${key}`, error);
            return false;
        }
    },

    clear() {
        try {
            sessionStorage.clear();
            return true;
        } catch (error) {
            console.error('Failed to clear sessionStorage', error);
            return false;
        }
    }
};
