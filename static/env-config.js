/**
 * Environment Configuration
 * 환경별 설정 관리 및 디버그 모드 제어
 */

const EnvConfig = {
    /**
     * 현재 환경 감지
     * @returns {string} 'development' | 'production'
     */
    getEnvironment() {
        // hostname으로 환경 판단
        const hostname = window.location.hostname;

        // localhost, 127.0.0.1, 또는 .local 도메인은 개발 환경
        if (hostname === 'localhost' ||
            hostname === '127.0.0.1' ||
            hostname.endsWith('.local') ||
            hostname.startsWith('192.168.') ||
            hostname.startsWith('10.')) {
            return 'development';
        }

        return 'production';
    },

    /**
     * 개발 환경 여부
     * @returns {boolean}
     */
    isDevelopment() {
        return this.getEnvironment() === 'development';
    },

    /**
     * 프로덕션 환경 여부
     * @returns {boolean}
     */
    isProduction() {
        return this.getEnvironment() === 'production';
    },

    /**
     * 환경별 console 래퍼
     * 프로덕션에서는 console.log 제거, 에러는 유지
     */
    console: {
        log: function(...args) {
            if (EnvConfig.isDevelopment()) {
                console.log(...args);
            }
        },

        info: function(...args) {
            if (EnvConfig.isDevelopment()) {
                console.info(...args);
            }
        },

        warn: function(...args) {
            // 경고는 프로덕션에서도 표시
            console.warn(...args);
        },

        error: function(...args) {
            // 에러는 프로덕션에서도 표시
            console.error(...args);
        },

        debug: function(...args) {
            if (EnvConfig.isDevelopment()) {
                console.debug(...args);
            }
        }
    },

    /**
     * 초기화 정보 출력
     */
    init() {
        const env = this.getEnvironment();
        const hostname = window.location.hostname;

        if (this.isDevelopment()) {
            console.log(`%c🔧 Environment: ${env}`, 'color: #4CAF50; font-weight: bold');
            console.log(`%c📍 Hostname: ${hostname}`, 'color: #2196F3');
            console.log('%c✅ Debug mode enabled', 'color: #FF9800');
        } else {
            // 프로덕션에서는 최소한의 정보만
            console.log(`Environment: ${env}`);
        }
    }
};

// 페이지 로드 시 환경 정보 출력
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => EnvConfig.init());
} else {
    EnvConfig.init();
}

// 전역으로 노출 (다른 스크립트에서 사용)
window.EnvConfig = EnvConfig;
