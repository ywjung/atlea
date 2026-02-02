# Modularization Implementation Plan

## Executive Summary

This document provides a comprehensive plan for modularizing the ATLEA codebase to improve maintainability, testability, and performance.

**Created**: 2026-02-02
**Status**: Planning Phase
**Effort**: 4-6 weeks (2 developers)

---

## Current State Analysis

### Critical Issues

| File | Lines | Status | Impact |
|------|-------|--------|--------|
| `src/web_server.py` | 8,000+ | 🔴 Critical | Backend monolith |
| `static/script.js` | 7,300+ | 🔴 Critical | Frontend monolith |
| `static/style.css` | 5,000+ | 🟡 High | CSS bloat |

### Impact Assessment

**Performance**:
- Initial load time: 3-5 seconds (unoptimized)
- Module loading: Synchronous, blocking
- Bundle size: ~250KB (uncompressed JS)

**Maintainability**:
- Code navigation: Difficult (search-based)
- Debugging: Time-consuming
- Testing: Limited coverage due to complexity

**Development**:
- Merge conflicts: Frequent
- Code review: Overwhelming
- Onboarding: 2-3 weeks

---

## Phase 2-1: Frontend Modularization

### Objective
Split `static/script.js` (7,300 lines) into logical ES6 modules.

### Proposed Structure

```
static/
├── js/
│   ├── main.js                 # Entry point, app initialization
│   ├── config.js               # Global configuration
│   ├── utils/
│   │   ├── dom.js             # DOM manipulation helpers
│   │   ├── http.js            # API client, fetch wrappers
│   │   ├── storage.js         # LocalStorage abstractions
│   │   └── sanitize.js        # DOMPurify wrappers (already created)
│   ├── auth/
│   │   ├── login.js           # Login logic
│   │   ├── register.js        # Registration logic
│   │   ├── session.js         # Session management
│   │   └── totp.js            # 2FA logic
│   ├── chat/
│   │   ├── conversation.js    # Conversation management
│   │   ├── message.js         # Message rendering
│   │   ├── websocket.js       # WebSocket connection
│   │   └── streaming.js       # Streaming response handling
│   ├── admin/
│   │   ├── dashboard.js       # Admin dashboard
│   │   ├── users.js           # User management
│   │   ├── documents.js       # Document management
│   │   └── stats.js           # Statistics
│   ├── export/
│   │   ├── pdf.js             # PDF export
│   │   ├── docx.js            # DOCX export
│   │   └── formats.js         # Format converters
│   ├── ui/
│   │   ├── toast.js           # Toast notifications
│   │   ├── modal.js           # Modal dialogs
│   │   ├── theme.js           # Theme switching
│   │   └── loading.js         # Loading indicators
│   └── markdown/
│       ├── renderer.js        # Markdown rendering
│       ├── code-highlight.js  # Syntax highlighting
│       └── mermaid.js         # Diagram rendering
└── css/
    ├── base/
    │   ├── reset.css
    │   ├── variables.css
    │   └── typography.css
    ├── components/
    │   ├── buttons.css
    │   ├── forms.css
    │   ├── cards.css
    │   └── modals.css
    ├── layouts/
    │   ├── grid.css
    │   └── flex.css
    └── pages/
        ├── chat.css
        ├── admin.css
        └── auth.css
```

### Implementation Steps

#### Step 1: Extract Utilities (Week 1)
```javascript
// utils/dom.js
export function safeSetInnerHTML(element, html, config = {}) {
    // Already implemented in sanitize.js
}

export function createElement(tag, attributes = {}, children = []) {
    const element = document.createElement(tag);
    Object.entries(attributes).forEach(([key, value]) => {
        element.setAttribute(key, value);
    });
    children.forEach(child => element.appendChild(child));
    return element;
}

// utils/http.js
export async function apiCall(endpoint, options = {}) {
    const token = localStorage.getItem('access_token');
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`/api${endpoint}`, {
        ...options,
        headers
    });

    if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
    }

    return response.json();
}
```

