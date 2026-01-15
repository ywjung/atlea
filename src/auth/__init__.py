"""Authentication and authorization module for v2.2.0

This module provides comprehensive authentication and authorization features:
- User registration and login
- JWT token-based authentication
- Password security (bcrypt hashing, strength validation)
- Session management
- Brute-force protection
"""

from .models import User, Session, TokenPair, UserCreate, UserLogin, LoginResponse
from .service import AuthService
from .middleware import get_current_user, get_current_active_user, require_admin
from .utils import hash_password, verify_password, create_access_token, verify_token

__version__ = "2.2.0-dev"
__all__ = [
    "User",
    "Session",
    "TokenPair",
    "UserCreate",
    "UserLogin",
    "LoginResponse",
    "AuthService",
    "get_current_user",
    "get_current_active_user",
    "require_admin",
    "hash_password",
    "verify_password",
    "create_access_token",
    "verify_token",
]
