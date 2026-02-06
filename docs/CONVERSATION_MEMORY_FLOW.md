# Conversation Memory - System Flow Diagram

## 📊 High-Level Architecture

```
┌─────────────┐
│   User      │
│  Frontend   │
└──────┬──────┘
       │ Q: "What is Python?"
       │ session_id: "abc123"
       ▼
┌──────────────────────────────────────────────────────────┐
│                    FastAPI Backend                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │ POST /api/query                                    │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │ 1. Save user question to Redis               │ │  │
│  │  │    conversation:abc123:messages             │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  │                                                     │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │ 2. Retrieve conversation history             │ │  │
│  │  │    GET last 10 messages from Redis          │ │  │
│  │  │    [Q1, A1, Q2, A2, ..., Current Q]         │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  │                                                     │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │ 3. Search RAG documents (Hybrid)             │ │  │
│  │  │    - Local documents                         │ │  │
│  │  │    - Web search (Tavily)                     │ │  │
│  │  │    - Official docs (Context7)                │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  │                                                     │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │ 4. Build LLM prompt                          │ │  │
│  │  │    messages = [                              │ │  │
│  │  │      {system: "System prompt"},              │ │  │
│  │  │      {user: "Q1"}, {assistant: "A1"},   ◄────┼─┼─ From Redis
│  │  │      {user: "Q2"}, {assistant: "A2"},        │ │  │
│  │  │      {user: "Current Q + RAG context"}       │ │  │
│  │  │    ]                                          │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  │                                                     │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │ 5. Generate answer from LLM                  │ │  │
│  │  │    Ollama/OpenAI/Claude with full context   │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  │                                                     │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │ 6. Save assistant response to Redis          │ │  │
│  │  │    conversation:abc123:messages             │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
       │
       │ A: "Python is a programming language..."
       ▼
┌─────────────┐
│   User      │
│  Frontend   │
└─────────────┘
```

## 🔄 Conversation Flow Example

### Turn 1: Initial Question
```
User: "What is Python?"
session_id: "session-001"

Redis State:
conversation:session-001:messages = [
  {role: "user", content: "What is Python?", timestamp: "10:00:00"}
]

LLM Input:
messages = [
  {role: "system", content: "You are a helpful assistant..."},
  {role: "user", content: "What is Python?\n\n[RAG Context: ...sources...]"}
]

LLM Output: "Python is a high-level programming language..."

Redis State After:
conversation:session-001:messages = [
  {role: "user", content: "What is Python?", timestamp: "10:00:00"},
  {role: "assistant", content: "Python is...", timestamp: "10:00:03"}
]
```

### Turn 2: Follow-up Question (Uses Context!)
```
User: "What are its main features?"  ◄─── "its" refers to Python
session_id: "session-001"

Redis Retrieval:
conversation_history = get_messages(session_id, limit=10)
→ Returns last 2 messages from Turn 1

Redis State:
conversation:session-001:messages = [
  {role: "user", content: "What is Python?"},
  {role: "assistant", content: "Python is..."},
  {role: "user", content: "What are its main features?"}  ◄─── NEW
]

LLM Input (with history!):
messages = [
  {role: "system", content: "You are a helpful assistant..."},
  {role: "user", content: "What is Python?"},           ◄─── From history
  {role: "assistant", content: "Python is..."},         ◄─── From history
  {role: "user", content: "What are its main features?\n\n[RAG Context: ...]"}
]

LLM Output: "Python's main features include..."  ◄─── Correctly understands "its"

Redis State After:
conversation:session-001:messages = [
  {role: "user", content: "What is Python?"},
  {role: "assistant", content: "Python is..."},
  {role: "user", content: "What are its main features?"},
  {role: "assistant", content: "Python's main features...", timestamp: "10:01:05"}
]
```

### Turn 3: Another Follow-up
```
User: "Show me an example"  ◄─── "example" refers to Python features
session_id: "session-001"

Redis Retrieval:
conversation_history = get_messages(session_id, limit=10)
→ Returns last 4 messages

LLM Input (with full context!):
messages = [
  {role: "system", content: "You are a helpful assistant..."},
  {role: "user", content: "What is Python?"},
  {role: "assistant", content: "Python is..."},
  {role: "user", content: "What are its main features?"},
  {role: "assistant", content: "Python's main features..."},
  {role: "user", content: "Show me an example\n\n[RAG Context: ...]"}
]

LLM Output: "Here's a Python example demonstrating these features:\n```python\n..."
```

## 🎯 Memory Window Behavior

```
Messages in Redis:
┌────────────────────────────────────────┐
│ M1:  Q: "What is Python?"              │
│ M2:  A: "Python is..."                 │
│ M3:  Q: "What are its features?"       │
│ M4:  A: "Features include..."          │
│ M5:  Q: "Show me an example"           │  ◄─── Limit = 10 messages
│ M6:  A: "Here's an example..."         │       (5 Q&A pairs)
│ M7:  Q: "How about async?"             │
│ M8:  A: "Async works with..."          │
│ M9:  Q: "Compare to JavaScript"        │
│ M10: A: "Python vs JS..."              │
│ M11: Q: "Which is better?"             │  ◄─── Current question
└────────────────────────────────────────┘

Retrieved for LLM (limit=10, excluding current):
┌────────────────────────────────────────┐
│ M2:  A: "Python is..."                 │  ◄─── Oldest kept
│ M3:  Q: "What are its features?"       │
│ M4:  A: "Features include..."          │
│ M5:  Q: "Show me an example"           │
│ M6:  A: "Here's an example..."         │
│ M7:  Q: "How about async?"             │
│ M8:  A: "Async works with..."          │
│ M9:  Q: "Compare to JavaScript"        │
│ M10: A: "Python vs JS..."              │
└────────────────────────────────────────┘
                +