#### Step 2: Extract Auth Module (Week 1-2)
```javascript
// auth/login.js
import { apiCall } from '../utils/http.js';
import { showToast } from '../ui/toast.js';

export async function login(email, password, totpCode = null) {
    try {
        const response = await apiCall('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password, totp_code: totpCode })
        });

        localStorage.setItem('access_token', response.tokens.access_token);
        localStorage.setItem('user_id', response.user.user_id);

        showToast('로그인 성공!', 'success');
        return response;
    } catch (error) {
        showToast('로그인 실패: ' + error.message, 'error');
        throw error;
    }
}
```

#### Step 3: Extract Chat Module (Week 2-3)
```javascript
// chat/conversation.js
import { apiCall } from '../utils/http.js';
import { renderMessage } from './message.js';

export class ConversationManager {
    constructor() {
        this.currentConversation = null;
        this.conversations = [];
    }

    async loadConversations() {
        const response = await apiCall('/conversations');
        this.conversations = response.conversations;
        this.renderList();
    }

    async createConversation(title) {
        const response = await apiCall('/conversations', {
            method: 'POST',
            body: JSON.stringify({ title })
        });
        this.currentConversation = response.conversation;
        return response;
    }

    renderList() {
        // Render conversation list
    }
}
```

#### Step 4: Build System Setup (Week 3-4)
```javascript
// vite.config.js
import { defineConfig } from 'vite';

export default defineConfig({
    build: {
        rollupOptions: {
            input: {
                main: 'static/js/main.js',
                admin: 'static/admin/js/admin-core.js'
            },
            output: {
                entryFileNames: 'js/[name]-[hash].js',
                chunkFileNames: 'js/[name]-[hash].js',
                assetFileNames: 'assets/[name]-[hash][extname]'
            }
        },
        sourcemap: true,
        minify: 'terser',
        terserOptions: {
            compress: {
                drop_console: true,
                drop_debugger: true
            }
        }
    },
    server: {
        proxy: {
            '/api': 'http://localhost:8000'
        }
    }
});
```

#### Step 5: Migration & Testing (Week 4)
- Gradual migration: one module at a time
- Parallel testing: old vs new implementation
- Feature flag: toggle between old/new code
- Rollback plan: keep old code until stable

### Expected Benefits

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Bundle size | 250KB | 180KB | 28% ↓ |
| Initial load | 3-5s | 1-2s | 60% ↓ |
| Code reuse | 10% | 40% | 300% ↑ |
| Test coverage | 20% | 60% | 200% ↑ |

---

## Phase 2-2: Backend Modularization

### Objective
Decompose `src/web_server.py` (8,000 lines) into clean architecture.

### Proposed Structure

```
src/
├── main.py                     # FastAPI app initialization
├── config/
│   ├── settings.py            # Configuration (already exists)
│   ├── database.py            # Redis connection
│   └── security.py            # Security constants
├── core/
│   ├── dependencies.py        # Dependency injection
│   ├── exceptions.py          # Custom exceptions
│   └── middleware.py          # Middleware registry
├── services/
│   ├── auth_service.py        # Authentication (already exists)
│   ├── chat_service.py        # Chat logic
│   ├── document_service.py   # Document processing
│   ├── embedding_service.py  # Embedding generation
│   ├── llm_service.py         # LLM integration
│   ├── rag_service.py         # RAG orchestration
│   └── tts_service.py         # Text-to-speech (already exists)
├── repositories/
│   ├── user_repository.py     # User data access
│   ├── conversation_repository.py
│   ├── document_repository.py
│   └── cache_repository.py
├── routers/
│   # (Already well-structured)
│   ├── auth.py
│   ├── chat.py
│   ├── documents.py
│   └── admin.py
├── models/
│   ├── domain/               # Business models
│   │   ├── user.py
│   │   ├── conversation.py
│   │   └── document.py
│   └── api/                  # API models (Pydantic)
│       ├── requests.py
│       └── responses.py
└── utils/
    ├── validators.py
    ├── formatters.py
    └── helpers.py
```

### Implementation Steps

#### Step 1: Extract Services (Week 1-2)

