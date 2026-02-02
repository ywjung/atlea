/**
 * HTTP API Client
 * 
 * Wrapper for API calls with authentication and error handling.
 */

/**
 * Make authenticated API call
 * @param {string} endpoint - API endpoint (without /api prefix)
 * @param {Object} options - Fetch options
 * @returns {Promise<any>} - Response data
 */
export async function apiCall(endpoint, options = {}) {
    const token = localStorage.getItem('access_token');
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const url = endpoint.startsWith('/api') ? endpoint : `/api${endpoint}`;
    
    try {
        const response = await fetch(url, {
            ...options,
            headers
        });

        // Handle authentication errors
        if (response.status === 401) {
            // Token expired or invalid
            localStorage.removeItem('access_token');
            localStorage.removeItem('user_id');
            window.location.href = '/login.html';
            throw new Error('Authentication required');
        }

        // Handle other HTTP errors
        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: response.statusText }));
            throw new Error(error.error || error.message || `HTTP ${response.status}`);
        }

        // Parse response
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        }
        
        return await response.text();
        
    } catch (error) {
        console.error(`API call failed: ${endpoint}`, error);
        throw error;
    }
}

/**
 * GET request helper
 * @param {string} endpoint - API endpoint
 * @param {Object} params - Query parameters
 * @returns {Promise<any>} - Response data
 */
export async function get(endpoint, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    
    return apiCall(url, { method: 'GET' });
}

/**
 * POST request helper
 * @param {string} endpoint - API endpoint
 * @param {Object} data - Request body
 * @returns {Promise<any>} - Response data
 */
export async function post(endpoint, data = {}) {
    return apiCall(endpoint, {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

/**
 * PUT request helper
 * @param {string} endpoint - API endpoint
 * @param {Object} data - Request body
 * @returns {Promise<any>} - Response data
 */
export async function put(endpoint, data = {}) {
    return apiCall(endpoint, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
}

/**
 * DELETE request helper
 * @param {string} endpoint - API endpoint
 * @returns {Promise<any>} - Response data
 */
export async function del(endpoint) {
    return apiCall(endpoint, { method: 'DELETE' });
}

/**
 * Upload file with progress
 * @param {string} endpoint - API endpoint
 * @param {File} file - File to upload
 * @param {Function} onProgress - Progress callback (percent)
 * @returns {Promise<any>} - Response data
 */
export async function uploadFile(endpoint, file, onProgress = null) {
    const token = localStorage.getItem('access_token');
    
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const formData = new FormData();
        formData.append('file', file);

        // Progress tracking
        if (onProgress) {
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    onProgress(percent);
                }
            });
        }

        // Response handling
        xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    resolve(response);
                } catch (e) {
                    resolve(xhr.responseText);
                }
            } else {
                reject(new Error(`Upload failed: ${xhr.status}`));
            }
        });

        xhr.addEventListener('error', () => {
            reject(new Error('Upload failed'));
        });

        xhr.addEventListener('abort', () => {
            reject(new Error('Upload aborted'));
        });

        // Send request
        const url = endpoint.startsWith('/api') ? endpoint : `/api${endpoint}`;
        xhr.open('POST', url);
        
        if (token) {
            xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        }
        
        xhr.send(formData);
    });
}
