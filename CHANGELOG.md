# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Performance Optimization System**: Comprehensive frontend and backend optimizations
  - **Frontend Utilities** (`utils.js`):
    - Debounce and throttle functions for event handling optimization
    - DOM element caching system to reduce repeated queries (149→cached)
    - Lazy loading utilities for non-critical features
    - Request queue for batching API calls
    - Event delegation for memory-efficient event handling
    - Performance monitoring with timing measurements
  - **Frontend Optimizations** (`optimizations.js`):
    - Memoized markdown rendering with LRU cache (100 items)
    - Virtual scrolling for large conversation lists
    - Message object pooling for efficient DOM manipulation
    - Request deduplication to prevent redundant API calls
    - Lazy image loading with Intersection Observer
    - Optimized localStorage with automatic cleanup
    - Performance metrics tracking and reporting
  - **Backend Performance** (`performance_optimizer.py`):
    - Query result caching with TTL (10 minutes, 500 item LRU)
    - Performance monitoring decorators for function tracking
    - Batch processing utilities for efficient operations
    - Query parameter optimization and sanitization
    - Execution time tracking for all queries

### Changed
- **Script Loading**: Added performance utilities loaded before main scripts
  - utils.js loaded first for global utility functions
  - optimizations.js provides app-specific performance enhancements
  - Modular architecture enables selective feature loading

### Fixed
- **Welcome Screen Display**: Fixed blank screen issue on page refresh and new conversation
  - Page refresh now shows welcome message and suggested questions instead of blank screen
  - "새 대화" button now displays initial conversation screen with welcome message
  - Removed 43 lines of duplicate HTML code by reusing `createNewConversation()`
- **Scrollbar Styling**: Matched conversation history scrollbar with dark theme UI
  - Applied consistent 8px scrollbar width and CSS variable-based theming
  - Unified scrollbar appearance across all UI components
- **Suggested Questions Refresh**: Fixed static questions appearing on every refresh
  - Expanded fallback question pool from 5 to 30 diverse questions
  - Questions now randomly selected on each refresh (5 from pool of 30)
  - Categories: general, detailed analysis, practical, comparison, specific details, context
  - Added cache-busting parameter to API requests
- **Regenerate Button**: Fixed "no question to regenerate" error on loaded conversations
  - Issue: Clicking regenerate button on previously loaded conversations showed error alert
  - Solution: Restore `lastUserQuestion` from loaded messages
  - Regenerate button now works correctly on all conversations

## [2.1.0] - 2025-12-23

### Added
- **Document Grouping System**: Hierarchical group management for document organization
  - Create, edit, delete groups with metadata (name, description, color, icon)
  - Drag-and-drop document assignment to groups
  - Group-based OR search filtering
  - Tree view navigation for groups and documents
  - Batch document assignment to groups
  - Circular hierarchy prevention
- **Production Server Features**:
  - Multi-worker architecture: Auto-scaling based on CPU cores `(cores * 2) + 1`
  - Async processing: `asyncio.to_thread()` for blocking operations (embedding, LLM)
  - Health check endpoint: `/health` with Redis, models, and system metrics
  - Prometheus metrics endpoint: `/metrics` for monitoring
  - Swagger UI: `/docs` for interactive API documentation
  - ReDoc: `/redoc` for alternative API documentation
  - Production logging: Structured logging with rotation (100MB, 7-day retention)
- **Redis Optimizations**:
  - Configurable connection pool (default: 50 connections, up from 20)
  - Socket timeout and keepalive configuration
  - Connection health checks every 30 seconds
  - Environment-based parameter tuning
- **Cache Enhancements**:
  - Configurable similarity threshold (default: 0.95)
  - Configurable TTL (default: 3600s)
  - Environment variable support for cache parameters
- **API Documentation**:
  - Auto-generated Swagger UI with proper CSP headers
  - Interactive API testing interface
  - OpenAPI 3.0 schema at `/openapi.json`

### Changed
- **Server Configuration**:
  - Environment-based configuration (production vs development)
  - Uvicorn worker count: Automatic based on CPU cores
  - Timeout settings: Keep-alive 65s, graceful shutdown 30s
  - Connection limits: 1,000 concurrent connections, 2,048 backlog queue
  - Worker recycling: 10,000 requests per worker before restart
- **Security Headers**:
  - Relaxed CSP for API documentation pages
  - Maintained strict CSP for main application
  - Enhanced security headers (X-Frame-Options, X-XSS-Protection)
  - Server version information hiding
- **Vector Database**:
  - Added `group_id` TagField for group-based filtering
  - Support for OR search across multiple groups
  - Document-level filtering with exact filename matching
- **UI Enhancements**:
  - Filter tab visual feedback (active state, selection counts)
  - Group management modal with tree view
  - Document-to-group assignment interface
  - Improved filter UX (문서별/그룹별 tabs)

### Fixed
- **Concurrent Request Handling**: Server now properly handles multiple simultaneous requests
  - Issue: Single worker + blocking operations caused request queuing
  - Solution: Multi-worker + async thread pool for concurrent processing
- **Document Filter Search**: Fixed "no documents found" issue
  - Issue: TextField tokenization prevented exact filename matching
  - Solution: Python-level exact match filtering instead of Redis query filter
- **Duplicate Document Assignment**: Prevented assigning same document to group multiple times
  - Added pre-check to skip already-assigned documents
  - Performance: Optimized batch assignment with single scan
- **Swagger UI Styling**: Fixed broken CSS/JavaScript loading
  - Issue: CSP headers blocked CDN resources
  - Solution: Relaxed CSP for `/docs`, `/redoc`, `/openapi.json` endpoints