│ M11: Q: "Which is better? [RAG ctx]"   │  ◄─── Current + RAG

Note: M1 ("What is Python?") dropped from context window
```

## 🔀 Session Isolation

```
┌─────────────────────────────────────────────────────────────┐
│                         Redis Storage                        │
│                                                               │
│  conversation:session-A:messages          Session A          │
│  ┌────────────────────────────────────┐                     │
│  │ Q: "What is Redis?"                │  User: Alice        │
│  │ A: "Redis is an in-memory..."      │                     │
│  │ Q: "How does it work?"             │                     │
│  │ A: "Redis stores data in RAM..."   │                     │
│  └────────────────────────────────────┘                     │
│                                                               │
│  conversation:session-B:messages          Session B          │
│  ┌────────────────────────────────────┐                     │
│  │ Q: "What is Python?"               │  User: Bob          │
│  │ A: "Python is a language..."       │                     │
│  │ Q: "Show me code"                  │                     │
│  │ A: "Here's Python code..."         │                     │
│  └────────────────────────────────────┘                     │
│                                                               │
│  conversation:session-C:messages          Session C          │
│  ┌────────────────────────────────────┐                     │
│  │ Q: "Explain async/await"           │  User: Alice        │
│  │ A: "Async/await enables..."        │  (different topic)  │
│  └────────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘

Key Points:
✅ Session A and B are completely isolated
✅ Alice can have multiple concurrent sessions (A and C)
✅ No cross-contamination between sessions
✅ Each session maintains its own conversation context
```

## 🚀 Streaming Mode Flow

```
POST /api/query/stream
session_id: "stream-001"
question: "Explain decorators"

┌────────────────────────────────────────────────────────────┐
│ 1. Save question to Redis                                  │
│ 2. Retrieve history (last 10 messages)                     │
│ 3. Search RAG sources                                      │
│ 4. Build LLM prompt with history                           │
│ 5. Start streaming response                                │
│    ┌─────────────────────────────────────────────────┐   │
│    │ Generator yields tokens:                        │   │
│    │   "Dec" → "orators" → " are" → " a" → ...     │   │
│    └─────────────────────────────────────────────────┘   │
│                                                            │
│ 6. Stream to client via Server-Sent Events (SSE)         │
│    ┌─────────────────────────────────────────────────┐   │
│    │ data: {"type": "metadata", "data": {...}}      │   │
│    │ data: {"type": "chunk", "data": "Dec"}         │   │
│    │ data: {"type": "chunk", "data": "orators"}     │   │
│    │ data: {"type": "chunk", "data": " are"}        │   │
│    │ ...                                             │   │
│    │ data: {"type": "done"}                         │   │
│    └─────────────────────────────────────────────────┘   │
│                                                            │
│ 7. Save complete response to Redis after streaming        │
└────────────────────────────────────────────────────────────┘

Note: History is passed BEFORE streaming starts, ensuring
      consistent context throughout the generation.
```

## 📊 Performance Characteristics

```
Without Conversation Memory:
┌──────────┬──────────┬──────────┬──────────┐
│  Query   │   RAG    │   LLM    │  Total   │
│ Embedding│  Search  │ Generate │ Response │
├──────────┼──────────┼──────────┼──────────┤
│   50ms   │  200ms   │  250ms   │  500ms   │
└──────────┴──────────┴──────────┴──────────┘

With Conversation Memory (10 messages):
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│  Query   │  Redis   │   RAG    │   LLM    │  Total   │
│ Embedding│  GET     │  Search  │ Generate │ Response │
├──────────┼──────────┼──────────┼──────────┼──────────┤
│   50ms   │   20ms   │  200ms   │  250ms   │  520ms   │
└──────────┴──────────┴──────────┴──────────┴──────────┘
                        ↑
                   +20ms overhead
                   (Redis retrieval)

Impact: ~4% increase (20ms out of 500ms)
Negligible and worth the context benefit!
```

## 🔍 Debugging Flow

```
Check Conversation State:
┌────────────────────────────────────────────────────────┐
│ 1. Verify session exists                               │
│    $ redis-cli EXISTS "conversation:SESSION_ID"        │
│    → (integer) 1  ✅                                   │
│                                                         │
│ 2. Check message count                                 │
│    $ redis-cli LLEN "conversation:SESSION_ID:messages" │
│    → (integer) 6  ✅                                   │
│                                                         │
│ 3. View messages                                       │
│    $ redis-cli LRANGE "conversation:SESSION_ID:messages" 0 -1 │
│    → ["{\"role\":\"user\",\"content\":\"...\"}",...]  │
│                                                         │
│ 4. Check logs                                          │
│    $ grep "Retrieve conversation history" logs/app.log│
│    → 🆕 Retrieve conversation history (last 10)       │
│    $ grep "Retrieved.*messages" logs/app.log          │
│    → Retrieved 6 messages                              │
└────────────────────────────────────────────────────────┘
```

## 🎨 Visual Legend

```
┌────────┐
│ User   │  Human user interacting with system
└────────┘

┌────────┐
│ Redis  │  Persistent conversation storage
└────────┘

┌────────┐
│  LLM   │  Language model (Ollama/OpenAI/Claude)
└────────┘

  ────►    Data flow / API call
  ◄────    Response / Result
  [...]    Optional / Conditional
  {...}    Data structure
```

---

**Last Updated**: 2026-02-05
**Version**: 1.0
