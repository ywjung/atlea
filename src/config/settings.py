"""Application settings and constants

시스템 전역에서 사용되는 설정 상수들을 정의합니다.
"""

# Redis keys
REDIS_SETTINGS_KEY = "system:settings"

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
