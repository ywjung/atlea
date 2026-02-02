# JavaScript Modules

Modular JavaScript architecture for the chatbot application.

## Structure

```
static/js/
├── index.js                 # Main entry point - import from here
├── app/                     # Application initialization
│   ├── init.js             # App initialization and feature coordination
│   └── index.js            # App module exports
├── auth/                    # Authentication
│   ├── session.js          # Session and token management
│   ├── login.js            # Login/logout functionality
│   ├── register.js         # User registration
│   ├── password.js         # Password management
│   └── index.js            # Auth module exports
├── chat/                    # Chat functionality
│   ├── conversation.js     # Conversation lifecycle management
│   ├── message.js          # Message rendering
│   ├── streaming.js        # SSE streaming responses
│   └── index.js            # Chat module exports
├── ui/                      # UI components
│   ├── toast.js            # Toast notifications
│   ├── loading.js          # Loading indicators
│   ├── theme.js            # Theme management
│   ├── modal.js            # Modal stack management
│   └── index.js            # UI module exports
├── utils/                   # Utility functions
│   ├── sanitize.js         # XSS protection
│   ├── formatters.js       # Date/time/number formatting
│   ├── http.js             # HTTP request wrapper
│   ├── storage.js          # LocalStorage/SessionStorage wrapper
│   ├── dom.js              # DOM manipulation helpers
│   └── index.js            # Utils module exports
└── markdown/                # Markdown processing
    ├── config.js           # marked.js configuration
    ├── helpers.js          # Markdown utilities
    └── index.js            # Markdown module exports
```

## Usage

### Example: Basic Page Initialization

```javascript
import { initApp, initFeatures } from '/static/js/index.js';

const initialized = await initApp();
if (initialized) {
    await initFeatures({ chat: true });
}
```

### Example: Authentication

```javascript
import { login, showToast } from '/static/js/index.js';

try {
    await login(email, password);
    window.location.href = '/';
} catch (error) {
    showToast('로그인 실패', 'error');
}
```

## Migration Guide

### Step 1: Update HTML
Add `type="module"` to script tags

### Step 2: Import Modules
Replace global functions with imports

### Step 3: Update Event Handlers
Use addEventListener instead of inline handlers

## Next Steps

1. ✅ Extract core modules (utils, auth, chat, UI, markdown)
2. ⏳ Integrate modules into existing pages
3. ⏳ Setup build system (Vite)
4. ⏳ Write unit tests
5. ⏳ Extract remaining functionality
6. ⏳ Remove legacy script.js