### Performance
- **Multi-Worker Architecture**: Up to 8x concurrent request capacity (8 workers)
- **Async Processing**: No event loop blocking, smooth request handling
- **Redis Connection Pool**: 2.5x connection capacity (50 vs 20)
- **Batch Operations**: Optimized group assignment with Redis pipelines
- **Health Checks**: <100ms response time for system status

### Environment Variables
- `ENVIRONMENT`: production/development mode
- `REDIS_MAX_CONNECTIONS`: Connection pool size (default: 50)
- `REDIS_SOCKET_TIMEOUT`: Socket timeout in seconds (default: 5)
- `CACHE_SIMILARITY_THRESHOLD`: Cache similarity threshold (default: 0.95)
- `CACHE_TTL`: Cache time-to-live in seconds (default: 3600)
- `TIMEOUT_KEEP_ALIVE`: Keep-alive timeout (default: 65)
- `TIMEOUT_GRACEFUL_SHUTDOWN`: Graceful shutdown wait (default: 30)
- `LIMIT_CONCURRENCY`: Max concurrent connections (default: 1000)
- `LIMIT_MAX_REQUESTS`: Requests before worker restart (default: 10000)
- `LOG_LEVEL`: Logging level (default: info)
- `LOG_FILE`: Log file path (default: /tmp/chatbot_production.log)

### API Endpoints (New)
- `GET /health` - System health check
- `GET /metrics` - Prometheus metrics
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc documentation
- `GET /api/groups` - List all groups
- `POST /api/groups` - Create new group
- `PUT /api/groups/{group_id}` - Update group
- `DELETE /api/groups/{group_id}` - Delete group
- `PATCH /api/groups/{group_id}/move` - Move group in hierarchy
- `PUT /api/documents/{filename}/group` - Assign document to group
- `POST /api/groups/{group_id}/documents` - Batch assign documents
- `GET /api/groups/{group_id}/documents` - Get group documents

## [2.0.0] - 2025-12-21

### Added
- **Multi-format Document Support**: Added support for 7 additional document formats
  - PDF, HWP, HWPX (existing)
  - DOC, DOCX, XLS, XLSX, PPT, PPTX (new)
- **Java Document Service**: New Spring Boot microservice for document extraction
  - Apache PDFBox 3.0 for PDF processing
  - Apache POI 5.3 for Microsoft Office documents
  - hwplib for HWP file processing
- **Performance Optimizations**:
  - HTTP connection pooling in Python services (10-35% improvement)
  - Caffeine LRU caching in Java service (99% faster on cache hits)
  - Async processing with thread pool (2-3x faster batch processing)
  - JVM memory optimization with G1GC
  - Tomcat server tuning (200 worker threads, HTTP compression)
- **Monitoring & Metrics**:
  - Micrometer metrics integration
  - Prometheus endpoint at port 8082
  - Health check endpoints for all services
- **Documentation**:
  - OPTIMIZATION.md - Comprehensive optimization guide
  - Updated README.md with new features and architecture
  - Environment variable examples for Document Service

### Changed
- **Architecture**: Migrated from monolithic to microservices architecture
  - Python FastAPI web server (frontend + RAG logic)
  - Java Spring Boot document service (document extraction)
  - Redis for vector storage
- **Service Names**: Renamed HWP Service to Document Service to reflect broader capabilities
- **Docker Configuration**:
  - Optimized Dockerfile with JVM performance flags
  - Added management port 8082 for metrics
  - Updated docker-compose.yml with new service architecture
  - Added document-service to production deployment
- **Environment Variables**:
  - Added DOCUMENT_SERVICE_URL configuration
  - Kept HWP_SERVICE_URL for backward compatibility
- **Python Code**:
  - Refactored DocumentProcessor with 2-stage HWP fallback
  - Added DocumentService client with connection pooling
  - Improved HWPProcessor with connection pooling

### Removed
- **Deprecated Code**: Removed pdf_service.py (118 lines)
  - Functionality replaced by unified DocumentService

### Fixed
- **Connection Overhead**: Eliminated TCP handshake overhead with connection pooling
- **Memory Management**: Improved JVM heap management and GC tuning
- **Concurrent Requests**: Enhanced handling of multiple simultaneous users (now supports 200+ concurrent users)

### Performance
- **Single Document Processing**: 10-15% faster
- **Batch Processing**: 25-35% faster with connection pooling
- **Cache Hits**: 99% faster (sub-5ms response time)
- **Startup Time**: 37% faster Java service startup (1.26s)
- **Memory Usage**: More efficient with dynamic heap allocation (512MB-2GB)
- **GC Pauses**: Reduced to <200ms with G1GC

### Security
- **File Validation**: Magic bytes validation for uploaded files
- **Input Sanitization**: Enhanced validation in document endpoints

## [1.0.0] - 2024-12-XX

### Added
- Initial release
- PDF and HWP document support
- Korean language RAG chatbot
- Redis vector storage
- Sentence transformers for embeddings
- MLX-based LLM (Qwen3-30B)
- Web-based chat interface
- Document upload and processing
- Session management
- Auto-generated follow-up questions

---

## Version History Summary

- **2.1.0** (2025-12-23): Document grouping, production server optimizations, multi-worker architecture, monitoring
- **2.0.0** (2025-12-21): Multi-format support, microservices architecture, major performance optimizations
- **1.0.0** (2024-12-XX): Initial release with PDF/HWP support

[Unreleased]: https://github.com/yourusername/chatbot_redis/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/yourusername/chatbot_redis/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/yourusername/chatbot_redis/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/yourusername/chatbot_redis/releases/tag/v1.0.0
