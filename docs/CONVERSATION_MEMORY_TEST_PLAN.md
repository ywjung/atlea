# Conversation Memory Feature - Test Plan

## 📋 Overview
Testing plan for the conversation memory feature that enables the LLM to remember and use previous conversation context.

## ✅ Implementation Summary

### Files Modified
1. **src/routers/query.py** (2 endpoints updated)
   - `/api/query` (non-streaming)
   - `/api/query/stream` (streaming)

2. **src/hybrid_rag.py** (3 methods updated)
   - `HybridRAGOrchestrator.answer()`
   - `HybridRAGOrchestrator._generate_answer()`
   - `HybridRAGOrchestrator._generate_answer_stream()`

### Key Changes
- Conversation history retrieval: Last 10 messages (5 Q&A pairs)
- History passed to LLM with system prompt + history + current question
- Both streaming and non-streaming endpoints support conversation memory
- Session-based isolation: Different sessions maintain separate conversations

## 🧪 Test Scenarios

### 1. Basic Conversation Context Test
**Objective**: Verify LLM remembers previous conversation

**Steps**:
1. Start a new session
2. Ask: "What is Python?"
3. Wait for response
4. Ask: "What are its main features?" (using pronoun "its")
5. Verify the LLM understands "its" refers to Python from previous context

**Expected Result**:
- Second answer should correctly reference Python without re-asking what "it" is
- Response should show understanding of the context

**Test Command**:
```bash
# Session 1 - First Question
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is Python?",
    "session_id": "test-session-001",
    "group_ids": ["test-group"]
  }'

# Session 1 - Follow-up Question (tests context)
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are its main features?",
    "session_id": "test-session-001",
    "group_ids": ["test-group"]
  }'
```

### 2. Session Isolation Test
**Objective**: Verify different sessions don't share conversation memory

**Steps**:
1. Session A: Ask "What is Redis?"
2. Session B: Ask "What is it used for?" (should NOT know about Redis)
3. Session A: Ask "How does it compare to Memcached?" (should know about Redis)

**Expected Result**:
- Session B should ask for clarification or give generic answer
- Session A should correctly compare Redis to Memcached

**Test Command**:
```bash
# Session A
curl -X POST http://localhost:8000/api/query \
  -d '{"question": "What is Redis?", "session_id": "session-A", "group_ids": ["test"]}'

# Session B (different session)
curl -X POST http://localhost:8000/api/query \
  -d '{"question": "What is it used for?", "session_id": "session-B", "group_ids": ["test"]}'

# Session A again
curl -X POST http://localhost:8000/api/query \
  -d '{"question": "How does it compare to Memcached?", "session_id": "session-A", "group_ids": ["test"]}'
```

### 3. Long Conversation Test
**Objective**: Verify memory limit works correctly (10 messages max)

**Steps**:
1. Have a conversation with 6+ exchanges (12+ messages)
2. Reference something from the 1st question
3. Verify LLM remembers context from recent messages but may not remember very old context

**Expected Result**:
- Recent context (within last 10 messages) should be remembered
- Very old context (beyond 10 messages) may be forgotten

### 4. Streaming Mode Test
**Objective**: Verify conversation memory works in streaming mode

**Steps**:
1. Use `/api/query/stream` endpoint
2. Ask: "Explain async/await"
3. Ask: "Show me an example" (using streaming)
4. Verify streaming response shows context awareness

**Expected Result**:
- Streaming responses maintain conversation context
- Example should be related to async/await from previous question

**Test Command**:
```bash
# First question (streaming)
curl -X POST http://localhost:8000/api/query/stream \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "question": "Explain async/await in Python",
    "session_id": "stream-test-001"
  }'

# Follow-up (streaming, tests context)
curl -X POST http://localhost:8000/api/query/stream \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "question": "Show me a practical example",
    "session_id": "stream-test-001"
  }'
```

### 5. Empty Session Test
**Objective**: Verify system works without session_id (no memory)

**Steps**:
1. Query without session_id
2. Make follow-up question without session_id
3. Verify no context is maintained (independent answers)

**Expected Result**:
- Each question treated independently
- No error occurs
- System gracefully handles missing session

