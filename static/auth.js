/**
 * Authentication Module
 * JWT 토큰 관리 및 인증 API 호출
 */

const Auth = {
    // Token Storage Keys
    ACCESS_TOKEN_KEY: 'access_token',
    REFRESH_TOKEN_KEY: 'refresh_token',
    USER_KEY: 'user_data',

    // Auto-logout settings (in milliseconds)
    INACTIVITY_TIMEOUT: 30 * 60 * 1000, // 30분
    WARNING_TIME: 5 * 60 * 1000, // 로그아웃 5분 전 경고
    CHECK_INTERVAL: 60 * 1000, // 1분마다 체크

    // Activity tracking
    lastActivityTime: Date.now(),
    inactivityTimer: null,
    warningShown: false,
    warningModal: null,

    /**
     * 토큰 저장
     */
    setTokens(accessToken, refreshToken) {
        localStorage.setItem(this.ACCESS_TOKEN_KEY, accessToken);
        localStorage.setItem(this.REFRESH_TOKEN_KEY, refreshToken);
    },

    /**
     * Access Token 가져오기
     */
    getAccessToken() {
        return localStorage.getItem(this.ACCESS_TOKEN_KEY);
    },

    /**
     * Refresh Token 가져오기
     */
    getRefreshToken() {
        return localStorage.getItem(this.REFRESH_TOKEN_KEY);
    },

    /**
     * 사용자 정보 저장
     */
    setUser(user) {
        localStorage.setItem(this.USER_KEY, JSON.stringify(user));
    },

    /**
     * 사용자 정보 가져오기
     */
    getUser() {
        const userData = localStorage.getItem(this.USER_KEY);
        return userData ? JSON.parse(userData) : null;
    },

    /**
     * 로그인 상태 확인
     */
    isAuthenticated() {
        return !!this.getAccessToken();
    },

    /**
     * 관리자 권한 확인
     */
    isAdmin() {
        const user = this.getUser();
        return user && user.role === 'admin';
    },

    /**
     * 모든 인증 정보 삭제
     */
    clearAuth() {
        localStorage.removeItem(this.ACCESS_TOKEN_KEY);
        localStorage.removeItem(this.REFRESH_TOKEN_KEY);
        localStorage.removeItem(this.USER_KEY);
    },

    /**
     * API 요청 헬퍼 (자동 토큰 포함)
     */
    async apiCall(url, options = {}) {
        const token = this.getAccessToken();
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers
            });

            // 401 에러 시 토큰 갱신 시도
            if (response.status === 401 && this.getRefreshToken()) {
                const refreshed = await this.refreshToken();
                if (refreshed) {
                    // 토큰 갱신 성공, 원래 요청 재시도
                    headers['Authorization'] = `Bearer ${this.getAccessToken()}`;
                    const retryResponse = await fetch(url, {
                        ...options,
                        headers
                    });
                    return await this.handleResponse(retryResponse);
                } else {
                    // 토큰 갱신 실패, 인증 정보 삭제 후 로그인 페이지로
                    this.clearAuth();
                    this.redirectToLogin();
                    throw new Error('Authentication failed');
                }
            }

            return await this.handleResponse(response);
        } catch (error) {
            console.error('API call failed:', error);
            throw error;
        }
    },

    /**
     * 응답 처리
     */
    async handleResponse(response) {
        if (response.status === 429) {
            const retryAfter = response.headers.get('Retry-After');
            throw new Error(`요청이 너무 많습니다. ${retryAfter}초 후에 다시 시도하세요.`);
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Request failed');
        }

        return data;
    },

    /**
     * 회원가입
     */
    async register(email, username, password, captcha_token = null) {
        const payload = { email, username, password };
        if (captcha_token) {
            payload.captcha_token = captcha_token;
        }

        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        return await this.handleResponse(response);
    },

    /**
     * 로그인
     */
    async login(email, password, captcha_token = null) {
        const payload = { email, password };
        if (captcha_token) {
            payload.captcha_token = captcha_token;
        }

        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await this.handleResponse(response);

        // 토큰 및 사용자 정보 저장
        this.setTokens(data.tokens.access_token, data.tokens.refresh_token);
        this.setUser(data.user);

        return data;
    },

    /**
     * 로그아웃
     */
    async logout() {
        try {
            await this.apiCall('/api/auth/logout', { method: 'POST' });
        } catch (error) {
            console.error('Logout API failed:', error);
        } finally {
            this.clearAuth();
            this.redirectToLogin();
        }
    },

    /**
     * 토큰 갱신
     */
    async refreshToken() {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) return false;

        try {
            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (!response.ok) return false;

            const data = await response.json();
            this.setTokens(data.tokens.access_token, data.tokens.refresh_token);
            this.setUser(data.user);

            return true;
        } catch (error) {
            console.error('Token refresh failed:', error);
            return false;
        }
    },

    /**
     * 프로필 업데이트
     */
    async updateProfile(username) {
        const data = await this.apiCall('/api/auth/profile', {
            method: 'PUT',
            body: JSON.stringify({ username })
        });

        this.setUser(data.user);
        return data;
    },

    /**
     * 비밀번호 변경
     */
    async changePassword(oldPassword, newPassword) {
        return await this.apiCall('/api/auth/change-password', {
            method: 'POST',
            body: JSON.stringify({
                old_password: oldPassword,
                new_password: newPassword
            })
        });
    },

    /**
     * 세션 목록 조회
     */
    async getSessions() {
        return await this.apiCall('/api/auth/sessions');
    },

    /**
     * 세션 무효화
     */
    async revokeSession(sessionId) {
        return await this.apiCall(`/api/auth/sessions/${sessionId}`, {
            method: 'DELETE'
        });
    },

    /**
     * 비밀번호 재설정 요청
     */
    async requestPasswordReset(email) {
        const response = await fetch('/api/auth/password-reset/request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });

        return await this.handleResponse(response);
    },

    /**
     * 비밀번호 재설정 확인
     */
    async confirmPasswordReset(token, newPassword) {
        const response = await fetch('/api/auth/password-reset/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: token,
                new_password: newPassword
            })
        });

        return await this.handleResponse(response);
    },

    /**
     * 현재 사용자 정보 조회
     */
    async getCurrentUser() {
        const data = await this.apiCall('/api/auth/me');
        this.setUser(data.user);
        return data.user;
    },

    /**
     * 로그인 페이지로 리다이렉트
     */
    redirectToLogin() {
        if (!window.location.pathname.includes('/login.html')) {
            window.location.href = '/static/login.html';
        }
    },

    /**
     * 페이지 보호 (로그인 필요)
     */
    requireAuth() {
        if (!this.isAuthenticated()) {
            this.redirectToLogin();
            return false;
        }
        return true;
    },

    /**
     * 관리자 페이지 보호
     */
    requireAdmin() {
        if (!this.isAuthenticated()) {
            this.redirectToLogin();
            return false;
        }
        if (!this.isAdmin()) {
            alert('관리자 권한이 필요합니다.');
            window.location.href = '/';
            return false;
        }
        return true;
    },

    /**
     * 비밀번호 강도 검증
     */
    validatePassword(password) {
        const errors = [];

        if (password.length < 8) {
            errors.push('최소 8자 이상이어야 합니다');
        }
        if (password.length > 128) {
            errors.push('최대 128자까지 가능합니다');
        }
        if (!/[A-Z]/.test(password)) {
            errors.push('최소 1개의 대문자가 필요합니다');
        }
        if (!/[a-z]/.test(password)) {
            errors.push('최소 1개의 소문자가 필요합니다');
        }
        if (!/[0-9]/.test(password)) {
            errors.push('최소 1개의 숫자가 필요합니다');
        }
        if (!/[!@#$%^&*()_+\-=\[\]{}|;:',.<>?/~`]/.test(password)) {
            errors.push('최소 1개의 특수문자가 필요합니다');
        }
        if (/\s/.test(password)) {
            errors.push('공백은 사용할 수 없습니다');
        }

        return {
            valid: errors.length === 0,
            errors: errors
        };
    },

    /**
     * 에러 메시지 표시
     */
    showError(message, elementId = 'error-message') {
        const errorElement = document.getElementById(elementId);
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.style.display = 'block';
        } else {
            alert(message);
        }
    },

    /**
     * 성공 메시지 표시
     */
    showSuccess(message, elementId = 'success-message') {
        const successElement = document.getElementById(elementId);
        if (successElement) {
            successElement.textContent = message;
            successElement.style.display = 'block';
        } else {
            alert(message);
        }
    },

    /**
     * 에러 메시지 숨기기
     */
    hideError(elementId = 'error-message') {
        const errorElement = document.getElementById(elementId);
        if (errorElement) {
            errorElement.style.display = 'none';
        }
    },

    /**
     * 성공 메시지 숨기기
     */
    hideSuccess(elementId = 'success-message') {
        const successElement = document.getElementById(elementId);
        if (successElement) {
            successElement.style.display = 'none';
        }
    },

    /**
     * 활동 모니터링 초기화
     */
    async initActivityMonitor() {
        // 인증되지 않은 경우 실행 안함
        if (!this.isAuthenticated()) {
            return;
        }

        // 서버로부터 설정 로드
        await this.loadSettings();

        // 마지막 활동 시간 초기화
        this.lastActivityTime = Date.now();
        this.warningShown = false;

        // 사용자 활동 이벤트 리스너 등록
        const activityEvents = ['mousedown', 'keydown', 'scroll', 'touchstart', 'click'];
        activityEvents.forEach(event => {
            document.addEventListener(event, () => this.resetActivityTimer(), { passive: true });
        });

        // 비활성 체크 타이머 시작
        this.startInactivityCheck();

        console.log('Activity monitor initialized with settings:', {
            inactivity_timeout: this.INACTIVITY_TIMEOUT / 60000,
            warning_time: this.WARNING_TIME / 60000,
            check_interval: this.CHECK_INTERVAL / 60000
        });
    },

    /**
     * 활동 타이머 리셋
     */
    resetActivityTimer() {
        this.lastActivityTime = Date.now();

        // 경고가 표시된 상태면 닫기
        if (this.warningShown) {
            this.closeInactivityWarning();
        }
    },

    /**
     * 비활성 체크 시작
     */
    startInactivityCheck() {
        // 기존 타이머가 있으면 제거
        if (this.inactivityTimer) {
            clearInterval(this.inactivityTimer);
        }

        // 1분마다 비활성 상태 체크
        this.inactivityTimer = setInterval(() => {
            this.checkInactivity();
        }, this.CHECK_INTERVAL);
    },

    /**
     * 비활성 상태 체크
     */
    checkInactivity() {
        if (!this.isAuthenticated()) {
            this.stopActivityMonitor();
            return;
        }

        const now = Date.now();
        const inactiveTime = now - this.lastActivityTime;
        const timeUntilLogout = this.INACTIVITY_TIMEOUT - inactiveTime;

        // 타임아웃 시간이 지났으면 자동 로그아웃
        if (inactiveTime >= this.INACTIVITY_TIMEOUT) {
            console.log('Auto-logout due to inactivity');
            this.handleAutoLogout();
            return;
        }

        // 경고 시간이 되었고 아직 경고를 안 보여줬으면 경고 표시
        if (timeUntilLogout <= this.WARNING_TIME && !this.warningShown) {
            const minutesLeft = Math.ceil(timeUntilLogout / 60000);
            this.showInactivityWarning(minutesLeft);
        }
    },

    /**
     * 비활성 경고 표시
     */
    showInactivityWarning(minutesLeft) {
        this.warningShown = true;

        // 경고 모달 생성
        const modal = document.createElement('div');
        modal.id = 'inactivity-warning-modal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        `;

        modal.innerHTML = `
            <div style="
                background: white;
                padding: 30px;
                border-radius: 8px;
                max-width: 400px;
                text-align: center;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            ">
                <h3 style="margin: 0 0 15px 0; color: #f59e0b;">⚠️ 세션 만료 경고</h3>
                <p style="margin: 0 0 20px 0; color: #666;">
                    비활성 상태가 지속되어<br>
                    <strong style="color: #ef4444;">${minutesLeft}분 후</strong> 자동 로그아웃됩니다.
                </p>
                <button id="stay-logged-in-btn" style="
                    background: #3b82f6;
                    color: white;
                    border: none;
                    padding: 10px 24px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 16px;
                    font-weight: 500;
                ">
                    계속 사용하기
                </button>
            </div>
        `;

        document.body.appendChild(modal);
        this.warningModal = modal;

        // 계속 사용하기 버튼 클릭 시
        document.getElementById('stay-logged-in-btn').addEventListener('click', () => {
            this.resetActivityTimer();
        });

        // 모달 배경 클릭 시에도 활동으로 간주
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.resetActivityTimer();
            }
        });
    },

    /**
     * 비활성 경고 닫기
     */
    closeInactivityWarning() {
        if (this.warningModal) {
            this.warningModal.remove();
            this.warningModal = null;
        }
        this.warningShown = false;
    },

    /**
     * 자동 로그아웃 처리
     */
    async handleAutoLogout() {
        this.stopActivityMonitor();

        try {
            await this.apiCall('/api/auth/logout', { method: 'POST' });
        } catch (error) {
            console.error('Auto-logout API failed:', error);
        } finally {
            this.clearAuth();
            alert('비활성 상태로 인해 자동 로그아웃되었습니다.');
            this.redirectToLogin();
        }
    },

    /**
     * 활동 모니터링 중지
     */
    stopActivityMonitor() {
        if (this.inactivityTimer) {
            clearInterval(this.inactivityTimer);
            this.inactivityTimer = null;
        }
        this.closeInactivityWarning();
    },

    /**
     * 서버로부터 설정 로드
     */
    async loadSettings() {
        try {
            const data = await this.apiCall('/api/settings');
            this.updateSettings(data.settings);
        } catch (error) {
            // 에러 발생 시 기본값 사용
            console.warn('Error loading settings, using defaults:', error);
        }
    },

    /**
     * 설정 업데이트
     */
    updateSettings(settings) {
        // 분 단위 → 밀리초 단위로 변환
        this.INACTIVITY_TIMEOUT = settings.inactivity_timeout * 60 * 1000;
        this.WARNING_TIME = settings.warning_time * 60 * 1000;
        this.CHECK_INTERVAL = settings.check_interval * 60 * 1000;

        // 타이머가 실행 중이면 재시작
        if (this.inactivityTimer) {
            this.stopActivityMonitor();
            this.startInactivityCheck();
        }

        console.log('Settings updated:', {
            inactivity_timeout: settings.inactivity_timeout,
            warning_time: settings.warning_time,
            check_interval: settings.check_interval
        });
    }
};

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Auth;
}
