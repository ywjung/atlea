# Unit Tests with Vitest

Unit testing suite for Chatbot Redis modular JavaScript code.

## Overview

This test suite provides unit-level testing for ES6 modules:

### Test Coverage

| Module | Test File | Tests | Status |
|--------|-----------|-------|--------|
| **Utils/Storage** | `utils/storage.test.js` | 15 | ✅ 100% Passing |
| **Utils/Validation** | `utils/validation.test.js` | 18 | ⚠️ 78% Passing |
| **Utils/Helpers** | `utils/helpers.test.js` | 18 | ⚠️ 33% Passing |
| **Auth/Session** | `auth/session.test.js` | 24 | ⚠️ 75% Passing |
| **UI/Toast** | `ui/toast.test.js` | 14 | ❌ Needs Implementation |

**Current Status**: 53/89 tests passing (60%)

## Setup

### Install Dependencies

```bash
npm install
```

Dependencies include:
- `vitest`: Fast unit test framework
- `@vitest/ui`: Interactive UI for tests
- `@vitest/coverage-v8`: Coverage reporting
- `jsdom`: DOM environment for testing

## Running Tests

### Run All Unit Tests

```bash
npm run test:unit
```

### Watch Mode (Auto-rerun on changes)

```bash
npm run test:unit:watch
# or
npm test
```

### Interactive UI Mode

```bash
npm run test:unit:ui
```

Opens browser with interactive test dashboard.

### Coverage Report

```bash
npm run test:coverage
```

Generates coverage reports in multiple formats:
- Terminal output
- HTML report in `coverage/` directory
- JSON/LCOV for CI integration

## Test Structure

### Utilities: Storage (`utils/storage.test.js`)

**Status**: ✅ 15/15 passing

Tests localStorage and sessionStorage wrapper functions:

```javascript
✅ should set and get items
✅ should handle JSON objects
✅ should remove items
✅ should return null for non-existent keys
✅ should handle arrays
✅ should overwrite existing values
✅ should set and get session items
✅ should handle JSON objects in session
✅ should remove session items
✅ should be independent from localStorage
✅ should handle invalid JSON gracefully
✅ should handle null values
✅ should persist primitive types correctly
✅ should persist nested objects
```

**Coverage**: 100%
- All storage operations tested
- Error handling verified
- Session/local independence confirmed

### Utilities: Validation (`utils/validation.test.js`)

**Status**: ⚠️ 14/18 passing (4 failing due to API mismatch)

Tests input validation functions:

```javascript
Email Validation:
✅ should validate correct email addresses
✅ should reject invalid email addresses
✅ should handle edge cases

Password Validation (6 criteria):
✅ should accept strong passwords
✅ should reject passwords without uppercase
✅ should reject passwords without lowercase
✅ should reject passwords without numbers
✅ should reject passwords without special characters
✅ should reject passwords shorter than 8 characters
✅ should reject passwords with spaces
✅ should return all errors for very weak passwords

Username Validation:
❌ API returns {valid, error} instead of boolean
⚠️ Needs test adjustment

Filename Sanitization:
✅ should remove dangerous characters
✅ should preserve safe characters
✅ should handle edge cases
```

**Coverage**: ~80%
- Email validation: Complete
- Password validation: Complete (6-criteria system)
- Username validation: Needs API adjustment
- Filename sanitization: Complete

### Utilities: Helpers (`utils/helpers.test.js`)