**Test Command**:
```bash
# No session_id provided
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"question": "What is FastAPI?", "group_ids": ["test"]}'

curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"question": "What are its advantages?", "group_ids": ["test"]}'
```

### 6. Performance Test
**Objective**: Verify conversation memory doesn't significantly impact performance

**Steps**:
1. Measure response time without conversation history
2. Measure response time with full conversation history (10 messages)
3. Compare response times

**Expected Result**:
- Performance impact should be < 10% (< 100ms increase)
- No memory leaks or degradation over time

**Test Command**:
```bash
# Measure baseline (no history)
time curl -X POST http://localhost:8000/api/query \
  -d '{"question": "Test question", "session_id": "perf-new"}'

# Measure with history (after 5 Q&A exchanges)
# ... perform 5 Q&A exchanges first ...
time curl -X POST http://localhost:8000/api/query \
  -d '{"question": "Test question", "session_id": "perf-history"}'
```

### 7. Redis Persistence Test
**Objective**: Verify conversation persists across server restarts

**Steps**:
1. Start conversation, ask 2 questions
2. Restart the server
3. Continue conversation with follow-up question
4. Verify context is maintained

**Expected Result**:
- Conversation history survives server restart
- Redis persistence ensures no data loss

### 8. Concurrent Users Test
**Objective**: Verify multiple users don't interfere with each other

**Steps**:
1. Start 3 concurrent conversations with different session_ids
2. Interleave questions from different sessions
3. Verify each session maintains its own context

**Expected Result**:
- No cross-contamination between sessions
- Each session maintains independent conversation history

## 🎯 Manual Testing Checklist

- [ ] Basic context test (pronoun resolution)
- [ ] Session isolation test
- [ ] Long conversation test (10+ messages)
- [ ] Streaming mode test
- [ ] Empty session test
- [ ] Performance test
- [ ] Redis persistence test
- [ ] Concurrent users test

## 📊 Success Criteria

1. **Functionality**: ✅ LLM correctly uses previous conversation context
2. **Isolation**: ✅ Different sessions don't share memory
3. **Performance**: ✅ Response time increase < 10%
4. **Reliability**: ✅ No errors or crashes
5. **Persistence**: ✅ Conversation survives restarts
6. **Scalability**: ✅ Works with multiple concurrent users

## 🔍 Monitoring Points

### Logs to Check
```bash
# Check conversation retrieval
grep "🆕 Retrieve conversation history" logs/app.log

# Check message counts
grep "Retrieved.*messages" logs/app.log

# Check performance
grep "⏱️.*TIMING" logs/app.log
```

### Redis Commands
```bash
# List all conversation sessions
redis-cli KEYS "conversation:*"

# Check specific session messages
redis-cli LRANGE "conversation:SESSION_ID:messages" 0 -1

# Count messages in session
redis-cli LLEN "conversation:SESSION_ID:messages"
```

## 🐛 Known Limitations

1. **Memory Window**: Limited to last 10 messages (5 Q&A pairs)
   - Very long conversations may lose early context
   - Mitigation: Implement conversation summarization in future

2. **Token Limits**: Large conversation history may exceed LLM token limits
   - Current limit: 10 messages should be safe for most LLMs
   - Monitor: Check for truncation warnings in logs

3. **Context Quality**: LLM may still misunderstand ambiguous pronouns
   - This is an LLM capability limitation, not a system bug
   - Improvement: Use better LLM models or prompt engineering

## 📝 Future Enhancements

1. **Adaptive History Length**: Adjust based on message size
2. **Conversation Summarization**: Compress old context
3. **Semantic Memory**: Store important facts separately
4. **Context Compression**: Use Claude's context window optimization
5. **Memory Search**: Retrieve relevant past conversations beyond 10 messages
6. **UI Indicators**: Show memory status in frontend

## 🚀 Deployment Notes

- No database schema changes required
- Redis already stores conversation history
- Backward compatible (works without session_id)
- No additional dependencies needed
- Safe to deploy gradually (feature flag not needed as it's opt-in via session_id)

## ✅ Sign-off

- [ ] Code review completed
- [ ] All tests passing
- [ ] Performance verified
- [ ] Documentation updated
- [ ] Ready for production deployment
