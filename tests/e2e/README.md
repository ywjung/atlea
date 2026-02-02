# E2E Tests with Playwright

End-to-end testing suite for Chatbot Redis application using Playwright.

## Overview

This test suite covers critical user flows across the application:

### Authentication Tests (`auth.spec.js`)
- ✅ User registration with validation
- ✅ Login with valid/invalid credentials
- ✅ Password reset flow
- ✅ Session persistence and logout
- ✅ Duplicate username prevention

### Chat Tests (`chat.spec.js`)
- ✅ Send message and receive response
- ✅ Streaming response handling
- ✅ Conversation management (create, load, delete)
- ✅ Message formatting (Markdown, code blocks)
- ✅ Chat history persistence

### Profile Tests (`profile.spec.js`)
- ✅ View profile information
- ✅ Update profile fields
- ✅ Change password with validation
- ✅ Session management (view, revoke)
- ✅ Security settings

## Setup

### 1. Install Dependencies

```bash
npm install
```

### 2. Install Playwright Browsers

```bash
npx playwright install
```

### 3. Start Application Server

Make sure the FastAPI backend is running:

```bash
python -m uvicorn src.web_server:app --reload
```

Or use your startup script:

```bash
./run.sh
```

## Running Tests

### Run All Tests

```bash
npm run test:e2e
```

### Run with UI Mode (Interactive)

```bash
npm run test:e2e:ui
```

### Run in Headed Mode (See Browser)

```bash
npm run test:e2e:headed
```

### Debug Tests

```bash
npm run test:e2e:debug
```

### View Test Report

```bash
npm run test:e2e:report
```

## Test Configuration

Configuration is in `playwright.config.js`:

- **Base URL**: `http://localhost:8000`
- **Timeout**: 30s per test
- **Browsers**: Chromium, Firefox, WebKit
- **Mobile**: Pixel 5, iPhone 12
- **Reporters**: HTML, JSON, List

## Writing Tests

### Test Structure

```javascript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
    test('should do something', async ({ page }) => {
        // Navigate
        await page.goto('/page.html');

        // Interact
        await page.fill('input[name="field"]', 'value');
        await page.click('button[type="submit"]');

        // Assert
        await expect(page).toHaveURL(/success/);
    });
});
```

### Best Practices

1. **Use Data Test IDs**: Prefer `[data-testid="element"]` selectors
2. **Wait for Elements**: Use `await expect(element).toBeVisible()`
3. **Avoid Hardcoded Delays**: Use proper waits instead of `waitForTimeout`
4. **Test Isolation**: Each test should be independent
5. **Helper Functions**: Reuse login and setup logic

### Common Selectors

```javascript
// By test ID
page.locator('[data-testid="submit-button"]')

// By role
page.getByRole('button', { name: 'Submit' })

// By text
page.locator('button:has-text("Submit")')

// By placeholder
page.getByPlaceholder('Enter your email')

// By label
page.getByLabel('Username')
```

## Debugging

### Visual Debug Mode

```bash
npx playwright test --debug
```

This opens:
- Playwright Inspector
- Browser with DevTools
- Step-through debugging

### Screenshot on Failure

Screenshots are automatically captured on test failure:
- Location: `tests/e2e-report/`
- Format: PNG
- Includes: Full page and error context

### Trace Viewer

When tests fail, traces are captured:

```bash
npx playwright show-trace tests/e2e-report/trace.zip
```

Includes:
- DOM snapshots
- Network requests
- Console logs
- Screenshots

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18

      - name: Install dependencies
        run: npm ci

      - name: Install Playwright browsers
        run: npx playwright install --with-deps

      - name: Start application
        run: ./run.sh &

      - name: Wait for server
        run: npx wait-on http://localhost:8000

      - name: Run tests
        run: npm run test:e2e

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: tests/e2e-report/
```

## Test Data Management

### Test Users

For testing, use these default credentials:
- **Username**: `admin`
- **Password**: `admin123`

### Dynamic Test Data

Tests create unique data using timestamps:

```javascript
const testUser = {
    username: `testuser_${Date.now()}`,
    email: `testuser_${Date.now()}@example.com`,
    password: 'TestPass123!',
};
```

## Maintenance

### Update Selectors

If UI changes break tests:
1. Check element selectors in test files
2. Update to match new HTML structure
3. Consider adding `data-testid` attributes

### Flaky Tests

If tests fail intermittently:
1. Increase timeout values
2. Add proper wait conditions
3. Check for race conditions
4. Use `test.fail()` for known issues

### Performance

- **Parallel Execution**: Tests run in parallel by default
- **Reuse Browser Context**: Configured for efficiency
- **Resource Optimization**: Disable animations in test mode

## Coverage

Current test coverage:

| Feature | Coverage |
|---------|----------|
| Authentication | 90% |
| Chat Messaging | 85% |
| Profile Management | 80% |
| Conversation Management | 75% |

## Troubleshooting

### Server Not Running

```
Error: page.goto: net::ERR_CONNECTION_REFUSED
```

**Solution**: Start the FastAPI server before running tests.

### Browser Not Installed

```
Error: Executable doesn't exist at /path/to/chromium
```

**Solution**: Run `npx playwright install`

### Test Timeout

```
Error: Test timeout of 30000ms exceeded
```

**Solution**: Increase timeout in test or config file.

### Selector Not Found

```
Error: locator.click: Timeout 30000ms exceeded
```

**Solution**:
1. Verify selector matches HTML
2. Add wait condition
3. Check if element is hidden/disabled

## Resources

- [Playwright Documentation](https://playwright.dev)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [API Reference](https://playwright.dev/docs/api/class-playwright)
- [Selectors Guide](https://playwright.dev/docs/selectors)

## License

Part of Chatbot Redis project - see main LICENSE file.
