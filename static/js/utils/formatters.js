/**
 * Formatting Utilities
 * 
 * Date, time, and data formatting helpers.
 */

/**
 * Format timestamp as relative time
 * @param {string|Date} timestamp - Timestamp to format
 * @returns {string} - Formatted relative time (e.g., "5분 전", "2시간 전")
 */
export function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    // Less than 1 minute
    if (diff < 60000) {
        return '방금 전';
    }

    // Less than 1 hour
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return `${minutes}분 전`;
    }

    // Less than 1 day
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours}시간 전`;
    }

    // Less than 7 days
    if (diff < 604800000) {
        const days = Math.floor(diff / 86400000);
        return `${days}일 전`;
    }

    // More than 7 days: show full date
    return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

/**
 * Format date as relative or absolute
 * @param {string} isoString - ISO date string
 * @returns {string} - Formatted date (e.g., "오늘", "어제", "3일 전")
 */
export function formatDate(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
        return '오늘';
    } else if (diffDays === 1) {
        return '어제';
    } else if (diffDays < 7) {
        return `${diffDays}일 전`;
    } else {
        return date.toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
}

/**
 * Format date and time with precision
 * @param {string} isoString - ISO date string
 * @returns {string} - Formatted datetime (e.g., "2024.01.15 14:30:45")
 */
export function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

/**
 * Format file size in human-readable format
 * @param {number} bytes - File size in bytes
 * @returns {string} - Formatted size (e.g., "1.5 MB")
 */
export function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Format number with thousand separators
 * @param {number} num - Number to format
 * @returns {string} - Formatted number (e.g., "1,234,567")
 */
export function formatNumber(num) {
    return num.toLocaleString('ko-KR');
}
