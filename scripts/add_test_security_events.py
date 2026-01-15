#!/usr/bin/env python3
"""
Add test security events directly to server.log
No dependencies required - just writes JSON formatted events
"""
import json
from datetime import datetime, timedelta
import random

# Log file path
LOG_FILE = "server.log"

# Generate test events
test_events = [
    {
        "timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
        "event_type": "AUTH_LOGIN_SUCCESS",
        "level": "INFO",
        "user_id": "test-user-001",
        "ip_address": "192.168.1.100",
        "message": "User logged in successfully",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(hours=1, minutes=45)).isoformat(),
        "event_type": "AUTH_LOGIN_FAILED",
        "level": "WARNING",
        "user_id": "anonymous",
        "ip_address": "192.168.1.101",
        "message": "Login failed: Invalid credentials",
        "email": "tes***@example.com",
        "reason": "Invalid credentials"
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(hours=1, minutes=30)).isoformat(),
        "event_type": "ACCOUNT_LOCKED",
        "level": "CRITICAL",
        "user_id": "test-user-002",
        "ip_address": "192.168.1.102",
        "message": "Account locked: Too many failed login attempts",
        "reason": "Too many failed login attempts",
        "failed_attempts": 5
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(hours=1, minutes=15)).isoformat(),
        "event_type": "RATE_LIMIT_EXCEEDED",
        "level": "WARNING",
        "user_id": "anonymous",
        "ip_address": "192.168.1.103",
        "message": "Rate limit exceeded for /api/auth/login",
        "endpoint": "/api/auth/login",
        "limit": 5
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        "event_type": "TOKEN_ISSUED",
        "level": "INFO",
        "user_id": "test-user-003",
        "ip_address": "192.168.1.100",
        "message": "Access token issued",
        "token_type": "access"
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(minutes=45)).isoformat(),
        "event_type": "AUTH_LOGOUT",
        "level": "INFO",
        "user_id": "test-user-001",
        "ip_address": "192.168.1.100",
        "message": "User logged out"
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(minutes=30)).isoformat(),
        "event_type": "BRUTE_FORCE_ATTEMPT",
        "level": "CRITICAL",
        "user_id": "anonymous",
        "ip_address": "192.168.1.104",
        "message": "Potential brute force attack detected",
        "email": "adm***@example.com",
        "attempts": 10
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat(),
        "event_type": "UNAUTHORIZED_ACCESS",
        "level": "ERROR",
        "user_id": "test-user-004",
        "ip_address": "192.168.1.105",
        "message": "Unauthorized access attempt to /api/admin/users",
        "resource": "/api/admin/users"
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(minutes=10)).isoformat(),
        "event_type": "TOKEN_INVALID",
        "level": "WARNING",
        "user_id": "anonymous",
        "ip_address": "192.168.1.106",
        "message": "Invalid token attempt: Token signature invalid",
        "reason": "Token signature invalid"
    },
    {
        "timestamp": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
        "event_type": "AUTH_LOGIN_SUCCESS",
        "level": "INFO",
        "user_id": "test-user-005",
        "ip_address": "192.168.1.107",
        "message": "User logged in successfully",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
]

# Write events to log file
print(f"📝 Writing {len(test_events)} security events to {LOG_FILE}...")

with open(LOG_FILE, 'a', encoding='utf-8') as f:
    for event in test_events:
        # Format according to Loguru output with SECURITY_EVENT marker
        timestamp = datetime.fromisoformat(event["timestamp"]).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level_map = {
            "INFO": "INFO",
            "WARNING": "WARNING",
            "ERROR": "ERROR",
            "CRITICAL": "CRITICAL"
        }
        level = level_map.get(event["level"], "INFO")

        # Write in loguru format
        log_line = f"{timestamp} | {level:8} | src.auth.security_logger:log_event:130 - SECURITY_EVENT: {json.dumps(event, ensure_ascii=False)}\n"
        f.write(log_line)

print(f"✅ Successfully wrote {len(test_events)} security events!")
print(f"📋 Check with: grep 'SECURITY_EVENT:' {LOG_FILE} | tail -10")
print(f"🌐 View in admin dashboard: http://localhost:8000 → 관리자 대시보드 → 보안 로그")
