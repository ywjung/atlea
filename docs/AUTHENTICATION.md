# Authentication System Documentation

Complete authentication system with JWT-based authentication, rate limiting, security logging, and user management.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [API Endpoints](#api-endpoints)
- [Security Features](#security-features)
- [Testing](#testing)
- [Configuration](#configuration)

## Features

### Core Authentication
- ✅ User registration with email validation
- ✅ Login with JWT token generation (Access + Refresh tokens)
- ✅ Logout with session invalidation
- ✅ Token refresh mechanism
- ✅ Password reset via email tokens
- ✅ Multi-session management

### Security
- ✅ Rate limiting (login, registration, password reset)
- ✅ Account lockout after failed attempts (5 failures = 15 min lock)
- ✅ OWASP-compliant password complexity
- ✅ Security event logging with data sanitization
- ✅ Session invalidation on password change
- ✅ IP tracking and user agent logging

### User Profile Management
- ✅ Profile updates (username)
- ✅ Password change (requires old password)
- ✅ Session listing and management
- ✅ Individual session revocation

## Architecture

### Components

```
src/auth/
├── models.py           # Pydantic data models
├── service.py          # Business logic layer
├── middleware.py       # JWT validation middleware
├── utils.py            # Password hashing, JWT utilities
├── rate_limiter.py     # Rate limiting middleware
├── security_logger.py  # Security event logging
├── password_policy.py  # Password complexity validation
└── password_reset.py   # Password reset tokens

src/routers/
└── auth.py            # FastAPI route handlers

tests/auth/
├── test_service.py         # Service layer tests
├── test_middleware.py      # Middleware tests
├── test_utils.py           # Utility tests
├── test_rate_limiter.py    # Rate limiting tests
├── test_security_logger.py # Security logging tests
├── test_password_policy.py # Password policy tests
├── test_token_refresh.py   # Token refresh tests
├── test_password_reset.py  # Password reset tests
└── test_profile.py         # Profile management tests
```

### Data Flow

```
Client Request
    ↓
Rate Limiter (Middleware)
    ↓
JWT Validation (Middleware) [Protected Routes]
    ↓
Route Handler (auth.py)
    ↓
Service Layer (service.py)
    ↓
PostgreSQL Storage
    ↓
Security Logger
```

## API Endpoints

### Public Endpoints

#### POST /api/auth/register
Register a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "username": "username",
  "password": "SecurePass123!"
}
```

**Password Requirements:**
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character (!@#$%^&*()_+-=[]{}|;:',.<>?/~`)
- No spaces

**Response:** (201 Created)
```json
{
  "message": "회원가입이 완료되었습니다",
  "user": {
    "user_id": "uuid",
    "email": "user@example.com",
    "username": "username",
    "created_at": "2025-12-26T00:00:00",
    "is_active": true,
    "role": "user"
  }
}
```

**Rate Limit:** 5 requests per 1 hour per IP

---

#### POST /api/auth/login
Authenticate user and receive tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response:** (200 OK)
```json
{
  "user": { /* user object */ },
  "tokens": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer"
  }
}
```

**Token Expiration:**
- Access Token: 1 hour
- Refresh Token: 7 days

**Rate Limit:** 10 requests per 5 minutes per IP

**Account Lockout:**
- 5 failed attempts → Account locked for 15 minutes
- Successful login resets failed attempt count

---

#### POST /api/auth/refresh
Refresh access token using refresh token.

**Request:**
```json
{
  "refresh_token": "eyJ..."
}
```

**Response:** (200 OK)
```json
{
  "user": { /* user object */ },
  "tokens": {
    "access_token": "new_eyJ...",
    "refresh_token": "new_eyJ...",
    "token_type": "bearer"
  }
}
```

**Rate Limit:** 10 requests per 5 minutes per IP

---

#### POST /api/auth/password-reset/request
Request password reset token.

**Request:**
```json
{
  "email": "user@example.com"
}
```

**Response:** (200 OK)
```json
{
  "message": "비밀번호 재설정 이메일이 발송되었습니다"
}
```

**Note:** 보안상 토큰은 응답에 포함되지 않으며, 실제 환경에서는 이메일로 전송됩니다.

**Token Expiration:** 30 minutes

**Rate Limit:** 3 requests per 1 hour per IP

---

#### POST /api/auth/password-reset/confirm
Reset password using reset token.

**Request:**
```json
{
  "token": "eyJ...",
  "new_password": "NewSecurePass123!"
}
```

**Response:** (200 OK)
```json
{
  "message": "비밀번호가 성공적으로 재설정되었습니다"
}
```

**Effects:**
- Password updated
- All sessions invalidated

---

### Protected Endpoints

All protected endpoints require `Authorization: Bearer <access_token>` header.

#### GET /api/auth/me
Get current user information.

**Response:** (200 OK)
```json
{
  "user": {
    "user_id": "uuid",
    "email": "user@example.com",
    "username": "username",
    "created_at": "2025-12-26T00:00:00",
    "last_login": "2025-12-26T12:00:00",
    "is_active": true,
    "role": "user"
  }
}
```

---

#### PUT /api/auth/profile
Update user profile.

**Request:**
```json
{
  "username": "new_username"
}
```

**Response:** (200 OK)
```json
{
  "message": "프로필이 업데이트되었습니다",
  "user": { /* updated user object */ }
}
```

---

#### POST /api/auth/change-password
Change user password.

**Request:**
```json
{
  "old_password": "OldPass123!",
  "new_password": "NewPass123!"
}
```

**Response:** (200 OK)
```json
{
  "message": "비밀번호가 변경되었습니다. 모든 세션이 로그아웃되었습니다."
}
```

**Effects:**
- Password updated
- All sessions invalidated (user must re-login)

---

#### GET /api/auth/sessions
List all active sessions for current user.

**Response:** (200 OK)
```json
{
  "sessions": [
    {
      "session_id": "uuid",
      "user_id": "uuid",
      "created_at": "2025-12-26T12:00:00",
      "expires_at": "2025-12-26T13:00:00",
      "ip_address": "192.168.1.100",
      "user_agent": "Mozilla/5.0..."
    }
  ]
}
```

---

#### DELETE /api/auth/sessions/{session_id}
Revoke a specific session.

**Response:** (200 OK)
```json
{
  "message": "세션이 무효화되었습니다"
}
```

---

#### POST /api/auth/logout
Logout and invalidate all sessions.

**Response:** (200 OK)
```json
{
  "message": "로그아웃되었습니다"
}
```

## Security Features

### Rate Limiting

Implemented using sliding window algorithm with in-memory storage.

| Endpoint | Max Requests | Window |
|----------|-------------|--------|
| Register | 5 | 1 hour |
| Login | 10 | 5 min |
| Password Reset Request | 3 | 1 hour |
| Token Refresh | 10 | 5 min |
| General API | 60 | 1 min |

**Response when rate limit exceeded:**
```json
HTTP 429 Too Many Requests
{
  "detail": "요청이 너무 많습니다. 300초 후에 다시 시도하세요."
}
Headers: {
  "Retry-After": "300"
}
```

### Account Lockout

- **Trigger:** 5 failed login attempts
- **Duration:** 15 minutes
- **Reset:** Successful login

**Locked account response:**
```json
HTTP 401 Unauthorized
{
  "detail": "계정이 잠겼습니다. 15분 후에 다시 시도하세요."
}
```

### Password Policy

OWASP-compliant requirements:

- **Length:** 8-128 characters
- **Uppercase:** At least 1 (A-Z)
- **Lowercase:** At least 1 (a-z)
- **Digit:** At least 1 (0-9)
- **Special Character:** At least 1 from `!@#$%^&*()_+-=[]{}|;:',.<>?/~\``
- **Forbidden:** No spaces

### Security Logging

All security events are logged with structured JSON:

```json
{
  "timestamp": "2025-12-26T12:00:00.000000",
  "event_type": "AUTH_LOGIN_SUCCESS",
  "level": "INFO",
  "user_id": "uuid",
  "ip_address": "192.168.1.100",
  "message": "User logged in successfully"
}
```

**Event Types:**
- `ACCOUNT_REGISTERED` - New user registration
- `AUTH_LOGIN_SUCCESS` - Successful login
- `AUTH_LOGIN_FAILED` - Failed login attempt
- `ACCOUNT_LOCKED` - Account locked due to failures
- `ACCOUNT_UNLOCKED` - Account unlocked
- `AUTH_LOGOUT` - User logout
- `RATE_LIMIT_EXCEEDED` - Rate limit hit
- `PASSWORD_RESET_REQUESTED` - Password reset requested
- `PASSWORD_RESET_COMPLETED` - Password successfully reset
- `PASSWORD_CHANGED` - Password changed via profile
- `PASSWORD_CHANGE_FAILED` - Password change failed
- `PROFILE_UPDATED` - Profile information updated
- `SESSION_REVOKED` - Session manually revoked
- `TOKEN_INVALID` - Invalid token used

**Data Sanitization:**
- Passwords: `***REDACTED***`
- Tokens: `***REDACTED***`
- Email: Partial masking (`use***@example.com`)

## Testing

### Test Coverage

Total: **164 tests** across 10 test files

| Test File | Tests | Coverage |
|-----------|-------|----------|
| test_service.py | 26 | Service layer logic |
| test_middleware.py | 9 | JWT validation |
| test_utils.py | 12 | Password hashing, JWT |
| test_rate_limiter.py | 14 | Rate limiting |
| test_security_logger.py | 20 | Security logging |
| test_password_policy.py | 28 | Password validation |
| test_token_refresh.py | 10 | Token refresh |
| test_password_reset.py | 15 | Password reset |
| test_profile.py | 13 | Profile management |
| test_routes.py | 17 | API endpoints |

### Running Tests

```bash
# All auth tests
python -m pytest tests/auth/ -v

# Specific test file
python -m pytest tests/auth/test_service.py -v

# With coverage
python -m pytest tests/auth/ --cov=src/auth --cov-report=html
```

### Test Environment

Tests use SQLite in-memory database to avoid external dependencies. All tests are async-compatible using `pytest-asyncio`.

## Configuration

### Environment Variables

```bash
# JWT Configuration
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256

# Token Expiration
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Rate Limiting
REGISTER_MAX_REQUESTS=5
REGISTER_WINDOW_SECONDS=3600
LOGIN_MAX_REQUESTS=10
LOGIN_WINDOW_SECONDS=300

# Account Lockout
MAX_FAILED_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=15
```

### PostgreSQL Storage Schema

```sql
-- User Data (users table)
users: id (UUID), email, username, hashed_password,
  created_at, last_login, is_active, role,
  failed_login_attempts, locked_until

-- Session Data (sessions table)
sessions: id (UUID), user_id (FK), created_at, expires_at,
  ip_address, user_agent, is_active

-- Rate Limiting (in-memory)
-- Sliding window algorithm, no persistent storage

-- Token Blacklist (token_blacklist table)
token_blacklist: id, token_jti, user_id, expires_at
```

## Error Responses

### 400 Bad Request
```json
{
  "detail": "이메일이 이미 사용 중입니다"
}
```

### 401 Unauthorized
```json
{
  "detail": "유효하지 않은 인증 정보입니다"
}
```

### 403 Forbidden
```json
{
  "detail": "세션에 대한 권한이 없습니다"
}
```

### 429 Too Many Requests
```json
{
  "detail": "요청이 너무 많습니다. 300초 후에 다시 시도하세요."
}
```

## Best Practices

### Client Implementation

1. **Store tokens securely:**
   - Never store in localStorage (XSS vulnerable)
   - Use httpOnly cookies or secure session storage

2. **Handle token refresh:**
   ```javascript
   if (response.status === 401) {
     const newTokens = await refreshTokens(refreshToken);
     // Retry original request with new access token
   }
   ```

3. **Implement rate limit handling:**
   ```javascript
   if (response.status === 429) {
     const retryAfter = response.headers.get('Retry-After');
     // Wait and retry
   }
   ```

4. **Secure password transmission:**
   - Always use HTTPS
   - Never log passwords
   - Clear password fields after use

### Production Deployment

1. **Change JWT secret key** - Generate strong random key
2. **Enable HTTPS** - Enforce TLS 1.2+
3. **Configure Redis persistence** - Enable AOF/RDB
4. **Set up monitoring** - Track security events
5. **Email integration** - Send password reset tokens via email
6. **Backup strategy** - Regular PostgreSQL backups

## Migration Guide

### From No Auth to This System

1. **Install dependencies:**
   ```bash
   pip install python-jose[cryptography] passlib[bcrypt] pydantic[email]
   ```

2. **Set environment variables** in `.env`

3. **Initialize PostgreSQL** with appropriate configuration

4. **Update routes** to include authentication middleware

5. **Test thoroughly** using provided test suite

### Upgrading Password Policy

If you need stricter password requirements:

1. Edit `src/auth/password_policy.py`
2. Update `MIN_LENGTH`, `REQUIRE_*` constants
3. Update tests in `test_password_policy.py`
4. Document changes in API documentation

## Troubleshooting

### Common Issues

**Issue:** "Account locked" error persists
- **Solution:** Check database for `locked_until` field, verify system time

**Issue:** Token refresh fails
- **Solution:** Ensure refresh token type is correct, check expiration

**Issue:** Rate limiting too aggressive
- **Solution:** Adjust `RateLimitConfig` values in `rate_limiter.py`

**Issue:** Tests failing with database connection
- **Solution:** Tests use SQLite in-memory database, no external DB needed. Check conftest.py imports.

## Changelog

### Week 4 (Latest)
- ✅ Token refresh mechanism
- ✅ Password reset functionality
- ✅ User profile management
- ✅ Session management
- ✅ Comprehensive testing (164 auth tests, 328 total project tests)

### Week 3
- ✅ Rate limiting middleware
- ✅ Security event logging
- ✅ Password complexity policy
- ✅ Account lockout mechanism

### Week 2
- ✅ Core authentication (register, login, logout)
- ✅ JWT middleware
- ✅ Session management
- ✅ Basic testing (63 tests)

## License

This authentication system is part of the ATLEA project.
