#!/usr/bin/env python3
"""
Organization Management Feature Testing Script

Tests all organization-based access control features:
1. User transfer between organizations
2. Self-service organization changes
3. Self-removal from organizations
4. Default organization protection
5. Permission scenarios
"""

import requests
import sys
from typing import Optional, Dict, List

BASE_URL = "http://localhost:8085"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_test(name: str):
    print(f"\n{Colors.BLUE}{Colors.BOLD}🧪 TEST: {name}{Colors.END}")

def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.END}")

def print_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.END}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.END}")

def print_info(msg: str):
    print(f"   {msg}")

class OrgTester:
    def __init__(self):
        self.tokens: Dict[str, str] = {}
        self.users: Dict[str, dict] = {}

    def login(self, email: str, password: str, label: str = None) -> bool:
        """Login and store JWT token"""
        label = label or email
        print_test(f"Login as {label}")

        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": password}
            )

            if response.status_code == 200:
                data = response.json()
                # Token is nested under "tokens" object
                tokens_obj = data.get("tokens", {})
                self.tokens[label] = tokens_obj.get("access_token")
                self.users[label] = data.get("user")

                user = self.users[label]
                print_success(f"Logged in as {user.get('username')}")
                print_info(f"Role: {user.get('role')}, Org: {user.get('org_id')}, Org Role: {user.get('org_role')}")
                return True
            else:
                print_error(f"Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print_error(f"Login exception: {e}")
            return False

    def get_headers(self, user_label: str) -> dict:
        """Get authorization headers for a user"""
        if user_label not in self.tokens:
            raise ValueError(f"User {user_label} not logged in")
        return {"Authorization": f"Bearer {self.tokens[user_label]}"}

    def test_get_organizations(self, user_label: str) -> Optional[List[dict]]:
        """Test GET /api/organizations"""
        print_test(f"Get Organizations ({user_label})")

        try:
            response = requests.get(
                f"{BASE_URL}/api/organizations",
                headers=self.get_headers(user_label)
            )

            if response.status_code == 200:
                data = response.json()
                orgs = data.get("organizations", [])
                print_success(f"Found {len(orgs)} organization(s)")
                for org in orgs:
                    print_info(f"- {org.get('name')} (ID: {org.get('id')}, Members: {org.get('member_count')})")
                return orgs
            else:
                print_error(f"Failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print_error(f"Exception: {e}")
            return None

    def test_create_organization(self, user_label: str, name: str, description: str) -> Optional[str]:
        """Test POST /api/organizations"""
        print_test(f"Create Organization: {name} ({user_label})")

        try:
            response = requests.post(
                f"{BASE_URL}/api/organizations",
                headers=self.get_headers(user_label),
                json={"name": name, "description": description}
            )

            if response.status_code == 200:
                data = response.json()
                org_id = data.get("organization", {}).get("id")
                print_success(f"Created organization: {name} (ID: {org_id})")
                return org_id
            else:
                print_error(f"Failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print_error(f"Exception: {e}")
            return None

    def test_add_member(self, user_label: str, org_id: str, member_email: str) -> bool:
        """Test POST /api/organizations/{org_id}/members"""
        print_test(f"Add Member: {member_email} to {org_id} ({user_label})")

        # Get user_id from email
        user_id = None
        for label, user in self.users.items():
            if user.get('email') == member_email:
                user_id = user.get('user_id')
                break

        if not user_id:
            print_error(f"User not found: {member_email}")
            return False

        try:
            response = requests.post(
                f"{BASE_URL}/api/organizations/{org_id}/members",
                headers=self.get_headers(user_label),
                json={"user_id": user_id}
            )

            if response.status_code == 200:
                data = response.json()
                print_success(data.get("message", "Member added"))
                return True
            else:
                print_error(f"Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print_error(f"Exception: {e}")
            return False

    def test_remove_member(self, user_label: str, org_id: str, member_email: str) -> bool:
        """Test DELETE /api/organizations/{org_id}/members/{user_id}"""
        print_test(f"Remove Member: {member_email} from {org_id} ({user_label})")

        # Get user_id from email
        user_id = None
        for label, user in self.users.items():
            if user.get('email') == member_email:
                user_id = user.get('user_id')
                break

        if not user_id:
            print_error(f"User not found: {member_email}")
            return False

        try:
            response = requests.delete(
                f"{BASE_URL}/api/organizations/{org_id}/members/{user_id}",
                headers=self.get_headers(user_label)
            )

            if response.status_code == 200:
                data = response.json()
                print_success(data.get("message", "Member removed"))
                return True
            else:
                print_error(f"Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print_error(f"Exception: {e}")
            return False

    def test_delete_organization(self, user_label: str, org_id: str) -> bool:
        """Test DELETE /api/organizations/{org_id}"""
        print_test(f"Delete Organization: {org_id} ({user_label})")

        try:
            response = requests.delete(
                f"{BASE_URL}/api/organizations/{org_id}",
                headers=self.get_headers(user_label)
            )

            if response.status_code == 200:
                data = response.json()
                print_success(data.get("message", "Organization deleted"))
                return True
            else:
                print_error(f"Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print_error(f"Exception: {e}")
            return False


def run_tests():
    """Run comprehensive organization feature tests"""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}🧪 Organization Management Feature Testing{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

    tester = OrgTester()

    # Test 1: Login as admin
    if not tester.login("admin@admin.com", "Admin123!@#", "admin"):
        print_error("Cannot proceed without admin login")
        return False

    # Test 2: Login as test user (if exists)
    tester.login("test@example.com", "Admin123!@#", "test_user")

    # Test 3: Get organizations (admin)
    orgs = tester.test_get_organizations("admin")
    if not orgs:
        print_error("Cannot get organizations")
        return False

    # Find default organization
    default_org = next((o for o in orgs if o.get('id') == 'default'), None)
    if not default_org:
        print_error("Default organization not found")
        return False

    # Test 4: Create test organization
    test_org_id = tester.test_create_organization(
        "admin",
        "Test Organization",
        "Organization for testing features"
    )
    if not test_org_id:
        print_warning("Couldn't create test organization (may already exist)")

    # Test 5: Transfer user between organizations
    if "test_user" in tester.users and test_org_id:
        print_test("User Transfer Scenario")
        # Add test user to test org (should transfer from default)
        tester.test_add_member("admin", test_org_id, "test@example.com")

        # Transfer back to default
        tester.test_add_member("admin", "default", "test@example.com")

    # Test 6: Self-service organization change
    if "test_user" in tester.users and test_org_id:
        print_test("Self-Service Organization Change")
        # User changes their own organization
        tester.test_add_member("test_user", test_org_id, "test@example.com")

    # Test 7: Self-removal from organization
    if "test_user" in tester.users and test_org_id:
        print_test("Self-Removal from Organization")
        # User removes themselves (should return to default)
        tester.test_remove_member("test_user", test_org_id, "test@example.com")

    # Test 8: Default organization protection
    print_test("Default Organization Protection")
    tester.test_delete_organization("admin", "default")
    print_info("Expected: Should fail with error message")

    # Test 9: Prevent removal from default org
    if "test_user" in tester.users:
        print_test("Prevent Removal from Default Organization")
        tester.test_remove_member("admin", "default", "test@example.com")
        print_info("Expected: Should fail with error message")

    # Test 10: Permission scenarios
    if "test_user" in tester.users and test_org_id:
        print_test("Permission Scenario: Non-admin adding other users")
        # Test user tries to add admin to test org (should fail)
        tester.test_add_member("test_user", test_org_id, "admin@admin.com")
        print_info("Expected: Should fail - only org admins can add others")

    # Cleanup: Delete test organization
    if test_org_id and test_org_id != "default":
        print_test("Cleanup: Delete test organization")
        tester.test_delete_organization("admin", test_org_id)

    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.GREEN}{Colors.BOLD}✅ Testing completed!{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

    return True


if __name__ == "__main__":
    try:
        success = run_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Testing interrupted by user{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.END}")
        sys.exit(1)
