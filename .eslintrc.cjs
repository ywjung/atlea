module.exports = {
  env: {
    browser: true,
    es2022: true,
  },
  extends: ['eslint:recommended'],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  rules: {
    // Code Quality
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    'no-console': 'off', // Allow console for logging
    'no-debugger': 'warn',
    'no-alert': 'warn',

    // Best Practices
    'eqeqeq': ['error', 'always'],
    'curly': ['error', 'all'],
    'no-eval': 'error',
    'no-implied-eval': 'error',
    'no-new-func': 'error',
    'prefer-const': 'warn',
    'no-var': 'error',

    // Style
    'indent': ['error', 4, { SwitchCase: 1 }],
    'quotes': ['error', 'single', { avoidEscape: true }],
    'semi': ['error', 'always'],
    'comma-dangle': ['error', 'only-multiline'],
    'no-trailing-spaces': 'warn',
    'eol-last': ['error', 'always'],
  },
  globals: {
    // Global variables from external libraries
    DOMPurify: 'readonly',
    marked: 'readonly',
    hljs: 'readonly',
    katex: 'readonly',
    renderMathInElement: 'readonly',
    logger: 'readonly',
  },
};