```python
# services/chat_service.py
from typing import List, Optional
from ..repositories.conversation_repository import ConversationRepository
from ..repositories.cache_repository import CacheRepository
from ..services.llm_service import LLMService
from ..services.rag_service import RAGService

class ChatService:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        cache_repo: CacheRepository,
        llm_service: LLMService,
        rag_service: RAGService
    ):
        self.conversation_repo = conversation_repo
        self.cache_repo = cache_repo
        self.llm = llm_service
        self.rag = rag_service

    async def create_conversation(
        self,
        user_id: str,
        title: str
    ) -> Conversation:
        """Create a new conversation"""
        conversation_id = generate_id()
        conversation = Conversation(
            id=conversation_id,
            user_id=user_id,
            title=title,
            created_at=datetime.now()
        )
        await self.conversation_repo.save(conversation)
        return conversation

    async def send_message(
        self,
        conversation_id: str,
        message: str,
        user_id: str
    ) -> AsyncGenerator[str, None]:
        """Send message and stream response"""
        # Load conversation
        conversation = await self.conversation_repo.get(conversation_id)

        # Get relevant context from RAG
        context = await self.rag.retrieve(message, user_id)

        # Stream LLM response
        async for chunk in self.llm.stream_chat(message, context):
            yield chunk

        # Save message history
        await self.conversation_repo.add_message(
            conversation_id,
            role="user",
            content=message
        )
```

#### Step 2: Extract Repositories (Week 2-3)

```python
# repositories/conversation_repository.py
from redis import Redis
from typing import List, Optional
from ..models.domain.conversation import Conversation

class ConversationRepository:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def save(self, conversation: Conversation) -> None:
        """Save conversation to Redis"""
        key = f"conversation:{conversation.id}"
        self.redis.hset(key, mapping=conversation.dict())

    async def get(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID"""
        key = f"conversation:{conversation_id}"
        data = self.redis.hgetall(key)
        if not data:
            return None
        return Conversation.parse_obj(data)

    async def list_by_user(self, user_id: str) -> List[Conversation]:
        """List all conversations for a user"""
        pattern = f"conversation:*"
        keys = self.redis.keys(pattern)

        conversations = []
        for key in keys:
            data = self.redis.hgetall(key)
            if data.get('user_id') == user_id:
                conversations.append(Conversation.parse_obj(data))

        return sorted(conversations, key=lambda c: c.created_at, reverse=True)
```

#### Step 3: Dependency Injection (Week 3)

```python
# core/dependencies.py
from fastapi import Depends
from redis import Redis
from ..config.database import get_redis
from ..services.chat_service import ChatService
from ..services.llm_service import LLMService
from ..services.rag_service import RAGService
from ..repositories.conversation_repository import ConversationRepository
from ..repositories.cache_repository import CacheRepository

def get_chat_service(
    redis: Redis = Depends(get_redis)
) -> ChatService:
    """Dependency injection for ChatService"""
    conversation_repo = ConversationRepository(redis)
    cache_repo = CacheRepository(redis)
    llm_service = LLMService()
    rag_service = RAGService()

    return ChatService(
        conversation_repo=conversation_repo,
        cache_repo=cache_repo,
        llm_service=llm_service,
        rag_service=rag_service
    )
```

#### Step 4: Router Simplification (Week 3-4)

```python
# routers/chat.py (Simplified)
from fastapi import APIRouter, Depends
from ..services.chat_service import ChatService
from ..core.dependencies import get_chat_service, get_current_user
from ..models.api.requests import SendMessageRequest
from ..models.api.responses import ConversationResponse

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    title: str,
    user = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Create a new conversation"""
    conversation = await chat_service.create_conversation(
        user_id=user.user_id,
        title=title
    )
    return ConversationResponse.from_domain(conversation)

@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    user = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Send message and stream response"""
    return StreamingResponse(
        chat_service.send_message(
            conversation_id=conversation_id,
            message=request.message,
            user_id=user.user_id
        ),
        media_type="text/event-stream"
    )
```

#### Step 5: Main App Cleanup (Week 4)

```python
# main.py (Clean)
from fastapi import FastAPI
from .core.middleware import setup_middleware
from .routers import auth, chat, documents, admin
from .config.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="ATLEA API",
    version="2.4.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Setup middleware
setup_middleware(app)

# Include routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(admin.router)

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### Expected Benefits

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Lines per file | 8,000 | <500 | 94% ↓ |
| Cyclomatic complexity | 150+ | <10 | 93% ↓ |
| Test coverage | 30% | 70% | 133% ↑ |
| Import time | 3-5s | <1s | 80% ↓ |

---

## Testing Strategy

### Unit Tests
```python
# tests/services/test_chat_service.py
import pytest
from unittest.mock import Mock
from src.services.chat_service import ChatService

