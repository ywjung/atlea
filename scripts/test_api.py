#!/usr/bin/env python3
"""
API Endpoint Testing Script

Tests organization-based access control implementation
"""

import requests
import sys
from typing import Optional

BASE_URL = "http://localhost:8085"

class APITester:
    def __init__(self):
        self.token: Optional[str] = None
        self.user_info: Optional[dict] = None

    def login(self, email: str, password: str) -> bool:
        """Login and get JWT token"""
        print(f"\n🔐 Logging in as {email}...")

        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )

        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.user_info = data.get("user")
            print(f"✅ Login successful!")
            print(f"   User: {self.user_info.get('username')}")
            print(f"   Role: {self.user_info.get('role')}")
            print(f"   Org ID: {self.user_info.get('org_id')}")
            print(f"   Org Role: {self.user_info.get('org_role')}")
            return True
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   {response.text}")
            return False

    def get_headers(self) -> dict:
        """Get authorization headers"""
        if not self.token:
            raise ValueError("Not logged in")
        return {"Authorization": f"Bearer {self.token}"}

    def test_get_organizations(self) -> bool:
        """Test GET /api/organizations"""
        print("\n📋 Testing GET /api/organizations...")

        response = requests.get(
            f"{BASE_URL}/api/organizations",
            headers=self.get_headers()
        )

        if response.status_code == 200:
            data = response.json()
            orgs = data.get("organizations", [])
            print(f"✅ Success! Found {len(orgs)} organization(s)")
            for org in orgs:
                print(f"   - {org.get('name')} (ID: {org.get('id')})")
                print(f"     Members: {org.get('member_count')}, Active: {org.get('is_active')}")
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"   {response.text}")
            return False

    def test_get_organization_details(self, org_id: str) -> bool:
        """Test GET /api/organizations/{org_id}"""
        print(f"\n🔍 Testing GET /api/organizations/{org_id}...")

        response = requests.get(
            f"{BASE_URL}/api/organizations/{org_id}",
            headers=self.get_headers()
        )

        if response.status_code == 200:
            data = response.json()
            org = data.get("organization", {})
            print(f"✅ Success!")
            print(f"   Name: {org.get('name')}")
            print(f"   Description: {org.get('description')}")
            print(f"   Created: {org.get('created_at')}")

            stats = org.get('stats', {})
            print(f"   Stats:")
            print(f"     - Members: {stats.get('member_count')}")
            print(f"     - Admins: {stats.get('admin_count')}")
            print(f"     - Groups: {stats.get('group_count')}")
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"   {response.text}")
            return False

    def test_get_groups(self) -> bool:
        """Test GET /api/groups (organization-filtered)"""
        print("\n📁 Testing GET /api/groups (should be filtered by org)...")

        response = requests.get(
            f"{BASE_URL}/api/groups",
            headers=self.get_headers()
        )

        if response.status_code == 200:
            data = response.json()
            groups = data.get("groups", [])
            print(f"✅ Success! Found {len(groups)} group(s)")
            for group in groups[:5]:  # Show first 5
                print(f"   - {group.get('name')} (ID: {group.get('id')})")
            if len(groups) > 5:
                print(f"   ... and {len(groups) - 5} more")
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"   {response.text}")
            return False

    def test_get_documents(self) -> bool:
        """Test GET /api/documents (organization-filtered)"""
        print("\n📄 Testing GET /api/documents (should be filtered by org)...")

        response = requests.get(
            f"{BASE_URL}/api/documents",
            headers=self.get_headers()
        )

        if response.status_code == 200:
            data = response.json()
            docs = data.get("documents", [])
            print(f"✅ Success! Found {len(docs)} document(s)")
            for doc in docs[:5]:  # Show first 5
                print(f"   - {doc.get('name')} (Group: {doc.get('group_name', 'N/A')})")
            if len(docs) > 5:
                print(f"   ... and {len(docs) - 5} more")
            return True
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"   {response.text}")
            return False


def main():
    """Run API tests"""
    print("=" * 60)
    print("API Endpoint Testing")
    print("=" * 60)

    # Get login credentials
    if len(sys.argv) < 3:
        print("\nUsage: python test_api.py <email> <password>")
        print("\nExample: python test_api.py admin@example.com adminpass")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]

    tester = APITester()

    # Test 1: Login
    if not tester.login(email, password):
        print("\n❌ Login failed. Cannot proceed with tests.")
        sys.exit(1)

    # Test 2: Get Organizations
    tester.test_get_organizations()

    # Test 3: Get Organization Details (if user has org_id)
    if tester.user_info and tester.user_info.get("org_id"):
        org_id = tester.user_info["org_id"]
        tester.test_get_organization_details(org_id)

    # Test 4: Get Groups (filtered by org)
    tester.test_get_groups()

    # Test 5: Get Documents (filtered by org)
    tester.test_get_documents()

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
