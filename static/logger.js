/**
 * Logger - Frontend logging system with level control
 *
 * Changelog:
 * - 2025-12-30: Created structured logging system
 *   - Level-based filtering (DEBUG, INFO, WARN, ERROR)
 *   - Production/development mode support
 *   - Styled console output
 */

class Logger {
    constructor() {
        // Log levels
        this.levels = {
            DEBUG: 0,
            INFO: 1,
            WARN: 2,
            ERROR: 3,
            NONE: 999
        };

        // Auto-detect environment based on hostname
        this.environment = this.detectEnvironment();

        // Set log level based on environment
        this.currentLevel = this.environment === 'production'
            ? this.levels.WARN  // Production: only warnings and errors
            : this.levels.DEBUG; // Development: all logs

        // Allow override via localStorage
        const savedLevel = localStorage.getItem('log_level');
        if (savedLevel && this.levels[savedLevel] !== undefined) {
            this.currentLevel = this.levels[savedLevel];
        }

        // Log initialization
        if (this.environment === 'development') {
            console.log(
                '%c🔧 Logger initialized',
                'background: #667eea; color: white; padding: 2px 6px; border-radius: 3px;',
                `Level: ${this.getLevelName(this.currentLevel)} | Environment: ${this.environment}`
            );
        }
    }

    /**
     * Detect environment based on hostname
     * @returns {string} 'development' | 'production'
     */
    detectEnvironment() {
        const hostname = window.location.hostname;

        // localhost, 127.0.0.1, or local network = development
        if (hostname === 'localhost' ||
            hostname === '127.0.0.1' ||
            hostname.endsWith('.local') ||
            hostname.startsWith('192.168.') ||
            hostname.startsWith('10.')) {
            return 'development';
        }

        return 'production';
    }

    /**
     * Get level name from level number
     */
    getLevelName(level) {
        return Object.keys(this.levels).find(key => this.levels[key] === level) || 'UNKNOWN';
    }

    /**
     * Set log level
     * @param {string} level - DEBUG, INFO, WARN, ERROR, NONE
     */
    setLevel(level) {
        const levelUpper = level.toUpperCase();
        if (this.levels[levelUpper] !== undefined) {
            this.currentLevel = this.levels[levelUpper];
            localStorage.setItem('log_level', levelUpper);
            console.log(`📝 Log level set to: ${levelUpper}`);
        } else {
            console.error(`Invalid log level: ${level}. Valid levels:`, Object.keys(this.levels));
        }
    }

    /**
     * Check if should log at given level
     */
    shouldLog(level) {
        return level >= this.currentLevel;
    }

    /**
     * Debug level logging (development only)
     */
    debug(...args) {
        if (!this.shouldLog(this.levels.DEBUG)) return;
        console.log(
            '%c[DEBUG]',
            'color: #8b5cf6; font-weight: bold;',
            ...args
        );
    }

    /**
     * Info level logging
     */
    info(...args) {
        if (!this.shouldLog(this.levels.INFO)) return;
        console.info(
            '%c[INFO]',
            'color: #3b82f6; font-weight: bold;',
            ...args
        );
    }

    /**
     * Warning level logging
     */
    warn(...args) {
        if (!this.shouldLog(this.levels.WARN)) return;
        console.warn(
            '%c[WARN]',
            'color: #f59e0b; font-weight: bold;',
            ...args
        );
    }

    /**
     * Error level logging (always shown)
     */
    error(...args) {
        if (!this.shouldLog(this.levels.ERROR)) return;
        console.error(
            '%c[ERROR]',
            'color: #ef4444; font-weight: bold;',
            ...args
        );
    }

    /**
     * Group logging for related messages
     */
    group(title, callback, level = 'INFO') {
        const levelNum = this.levels[level.toUpperCase()] || this.levels.INFO;
        if (!this.shouldLog(levelNum)) return;

        console.group(`%c${title}`, 'font-weight: bold; font-size: 1.1em;');
        callback();
        console.groupEnd();
    }

    /**
     * Table logging for data
     */
    table(data, level = 'DEBUG') {
        const levelNum = this.levels[level.toUpperCase()] || this.levels.DEBUG;
        if (!this.shouldLog(levelNum)) return;
        console.table(data);
    }

    /**
     * Performance timing
     */
    time(label) {
        if (!this.shouldLog(this.levels.DEBUG)) return;
        console.time(label);
    }

    timeEnd(label) {
        if (!this.shouldLog(this.levels.DEBUG)) return;
        console.timeEnd(label);
    }
}

// Create global logger instance
const logger = new Logger();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = logger;
}
