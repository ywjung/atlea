#!/usr/bin/env python3
"""
Generate test security events for testing the admin dashboard
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auth.security_logger import SecurityLogger

print("🔐 Generating test security events...\n")

# 1. Login success events
SecurityLogger.log_login_success(
    user_id="test-user-001",
    ip_address="192.168.1.100",
    user_agent="Mozilla/5.0"
)
print("✅ Login success event logged")

# 2. Login failed event
SecurityLogger.log_login_failed(
    email="test@example.com",
    ip_address="192.168.1.101",
    reason="Invalid credentials"
)
print("✅ Login failed event logged")

# 3. Account locked event
SecurityLogger.log_account_locked(
    user_id="test-user-002",
    ip_address="192.168.1.102",
    reason="Too many failed login attempts",
    failed_attempts=5
)
print("✅ Account locked event logged")

# 4. Rate limit exceeded
SecurityLogger.log_rate_limit_exceeded(
    ip_address="192.168.1.103",
    endpoint="/api/auth/login",
    limit=5
)
print("✅ Rate limit exceeded event logged")

# 5. Token issued
SecurityLogger.log_token_issued(
    user_id="test-user-003",
    token_type="access"
)
print("✅ Token issued event logged")

# 6. Logout event
SecurityLogger.log_logout(
    user_id="test-user-001",
    ip_address="192.168.1.100"
)
print("✅ Logout event logged")

# 7. Brute force attempt
SecurityLogger.log_brute_force_attempt(
    email="admin@example.com",
    ip_address="192.168.1.104",
    attempts=10
)
print("✅ Brute force attempt event logged")

# 8. Unauthorized access
SecurityLogger.log_unauthorized_access(
    user_id="test-user-004",
    ip_address="192.168.1.105",
    resource="/api/admin/users"
)
print("✅ Unauthorized access event logged")

print("\n🎉 Generated 8 test security events!")
print("📋 Check the logs with: grep 'SECURITY_EVENT:' server.log")
print("🌐 View in admin dashboard: http://localhost:8000 → 관리자 대시보드 → 보안 로그")
