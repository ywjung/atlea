import { test, expect } from '@playwright/test';

/**
 * E2E Tests: Authentication Flows
 *
 * Tests:
 * - User registration
 * - User login
 * - Password reset
 * - Session management
 * - Logout
 */

// Test data
const testUser = {
    username: `testuser_${Date.now()}`,
    email: `testuser_${Date.now()}@example.com`,
    password: 'TestPass123!',
    fullName: 'Test User',
};

test.describe('Authentication', () => {
    test.describe('Registration', () => {
        test('should register a new user successfully', async ({ page }) => {
            await page.goto('/register.html');

            // Fill registration form
            await page.fill('input[name="username"]', testUser.username);
            await page.fill('input[name="email"]', testUser.email);
            await page.fill('input[name="password"]', testUser.password);
            await page.fill('input[name="confirm_password"]', testUser.password);
            await page.fill('input[name="full_name"]', testUser.fullName);

            // Handle captcha if present (mock or skip in test environment)
            const captchaInput = page.locator('input[name="captcha"]');
            if (await captchaInput.isVisible()) {
                // In test environment, captcha might be disabled or have a test bypass
                await captchaInput.fill('1234');
            }

            // Submit form
            await page.click('button[type="submit"]');

            // Wait for success message or redirect
            await expect(page).toHaveURL(/login\.html/, { timeout: 10000 });

            // Verify success toast or message
            const toast = page.locator('.toast, .notification, .alert');
            if (await toast.isVisible()) {
                await expect(toast).toContainText(/success|registered/i);
            }
        });

        test('should show validation errors for invalid input', async ({ page }) => {
            await page.goto('/register.html');

            // Try to submit with weak password
            await page.fill('input[name="username"]', 'testuser');
            await page.fill('input[name="email"]', 'invalid-email');
            await page.fill('input[name="password"]', 'weak');
            await page.fill('input[name="confirm_password"]', 'weak');

            await page.click('button[type="submit"]');

            // Should show validation errors
            const errorMessages = page.locator('.error, .text-danger, [role="alert"]');
            await expect(errorMessages.first()).toBeVisible();
        });

        test('should prevent duplicate username registration', async ({ page }) => {
            await page.goto('/register.html');

            // Try to register with existing username
            await page.fill('input[name="username"]', 'admin');
            await page.fill('input[name="email"]', `unique_${Date.now()}@example.com`);
            await page.fill('input[name="password"]', testUser.password);
            await page.fill('input[name="confirm_password"]', testUser.password);
            await page.fill('input[name="full_name"]', 'Test User');

            await page.click('button[type="submit"]');

            // Should show error about duplicate username
            const errorMessage = page.locator('.toast, .notification, .alert');
            await expect(errorMessage).toContainText(/already exists|taken/i, {
                timeout: 5000,
            });
        });
    });

    test.describe('Login', () => {
        test('should login successfully with valid credentials', async ({ page }) => {
            await page.goto('/login.html');

            // Fill login form
            await page.fill('input[name="username"]', 'admin');
            await page.fill('input[name="password"]', 'admin123'); // Default admin password

            // Submit form
            await page.click('button[type="submit"]');

            // Should redirect to main page
            await expect(page).toHaveURL(/index\.html|\/$/);

            // Verify user is logged in (check for user menu or profile)
            const userMenu = page.locator(
                '#user-menu, .user-profile, [data-testid="user-menu"]'
            );
            await expect(userMenu).toBeVisible({ timeout: 5000 });
        });

        test('should show error with invalid credentials', async ({ page }) => {
            await page.goto('/login.html');

            await page.fill('input[name="username"]', 'nonexistent');
            await page.fill('input[name="password"]', 'wrongpassword');

            await page.click('button[type="submit"]');

            // Should show error message
            const errorMessage = page.locator('.toast, .notification, .alert');
            await expect(errorMessage).toContainText(/invalid|incorrect|failed/i);

            // Should remain on login page
            await expect(page).toHaveURL(/login\.html/);
        });

        test('should prevent login with empty credentials', async ({ page }) => {
            await page.goto('/login.html');

            await page.click('button[type="submit"]');

            // Should show validation errors
            const usernameInput = page.locator('input[name="username"]');
            const passwordInput = page.locator('input[name="password"]');

            await expect(usernameInput).toHaveAttribute('required', '');
            await expect(passwordInput).toHaveAttribute('required', '');
        });
    });

    test.describe('Password Reset', () => {
        test('should initiate password reset flow', async ({ page }) => {
            await page.goto('/reset-password.html');

            await page.fill('input[name="email"]', 'admin@example.com');
            await page.click('button[type="submit"]');

            // Should show success message
            const successMessage = page.locator('.toast, .notification, .alert');
            await expect(successMessage).toContainText(/sent|check your email/i, {
                timeout: 5000,
            });
        });

        test('should validate email format in password reset', async ({ page }) => {
            await page.goto('/reset-password.html');

            await page.fill('input[name="email"]', 'invalid-email');
            await page.click('button[type="submit"]');

            // Should show validation error
            const errorMessage = page.locator('.error, .text-danger, [role="alert"]');
            await expect(errorMessage.first()).toBeVisible();
        });
    });

    test.describe('Session Management', () => {
        test('should maintain session after page reload', async ({ page }) => {
            // Login first
            await page.goto('/login.html');
            await page.fill('input[name="username"]', 'admin');
            await page.fill('input[name="password"]', 'admin123');
            await page.click('button[type="submit"]');

            await expect(page).toHaveURL(/index\.html|\/$/);

            // Reload page
            await page.reload();

            // Should still be logged in
            const userMenu = page.locator(
                '#user-menu, .user-profile, [data-testid="user-menu"]'
            );
            await expect(userMenu).toBeVisible({ timeout: 5000 });
        });

        test('should logout successfully', async ({ page }) => {
            // Login first
            await page.goto('/login.html');
            await page.fill('input[name="username"]', 'admin');
            await page.fill('input[name="password"]', 'admin123');
            await page.click('button[type="submit"]');

            await expect(page).toHaveURL(/index\.html|\/$/);

            // Click logout
            const logoutButton = page.locator(
                'button:has-text("Logout"), a:has-text("Logout"), [data-testid="logout"]'
            );
            await logoutButton.click();

            // Should redirect to login page
            await expect(page).toHaveURL(/login\.html/, { timeout: 5000 });

            // Try to access protected page
            await page.goto('/');

            // Should be redirected back to login
            await expect(page).toHaveURL(/login\.html/);
        });
    });
});
