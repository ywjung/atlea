# Backend Services Layer

Business logic layer following Clean Architecture principles.

## Purpose

Services contain business logic and orchestrate between repositories, external APIs, and domain models.

## Existing Services

✅ Already modularized:
- question_generation.py
- reindex_service.py
- scheduler_service.py
- settings_service.py
- tts_service.py

## Planned (Phase 2-B)

Chat: chat_service.py, conversation_service.py
RAG: rag_service.py, embedding_service.py
User: user_service.py, auth_service.py
Document: document_service.py, vector_service.py

## Guidelines

- Dependency injection via constructor
- Raise domain-specific exceptions
- 80%+ test coverage
- Full type hints and docstrings

---
Last Updated: 2026-02-02
Status: Partial - full extraction pending
