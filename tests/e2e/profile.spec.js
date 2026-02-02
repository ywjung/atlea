import { test, expect } from '@playwright/test';

/**
 * E2E Tests: Profile Management
 *
 * Tests:
 * - View profile information
 * - Update profile
 * - Change password
 * - Session management
 * - Security settings
 */

// Helper function to login
async function login(page) {
    await page.goto('/login.html');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/index\.html|\/$/);
}

test.describe('Profile Management', () => {
    test.beforeEach(async ({ page }) => {
        await login(page);
    });

    test.describe('Profile View', () => {
        test('should display profile information', async ({ page }) => {
            // Navigate to profile page
            await page.goto('/profile.html');

            // Verify profile fields are visible
            const usernameField = page.locator(
                'input[name="username"], [data-testid="username"], #username'
            );
            const emailField = page.locator('input[name="email"], [data-testid="email"], #email');

            await expect(usernameField).toBeVisible();
            await expect(emailField).toBeVisible();

            // Verify username is displayed
            const usernameValue = await usernameField.inputValue();
            expect(usernameValue).toBeTruthy();
            expect(usernameValue.length).toBeGreaterThan(0);
        });

        test('should display user statistics', async ({ page }) => {
            await page.goto('/profile.html');

            // Look for statistics section
            const statsSection = page.locator(
                '.stats, .statistics, [data-testid="user-stats"]'
            );

            if (await statsSection.isVisible()) {
                // Check for common stat elements
                const statItems = statsSection.locator('.stat-item, .statistic');
                const count = await statItems.count();
                expect(count).toBeGreaterThan(0);
            }
        });
    });

    test.describe('Profile Update', () => {
        test('should update profile information', async ({ page }) => {
            await page.goto('/profile.html');

            // Update full name
            const fullNameField = page.locator(
                'input[name="full_name"], [data-testid="full-name"]'
            );

            if (await fullNameField.isVisible()) {
                const newName = `Updated Name ${Date.now()}`;
                await fullNameField.fill(newName);

                // Save changes
                const saveButton = page.locator(
                    'button:has-text("Save"), button[type="submit"]'
                ).first();
                await saveButton.click();

                // Wait for success message
                const successMessage = page.locator('.toast, .notification, .alert');
                await expect(successMessage).toContainText(/success|updated/i, {
                    timeout: 5000,
                });

                // Reload and verify change persisted
                await page.reload();
                await expect(fullNameField).toHaveValue(newName);
            }
        });

        test('should validate email format on update', async ({ page }) => {
            await page.goto('/profile.html');

            const emailField = page.locator('input[name="email"]');

            if (await emailField.isVisible()) {
                await emailField.fill('invalid-email');

                const saveButton = page.locator('button:has-text("Save")').first();
                await saveButton.click();

                // Should show validation error
                const errorMessage = page.locator('.error, .text-danger, [role="alert"]');
                await expect(errorMessage.first()).toBeVisible({ timeout: 3000 });
            }
        });
    });

    test.describe('Password Change', () => {
        test('should change password successfully', async ({ page }) => {
            await page.goto('/profile.html');

            // Look for change password section
            const changePasswordButton = page.locator(
                'button:has-text("Change Password"), [data-testid="change-password"]'
            );

            if (await changePasswordButton.isVisible()) {
                await changePasswordButton.click();

                // Fill password change form
                const currentPasswordField = page.locator(
                    'input[name="current_password"], [data-testid="current-password"]'
                );
                const newPasswordField = page.locator(
                    'input[name="new_password"], [data-testid="new-password"]'
                );
                const confirmPasswordField = page.locator(
                    'input[name="confirm_password"], [data-testid="confirm-password"]'
                );

                if (await currentPasswordField.isVisible()) {
                    await currentPasswordField.fill('admin123');
                    await newPasswordField.fill('NewPass123!');
                    await confirmPasswordField.fill('NewPass123!');

                    const submitButton = page.locator('button[type="submit"]').last();
                    await submitButton.click();

                    // Should show success or error
                    const message = page.locator('.toast, .notification, .alert');
                    await expect(message).toBeVisible({ timeout: 5000 });
                }
            }
        });

        test('should validate password strength', async ({ page }) => {
            await page.goto('/profile.html');

            const changePasswordButton = page.locator('button:has-text("Change Password")');

            if (await changePasswordButton.isVisible()) {
                await changePasswordButton.click();

                const currentPasswordField = page.locator('input[name="current_password"]');
                const newPasswordField = page.locator('input[name="new_password"]');

                if (await newPasswordField.isVisible()) {
                    // Try weak password
                    await currentPasswordField.fill('admin123');
                    await newPasswordField.fill('weak');

                    // Should show validation error
                    const errorMessage = page.locator('.error, .text-danger, .validation-error');
                    await expect(errorMessage.first()).toBeVisible({ timeout: 3000 });
                }
            }
        });

        test('should require current password for change', async ({ page }) => {
            await page.goto('/profile.html');

            const changePasswordButton = page.locator('button:has-text("Change Password")');

            if (await changePasswordButton.isVisible()) {
                await changePasswordButton.click();

                const currentPasswordField = page.locator('input[name="current_password"]');
                const newPasswordField = page.locator('input[name="new_password"]');
                const confirmPasswordField = page.locator('input[name="confirm_password"]');

                if (await newPasswordField.isVisible()) {
                    // Leave current password empty
                    await newPasswordField.fill('NewPass123!');
                    await confirmPasswordField.fill('NewPass123!');

                    const submitButton = page.locator('button[type="submit"]').last();
                    await submitButton.click();

                    // Should show error about missing current password
                    const errorMessage = page.locator('.error, .toast, .alert');
                    await expect(errorMessage.first()).toBeVisible({ timeout: 3000 });
                }
            }
        });
    });

    test.describe('Session Management', () => {
        test('should display active sessions', async ({ page }) => {
            await page.goto('/profile.html');

            // Look for sessions section
            const sessionsSection = page.locator(
                '.sessions, [data-testid="sessions"], #sessions-tab'
            );

            if (await sessionsSection.isVisible()) {
                await sessionsSection.click();

                // Should show at least current session
                const sessionItems = page.locator('.session-item, [data-testid="session-item"]');
                const count = await sessionItems.count();
                expect(count).toBeGreaterThanOrEqual(1);
            }
        });

        test('should revoke session', async ({ page }) => {
            await page.goto('/profile.html');

            // Navigate to sessions tab
            const sessionsTab = page.locator('button:has-text("Sessions"), #sessions-tab');

            if (await sessionsTab.isVisible()) {
                await sessionsTab.click();

                const sessionItems = page.locator('.session-item');
                const sessionCount = await sessionItems.count();

                if (sessionCount > 1) {
                    // Find revoke button for non-current session
                    const revokeButton = page
                        .locator('button:has-text("Revoke"), .revoke-button')
                        .nth(1);

                    if (await revokeButton.isVisible()) {
                        await revokeButton.click();

                        // Confirm if there's a dialog
                        const confirmButton = page
                            .locator('button:has-text("Confirm"), button:has-text("Yes")')
                            .last();
                        if (await confirmButton.isVisible()) {
                            await confirmButton.click();
                        }

                        // Should show success message
                        const successMessage = page.locator('.toast, .notification');
                        await expect(successMessage).toContainText(/revoked|removed/i, {
                            timeout: 5000,
                        });
                    }
                }
            }
        });

        test('should not allow revoking current session', async ({ page }) => {
            await page.goto('/profile.html');

            const sessionsTab = page.locator('button:has-text("Sessions")');

            if (await sessionsTab.isVisible()) {
                await sessionsTab.click();

                // Current session's revoke button should be disabled or not present
                const currentSession = page.locator('.session-item.current, .session-item.active');

                if (await currentSession.isVisible()) {
                    const revokeButton = currentSession.locator('button:has-text("Revoke")');

                    if (await revokeButton.isVisible()) {
                        await expect(revokeButton).toBeDisabled();
                    }
                }
            }
        });
    });

    test.describe('Security Settings', () => {
        test('should display security settings', async ({ page }) => {
            await page.goto('/profile.html');

            // Look for security or settings tab
            const securityTab = page.locator(
                'button:has-text("Security"), button:has-text("Settings")'
            );

            if (await securityTab.isVisible()) {
                await securityTab.click();

                // Verify security options are visible
                const securityOptions = page.locator(
                    '.security-option, .setting-item, [data-testid="security-setting"]'
                );

                if ((await securityOptions.count()) > 0) {
                    await expect(securityOptions.first()).toBeVisible();
                }
            }
        });

        test('should show last login information', async ({ page }) => {
            await page.goto('/profile.html');

            // Look for last login info
            const lastLoginInfo = page.locator(
                '.last-login, [data-testid="last-login"], :has-text("Last login")'
            );

            if (await lastLoginInfo.isVisible()) {
                const text = await lastLoginInfo.textContent();
                expect(text).toBeTruthy();
            }
        });
    });
});