**Status**: ⚠️ 6/18 passing (12 failing - functions don't exist or have different APIs)

Tests utility helper functions:

```javascript
Format Functions:
❌ formatTimestamp (may not exist)
❌ formatFileSize (may not exist)
❌ formatNumber (may not exist)

Timing Functions:
❌ debounce (may not exist or different API)
❌ throttle (may not exist or different API)

ID Generation:
✅ generateId
✅ generateUUID

Async Utilities:
✅ sleep
```

**Issues**: Many helper functions either don't exist in the module or have different APIs than expected. Needs investigation and test adjustment.

### Auth: Session (`auth/session.test.js`)

**Status**: ⚠️ 18/24 passing (6 failing - edge cases)

Tests authentication session management:

```javascript
Token Management:
✅ should set and get access token
✅ should set and get refresh token
✅ should clear tokens
✅ should handle null tokens

User Management:
✅ should set and get user
✅ should clear user
❌ should get user ID (edge case)
✅ should get user role
✅ should return null for missing user data

Session ID:
✅ should set and get session ID
✅ should clear session ID

Authentication Status:
✅ should return true when authenticated
✅ should return false when not authenticated (no token)
❌ should return false when not authenticated (no user)
✅ should return false when nothing is set

Admin Check:
✅ should return true for admin users
✅ should return false for non-admin users
❌ should return false when no user is set
❌ should handle case-insensitive role check

Clear All:
✅ should clear all authentication data

Edge Cases:
✅ should handle malformed user data
✅ should handle empty strings
❌ should handle user without role
❌ should handle user without id
```

**Coverage**: ~75%
- Core functionality: Complete
- Edge cases: Need adjustment

### UI: Toast (`ui/toast.test.js`)

**Status**: ❌ 0/14 passing (needs real DOM or better mocks)

Toast notification system tests:

```javascript
❌ All tests failing - needs implementation adjustment

Tests planned:
- Create toast with message
- Apply correct type classes
- Handle different toast types
- Auto-remove after duration
- Handle multiple toasts
- Manual close
- Container creation
- Edge cases
```

**Issues**: Mock DOM implementation incomplete. Needs either:
1. Better jsdom integration
2. Simplified mocks
3. Integration tests instead of unit tests

## Configuration

### Vitest Config (`vite.config.js`)

```javascript
test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.js',
    include: ['tests/unit/**/*.test.js'],
    exclude: ['tests/e2e/**', 'node_modules/**', 'dist/**'],
    coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html', 'lcov'],
        exclude: [
            'node_modules/',
            'dist/',
            'tests/',
            '**/*.spec.js',
            '**/*.test.js',
            'static/js/compat/**', // Compatibility layer
            'static/*.js', // Legacy scripts
        ],
        all: true,
        lines: 70,
        functions: 70,
        branches: 70,
        statements: 70,
    },
},
```

### Test Setup (`tests/setup.js`)

Provides:
- Mock `localStorage` and `sessionStorage`
- Mock `fetch` for API calls
- Mock `DOMPurify` for sanitization
- Mock `marked` for markdown
- Automatic storage clearing before each test

## Writing Tests

### Basic Test Structure

```javascript
import { describe, it, expect, beforeEach } from 'vitest';
import { myFunction } from '../../../static/js/module/file.js';

describe('module/file', () => {
    beforeEach(() => {
        // Setup before each test
        localStorage.clear();
    });

    describe('Function Group', () => {
        it('should do something specific', () => {
            // Arrange
            const input = 'test';

            // Act
            const result = myFunction(input);

            // Assert
            expect(result).toBe('expected');
        });
    });
});
```

### Async Testing

```javascript
it('should handle async operations', async () => {
    const result = await asyncFunction();
    expect(result).toBeDefined();
});
```

### Mocking

```javascript
import { vi } from 'vitest';

it('should mock function', () => {
    const mockFn = vi.fn(() => 'mocked');
    expect(mockFn()).toBe('mocked');
});
```

### Timer Testing

```javascript
import { vi } from 'vitest';

it('should handle timers', async () => {
    vi.useFakeTimers();

    const callback = vi.fn();
    setTimeout(callback, 1000);

    vi.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalled();

    vi.restoreAllMocks();
});
```

## Best Practices

### 1. Test Independence
- Each test should run independently
- Use `beforeEach` for setup
- Clear state between tests

### 2. Clear Test Names
- Use descriptive names: `should validate email format`
- Group related tests in `describe` blocks

### 3. Arrange-Act-Assert Pattern
```javascript
// Arrange: Set up test data
const input = 'test';

// Act: Execute function
const result = myFunction(input);

// Assert: Verify outcome
expect(result).toBe('expected');
```

### 4. Test Edge Cases
- Null/undefined inputs
- Empty strings/arrays
- Boundary values
- Error conditions

### 5. Keep Tests Simple
- One assertion per test (when possible)
- Avoid complex logic in tests
- Focus on behavior, not implementation

## Coverage Goals

Target: 70%+ coverage for all metrics

Current Coverage:
- Lines: ~40%
- Functions: ~45%
- Branches: ~35%
- Statements: ~40%

**To Reach 70%:**
1. ✅ Fix failing tests (API mismatches)
2. ⬜ Add tests for uncovered modules
3. ⬜ Test chat module functions
4. ⬜ Test UI module functions (besides toast)
5. ⬜ Test markdown processing
6. ⬜ Test HTTP utilities

## Troubleshooting

### Tests Not Running

Check:
1. Dependencies installed: `npm install`
2. Test files in `tests/unit/`
3. File names end with `.test.js`

### Import Errors

```
Error: Cannot find module
```

Solution:
- Verify import paths are relative to test file
- Check module exports in source files
- Ensure paths use `.js` extension

### Mock Issues

```
TypeError: Cannot read property of undefined
```

Solution:
- Check `tests/setup.js` for proper mocks
- Verify global mocks are defined
- Consider adding module-specific mocks

### Coverage Not Generating

```bash
# Install coverage provider
npm install -D @vitest/coverage-v8

# Run with coverage
npm run test:coverage
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Unit Tests

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

      - name: Run tests
        run: npm run test:unit

      - name: Generate coverage
        run: npm run test:coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage/lcov.info
```

## Next Steps

1. **Fix Failing Tests** (Priority 1)
   - Adjust tests for actual API signatures
   - Fix edge case handling
   - Update toast tests with proper mocks

2. **Add Missing Tests** (Priority 2)
   - Chat module functions
   - UI components (loading, modal, theme)
   - HTTP utilities
   - Markdown processing

3. **Improve Coverage** (Priority 3)
   - Target 70%+ across all metrics
   - Add integration tests for complex flows
   - Test error handling paths

4. **Documentation** (Priority 4)
   - Add JSDoc comments to source code
   - Document complex test scenarios
   - Create testing guidelines

## Resources

- [Vitest Documentation](https://vitest.dev)
- [Testing Best Practices](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)
- [Jest/Vitest Matchers](https://vitest.dev/api/expect.html)
- [jsdom Documentation](https://github.com/jsdom/jsdom)

## License

Part of Chatbot Redis project - see main LICENSE file.