@pytest.fixture
def chat_service():
    conversation_repo = Mock()
    cache_repo = Mock()
    llm_service = Mock()
    rag_service = Mock()

    return ChatService(
        conversation_repo=conversation_repo,
        cache_repo=cache_repo,
        llm_service=llm_service,
        rag_service=rag_service
    )

async def test_create_conversation(chat_service):
    """Test conversation creation"""
    conversation = await chat_service.create_conversation(
        user_id="user123",
        title="Test Conversation"
    )

    assert conversation.id is not None
    assert conversation.title == "Test Conversation"
    chat_service.conversation_repo.save.assert_called_once()
```

### Integration Tests
```python
# tests/integration/test_chat_flow.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_full_chat_flow(async_client: AsyncClient, auth_token):
    """Test complete chat flow"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Create conversation
    response = await async_client.post(
        "/api/chat/conversations",
        json={"title": "Test"},
        headers=headers
    )
    assert response.status_code == 200
    conversation_id = response.json()["id"]

    # Send message
    response = await async_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"message": "Hello"},
        headers=headers
    )
    assert response.status_code == 200
```

---

## Migration Strategy

### Phase A: Preparation (Week 1)
- [ ] Create new directory structure
- [ ] Setup build tools (Vite for frontend)
- [ ] Create migration checklist
- [ ] Document current functionality

### Phase B: Backend Migration (Week 2-3)
- [ ] Extract services (one at a time)
- [ ] Extract repositories
- [ ] Setup dependency injection
- [ ] Parallel testing (old vs new)

### Phase C: Frontend Migration (Week 3-4)
- [ ] Extract utilities and helpers
- [ ] Modularize auth module
- [ ] Modularize chat module
- [ ] Setup build pipeline

### Phase D: Testing & Validation (Week 4-5)
- [ ] Unit test coverage 70%+
- [ ] Integration tests
- [ ] E2E tests (critical paths)
- [ ] Performance testing

### Phase E: Deployment (Week 5-6)
- [ ] Feature flag rollout
- [ ] Gradual traffic migration
- [ ] Monitor metrics
- [ ] Full rollout

---

## Risk Mitigation

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Breaking changes | High | High | Feature flags, parallel testing |
| Performance regression | Medium | High | Performance benchmarks, rollback plan |
| Module coupling | Medium | Medium | Dependency injection, clear interfaces |
| Build complexity | Low | Medium | Incremental adoption, documentation |

### Process Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Team learning curve | High | Medium | Training sessions, documentation |
| Timeline overrun | Medium | High | Buffer time, phased approach |
| Incomplete migration | Low | High | Mandatory completion, code freeze |

---

## Success Metrics

### Quantitative
- Bundle size: <180KB (from 250KB)
- Initial load: <2s (from 3-5s)
- Test coverage: >70% (from 30%)
- Lines per file: <500 (from 8,000)

### Qualitative
- Code review time: 50% reduction
- Onboarding time: 70% reduction
- Developer satisfaction: 80%+ positive
- Merge conflicts: 60% reduction

---

## Timeline & Resources

### Estimated Effort
- **Frontend**: 3-4 weeks (1 developer)
- **Backend**: 3-4 weeks (1 developer)
- **Total**: 4-6 weeks (2 developers working in parallel)

### Critical Path
1. Week 1: Extract utilities and services
2. Week 2: Backend repositories and DI
3. Week 3: Frontend modules and build system
4. Week 4: Testing and validation
5. Week 5-6: Deployment and monitoring

---

## Next Actions

### Immediate (This Week)
1. Review and approve this plan
2. Allocate resources (2 developers)
3. Setup project board
4. Schedule kickoff meeting

### Short Term (Weeks 1-2)
1. Create new directory structure
2. Extract first service (ChatService)
3. Extract first module (auth.js)
4. Setup CI/CD for modular tests

### Medium Term (Weeks 3-4)
1. Complete backend migration
2. Complete frontend migration
3. Achieve 70% test coverage
4. Performance benchmarks

---

**Document Status**: Planning Complete
**Next Phase**: Awaiting Approval
**Owner**: Development Team
**Reviewers**: Tech Lead, Product Manager
