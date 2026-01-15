#!/usr/bin/env python3
"""
프로덕션 비밀키 생성 스크립트
"""
import secrets

print("=" * 60)
print("프로덕션 환경용 비밀키 생성")
print("=" * 60)
print()

# JWT Secret Key
jwt_secret = secrets.token_hex(32)
print(f"JWT_SECRET_KEY={jwt_secret}")
print()

# General Secret Key
secret_key = secrets.token_hex(32)
print(f"SECRET_KEY={secret_key}")
print()

print("=" * 60)
print("위 키를 .env.production 파일에 복사하세요")
print("=" * 60)
