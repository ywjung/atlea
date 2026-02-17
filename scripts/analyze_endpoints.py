#!/usr/bin/env python3
"""
Analyze web_server.py endpoints for authentication status
"""
import re
from pathlib import Path

def analyze_endpoints():
    web_server_path = Path(__file__).parent.parent / "src" / "web_server.py"
    content = web_server_path.read_text()

    # Find all endpoint definitions
    endpoint_pattern = r'@app\.(get|post|put|delete|patch)\("([^"]+)".*?\)\s*\n\s*async def (\w+)\(([^)]*)\):'
    matches = re.finditer(endpoint_pattern, content, re.MULTILINE | re.DOTALL)

    public_endpoints = []
    user_endpoints = []
    admin_endpoints = []
    missing_auth = []

    for match in matches:
        method = match.group(1).upper()
        path = match.group(2)
        func_name = match.group(3)
        params = match.group(4)

        # Check authentication
        has_user_auth = "get_current_active_user" in params or "current_user" in params
        has_admin_check = False

        # Check function body for require_admin
        func_start = match.end()
        func_body = content[func_start:func_start+500]
        has_admin_check = "require_admin" in func_body

        # Classify endpoints
        endpoint_info = f"{method:6} {path:50} ({func_name})"

        # Public endpoints (no auth needed)
        if any(p in path for p in ["/health", "/metrics", "/favicon", "/static", "/docs", "/redoc", "/openapi.json", "^/$"]) or \
           path in ["/", "/api/auth/login", "/api/auth/register"]:
            public_endpoints.append(endpoint_info)
        # Admin endpoints
        elif "/admin/" in path or "/db-backup/" in path:
            if has_admin_check:
                admin_endpoints.append(f"✅ {endpoint_info}")
            else:
                missing_auth.append(f"❌ ADMIN: {endpoint_info}")
        # User endpoints
        else:
            if has_user_auth:
                user_endpoints.append(f"✅ {endpoint_info}")
            else:
                missing_auth.append(f"❌ USER:  {endpoint_info}")

    # Print results
    print("\n" + "="*100)
    print("PUBLIC ENDPOINTS (No Auth Required)")
    print("="*100)
    for ep in public_endpoints:
        print(ep)

    print("\n" + "="*100)
    print("USER ENDPOINTS (Authentication Required)")
    print("="*100)
    for ep in user_endpoints:
        print(ep)

    print("\n" + "="*100)
    print("ADMIN ENDPOINTS (Admin Authorization Required)")
    print("="*100)
    for ep in admin_endpoints:
        print(ep)

    print("\n" + "="*100)
    print("MISSING AUTHENTICATION ⚠️")
    print("="*100)
    for ep in missing_auth:
        print(ep)

    print(f"\n\nSummary:")
    print(f"  Public:  {len(public_endpoints)} endpoints")
    print(f"  User:    {len(user_endpoints)} endpoints (authenticated)")
    print(f"  Admin:   {len(admin_endpoints)} endpoints (authorized)")
    print(f"  Missing: {len(missing_auth)} endpoints ⚠️")

if __name__ == "__main__":
    analyze_endpoints()
