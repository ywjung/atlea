"""Application settings and constants

시스템 전역에서 사용되는 설정 상수들을 정의합니다.
"""

# Config keys
SETTINGS_KEY = "system:settings"

# Default system settings (in minutes)
DEFAULT_INACTIVITY_TIMEOUT = 30  # 30분
DEFAULT_WARNING_TIME = 5         # 5분
DEFAULT_CHECK_INTERVAL = 1       # 1분

# Setting validation ranges (in minutes)
MIN_INACTIVITY_TIMEOUT = 5
MAX_INACTIVITY_TIMEOUT = 480  # 8시간

MIN_WARNING_TIME = 1
MAX_WARNING_TIME = 60

MIN_CHECK_INTERVAL = 1
MAX_CHECK_INTERVAL = 10

# Error messages
ERROR_NOT_AUTHENTICATED = "Not authenticated"
ERROR_INVALID_TOKEN = "Invalid token"
ERROR_ADMIN_REQUIRED = "Admin access required"
ERROR_SETTINGS_RETRIEVAL = "Failed to retrieve settings"
ERROR_SETTINGS_UPDATE = "Failed to update settings"

# Success messages
SUCCESS_SETTINGS_UPDATED = "Settings updated successfully"

# Cache configuration (in seconds)
CACHE_TTL_SHORT = 60      # 1분 - 자주 변경되는 데이터
CACHE_TTL_MEDIUM = 300    # 5분 - 통계/대시보드 데이터
CACHE_TTL_LONG = 3600     # 1시간 - 거의 변경되지 않는 데이터

# API timeout configuration (in seconds)
API_TIMEOUT_SHORT = 5     # 빠른 응답이 필요한 요청
API_TIMEOUT_MEDIUM = 15   # 일반 API 요청
API_TIMEOUT_LONG = 30     # 외부 API 또는 대용량 처리
API_TIMEOUT_EXTENDED = 60 # 파일 업로드/다운로드 등

# Rate limit configuration (requests per window)
# Format: (max_requests, window_seconds)
#
# Endpoint-specific rate limits are defined in router files:
# - Query endpoints: 30 req/60s (query, query_stream, follow_up_questions)
# - DB backup: 5 req/60s (create), 3 req/60s (restore), 30 req/60s (list)
# - Admin sensitive: 5 req/60s (TOTP reset, password reset, API key reveal)
# - Admin session: 3 req/60s (revoke all), 20 req/60s (revoke single)
# - Statistics: 30 req/60s (db_stats, document_stats)
#
RATE_LIMIT_WINDOW = 60           # 기본 rate limit 윈도우 (초)
RATE_LIMIT_DEFAULT = 30          # 기본 요청 제한 수
RATE_LIMIT_SENSITIVE = 5         # 민감한 작업 요청 제한 수
RATE_LIMIT_HIGH_FREQUENCY = 60   # 자주 사용되는 API 요청 제한 수

# CSRF configuration
CSRF_COOKIE_MAX_AGE = 3600  # 1시간
