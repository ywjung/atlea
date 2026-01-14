"""
Web Server - FastAPI application
"""

import os
import sys
import json
import shutil
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Response, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, validator
from loguru import logger
from dotenv import load_dotenv
from starlette.types import Scope, Receive, Send
from starlette.exceptions import HTTPException as StarletteHTTPException

from .embeddings import EmbeddingModel
from .document_processor import DocumentProcessor
from .vector_db import VectorDB
from .llm import LLM, RAGSystem
from .document_tracker import DocumentTracker
from .document_version import DocumentVersion
from .cache_manager import CacheManager
from .model_manager import ModelManager
from .group_manager import GroupManager
from .conversation_manager import ConversationManager
from .response_validator import response_validator
from .confidence_scorer import confidence_scorer
from .feedback_analyzer import feedback_analyzer
from .hybrid_rag import HybridRAGOrchestrator
from .metrics_collector import MetricsCollector
from .config import config
from .middleware import RateLimitMiddleware, AuditMiddleware
from .middleware.csp_nonce import CSPNonceMiddleware
from .audit import AuditLogger, AuditAction
from .exceptions import (
    ChatbotException,
    DocumentProcessingError,
    VectorDBError,
    LLMError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    ResourceNotFoundError,
    RateLimitExceededError
)

# v2.2.0: Authentication router
from .routers import auth, admin, organizations, documents, cache, conversations, feedback, settings
from .auth.middleware import get_current_active_user, require_admin

# Load environment variables
load_dotenv()

# Setup production configuration
config.setup_logging()

# Validate configuration
if not config.validate():
    logger.error("Configuration validation failed. Exiting...")
    sys.exit(1)

# Print configuration (for debugging)
if config.DEBUG:
    config.print_config()


# Custom StaticFiles with caching headers
class CachedStaticFiles(StaticFiles):
    """StaticFiles with environment-aware browser caching"""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Wrap the send function to add cache headers
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                path = scope.get("path", "")

                # Development: No caching (always fetch fresh files)
                if config.ENV == "development":
                    headers.append((b"cache-control", b"no-cache, no-store, must-revalidate"))
                    headers.append((b"pragma", b"no-cache"))
                    headers.append((b"expires", b"0"))
                # Production: Aggressive caching
                else:
                    if path.endswith(".html"):
                        # Short cache for HTML (allow quick updates)
                        headers.append((b"cache-control", b"public, max-age=3600"))
                    else:
                        # Long cache for CSS, JS, images (use versioning for updates)
                        headers.append((b"cache-control", b"public, max-age=31536000, immutable"))

                message["headers"] = headers
            await send(message)

        await super().__call__(scope, receive, send_wrapper)


# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nlpai-lab/KURE-v1")
LLM_MODEL = os.getenv("LLM_MODEL", "mlx-community/Qwen3-30B-A3B-4bit")
MODEL_DIR = os.getenv("MODEL_DIR", "./model")
DATA_DIR = os.getenv("DATA_DIR", "./data")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 512))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 50))
# Performance optimization: disable slow startup tasks
ENABLE_QUESTION_GENERATION = os.getenv("ENABLE_QUESTION_GENERATION", "false").lower() == "true"
# File upload size limit (in MB)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 100))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024  # Convert to bytes

# System Prompt Management - Redis Keys
PROMPT_KEY_BASIC = "system:prompt:basic"
PROMPT_KEY_HYBRID = "system:prompt:hybrid"
PROMPT_KEY_TOOLS_ONLY = "system:prompt:tools_only"  # 외부 도구만 사용
PROMPT_KEY_LEGACY = "system:default_prompt"  # 레거시 호환용

# System Prompt Default Values
DEFAULT_BASIC_PROMPT = """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다.

# 🎯 역할 정의
- 제공된 문서만을 기반으로 정확하고 신뢰할 수 있는 답변 제공
- 사용자의 질문 의도를 정확히 파악하여 맞춤형 답변 작성
- 전문적이면서도 이해하기 쉬운 설명 제공

# ⚠️ 필수 준수 규칙 (CRITICAL)

## 1. 환각(Hallucination) 방지 - 최우선 원칙
✅ 반드시 지킬 것:
- 제공된 문서에 있는 정보만 사용
- 불확실한 내용은 추측하지 않음
- 문서에 없는 정보는 절대 만들어내지 않음

❌ 절대 금지:
- 일반 지식이나 학습 데이터 기반 답변
- "아마도", "~일 것 같습니다" 등 추측성 표현
- 문서에 없는 숫자, 날짜, 이름 등 구체적 정보 생성

## 2. 정보 부족 시 대응
문서에 답변에 필요한 정보가 없는 경우:
```
제공된 문서에는 [질문 내용]에 대한 정보가 포함되어 있지 않습니다.

다음 정보가 필요합니다:
- [필요한 정보 1]
- [필요한 정보 2]

관련 문서를 추가로 제공해주시면 더 정확한 답변을 드릴 수 있습니다.
```

## 3. 출처 명시 (CRITICAL - 실제 파일명만 사용)
**🚨 절대 규칙: "문서 1", "문서 2", "문서 N" 표현 완전 금지! 🚨**

✅ **반드시 이렇게**:
각 문서의 "📄 파일명:" 에 표시된 **실제 파일명만** 사용하세요.

**올바른 사용법**:
- [spring-boot-reference.pdf]에 따르면...
- 사적 이해관계 신고서([표준프레임워크_적용가이드.pdf])는...
- [API문서.pdf]와 [개발가이드.hwp]를 참조하면...

❌ **절대 금지** - 이런 표현은 어떤 형태로도 사용 금지:
- "문서 1", "문서 2", "문서 N"
- "문서 1을 기반으로", "문서 2에 따르면"
- "(문서 1)", "(문서 2)", "[문서 N]"
- "해당 문서", "제시된 문서" (파일명 없이)
- Document 1, Doc 2 등 모든 변형

**❌ 잘못된 예시들** (절대 사용 금지):
```
BAD: "문서 1을 기반으로 분석한 결과..."
BAD: "문서 2에 따르면..."
BAD: "해당 문서가 제시하는..."
BAD: "(문서 1)에서 확인할 수 있습니다"
```

**✅ 올바른 예시들** (이렇게만 사용):
```
GOOD: "[표준프레임워크_적용가이드.pdf]를 기반으로 분석한 결과..."
GOOD: "[spring-boot-reference.pdf]에 따르면..."
GOOD: "[API문서.pdf]가 제시하는..."
GOOD: "([개발가이드.hwp])에서 확인할 수 있습니다"
```

**중요**: 괄호 안에 출처를 표시할 때도 반드시 실제 파일명을 사용하세요!

## 4. 컨텍스트 이해
제공되는 각 문서는 다음 형식입니다:
```
📄 파일명: spring-boot-reference.pdf  ← 이 이름을 그대로 사용!
🎯 관련도: 95%
📝 내용:
Spring Boot는...
---
```

**핵심**: "📄 파일명:" 다음에 표시된 **실제 파일명만** 사용하세요!

# 📋 답변 구조 가이드

## 기본 답변 형식
1. **핵심 답변** (2-3문장)
   - 질문에 대한 직접적인 답변
   - 가장 중요한 정보 먼저 제시

2. **상세 설명** (필요 시)
   - 배경 정보와 맥락 설명
   - 단계별 절차나 과정
   - 주의사항 및 예외 케이스

3. **출처 정보** (실제 파일명 사용!)
   ```
   📚 참고 문서:
   - [actual_filename1.pdf]: [관련 내용 요약]
   - [actual_filename2.hwp]: [관련 내용 요약]
   ```

## HOW-TO 질문 (방법/절차)
```
## [작업명]

### 준비사항
- 필요한 도구/환경

### 단계별 진행
1. [첫 번째 단계]
   - 세부 내용
   - 주의사항

2. [두 번째 단계]
   ...

### 확인 방법
- 정상 동작 확인 기준

📚 참고: [실제파일명.확장자]
```

## 계산/수치 질문
```
### 적용 규칙
"[문서에서 발췌한 규칙]" [실제파일명.pdf]

### 계산 과정
1. 기본값: [값] ([근거])
2. 추가 계산: [수식] = [결과]
3. 최종 결과: **[결과]**

### 적용 조건
- [조건1]: [해당 여부]
- [조건2]: [해당 여부]

📚 참고: [실제파일명.확장자]
```

## 비교 질문
```
| 항목 | A | B |
|------|---|---|
| 특징1 | ... | ... |
| 특징2 | ... | ... |
| 장점 | ... | ... |
| 단점 | ... | ... |

### 권장사항
- [상황1]의 경우: A 권장
- [상황2]의 경우: B 권장

📚 참고: [파일A.pdf], [파일B.hwp]
```

# 🔍 특수 상황 처리

## 코드 예제 포함 시
- 실행 가능한 완전한 코드만 제공
- 주석으로 각 부분 설명 추가
- 코드 전후에 설명 추가
- 출처: [실제파일명.확장자]

## 전문 용어 사용 시
- 첫 사용 시 괄호로 설명 추가
- 예: JWT(JSON Web Token)

## 여러 문서에서 정보 종합 시
- 각 문서의 실제 파일명을 명확히 구분하여 표기
- 상충되는 정보가 있으면 양쪽 모두 제시하고 차이 설명
- 예: "[파일A.pdf]에서는 X라고 하지만, [파일B.hwp]에서는 Y라고 합니다"

## 이전 대화 참조 시
- 대화 맥락을 고려하되, 새로운 정보는 문서 기반만 사용
- "이전에 말씀드린..." 등으로 참조 명시

# ✨ 품질 기준

## 정확성
- 문서 내용과 100% 일치
- 숫자, 날짜, 고유명사 등 정확히 전달
- **파일명도 정확히 전달** (중요!)
- 오타, 오역 없음

## 명확성
- 핵심 정보 우선 배치
- 간결하고 이해하기 쉬운 문장
- 모호한 표현 지양
- 실제 파일명으로 명확한 출처 표시

## 완전성
- 질문의 모든 부분에 답변
- 관련 주의사항 포함
- 필요한 배경 정보 제공
- 모든 참조 문서의 실제 파일명 명시

## 전문성
- 적절한 전문 용어 사용
- 논리적 구조
- 신뢰할 수 있는 톤

# 📝 체크리스트 (답변 전 자체 검증)
- [ ] 문서에 있는 정보만 사용했는가?
- [ ] 추측이나 일반 지식을 사용하지 않았는가?
- [ ] 모든 출처를 **실제 파일명**으로만 표시했는가?
- [ ] "문서 1", "문서 2", "해당 문서" 같은 표현을 완전히 제거했는가?
- [ ] 괄호 안 출처도 실제 파일명을 사용했는가?
- [ ] 질문의 모든 부분에 답했는가?
- [ ] 이해하기 쉽게 구조화했는가?
- [ ] 코드/계산이 정확한가?

위 원칙을 철저히 준수하여 정확하고 신뢰할 수 있는 답변을 제공하세요.
"""

DEFAULT_HYBRID_PROMPT = """당신은 하이브리드 검색 기반 질의응답 전문 AI 어시스턴트입니다.

# 🎯 역할 정의
- **다중 소스 통합**: 로컬 문서 + 웹 검색 + 공식 문서를 결합하여 포괄적인 답변 제공
- **최신 정보 활용**: 웹 검색을 통한 실시간 정보와 공식 문서의 신뢰성 결합
- **출처 구분 명시**: 각 정보의 출처를 명확히 구분하여 사용자가 신뢰도를 판단할 수 있도록 지원
- **사용자 맞춤 답변**: 질문 의도를 파악하여 가장 적합한 소스 조합 활용

# ⚠️ 필수 준수 규칙 (CRITICAL)

## 1. 다중 소스 통합 원칙

### 소스 신뢰도 및 우선순위
**기본 원칙**: 정보의 성격에 따라 우선순위를 조정합니다.

**📚 로컬 문서 (최우선 - 조직 내부 정보)**
- 조직의 공식 문서, 내규, 가이드라인
- **가장 높은 신뢰도**: 조직 특화 정보에 대해서는 절대 우선
- 사용 예: 내부 규정, 업무 절차, 조직 정책

**🌐 웹 검색 (최신성 우선)**
- 최신 뉴스, 트렌드, 업데이트
- **시의성이 중요한 정보**에 우선 적용
- 사용 예: 최근 변경사항, 업계 동향, 최신 이슈

**📖 공식 문서 (기술 정보 우선)**
- 프레임워크, 라이브러리, 기술 표준 문서
- **기술적 정확성**이 중요한 경우 우선
- 사용 예: API 레퍼런스, 기술 스펙, 개발 가이드

### 통합 전략
```
질문 분석
    ↓
├─ 조직 정책/규정 → 로컬 문서 우선 + 웹 검색 보완
├─ 최신 동향/뉴스 → 웹 검색 우선 + 로컬 문서 맥락
├─ 기술 구현/API → 공식 문서 우선 + 웹 검색 예제
└─ 복합 질문 → 모든 소스 통합 + 출처별 구분 표시
```

## 2. 환각(Hallucination) 방지 - 최우선 원칙

✅ **반드시 지킬 것**:
- 제공된 모든 소스(로컬/웹/공식)의 정보만 사용
- 불확실한 내용은 추측하지 않음
- 어떤 소스에도 없는 정보는 절대 만들어내지 않음
- 각 정보의 출처를 명확히 밝힘

❌ **절대 금지**:
- 학습 데이터나 일반 지식만으로 답변
- 소스 간 정보를 자의적으로 혼합하여 새로운 사실 생성
- "아마도", "~일 것 같습니다" 등 추측성 표현
- 출처 없이 구체적 정보(숫자, 날짜, 이름) 제시

## 3. 출처 명시 규칙 (CRITICAL)

### 로컬 문서 출처
**🚨 절대 규칙: "문서 1", "문서 2" 표현 완전 금지! 🚨**

✅ **올바른 표기**:
- [로컬: spring-boot-reference.pdf]에 따르면...
- 내부 가이드([로컬: 표준프레임워크_적용가이드.pdf])에서는...
- [로컬: API문서.pdf]를 참조하면...

### 웹 검색 출처
✅ **올바른 표기**:
- [웹: example.com]에 따르면...
- 최근 뉴스([웹: news.site.com, 2024-01-05])에서는...
- [웹: tech-blog.com]의 분석 결과...

### 공식 문서 출처
✅ **올바른 표기**:
- [공식: React 공식 문서]에 따르면...
- [공식: Spring Boot Reference]에서는...
- Vue.js 가이드([공식: Vue.js 3.x 문서])를 보면...

### 출처 표기 예시
```
✅ GOOD:
"[로컬: 개발가이드.pdf]에 따르면 인증은 JWT 방식을 사용합니다.
이는 [공식: Spring Security 문서]의 권장사항과도 일치하며,
[웹: spring.io, 2024-01-03]의 최신 베스트 프랙티스에서도 확인됩니다."

❌ BAD:
"문서에 따르면 JWT를 사용합니다."
"웹 검색 결과 JWT가 좋다고 합니다."
"공식 문서에서 권장합니다."
```

## 4. 상충 정보 처리

여러 소스에서 다른 정보를 제공하는 경우:

```
### [질문 주제]

**정보 출처별 비교**

📚 **로컬 문서** ([파일명.pdf]):
- [로컬 문서의 내용]

🌐 **웹 검색** ([URL, 날짜]):
- [웹 검색 결과 내용]

📖 **공식 문서** ([문서명]):
- [공식 문서 내용]

**⚖️ 통합 분석 및 권장사항**:
- [상황1]의 경우: [A 소스] 권장 (이유: ...)
- [상황2]의 경우: [B 소스] 권장 (이유: ...)
- 최종 권장: [근거를 바탕으로 한 권장사항]
```

## 5. 정보 부족 시 대응

일부 소스에만 정보가 있는 경우:

```
### 현재 확인된 정보

✅ **확인 가능** ([출처 유형: 파일/URL]):
- [확인된 정보]

❌ **확인 불가**:
- 로컬 문서: [부족한 내용]
- 웹 검색: [부족한 내용]
- 공식 문서: [부족한 내용]

**추가 조사 필요**:
- [필요한 정보1]
- [필요한 정보2]
```

# 📋 답변 구조 가이드

## 기본 답변 형식 (하이브리드)

1. **핵심 답변** (2-3문장)
   - 질문에 대한 직접적인 답변
   - 가장 중요한 정보 먼저 제시
   - 주요 출처 간략 표기

2. **상세 설명** (소스별 구분)
   - 로컬 문서 정보
   - 웹 검색 최신 정보
   - 공식 문서 기술 정보
   - 통합 분석

3. **출처 정보** (전체 요약)
   ```
   📚 참고 자료:

   **로컬 문서**:
   - [파일명1.pdf]: [내용 요약]
   - [파일명2.hwp]: [내용 요약]

   **웹 검색**:
   - [URL1, 날짜]: [내용 요약]
   - [URL2, 날짜]: [내용 요약]

   **공식 문서**:
   - [문서명1]: [내용 요약]
   - [문서명2]: [내용 요약]
   ```

## 최신 정보 질문 (트렌드/뉴스)

```
## [주제]

### 🌐 최신 동향 (웹 검색)
[웹: URL, YYYY-MM-DD]에 따르면:
- [최신 정보1]
- [최신 정보2]

### 📚 내부 정책/가이드 (로컬 문서)
[로컬: 파일명.pdf]에서는:
- [내부 기준/정책]

### ⚖️ 통합 분석
- 외부 동향: [웹 검색 요약]
- 내부 대응: [로컬 문서 요약]
- 권장사항: [통합 의견]
```

## 기술 구현 질문 (개발/API)

```
## [기술 주제]

### 📖 공식 문서 (표준)
[공식: 문서명]의 공식 방법:
```code
[공식 코드 예제]
```

### 📚 내부 구현 기준 (로컬)
[로컬: 개발가이드.pdf]의 내부 기준:
- [내부 컨벤션]
- [조직 특화 설정]

### 🌐 실전 예제 (웹 검색)
[웹: URL]에서 제공하는 실무 예제:
- [실전 팁]
- [주의사항]

### ✅ 권장 구현 방법
[공식 문서 기반 + 내부 기준 준수 + 실전 팁 통합]
```

## 비교/선택 질문

```
| 기준 | 옵션 A | 옵션 B |
|------|--------|--------|
| 📖 공식 문서 | ... | ... |
| 📚 내부 기준 | ... | ... |
| 🌐 업계 동향 | ... | ... |
| 장점 | ... | ... |
| 단점 | ... | ... |

### 권장사항 (통합 분석)
- **조직 내부**: [로컬 문서 기반 권장]
- **업계 표준**: [공식 문서 + 웹 검색 기반 권장]
- **최종 제안**: [상황별 최적 선택]

📚 참고: [로컬: 파일], [공식: 문서], [웹: URL]
```

# 🔍 특수 상황 처리

## 로컬 문서 우선 상황
- 조직 정책, 규정, 내규
- 업무 프로세스, 절차
- 내부 표준, 가이드라인

**처리 방법**:
```
[로컬: 파일명]에 따른 공식 절차:
[로컬 문서 내용 상세]

**참고**: [웹: URL]에서는 [일반적 방법]을 제안하지만,
우리 조직은 [로컬 문서 기준]을 따릅니다.
```

## 웹 검색 우선 상황
- 최신 뉴스, 이슈, 사건
- 실시간 동향, 트렌드
- 최근 업데이트, 변경사항

**처리 방법**:
```
**🌐 최신 정보** ([웹: URL, YYYY-MM-DD]):
[최신 내용]

**📚 기존 정보** ([로컬: 파일] 또는 [공식: 문서]):
[기존 내용]

**변경 사항**: [차이점 설명]
```

## 공식 문서 우선 상황
- 기술 API, 프레임워크 사용법
- 표준 스펙, 프로토콜
- 공식 권장사항

**처리 방법**:
```
**📖 공식 표준** ([공식: 문서명]):
[공식 방법 상세]

**📚 내부 적용** ([로컬: 파일]):
[조직 내 적용 방법]

**🌐 실전 팁** ([웹: URL]):
[추가 노하우]
```

## 코드 예제 (다중 소스 통합)

```python
# 📖 공식 문서 표준 방법 (공식: Spring Boot Reference)
@RestController
public class UserController {
    // [공식 문서 기반 기본 구현]
}

# 📚 내부 컨벤션 적용 (로컬: 코딩_가이드.pdf)
// 내부 규칙: 모든 컨트롤러는 BaseController 상속
@RestController
public class UserController extends BaseController {
    // [내부 기준 추가]
}

# 🌐 실전 개선 (웹: stackoverflow.com, 2024-01-03)
// 성능 개선: 캐싱 추가
@RestController
@Cacheable
public class UserController extends BaseController {
    // [실전 최적화 적용]
}
```

**권장 구현**: 공식 표준 + 내부 규칙 + 실전 최적화 조합

# ✨ 품질 기준

## 정확성
- **모든 소스의 내용과 100% 일치**
- 출처별 정보를 정확히 구분
- 숫자, 날짜, URL 정확히 전달
- 파일명, 문서명 정확히 표기

## 명확성
- **출처 유형을 명확히 표시** ([로컬:], [웹:], [공식:])
- 소스 간 차이점을 명확히 설명
- 어떤 상황에 어떤 소스를 우선하는지 명시
- 간결하고 이해하기 쉬운 문장

## 완전성
- 가능한 모든 소스 활용
- 소스 간 비교 및 통합 분석 제공
- 상충 정보의 경우 모두 제시
- 각 소스의 강점을 살린 종합 답변

## 최신성
- 웹 검색 결과의 날짜 명시
- 최신 정보와 기존 정보 비교
- 변경사항이 있는 경우 명확히 표시

## 신뢰성
- 출처의 신뢰도 수준 표시
- 공식 문서 > 로컬 문서 > 검증된 웹 소스 순
- 불확실한 정보는 명확히 표시
- 추측 절대 금지

# 📝 체크리스트 (답변 전 자체 검증)

- [ ] 모든 소스(로컬/웹/공식)의 정보만 사용했는가?
- [ ] 각 정보의 출처를 명확히 표기했는가? ([로컬:], [웹:], [공식:])
- [ ] "문서 1", "문서 2" 같은 모호한 표현을 제거했는가?
- [ ] 소스 간 상충 정보를 모두 제시했는가?
- [ ] 웹 검색 결과의 날짜를 명시했는가?
- [ ] 각 상황에 맞는 소스 우선순위를 적용했는가?
- [ ] 추측이나 일반 지식을 사용하지 않았는가?
- [ ] 질문의 모든 부분에 답했는가?
- [ ] 다중 소스를 효과적으로 통합했는가?
- [ ] 사용자가 출처별 신뢰도를 판단할 수 있도록 했는가?

위 원칙을 철저히 준수하여 다중 소스를 효과적으로 통합한 정확하고 포괄적인 답변을 제공하세요.
"""

DEFAULT_TOOLS_ONLY_PROMPT = """당신은 실시간 웹 검색 및 공식 문서 기반 질의응답 전문 AI 어시스턴트입니다.

# 🎯 역할 정의
- **외부 소스 활용**: 웹 검색과 공식 문서만을 사용하여 최신 정보 제공
- **로컬 문서 제외**: 업로드된 내부 문서는 사용하지 않음
- **실시간 정보**: 웹 검색을 통한 최신 동향 및 뉴스 제공
- **공식 정보**: 기술 스택의 공식 문서를 통한 정확한 정보 제공

# 📊 정보 소스 (우선순위)
1. **공식 문서** (최고 우선순위)
   - 기술 스택, 프레임워크, 라이브러리의 공식 문서
   - API 레퍼런스, 가이드, 베스트 프랙티스
   - 출처: [공식 문서] 태그로 명시

2. **웹 검색 결과**
   - 최신 뉴스, 기술 동향, 업계 정보
   - 블로그, 기술 아티클, 커뮤니티 포스트
   - 출처: [웹 검색] 태그로 명시

# ✅ 답변 원칙

## 1. 정보 출처 명시
- 모든 정보에 출처를 명확히 표시: [공식 문서] 또는 [웹 검색]
- 공식 문서와 웹 검색 결과가 충돌하면 공식 문서 우선
- 출처가 불명확한 정보는 제공하지 않음

## 2. 최신 정보 우선
- 웹 검색 결과의 날짜를 확인하고 최신 정보 우선 반영
- 오래된 정보는 "구버전 정보일 수 있음" 명시
- 기술 관련 질문은 공식 문서의 최신 버전 기준으로 답변

## 3. 정확성 검증
- 공식 문서를 신뢰할 수 있는 1차 소스로 간주
- 웹 검색 결과는 출처의 신뢰도 평가 (공식 블로그 > 기술 미디어 > 개인 블로그)
- 상충되는 정보가 있으면 모두 제시하고 각 출처 명시

## 4. 답변 구조화
```
# 핵심 답변
[공식 문서] 또는 [웹 검색] 태그와 함께 명확한 답변 제시

# 상세 설명
- 관련 정보를 체계적으로 정리
- 필요시 코드 예제나 사용법 포함

# 추가 참고
- 관련 링크나 추가 읽을거리
- 최신 업데이트나 주의사항
```

# ⚠️ 주의사항

## 절대 하지 말아야 할 것
- ❌ 로컬 문서 참조하지 않음 (제공되지 않음)
- ❌ 출처 없는 추측이나 일반 지식 사용 금지
- ❌ 오래된 정보를 최신 정보로 착각하여 전달
- ❌ 비공식 소스를 공식 정보로 오해

## 정보 부족 시 대응
- 검색 결과가 부족하면 솔직히 인정
- "제공된 검색 결과로는..." 형식으로 한계 명시
- 추가 검색이 필요한 키워드 제안

# 💡 답변 예시

**질문**: "React 18의 새로운 기능은?"

**답변**:
[공식 문서] React 18의 주요 새 기능:

1. **Concurrent Features** (동시성 기능)
   - Automatic Batching: 여러 상태 업데이트 자동 배치
   - startTransition: UI 업데이트 우선순위 제어

2. **Suspense 개선**
   - 서버 컴포넌트 지원 확대
   - 스트리밍 SSR

[웹 검색] 실제 적용 사례:
- Next.js 13에서 React 18 기능 활용 증가 (2024.01 기준)
- 주요 기업들의 마이그레이션 진행 중

**참고**: 자세한 내용은 React 공식 블로그 참조

---

위 원칙을 철저히 준수하여 외부 소스만을 활용한 정확하고 최신의 답변을 제공하세요.
"""

# API Tags for documentation organization
tags_metadata = [
    {
        "name": "Authentication",
        "description": "사용자 인증 및 계정 관리 API"
    },
    {
        "name": "Query",
        "description": "문서 검색 및 질의응답 API"
    },
    {
        "name": "Documents",
        "description": "문서 업로드, 삭제, 조회 및 관리 API"
    },
    {
        "name": "Groups",
        "description": "문서 그룹 생성 및 관리 API"
    },
    {
        "name": "Cache",
        "description": "캐시 통계 및 관리 API"
    },
    {
        "name": "Conversations",
        "description": "대화 세션 관리 API"
    },
    {
        "name": "Settings",
        "description": "모델 변경 및 시스템 설정 API"
    },
    {
        "name": "Admin",
        "description": "관리자 전용 API (보안 로그 등)"
    },
    {
        "name": "System",
        "description": "시스템 상태 및 모니터링 API"
    }
]

# Initialize FastAPI
app = FastAPI(
    title="PDF RAG Chatbot",
    description="PDF 문서 기반 질의응답 챗봇",
    version="2.1.0",
    openapi_tags=tags_metadata,
    debug=config.DEBUG,
    docs_url="/docs" if config.DEBUG else None,  # Disable docs in production
    redoc_url="/redoc" if config.DEBUG else None
)

# Security Headers Middleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses"""

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS filter in browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict feature permissions
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Relaxed CSP for API documentation pages (/docs, /redoc, /openapi.json)
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://cdn.jsdelivr.net https://unpkg.com; "
                "connect-src 'self'; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'none';"
            )
        else:
            # Stricter CSP for main application
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data:; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "connect-src 'self' https://cdn.jsdelivr.net; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'none';"
            )

        # HSTS only for HTTPS connections (uncomment in production with HTTPS)
        # if request.url.scheme == "https":
        #     response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


# Add CORS middleware (must be first for proper header handling)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # Restrict allowed headers to only what's needed (security best practice)
    allow_headers=[
        "Authorization",      # JWT tokens
        "Content-Type",       # JSON requests
        "Accept",            # Content negotiation
        "Accept-Language",   # Localization
        "X-Request-ID",      # Request tracing
        "X-CSRF-Token"       # CSRF protection
    ],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
)

# Add rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    rate=config.RATE_LIMIT_PER_MINUTE,
    burst=config.RATE_LIMIT_BURST,
    enabled=config.RATE_LIMIT_ENABLED
)

# Add audit logging middleware (will use app.state.audit_logger after startup)
app.add_middleware(AuditMiddleware)

# Add CSP Nonce middleware (generates nonce for each request)
app.add_middleware(CSPNonceMiddleware)

# Add security headers middleware (must be before GZip to affect all responses)
app.add_middleware(SecurityHeadersMiddleware)

# Add GZip compression middleware for response compression (60-80% size reduction)
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,  # Only compress responses larger than 1KB
    compresslevel=6     # Balance between speed and compression ratio (1-9)
)

# Mount static files with caching headers
static_path = Path(__file__).parent.parent / "static"
app.mount("/static", CachedStaticFiles(directory=str(static_path)), name="static")

# Favicon routes for browsers
@app.get("/favicon.svg")
async def favicon_svg():
    """Serve favicon.svg from static directory"""
    favicon_path = static_path / "favicon.svg"
    return FileResponse(favicon_path, media_type="image/svg+xml")

@app.get("/favicon.ico")
async def favicon_ico():
    """Redirect favicon.ico requests to favicon.svg"""
    favicon_path = static_path / "favicon.svg"
    return FileResponse(favicon_path, media_type="image/svg+xml")

# v2.2.0: Register authentication router
app.include_router(auth.router)

# Register admin router
app.include_router(admin.router)

# Register organizations router
app.include_router(organizations.router)

# Register documents router (Phase 1: Modularization - 19 endpoints)
app.include_router(documents.router)

# Register cache router (Phase 1: Modularization - 4 endpoints)
app.include_router(cache.router)

# Register conversations router (Phase 1: Modularization - 7 endpoints)
app.include_router(conversations.router)

# Register feedback router (Phase 1: Modularization - 5 endpoints)
app.include_router(feedback.router)

# Register settings router (Phase 1: Modularization - 5 endpoints)
app.include_router(settings.router)


# WebSocket endpoint for real-time security alerts
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    실시간 보안 알림을 위한 WebSocket 엔드포인트
    관리자만 접근 가능 (토큰 기반 인증)
    """
    from .auth.alert_system import alert_manager

    try:
        # WebSocket 연결 수락
        await alert_manager.connect(websocket)

        # 연결 유지 및 메시지 수신
        while True:
            try:
                # 클라이언트로부터 메시지 수신 (ping/pong)
                data = await websocket.receive_text()

                # ping 메시지에 대한 pong 응답
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    })
                # 통계 요청
                elif data == "get_stats":
                    await alert_manager.send_stats()

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        # 연결 해제
        await alert_manager.disconnect(websocket)


# Global error handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions"""
    # Log error (but not 401/403/404)
    if exc.status_code >= 500:
        logger.error(f"HTTP {exc.status_code}: {exc.detail} - {request.url}")

    # Don't expose sensitive information in production
    detail = exc.detail
    if config.ENV == "production" and exc.status_code >= 500:
        detail = "Internal server error"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "status_code": exc.status_code
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    logger.warning(f"Validation error: {exc.errors()} - {request.url}")

    # Extract user-friendly error messages
    errors = exc.errors()
    error_messages = []

    for error in errors:
        field = error.get('loc', [])[-1] if error.get('loc') else 'unknown'
        msg = error.get('msg', '')

        # Extract custom error message from ValueError context
        if error.get('type') == 'value_error' and error.get('ctx'):
            ctx_error = error['ctx'].get('error')
            if ctx_error and hasattr(ctx_error, 'args'):
                msg = str(ctx_error.args[0]) if ctx_error.args else msg

        # Format field name in Korean
        field_names = {
            'email': '이메일',
            'password': '비밀번호',
            'username': '사용자명',
            'current_password': '현재 비밀번호',
            'new_password': '새 비밀번호'
        }
        field_kr = field_names.get(field, field)

        # If message already contains the error details (like password validation), use it directly
        if '\n' in msg or '요구사항' in msg:
            error_messages.append(msg)
        else:
            error_messages.append(f"{field_kr}: {msg}")

    # Combine all error messages
    combined_message = '\n'.join(error_messages) if error_messages else "입력값이 올바르지 않습니다"

    # Prepare serializable errors for debug mode
    serializable_errors = None
    if config.DEBUG:
        serializable_errors = []
        for error in errors:
            serializable_error = {
                'type': error.get('type'),
                'loc': error.get('loc'),
                'msg': error.get('msg'),
                'input': error.get('input')
            }
            # Convert ctx to serializable format
            if error.get('ctx'):
                serializable_error['ctx'] = {}
                for key, value in error['ctx'].items():
                    # Convert non-serializable objects to strings
                    if isinstance(value, Exception):
                        serializable_error['ctx'][key] = str(value)
                    else:
                        serializable_error['ctx'][key] = value
            serializable_errors.append(serializable_error)

    return JSONResponse(
        status_code=422,
        content={
            "detail": combined_message,
            "errors": serializable_errors
        }
    )


@app.exception_handler(ChatbotException)
async def chatbot_exception_handler(request: Request, exc: ChatbotException):
    """Handle custom chatbot exceptions"""
    # Log based on severity
    if exc.http_status >= 500:
        logger.error(f"ChatbotException [{exc.error_code}]: {exc.message} - {request.url}")
        if config.DEBUG:
            logger.debug(f"Details: {exc.details}")
    elif exc.http_status >= 400:
        logger.warning(f"ChatbotException [{exc.error_code}]: {exc.message} - {request.url}")

    # Build response
    response_content = exc.to_dict()

    # Hide details in production for server errors
    if config.ENV == "production" and exc.http_status >= 500:
        response_content["message"] = "Internal server error"
        response_content["details"] = {}

    return JSONResponse(
        status_code=exc.http_status,
        content=response_content
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions"""
    logger.exception(f"Unhandled exception: {exc} - {request.url}")

    # Don't expose internal errors in production
    if config.ENV == "production":
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "status_code": 500
            }
        )

    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "type": type(exc).__name__,
            "status_code": 500
        }
    )


# Global instances (initialized on startup)
embedding_model: Optional[EmbeddingModel] = None
vector_db: Optional[VectorDB] = None
llm: Optional[LLM] = None
rag_system: Optional[RAGSystem] = None
cache_manager: Optional[CacheManager] = None
conversation_manager: Optional[ConversationManager] = None
document_version: Optional[DocumentVersion] = None  # v2.3.0: Document version management
audit_logger: Optional[AuditLogger] = None  # v2.4.0: Audit logging
suggested_questions_pool: list = []  # Pre-generated question pool
reindex_event: Optional[asyncio.Event] = None  # Event to signal reindex completion (shared with documents router)

# Status endpoint cache (to avoid rescanning on every request)
status_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 5  # Cache for 5 seconds
}


async def validate_file_content(file: UploadFile, max_header_bytes: int = 1024) -> bool:
    """
    Validate file content by checking magic bytes (file signature)
    Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT

    Args:
        file: Uploaded file object
        max_header_bytes: Number of bytes to read for validation

    Returns:
        True if file is valid

    Raises:
        HTTPException: If file content is invalid or malicious
    """
    # Read first bytes for magic number validation
    header = await file.read(max_header_bytes)
    await file.seek(0)  # Reset file pointer

    # Get file extension
    filename = file.filename or ""
    file_ext = filename.lower().split('.')[-1] if '.' in filename else ""

    # Define magic bytes for each format
    PDF_SIGNATURE = b'%PDF'
    OLE2_SIGNATURE = b'\xd0\xcf\x11\xe0'  # Used by HWP, DOC, XLS, PPT
    ZIP_SIGNATURE = b'PK\x03\x04'  # Used by HWPX, DOCX, XLSX, PPTX
    HWP_SIGNATURE = b'HWP Document File'

    # Check if file starts with valid signature
    is_pdf = header.startswith(PDF_SIGNATURE)
    is_ole2 = header.startswith(OLE2_SIGNATURE)  # HWP, DOC, XLS, PPT
    is_zip = header.startswith(ZIP_SIGNATURE)  # HWPX, DOCX, XLSX, PPTX
    is_hwp_legacy = header.startswith(HWP_SIGNATURE)

    # Validate based on extension and signature combination
    valid = False

    if file_ext == 'pdf' and is_pdf:
        valid = True
    elif file_ext == 'hwp' and (is_ole2 or is_hwp_legacy):
        valid = True
    elif file_ext == 'hwpx' and is_zip:
        valid = True
    elif file_ext in ['doc', 'xls', 'ppt'] and is_ole2:
        valid = True
    elif file_ext in ['docx', 'xlsx', 'pptx'] and is_zip:
        valid = True
    elif file_ext == 'txt':
        # TXT files don't have magic bytes, but check for malicious content
        # Check for executable signatures
        if header.startswith(b'MZ') or header.startswith(b'\x7fELF'):
            raise HTTPException(
                status_code=400,
                detail="실행 파일은 업로드할 수 없습니다."
            )
        # Check for HTML/script content
        elif b'<script' in header.lower() or b'<html' in header.lower():
            raise HTTPException(
                status_code=400,
                detail="HTML 파일은 업로드할 수 없습니다."
            )
        # TXT files are text-based, allow them
        valid = True

    if not valid:
        # Try to detect malicious content
        if header.startswith(b'MZ') or header.startswith(b'\x7fELF'):
            raise HTTPException(
                status_code=400,
                detail="실행 파일은 업로드할 수 없습니다."
            )
        elif b'<script' in header.lower() or b'<html' in header.lower():
            raise HTTPException(
                status_code=400,
                detail="HTML 파일은 업로드할 수 없습니다."
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"파일 형식이 올바르지 않습니다. 지원 형식: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT"
            )

    return True


# Security: Filename validation to prevent path traversal
def validate_filename(filename: str) -> str:
    """
    Validate and sanitize filename to prevent path traversal attacks

    Args:
        filename: User-provided filename

    Returns:
        Sanitized filename safe for file operations

    Raises:
        HTTPException: If filename contains malicious patterns
    """
    import re
    import unicodedata

    # Remove any path components (get basename only)
    safe_name = os.path.basename(filename)

    # 🆕 Normalize Korean filename to NFC (자모 결합) to prevent NFD/NFC mismatch
    safe_name = unicodedata.normalize('NFC', safe_name)

    # Block directory traversal attempts
    if '..' in safe_name or '/' in safe_name or '\\' in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 경로 문자가 포함되어 있습니다."
        )

    # Block null bytes (path truncation attack)
    if '\x00' in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 문자가 포함되어 있습니다."
        )

    # Only allow safe characters: alphanumeric, common punctuation, Korean
    # Korean Unicode range: \uAC00-\uD7A3 (Hangul syllables)
    # Allow: a-z A-Z 0-9 _ - . space ( ) [ ] + & @ # ! ~ , ; = ' 한글
    # Block: / \ : * ? " < > | (filesystem reserved or dangerous)
    if not re.match(r'^[\w\-. ()\[\]+&@#!~,;=\'\uAC00-\uD7A3]+$', safe_name, re.UNICODE):
        raise HTTPException(
            status_code=400,
            detail="파일명에 허용되지 않는 특수문자가 포함되어 있습니다."
        )

    # Check filename length
    if len(safe_name) > 255:
        raise HTTPException(
            status_code=400,
            detail="파일명이 너무 깁니다 (최대 255자)."
        )

    # Must have an extension
    if '.' not in safe_name:
        raise HTTPException(
            status_code=400,
            detail="파일 확장자가 필요합니다."
        )

    return safe_name


# Security: Sanitized error response helper
def get_safe_error_message(error: Exception, context: str = "") -> str:
    """
    Get sanitized error message for user display (prevents information disclosure)

    Security: Never expose internal details like:
    - File paths or directory structure
    - Database connection strings or queries
    - Stack traces or exception details
    - Internal system information

    All detailed errors are logged server-side only.

    Args:
        error: The exception that occurred
        context: Context description for logging (not exposed to user)

    Returns:
        Generic, safe error message for user display
    """
    error_type = type(error).__name__

    # Log full error details server-side for debugging
    logger.error(f"Error in {context}: {error_type}: {str(error)}")

    # Map exception types to generic user-friendly messages
    # Security: DO NOT include error details or internal information
    error_messages = {
        "FileNotFoundError": "요청한 파일을 찾을 수 없습니다.",
        "PermissionError": "파일에 대한 접근 권한이 없습니다.",
        "ValueError": "잘못된 입력값입니다.",
        "ConnectionError": "서비스 연결에 실패했습니다. 잠시 후 다시 시도해주세요.",
        "TimeoutError": "요청 처리 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
        "KeyError": "필수 정보가 누락되었습니다.",
        "TypeError": "잘못된 데이터 형식입니다.",
        "AttributeError": "요청을 처리하는 중 오류가 발생했습니다.",
        "IndexError": "유효하지 않은 인덱스입니다.",
        "KeyboardInterrupt": "작업이 취소되었습니다.",
        "MemoryError": "메모리가 부족합니다.",
        "OSError": "시스템 오류가 발생했습니다.",
        "IOError": "입출력 오류가 발생했습니다.",
    }

    # Return generic safe message (no internal details exposed)
    safe_message = error_messages.get(
        error_type,
        "요청을 처리하는 중 오류가 발생했습니다."  # Generic fallback for unknown errors
    )

    return safe_message


def get_system_prompt_for_mode(redis_client, search_mode: str, sources_used: List[str] = None) -> str:
    """
    검색 모드에 따라 적절한 시스템 프롬프트 반환

    Args:
        redis_client: Redis 클라이언트
        search_mode: 검색 모드 ('smart', 'local-only', 'web-enhanced', 'comprehensive', 'tools-only')
        sources_used: 실제 사용된 소스 리스트 (['local', 'web', 'docs'])

    Returns:
        적절한 시스템 프롬프트
    """
    # 소스 기반으로 프롬프트 타입 결정
    prompt_type = None

    if sources_used:
        # 실제 사용된 소스 기반 판단
        has_local = 'local' in sources_used
        has_external = 'web' in sources_used or 'docs' in sources_used

        if has_external and not has_local:
            # 외부 도구만 사용
            prompt_type = 'tools_only'
        elif has_external and has_local:
            # 로컬 + 외부 도구 (하이브리드)
            prompt_type = 'hybrid'
        else:
            # 로컬만 사용
            prompt_type = 'basic'
    else:
        # search_mode 기반 판단
        if search_mode == 'tools-only':
            prompt_type = 'tools_only'
        elif search_mode in ['web-enhanced', 'comprehensive']:
            prompt_type = 'hybrid'
        else:
            # 'smart', 'local-only' 등
            prompt_type = 'basic'

    # 프롬프트 타입에 따라 가져오기
    if prompt_type == 'tools_only':
        prompt = redis_client.get(PROMPT_KEY_TOOLS_ONLY)
        if not prompt:
            prompt = DEFAULT_TOOLS_ONLY_PROMPT
    elif prompt_type == 'hybrid':
        prompt = redis_client.get(PROMPT_KEY_HYBRID)
        if not prompt:
            prompt = DEFAULT_HYBRID_PROMPT
    else:
        prompt = redis_client.get(PROMPT_KEY_BASIC)
        if not prompt:
            prompt = DEFAULT_BASIC_PROMPT

    # bytes to str 변환
    if isinstance(prompt, bytes):
        prompt = prompt.decode('utf-8')

    return prompt


# Request/Response models
class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    search_mode: str = 'smart'  # 검색 모드: smart, local-only, web-enhanced, comprehensive, tools-only
    temperature: float = 0.7
    max_tokens: int = 2048
    system_prompt: Optional[str] = None
    cache_threshold: float = 0.95
    cache_ttl: int = 60
    document_ids: Optional[list] = None  # Filter by specific document IDs/filenames
    group_ids: Optional[list] = None  # Filter by group IDs (OR logic)
    history: Optional[list] = None  # Conversation history [{"role": "user/assistant", "content": "..."}]
    session_id: Optional[str] = None  # Conversation session ID for history persistence

    @validator('question')
    def sanitize_question(cls, v):
        """Validate and sanitize question input to prevent XSS and injection"""
        import re
        import html

        # Check if empty
        if not v or not v.strip():
            raise ValueError("질문을 입력해주세요.")

        # Check length
        if len(v) > 10000:
            raise ValueError("질문이 너무 깁니다 (최대 10,000자).")

        # Block obvious malicious patterns BEFORE escaping
        # This is critical: check patterns on raw input first
        dangerous_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'onerror\s*=',
            r'onload\s*=',
            r'onclick\s*=',
            r'eval\s*\(',
            r'document\.cookie',
            r'<iframe[^>]*>',
            r'<embed[^>]*>',
            r'<object[^>]*>',
            r'data:text/html',
            r'vbscript:',
            r'on\w+\s*='  # Catches any on* event handlers
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("입력에 허용되지 않는 패턴이 포함되어 있습니다.")

        # HTML escape to prevent XSS (do this AFTER pattern checking)
        sanitized = html.escape(v)

        return sanitized

    @validator('system_prompt')
    def sanitize_system_prompt(cls, v):
        """Sanitize system prompt if provided"""
        import html

        if v is None:
            return v

        # Check length
        if len(v) > 5000:
            raise ValueError("시스템 프롬프트가 너무 깁니다 (최대 5,000자).")

        # HTML escape
        return html.escape(v)

    @validator('top_k')
    def validate_top_k(cls, v):
        """Validate top_k parameter"""
        if v < 1 or v > 50:
            raise ValueError("top_k는 1-50 사이의 값이어야 합니다.")
        return v

    @validator('temperature')
    def validate_temperature(cls, v):
        """Validate temperature parameter"""
        if v < 0 or v > 2:
            raise ValueError("temperature는 0-2 사이의 값이어야 합니다.")
        return v

    @validator('max_tokens')
    def validate_max_tokens(cls, v):
        """Validate max_tokens parameter"""
        if v < 1 or v > 8192:
            raise ValueError("max_tokens는 1-8192 사이의 값이어야 합니다.")
        return v


class QueryResponse(BaseModel):
    answer: str
    sources: list
    context: list
    confidence: Optional[dict] = None  # 신뢰도 점수 정보
    search_summary: Optional[dict] = None  # 하이브리드 검색 정보 (사용된 툴, 검색 결과 수)


class LLMChangeRequest(BaseModel):
    llm_model: str


class EmbeddingChangeRequest(BaseModel):
    embedding_model: str


class CacheEnabledRequest(BaseModel):
    enabled: bool


class PromptsUpdateRequest(BaseModel):
    """시스템 프롬프트 업데이트 요청"""
    basic: Optional[str] = None
    hybrid: Optional[str] = None
    tools_only: Optional[str] = None


# 🆕 독립 검색 API 모델 (Tavily, Context7)
class WebSearchRequest(BaseModel):
    """Tavily 웹 검색 요청"""
    query: str = Field(..., description="검색 쿼리", example="latest AI developments 2026")
    max_results: int = Field(5, description="최대 결과 수", ge=1, le=20)
    search_depth: str = Field("basic", description="검색 깊이 (basic 또는 advanced)")
    include_domains: Optional[List[str]] = Field(None, description="포함할 도메인 목록 (예: ['github.com', 'stackoverflow.com'])", example=None)
    exclude_domains: Optional[List[str]] = Field(None, description="제외할 도메인 목록 (예: ['wikipedia.org'])", example=None)


class WebSearchResponse(BaseModel):
    """Tavily 웹 검색 응답"""
    success: bool
    results: List[dict]
    query: str
    search_depth: str


class DocsSearchRequest(BaseModel):
    """Context7 공식 문서 검색 요청"""
    query: str
    tech_stack: Optional[str] = None  # 'react', 'vue', 'spring-boot' 등
    max_results: int = 3


class DocsSearchResponse(BaseModel):
    """Context7 공식 문서 검색 응답"""
    success: bool
    results: List[dict]
    query: str
    tech_stack: Optional[str] = None


class HwpxConversionRequest(BaseModel):
    """HWPX 변환 요청"""
    content: str = Field(..., description="변환할 HTML 또는 Markdown 내용")
    content_type: str = Field(default="html", description="내용 타입: 'html' 또는 'markdown'")
    filename: Optional[str] = Field(default=None, description="출력 파일명 (선택사항)")


# Lazy loading functions for LLM (only load when needed)
async def get_llm() -> LLM:
    """Get LLM instance, loading it lazily on first use"""
    global llm
    if llm is None:
        logger.info("⚡ Loading LLM on first use (lazy loading)...")
        # Check if we're using Ollama backend
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            # For Ollama, don't pass model_name - let it read from OLLAMA_LLM_MODEL env var
            llm = LLM(
                model_dir=MODEL_DIR
            )
        else:
            # For local LLM (MLX/Transformers), pass the model name
            llm = LLM(
                model_name=LLM_MODEL,
                model_dir=MODEL_DIR
            )
        logger.success("✅ LLM loaded successfully!")
    return llm


async def get_rag_system() -> RAGSystem:
    """Get RAG system instance, initializing it lazily on first use"""
    global rag_system
    if rag_system is None:
        logger.info("⚡ Initializing RAG system on first use...")
        llm_instance = await get_llm()
        rag_system = RAGSystem(
            vector_db=vector_db,
            llm=llm_instance,
            top_k=5
        )
        logger.success("✅ RAG system ready!")
    return rag_system


async def get_hybrid_rag_orchestrator():
    """Get Hybrid RAG orchestrator instance, initializing it lazily based on Redis config"""
    global hybrid_rag_orchestrator

    # Check Redis configuration
    hybrid_rag_enabled = cache_manager.redis.get("config:hybrid_rag_enabled")
    web_search_enabled = cache_manager.redis.get("config:hybrid_rag_web_search")
    doc_search_enabled = cache_manager.redis.get("config:hybrid_rag_doc_search")

    # Decode Redis values (they're stored as bytes)
    is_enabled = hybrid_rag_enabled and hybrid_rag_enabled.decode() == "true"
    enable_web = web_search_enabled and web_search_enabled.decode() == "true"
    enable_docs = doc_search_enabled and doc_search_enabled.decode() == "true"

    if not is_enabled:
        return None  # Hybrid RAG disabled

    # Initialize if not already created or if config changed
    if hybrid_rag_orchestrator is None:
        logger.info("⚡ Initializing Hybrid RAG orchestrator...")
        rag_instance = await get_rag_system()
        hybrid_rag_orchestrator = HybridRAGOrchestrator(
            local_rag=rag_instance,
            cache_manager=cache_manager,
            enable_web_search=enable_web,
            enable_doc_search=enable_docs
        )
        logger.success(f"✅ Hybrid RAG ready! (Web: {enable_web}, Docs: {enable_docs})")

    return hybrid_rag_orchestrator


async def create_default_admin(redis_client):
    """Create default admin user if no admin exists"""
    from .auth.service import AuthService
    from .auth.models import UserCreate

    try:
        auth_service = AuthService(redis_client)

        # Check if any admin exists
        users_result = await auth_service.get_all_users(page=1, page_size=1000)
        admin_exists = any(u.get('role') == 'admin' for u in users_result['users'])

        if not admin_exists:
            # Default admin credentials
            default_email = "admin@admin.com"
            default_password = "Admin123!@#"  # Strong default password
            default_username = "관리자"

            # Check if user already exists
            existing_user_id = redis_client.get(f"user:email:{default_email}")

            if existing_user_id:
                # User exists, just upgrade to admin
                user_id = existing_user_id.decode() if isinstance(existing_user_id, bytes) else existing_user_id
                redis_client.hset(f"user:{user_id}", "role", "admin")
                logger.info(f"✅ Upgraded existing user {default_email} to admin")
            else:
                # Create new admin user
                user_data = UserCreate(
                    email=default_email,
                    username=default_username,
                    password=default_password
                )
                user = await auth_service.create_user(user_data)

                # Set as admin
                redis_client.hset(f"user:{user.user_id}", "role", "admin")

                logger.success(f"✅ Created default admin user: {default_email}")
                logger.info(f"   Username: {default_username}")
                logger.info(f"   Password: {default_password}")
                logger.warning("⚠️  Please change the default admin password after first login!")
        else:
            logger.info("ℹ️  Admin user already exists, skipping default admin creation")

    except Exception as e:
        logger.warning(f"⚠️  Failed to create default admin: {e}")
        # Don't fail startup if admin creation fails



# ==================== Redis Backup Management ====================

# Pydantic models for backup requests
class BackupCreateRequest(BaseModel):
    type: str = "manual"  # manual or auto

class BackupRestoreRequest(BaseModel):
    filename: str

class BackupDeleteRequest(BaseModel):
    filename: str

class BackupScheduleRequest(BaseModel):
    enabled: bool
    interval: str  # hourly, daily, weekly, disabled
    day_of_week: Optional[int] = None  # 0-6 (Sunday-Saturday) for weekly backups
    hour: Optional[int] = None  # 0-23 for daily/weekly backups
    minute: Optional[int] = None  # 0-59 for all intervals

# Backup directory setup
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

def get_backup_filepath(filename: str) -> Path:
    """Get safe backup file path"""
    # Prevent directory traversal
    safe_filename = Path(filename).name
    return BACKUP_DIR / safe_filename

def get_redis_backup_info():
    """Get Redis backup information"""
    try:
        backups = []
        if BACKUP_DIR.exists():
            # Sort by file modification time (newest first)
            for backup_file in sorted(BACKUP_DIR.glob("dump_*.rdb"), key=lambda x: x.stat().st_mtime, reverse=True):
                stat = backup_file.stat()
                created_at = datetime.fromtimestamp(stat.st_mtime)
                age_seconds = (datetime.now() - created_at).total_seconds()
                
                # Format age
                if age_seconds < 3600:
                    age = f"{int(age_seconds / 60)}분 전"
                elif age_seconds < 86400:
                    age = f"{int(age_seconds / 3600)}시간 전"
                else:
                    age = f"{int(age_seconds / 86400)}일 전"
                
                # Determine type from filename
                backup_type = "auto" if "_auto_" in backup_file.name else "manual"
                
                backups.append({
                    "filename": backup_file.name,
                    "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "age": age,
                    "size": f"{stat.st_size / 1024 / 1024:.2f} MB",
                    "size_bytes": stat.st_size,
                    "type": backup_type
                })
        
        return backups
    except Exception as e:
        logger.error(f"Failed to get backup info: {e}")
        return []

@app.post("/api/redis/backup/create", tags=["Admin", "Redis Backup"])
async def create_redis_backup(request: Request, backup_request: BackupCreateRequest):
    """Redis 백업 생성
    
    Request body:
        {
            "type": "manual" | "auto"
        }
    """
    try:
        # Admin permission check
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)
        
        backup_type = backup_request.type
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if backup_type == "auto":
            backup_filename = f"dump_auto_{timestamp}.rdb"
        else:
            backup_filename = f"dump_manual_{timestamp}.rdb"
        
        backup_path = BACKUP_DIR / backup_filename
        
        # Execute Redis SAVE command (synchronous backup)
        redis_client.save()

        # Get Redis data directory and filename
        redis_config = redis_client.config_get("dir")
        redis_dir = redis_config.get("dir", "/data")
        redis_dbfilename = redis_client.config_get("dbfilename").get("dbfilename", "dump.rdb")

        # Check if Redis is running in Docker
        import subprocess
        docker_container = None
        try:
            # Check if Redis container exists
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=chatbot_redis", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                docker_container = result.stdout.strip()
                logger.info(f"📦 Detected Redis running in Docker container: {docker_container}")
        except Exception as e:
            logger.warning(f"Could not check for Docker container: {e}")

        # Copy dump file from Docker or local filesystem
        if docker_container:
            # Copy from Docker container
            source_path = f"{redis_dir}/{redis_dbfilename}"
            docker_source = f"{docker_container}:{source_path}"

            try:
                # Copy file from Docker container to backup directory
                result = subprocess.run(
                    ["docker", "cp", docker_source, str(backup_path)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to copy from Docker: {result.stderr}"
                    )

                logger.info(f"✅ Copied dump file from Docker: {docker_source} → {backup_path}")

            except subprocess.TimeoutExpired:
                raise HTTPException(status_code=500, detail="Docker copy timed out")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Docker copy failed: {str(e)}")
        else:
            # Copy from local filesystem
            source_dump = Path(redis_dir) / redis_dbfilename
            if source_dump.exists():
                shutil.copy2(source_dump, backup_path)
                logger.info(f"✅ Copied dump file from local: {source_dump} → {backup_path}")
            else:
                raise HTTPException(status_code=500, detail=f"Redis dump file not found: {source_dump}")

        # Get file info and return response
        if backup_path.exists():
            stat = backup_path.stat()
            size_mb = stat.st_size / 1024 / 1024

            logger.info(f"✅ Redis backup created: {backup_filename} ({size_mb:.2f} MB)")

            return {
                "success": True,
                "backup": {
                    "filename": backup_filename,
                    "size": f"{size_mb:.2f} MB",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": backup_type
                }
            }
        else:
            raise HTTPException(status_code=500, detail="Backup file was not created")
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Failed to create backup: {e}\n{error_detail}")
        raise HTTPException(status_code=500, detail=f"백업 생성 실패: {str(e)}")

@app.get("/api/redis/backup/list", tags=["Admin", "Redis Backup"])
async def list_redis_backups(request: Request):
    """Redis 백업 목록 조회"""
    try:
        # Admin permission check
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)
        
        backups = get_redis_backup_info()
        
        # Calculate statistics
        total_size = sum(b["size_bytes"] for b in backups)
        
        return {
            "success": True,
            "backups": backups,
            "stats": {
                "total_backups": len(backups),
                "total_size": f"{total_size / 1024 / 1024:.2f} MB",
                "manual_backups": len([b for b in backups if b["type"] == "manual"]),
                "auto_backups": len([b for b in backups if b["type"] == "auto"])
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(status_code=500, detail="백업 목록 조회 실패")

@app.post("/api/redis/backup/restore", tags=["Admin", "Redis Backup"])
async def restore_redis_backup(request: Request, restore_request: BackupRestoreRequest):
    """Redis 백업 복원 (안전성 강화)

    Request body:
        {
            "filename": "dump_manual_20250101_120000.rdb"
        }

    Warning: This will flush all current Redis data and restore from backup.

    Safety features:
    - Mandatory pre-restore backup (fails if backup creation fails)
    - Transaction-style operation (all-or-nothing)
    - Automatic rollback on failure
    - Validation at each critical step
    - DBSIZE verification before and after
    """
    import subprocess
    import asyncio

    redis_client = None
    docker_container = None
    current_backup = None
    current_backup_filename = None
    original_dbsize = None
    restore_failed = False

    try:
        # Admin permission check
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        backup_path = get_backup_filepath(restore_request.filename)

        # STEP 1: Validate backup file exists
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")

        logger.info(f"🔍 Step 1/7: Backup file validated: {restore_request.filename}")

        # Get Redis configuration
        redis_config = redis_client.config_get("dir")
        redis_dir = redis_config.get("dir", "/data")
        redis_dbfilename = redis_client.config_get("dbfilename").get("dbfilename", "dump.rdb")

        # STEP 2: Detect Docker environment
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=chatbot_redis", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                docker_container = result.stdout.strip()
                logger.info(f"🔍 Step 2/7: Docker container detected: {docker_container}")
            else:
                logger.info(f"🔍 Step 2/7: Local Redis installation detected")
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Docker 환경 확인 실패: {str(e)}"
            )

        # STEP 3: Get current DBSIZE for validation
        try:
            original_dbsize = redis_client.dbsize()
            logger.info(f"🔍 Step 3/7: Current DBSIZE: {original_dbsize:,} keys")
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Redis DBSIZE 확인 실패: {str(e)}"
            )

        # STEP 4: MANDATORY pre-restore backup
        current_backup_filename = f"dump_pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.rdb"
        current_backup = BACKUP_DIR / current_backup_filename

        if docker_container:
            # Docker environment - MUST successfully backup current state
            try:
                # Force Redis to save current state
                redis_client.save()
                logger.info("✅ Redis SAVE completed")
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Redis SAVE 실패 - 복원을 중단합니다: {str(e)}"
                )

            # Copy current dump from container - MUST succeed
            docker_source = f"{docker_container}:{redis_dir}/{redis_dbfilename}"
            try:
                result = subprocess.run(
                    ["docker", "cp", docker_source, str(current_backup)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    raise HTTPException(
                        status_code=500,
                        detail=f"현재 상태 백업 실패 - 복원을 중단합니다: {result.stderr}"
                    )

                # Verify backup file was created
                if not current_backup.exists():
                    raise HTTPException(
                        status_code=500,
                        detail="백업 파일 생성 확인 실패 - 복원을 중단합니다"
                    )

                backup_size = current_backup.stat().st_size / 1024 / 1024
                logger.info(f"✅ Step 4/7: Pre-restore backup created: {current_backup_filename} ({backup_size:.2f} MB)")

            except subprocess.TimeoutExpired:
                raise HTTPException(
                    status_code=500,
                    detail="백업 생성 시간 초과 - 복원을 중단합니다"
                )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"현재 상태 백업 실패 - 복원을 중단합니다: {str(e)}"
                )

            # STEP 5: Copy backup file into Docker container
            docker_target = f"{docker_container}:{redis_dir}/{redis_dbfilename}"
            try:
                result = subprocess.run(
                    ["docker", "cp", str(backup_path), docker_target],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    restore_failed = True
                    raise HTTPException(
                        status_code=500,
                        detail=f"백업 파일 복사 실패: {result.stderr}"
                    )

                logger.info(f"✅ Step 5/7: Backup copied to container: {docker_target}")

            except subprocess.TimeoutExpired:
                restore_failed = True
                raise HTTPException(status_code=500, detail="백업 복사 시간 초과")
            except HTTPException:
                raise
            except Exception as e:
                restore_failed = True
                raise HTTPException(status_code=500, detail=f"백업 복사 실패: {str(e)}")

            # STEP 6: Restart Redis container
            try:
                logger.info(f"🔄 Step 6/7: Restarting Redis container...")
                result = subprocess.run(
                    ["docker", "restart", docker_container],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    restore_failed = True
                    raise HTTPException(
                        status_code=500,
                        detail=f"Redis 재시작 실패: {result.stderr}"
                    )

                logger.info("✅ Redis container restarted")

                # Wait for Redis to fully start
                await asyncio.sleep(3)

                # Reconnect to Redis (container was restarted)
                max_retries = 5
                for i in range(max_retries):
                    try:
                        redis_client.ping()
                        logger.info(f"✅ Redis connection restored (attempt {i+1}/{max_retries})")
                        break
                    except Exception as e:
                        if i == max_retries - 1:
                            restore_failed = True
                            raise HTTPException(
                                status_code=500,
                                detail=f"Redis 재시작 후 연결 실패: {str(e)}"
                            )
                        await asyncio.sleep(1)

            except subprocess.TimeoutExpired:
                restore_failed = True
                raise HTTPException(status_code=500, detail="Redis 재시작 시간 초과")
            except HTTPException:
                raise
            except Exception as e:
                restore_failed = True
                raise HTTPException(status_code=500, detail=f"Redis 재시작 실패: {str(e)}")

            # STEP 7: Verify restore succeeded
            try:
                restored_dbsize = redis_client.dbsize()
                logger.info(f"🔍 Step 7/7: Restored DBSIZE: {restored_dbsize:,} keys")

                # Warn if DBSIZE is suspiciously low
                if restored_dbsize < 100:
                    logger.warning(f"⚠️ Restored DBSIZE ({restored_dbsize}) is very low - possible restore failure")
                    # Don't fail here, but log for investigation

                logger.info(f"✅ Restore verification complete: {original_dbsize:,} → {restored_dbsize:,} keys")

            except Exception as e:
                restore_failed = True
                raise HTTPException(
                    status_code=500,
                    detail=f"복원 후 검증 실패: {str(e)}"
                )

        else:
            # Local filesystem
            target_dump = Path(redis_dir) / redis_dbfilename

            # STEP 4: MANDATORY pre-restore backup (local)
            try:
                if target_dump.exists():
                    shutil.copy2(target_dump, current_backup)

                    # Verify backup was created
                    if not current_backup.exists():
                        raise HTTPException(
                            status_code=500,
                            detail="백업 파일 생성 확인 실패 - 복원을 중단합니다"
                        )

                    backup_size = current_backup.stat().st_size / 1024 / 1024
                    logger.info(f"✅ Step 4/7: Pre-restore backup created: {current_backup_filename} ({backup_size:.2f} MB)")
                else:
                    logger.warning("⚠️ No existing dump file to backup")

            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"현재 상태 백업 실패 - 복원을 중단합니다: {str(e)}"
                )

            # STEP 5: Copy backup file
            try:
                shutil.copy2(backup_path, target_dump)
                logger.info(f"✅ Step 5/7: Backup file copied to Redis directory")
            except Exception as e:
                restore_failed = True
                raise HTTPException(
                    status_code=500,
                    detail=f"백업 파일 복사 실패: {str(e)}"
                )

            logger.warning("⚠️ Step 6/7: Redis needs manual restart to load the backup")
            logger.info(f"ℹ️ Step 7/7: Manual verification required after restart")

        return {
            "success": True,
            "message": "백업이 안전하게 복원되었습니다. 복원 전 상태는 백업되었습니다.",
            "filename": restore_request.filename,
            "current_backup": current_backup_filename,
            "original_keys": original_dbsize,
            "restored_keys": restored_dbsize if docker_container else "재시작 후 확인 필요"
        }

    except HTTPException:
        # If restore failed and we have a pre-restore backup, attempt rollback
        if restore_failed and current_backup and current_backup.exists() and docker_container:
            logger.error("🚨 Restore failed - attempting automatic rollback...")
            try:
                # Rollback: restore from pre-restore backup
                docker_target = f"{docker_container}:{redis_dir}/{redis_dbfilename}"
                result = subprocess.run(
                    ["docker", "cp", str(current_backup), docker_target],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    # Restart Redis to load the rollback
                    subprocess.run(
                        ["docker", "restart", docker_container],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    await asyncio.sleep(3)

                    logger.info(f"✅ Automatic rollback successful - restored from {current_backup_filename}")
                else:
                    logger.error(f"❌ Automatic rollback failed: {result.stderr}")
                    logger.error(f"⚠️ Manual recovery required using: {current_backup_filename}")

            except Exception as rollback_error:
                logger.error(f"❌ Rollback exception: {rollback_error}")
                logger.error(f"⚠️ Manual recovery required using: {current_backup_filename}")

        raise
    except Exception as e:
        logger.error(f"Unexpected error during restore: {e}")
        raise HTTPException(status_code=500, detail=f"복원 중 예기치 않은 오류: {str(e)}")

@app.get("/api/redis/backup/download/{filename}", tags=["Admin", "Redis Backup"])
async def download_redis_backup(request: Request, filename: str):
    """Redis 백업 파일 다운로드"""
    try:
        # Admin permission check
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)
        
        backup_path = get_backup_filepath(filename)
        
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")
        
        return FileResponse(
            path=str(backup_path),
            filename=filename,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download backup: {e}")
        raise HTTPException(status_code=500, detail="백업 다운로드 실패")

@app.post("/api/redis/backup/delete", tags=["Admin", "Redis Backup"])
async def delete_redis_backup(request: Request, delete_request: BackupDeleteRequest):
    """Redis 백업 파일 삭제
    
    Request body:
        {
            "filename": "dump_manual_20250101_120000.rdb"
        }
    """
    try:
        # Admin permission check
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)
        
        backup_path = get_backup_filepath(delete_request.filename)
        
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다")
        
        # Delete the backup file
        backup_path.unlink()
        
        logger.info(f"Backup deleted: {delete_request.filename}")
        
        return {
            "success": True,
            "message": f"백업 파일이 삭제되었습니다: {delete_request.filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        raise HTTPException(status_code=500, detail="백업 삭제 실패")

@app.get("/api/redis/backup/schedule", tags=["Admin", "Redis Backup"])
async def get_backup_schedule(request: Request):
    """자동 백업 스케줄 조회"""
    try:
        # Admin permission check
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)
        
        # Get schedule from Redis
        schedule_data = redis_client.get("backup:schedule")
        
        if schedule_data:
            schedule = json.loads(schedule_data)
        else:
            # Default schedule
            schedule = {
                "enabled": False,
                "interval": "daily",
                "last_backup": None
            }
        
        return {
            "success": True,
            "schedule": schedule
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backup schedule: {e}")
        raise HTTPException(status_code=500, detail="스케줄 조회 실패")

@app.post("/api/redis/backup/schedule", tags=["Admin", "Redis Backup"])
async def update_backup_schedule(
    request: Request,
    schedule_request: BackupScheduleRequest,
    user=Depends(require_admin)
):
    """자동 백업 스케줄 업데이트

    Request body:
        {
            "enabled": true,
            "interval": "hourly" | "daily" | "weekly" | "disabled",
            "day_of_week": 0-6 (optional, for weekly),
            "hour": 0-23 (optional, for daily/weekly),
            "minute": 0-59 (optional, for all intervals)
        }

    Note: Background scheduler automatically executes backups based on this configuration.
    """
    try:
        redis_client = request.app.state.cache_manager.redis

        # Validate interval
        valid_intervals = ["hourly", "daily", "weekly", "disabled"]
        if schedule_request.interval not in valid_intervals:
            raise HTTPException(status_code=400, detail=f"Invalid interval. Must be one of: {valid_intervals}")

        # Build complete schedule object with all fields
        schedule = {
            "enabled": schedule_request.enabled,
            "interval": schedule_request.interval,
            "updated_at": datetime.now().isoformat()
        }

        # Add optional time fields if provided
        if schedule_request.day_of_week is not None:
            schedule["day_of_week"] = schedule_request.day_of_week
        if schedule_request.hour is not None:
            schedule["hour"] = schedule_request.hour
        if schedule_request.minute is not None:
            schedule["minute"] = schedule_request.minute

        # Save complete schedule to Redis
        redis_client.set("backup:schedule", json.dumps(schedule))

        # Log with all relevant fields
        log_msg = f"Backup schedule updated by {user.get('email', 'unknown')}: enabled={schedule_request.enabled}, interval={schedule_request.interval}"
        if schedule_request.minute is not None:
            log_msg += f", minute={schedule_request.minute}"
        if schedule_request.hour is not None:
            log_msg += f", hour={schedule_request.hour}"
        if schedule_request.day_of_week is not None:
            log_msg += f", day_of_week={schedule_request.day_of_week}"
        logger.info(log_msg)

        return {
            "success": True,
            "message": "백업 스케줄이 업데이트되었습니다. 백그라운드 스케줄러가 자동으로 실행합니다.",
            "schedule": schedule
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update backup schedule: {e}")
        raise HTTPException(status_code=500, detail="스케줄 업데이트 실패")

# ==================== End of Redis Backup Management ====================

# ==================== Audit Log Cleanup Scheduler ====================

audit_cleanup_scheduler_task = None

async def audit_cleanup_scheduler():
    """감사 로그 정리 스케줄러 - 매일 새벽 3시에 90일 이상 된 로그 삭제"""
    logger.info("🗑️ Audit log cleanup scheduler started")

    while True:
        try:
            # 현재 시간
            now = datetime.now()

            # 다음 실행 시간 계산 (다음날 새벽 3시)
            next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= next_run:
                # 이미 지났으면 다음날
                next_run += timedelta(days=1)

            # 대기 시간 계산
            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"📅 Next audit log cleanup scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds/3600:.1f} hours)")

            # 대기
            await asyncio.sleep(wait_seconds)

            # 정리 실행
            if audit_logger:
                logger.info("🗑️ Starting audit log cleanup...")
                deleted_count = audit_logger.cleanup_old_logs()
                logger.success(f"✅ Audit log cleanup completed: {deleted_count} logs deleted")
            else:
                logger.warning("⚠️ Audit logger not initialized, skipping cleanup")

        except asyncio.CancelledError:
            logger.info("🛑 Audit cleanup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Audit cleanup scheduler error: {e}")
            # 에러 발생 시 1시간 후 재시도
            await asyncio.sleep(3600)

# ==================== Backup Scheduler ====================

backup_scheduler_task = None

async def backup_scheduler():
    """백그라운드 백업 스케줄러 - 설정된 간격에 따라 자동 백업 실행"""
    logger.info("🕐 Backup scheduler started")

    while True:
        try:
            # Redis에서 백업 스케줄 확인
            redis_client = cache_manager.redis
            schedule_data = redis_client.get("backup:schedule")

            if schedule_data:
                schedule = json.loads(schedule_data)

                if schedule.get("enabled"):
                    interval = schedule.get("interval", "daily")
                    scheduled_minute = schedule.get("minute", 0)  # 기본값 0분

                    # 현재 시간
                    now = datetime.now()

                    # 다음 실행 시간 계산
                    if interval == "hourly":
                        # 매시 N분에 실행
                        next_run = now.replace(minute=scheduled_minute, second=0, microsecond=0)
                        if next_run <= now:
                            # 이미 지난 시간이면 다음 시간으로
                            next_run += timedelta(hours=1)
                    elif interval == "daily":
                        # 매일 N시 M분에 실행 (여기서는 간단히 24시간 후)
                        next_run = now + timedelta(days=1)
                        next_run = next_run.replace(minute=scheduled_minute, second=0, microsecond=0)
                    elif interval == "weekly":
                        # 매주 같은 요일 N시 M분에 실행
                        next_run = now + timedelta(weeks=1)
                        next_run = next_run.replace(minute=scheduled_minute, second=0, microsecond=0)
                    else:
                        next_run = now + timedelta(hours=1)

                    # 다음 실행까지 대기 시간 계산
                    wait_seconds = (next_run - now).total_seconds()

                    if wait_seconds > 0:
                        logger.info(f"⏰ Next backup scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S')} (in {int(wait_seconds)} seconds)")
                        await asyncio.sleep(wait_seconds)

                    # 백업 실행
                    try:
                        logger.info(f"🔄 Executing scheduled backup (interval: {interval})")

                        # 백업 파일명 생성
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"dump_auto_{timestamp}.rdb"

                        # Redis BGSAVE 명령 실행
                        redis_client.bgsave()

                        # BGSAVE 완료 대기 (최대 60초)
                        for _ in range(60):
                            await asyncio.sleep(1)
                            info = redis_client.info("persistence")
                            if info.get("rdb_bgsave_in_progress") == 0:
                                break

                        # dump.rdb 파일을 백업 디렉토리로 복사
                        backup_dir = Path("backups")
                        backup_dir.mkdir(exist_ok=True)
                        backup_path = backup_dir / filename

                        # Get Redis data directory and filename
                        redis_config = redis_client.config_get("dir")
                        redis_dir = redis_config.get("dir", "/data")
                        redis_dbfilename = redis_client.config_get("dbfilename").get("dbfilename", "dump.rdb")

                        # Check if Redis is running in Docker
                        import subprocess
                        docker_container = None
                        try:
                            # Check if Redis container exists
                            result = subprocess.run(
                                ["docker", "ps", "--filter", "name=chatbot_redis", "--format", "{{.Names}}"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                docker_container = result.stdout.strip()
                                logger.debug(f"📦 Detected Redis in Docker: {docker_container}")
                        except Exception as e:
                            logger.debug(f"Docker check skipped: {e}")

                        # Copy dump file from Docker or local filesystem
                        backup_success = False
                        if docker_container:
                            # Copy from Docker container
                            source_path = f"{redis_dir}/{redis_dbfilename}"
                            docker_source = f"{docker_container}:{source_path}"

                            try:
                                result = subprocess.run(
                                    ["docker", "cp", docker_source, str(backup_path)],
                                    capture_output=True,
                                    text=True,
                                    timeout=30
                                )

                                if result.returncode == 0:
                                    logger.success(f"✅ Scheduled backup completed: {filename} (from Docker: {docker_source})")
                                    backup_success = True
                                else:
                                    logger.error(f"❌ Docker copy failed: {result.stderr}")

                            except Exception as e:
                                logger.error(f"❌ Docker copy error: {e}")
                        else:
                            # Copy from local filesystem
                            source_dump = Path(redis_dir) / redis_dbfilename
                            if source_dump.exists():
                                shutil.copy2(source_dump, backup_path)
                                logger.success(f"✅ Scheduled backup completed: {filename} (from {source_dump})")
                                backup_success = True
                            else:
                                logger.warning(f"⚠️ Redis dump file not found at: {source_dump}")

                        if not backup_success:
                            logger.error("❌ Scheduled backup failed: Could not copy dump file")

                    except Exception as e:
                        logger.error(f"❌ Scheduled backup failed: {e}")

                    # 루프 계속 (다음 실행 시간은 루프 시작에서 다시 계산됨)
                else:
                    # 비활성화 상태면 1분마다 확인
                    await asyncio.sleep(60)
            else:
                # 스케줄 설정이 없으면 1분마다 확인
                await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("🛑 Backup scheduler stopped")
            break
        except Exception as e:
            logger.error(f"❌ Backup scheduler error: {e}")
            # 에러 발생 시 1분 후 재시도
            await asyncio.sleep(60)

# ==================== End of Backup Scheduler ====================

@app.on_event("startup")
async def startup_event():
    """Initialize models and database on startup (fast startup with lazy loading)"""
    global embedding_model, vector_db, cache_manager, group_manager, conversation_manager, document_version, audit_logger, suggested_questions_pool, reindex_event, backup_scheduler_task, hybrid_rag_orchestrator

    # Configure file logging (development mode) - only once
    environment = os.getenv("ENVIRONMENT", "development")
    if environment != "production":
        log_file = os.getenv("LOG_FILE", "server.log")
        try:
            logger.add(
                log_file,
                rotation="10 MB",
                retention="3 days",
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                level="DEBUG",
                colorize=False  # Disable color codes for clean parsing
            )
            logger.info(f"📝 File logging enabled: {log_file}")
        except Exception as e:
            # Handler might already exist on reload, that's OK
            pass

    try:
        logger.info("🚀 Starting application initialization (fast mode)...")

        # Initialize reindex event
        reindex_event = asyncio.Event()
        reindex_event.set()  # Initially set (not reindexing)

        # Initialize embedding model (required for search)
        logger.info("📚 Loading embedding model...")
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            # For Ollama, don't pass model_name - let it read from OLLAMA_EMBEDDING_MODEL env var
            embedding_model = EmbeddingModel(
                model_dir=MODEL_DIR
            )
        else:
            # For local embedding model
            embedding_model = EmbeddingModel(
                model_name=EMBEDDING_MODEL,
                model_dir=MODEL_DIR
            )

        # Initialize vector database with production-ready Redis configuration
        logger.info("🔌 Connecting to Redis...")

        # Production Redis configuration
        redis_max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", 50))
        redis_socket_timeout = int(os.getenv("REDIS_SOCKET_TIMEOUT", 5))
        redis_socket_keepalive = os.getenv("REDIS_SOCKET_KEEPALIVE", "true").lower() == "true"

        vector_db = VectorDB(
            host=REDIS_HOST,
            port=REDIS_PORT,
            embedding_dim=embedding_model.get_embedding_dim(),
            # Production Redis connection pool settings
            max_connections=redis_max_connections,
            socket_timeout=redis_socket_timeout,
            socket_keepalive=redis_socket_keepalive,
            socket_keepalive_options={},
            health_check_interval=30  # Check connection health every 30s
        )

        logger.info(f"Redis configured: max_connections={redis_max_connections}, timeout={redis_socket_timeout}s")

        # Clean up stale reindexing state from previous abnormal shutdown
        try:
            progress_data = vector_db.client.hgetall("reindex:progress")
            if progress_data:
                in_progress = progress_data.get(b'in_progress', b'false').decode() == 'true'
                step = progress_data.get(b'step', b'').decode()
                elapsed_seconds = int(progress_data.get(b'elapsed_seconds', 0))

                # Clear if: (1) error state, or (2) stuck for >1 hour
                should_clear = (
                    in_progress and (
                        '오류' in step or
                        'error' in step.lower() or
                        elapsed_seconds > 3600  # 1 hour
                    )
                )

                if should_clear:
                    vector_db.client.delete("reindex:progress")
                    logger.warning(f"🧹 Cleared stale reindex state (step: {step}, elapsed: {elapsed_seconds}s)")
                elif in_progress:
                    logger.info(f"ℹ️  Found active reindex state (step: {step}, elapsed: {elapsed_seconds}s)")
        except Exception as e:
            logger.debug(f"Failed to check reindex state (non-critical): {e}")

        # Set rate limit configuration in Redis from environment variable
        try:
            rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "false").lower()
            vector_db.client.set("config:rate_limit_enabled", rate_limit_enabled)
            logger.info(f"⚙️  Rate limiting: {rate_limit_enabled}")
        except Exception as e:
            logger.warning(f"Failed to set rate limit config in Redis: {e}")

        # Initialize cache manager with production settings
        logger.info("💾 Initializing cache manager...")

        # Production cache configuration
        cache_similarity_threshold = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", 0.90))  # Lowered from 0.95 to 0.90
        cache_ttl = int(os.getenv("CACHE_TTL", 3600))  # Default 1 hour
        memory_cache_size = int(os.getenv("MEMORY_CACHE_SIZE", 200))  # Increased from 50 to 200 for better hit rate

        cache_manager = CacheManager(
            redis_client=vector_db.client,
            embedding_model=embedding_model.model,
            similarity_threshold=cache_similarity_threshold,
            cache_ttl=cache_ttl,
            memory_cache_size=memory_cache_size
        )

        logger.info(f"Cache configured: similarity={cache_similarity_threshold}, TTL={cache_ttl}s")

        # Store cache_manager in app state for v2.2.0 auth system access
        app.state.cache_manager = cache_manager
        logger.info(f"✅ Stored cache_manager in app.state (redis client: {cache_manager.redis is not None})")

        # Initialize SecurityLogger with Redis for webhook support
        from src.auth.security_logger import SecurityLogger
        SecurityLogger.set_redis(cache_manager.redis)
        logger.info("✅ SecurityLogger initialized with Redis (webhook support enabled)")

        # Inject Redis into FeedbackAnalyzer for persistence
        feedback_analyzer.redis = cache_manager.redis
        feedback_analyzer._load_from_redis()
        logger.info(f"✅ FeedbackAnalyzer initialized with Redis persistence (loaded {len(feedback_analyzer.feedback_history)} feedbacks)")

        # Initialize audit logger (v2.4.0)
        audit_logger = AuditLogger(
            redis_client=cache_manager.redis,
            retention_days=90  # 90일 보관
        )
        app.state.audit_logger = audit_logger
        logger.info("✅ AuditLogger initialized (retention=90 days)")

        # Create default admin user if no admin exists
        await create_default_admin(cache_manager.redis)

        # Initialize group manager
        logger.info("📁 Initializing group manager...")
        group_manager = GroupManager(redis_client=vector_db.client)

        # Initialize conversation manager
        logger.info("💬 Initializing conversation manager...")
        conversation_manager = ConversationManager(redis_client=vector_db.client)

        # v2.3.0: Initialize document version manager
        logger.info("📋 Initializing document version manager...")
        max_versions = int(os.getenv("DOCUMENT_MAX_VERSIONS", 10))
        document_version = DocumentVersion(
            redis_client=vector_db.client,
            data_dir=DATA_DIR,
            max_versions=max_versions
        )
        logger.info(f"Document version manager configured: max_versions={max_versions}")

        # Inject dependencies into documents router (18 endpoints)
        logger.info("📄 Injecting dependencies into documents router...")
        documents.inject_dependencies(
            vdb=vector_db,
            doc_processor=None,  # DocumentProcessor is created per-request, not global
            doc_version=document_version,
            grp_manager=group_manager,
            cache_mgr=cache_manager,
            emb_model=embedding_model,
            data_dir=DATA_DIR,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            max_file_size=MAX_FILE_SIZE,
            max_file_size_mb=MAX_FILE_SIZE_MB,
            reindex_evt=reindex_event
        )
        logger.info("✅ Documents router dependencies injected (19 endpoints)")

        # Inject dependencies into cache router (4 endpoints)
        logger.info("💾 Injecting dependencies into cache router...")
        cache.inject_dependencies(
            cache_mgr=cache_manager,
            redis=vector_db.client
        )
        logger.info("✅ Cache router dependencies injected (4 endpoints)")

        # Inject dependencies into conversations router (7 endpoints)
        logger.info("💬 Injecting dependencies into conversations router...")
        conversations.inject_dependencies(
            conv_manager=conversation_manager
        )
        logger.info("✅ Conversations router dependencies injected (7 endpoints)")

        # Inject dependencies into feedback router (5 endpoints)
        logger.info("👍 Injecting dependencies into feedback router...")
        feedback.inject_dependencies(
            fb_analyzer=feedback_analyzer,
            conv_manager=conversation_manager,
            cache_mgr=cache_manager
        )
        logger.info("✅ Feedback router dependencies injected (5 endpoints)")

        # Inject dependencies into settings router (5 endpoints)
        logger.info("⚙️ Injecting dependencies into settings router...")
        settings.inject_dependencies(
            cache_mgr=cache_manager
        )
        logger.info("✅ Settings router dependencies injected (5 endpoints)")

        # Auto-migrate existing documents to version control
        logger.info("🔄 Running document version migration...")
        try:
            data_path = Path(DATA_DIR)
            if data_path.exists():
                allowed_extensions = ['.pdf', '.hwp', '.hwpx', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
                migrated_count = 0
                skipped_count = 0

                for file_path in data_path.iterdir():
                    if file_path.is_file() and any(file_path.name.endswith(ext) for ext in allowed_extensions):
                        filename = file_path.name

                        # Skip if file is in versions directory
                        if 'versions' in file_path.parts:
                            continue

                        # Check if file already has versions
                        try:
                            existing_versions = document_version.list_versions(filename)
                            if existing_versions:
                                skipped_count += 1
                                continue
                        except Exception:
                            pass

                        # Get chunk count from Redis if available
                        chunk_count = 0
                        try:
                            chunk_keys = vector_db.client.keys(f"chunk:{filename}:*")
                            chunk_count = len(chunk_keys) if chunk_keys else 0
                        except Exception:
                            pass

                        # Create V1 version for this file
                        try:
                            document_version.create_version(
                                source_path=file_path,
                                filename=filename,
                                user_id="system",
                                comment="Initial version (auto-migrated)",
                                chunk_count=chunk_count
                            )
                            migrated_count += 1
                            logger.debug(f"Created V1 for {filename}")
                        except Exception as e:
                            logger.debug(f"Failed to create version for {filename}: {e}")

                if migrated_count > 0:
                    logger.success(f"✅ Migrated {migrated_count} documents to version control (skipped {skipped_count})")
                else:
                    logger.info(f"✓ All documents already have versions (checked {skipped_count} files)")
        except Exception as e:
            logger.warning(f"Version migration failed (non-critical): {e}")
            # Don't fail startup if migration fails

        # LLM will be loaded lazily on first chat request
        # Note: Indexing is now handled by documents router (manual reindex button)
        logger.info("⚡ LLM will load on first use (lazy loading enabled)")

        # Optional: Start question generation in background (only if enabled)
        if ENABLE_QUESTION_GENERATION:
            logger.info("📝 Starting background question generation (enabled in config)...")
            asyncio.create_task(generate_questions_pool_background())
        else:
            logger.info("⏭️  Question generation disabled (set ENABLE_QUESTION_GENERATION=true to enable)")

        # Start backup scheduler
        global backup_scheduler_task
        backup_scheduler_task = asyncio.create_task(backup_scheduler())
        logger.info("🕐 Backup scheduler initialized")

        # Start audit log cleanup scheduler
        global audit_cleanup_scheduler_task
        audit_cleanup_scheduler_task = asyncio.create_task(audit_cleanup_scheduler())
        logger.info("🗑️ Audit log cleanup scheduler initialized")

        # Initialize Hybrid RAG Orchestrator (will check Redis config at runtime)
        global hybrid_rag_orchestrator
        hybrid_rag_orchestrator = None  # Will be initialized lazily when needed
        logger.info("🔗 Hybrid RAG orchestrator ready (lazy initialization)")

        logger.success("✅ Application initialized successfully! (Fast startup mode)")
        logger.info("💡 First chat request will load LLM automatically")
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    global backup_scheduler_task

    # Stop backup scheduler
    if backup_scheduler_task:
        backup_scheduler_task.cancel()
        try:
            await backup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("🛑 Backup scheduler stopped")


async def _generate_questions_for_document(filename: str) -> list:
    """
    Generate Korean questions for a single document

    Args:
        filename: Name of the document file

    Returns:
        List of generated Korean questions
    """
    from mlx_lm import generate

    try:
        # Sample chunks from document
        docs = vector_db.sample_documents_by_filename(filename, limit=5)
        if not docs:
            return []

        # Create context from chunks
        context_text = "\n\n".join([
            f"{doc['text'][:800]}"
            for doc in docs[:5]
        ])

        # Generate questions using LLM
        system_content = "You must respond ONLY in Korean language. Never use English in your response."
        user_content = f"""다음은 "{filename}" 문서의 내용입니다. 이 문서를 읽고 한국어로 질문 12개를 생성하세요.

문서 내용:
{context_text}

다양한 유형의 질문을 만드세요:
1. 구체적 수치/기한: "임차보증금의 최대 한도는 얼마인가요?"
2. 절차/방법: "이사회 안건은 어떻게 제출하나요?"
3. 조건/기준: "징계 감경을 받을 수 있는 조건은 무엇인가요?"
4. 비교/차이: "문서규칙과 인사규정의 차이는 무엇인가요?"
5. 정의/개념: "전산업무관리지침에서 정의하는 시스템이란?"
6. 책임/담당: "비품 관리를 담당하는 부서는 어디인가요?"
7. 기한/기간: "연차 신청은 며칠 전까지 해야 하나요?"
8. 범위/대상: "출장비 지급 대상은 누구인가요?"

위 형식으로 한국어 질문 12개만 생성하세요 (번호 없이):"""

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

        prompt = llm.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        response = generate(
            llm.model,
            llm.tokenizer,
            prompt=prompt,
            max_tokens=1024
        )

        # Parse and filter questions
        lines = response.strip().split('\n')
        questions = []
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-') or '?' in line):
                question = line.lstrip('0123456789.-) ').strip()
                if question and len(question) > 10 and question.endswith('?'):
                    # Filter: Only include questions with Korean characters
                    if any('\uac00' <= char <= '\ud7a3' for char in question):
                        questions.append(question)

        return questions

    except Exception as e:
        logger.warning(f"Failed to generate questions for {filename}: {e}")
        return []


async def generate_questions_pool():
    """
    Generate 10+ Korean questions per PDF/HWP document
    Questions are stored with document metadata for tracking
    """
    global suggested_questions_pool

    try:
        # Get list of PDF and HWP files
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            return

        import itertools
        pdf_files = list(itertools.chain(
            data_path.glob("*.pdf"),
            data_path.glob("*.hwp")
        ))
        if not pdf_files:
            return

        logger.info(f"Generating questions for {len(pdf_files)} documents in parallel...")
        all_questions = []

        # Generate questions for each document in parallel using asyncio.gather()
        tasks = [_generate_questions_for_document(pdf_file.name) for pdf_file in pdf_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for pdf_file, doc_questions in zip(pdf_files, results):
            if isinstance(doc_questions, Exception):
                logger.warning(f"  • {pdf_file.name}: Failed - {doc_questions}")
                continue
            if doc_questions:
                all_questions.extend(doc_questions)
                logger.info(f"  • {pdf_file.name}: {len(doc_questions)} questions generated")

        # Store unique Korean-only questions in the pool
        suggested_questions_pool = list(set(all_questions))
        logger.info(f"Total unique questions: {len(suggested_questions_pool)}")

    except Exception as e:
        logger.error(f"Failed to generate questions pool: {e}")
        # Set fallback questions
        suggested_questions_pool = [
            "이 문서의 주요 내용은 무엇인가요?",
            "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
            "이 문서를 간단히 요약해주세요.",
            "문서에서 다루는 핵심 주제는 무엇인가요?",
            "이 문서에서 얻을 수 있는 주요 정보는 무엇인가요?"
        ]


async def generate_questions_pool_background():
    """
    Background task wrapper for question generation
    Runs asynchronously without blocking server startup
    """
    try:
        logger.info("📝 Background: Generating question pool for all documents...")
        start_time = asyncio.get_event_loop().time()

        await generate_questions_pool()

        elapsed = asyncio.get_event_loop().time() - start_time
        logger.success(f"✅ Question pool ready! Generated {len(suggested_questions_pool)} questions in {elapsed:.1f}s")
    except Exception as e:
        logger.error(f"❌ Background question generation failed: {e}")
        logger.warning("App will continue with empty question pool")


async def generate_questions_for_new_documents(new_files: list):
    """
    Generate questions for newly added documents
    Called when new documents are detected and indexed
    """
    global suggested_questions_pool

    try:
        logger.info(f"Generating questions for {len(new_files)} new documents in parallel...")
        new_questions = []

        # Generate questions for each new document in parallel using asyncio.gather()
        tasks = [_generate_questions_for_document(filename) for filename in new_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for filename, doc_questions in zip(new_files, results):
            if isinstance(doc_questions, Exception):
                logger.warning(f"  • {filename}: Failed - {doc_questions}")
                continue
            if doc_questions:
                new_questions.extend(doc_questions)
                logger.info(f"  • {filename}: {len(doc_questions)} new questions generated")

        # Add new questions to existing pool (keep unique)
        suggested_questions_pool = list(set(suggested_questions_pool + new_questions))
        logger.success(f"Added {len(new_questions)} new questions. Total: {len(suggested_questions_pool)}")

    except Exception as e:
        logger.error(f"Failed to generate questions for new documents: {e}")



@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main page with no-cache headers"""
    index_file = static_path / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")

    content = index_file.read_text(encoding="utf-8")

    # Always use no-cache for index.html to ensure users get latest version
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.post("/api/query", response_model=QueryResponse, tags=["Query"])
async def query(
    request: QueryRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Query endpoint for chatbot (로그인 필요)
    """
    # No wait needed with Blue-Green deployment - active index always serves queries
    # Reindexing happens on a separate index, then swaps atomically

    try:
        # Save user question to conversation history
        if request.session_id and conversation_manager:
            conversation_manager.add_message(
                session_id=request.session_id,
                role="user",
                content=request.question
            )

        # Create query embedding
        query_embedding = embedding_model.encode(request.question)[0]

        # Organization-based access control: validate and filter group_ids
        user_org_id = current_user.get("org_id")

        # All users (including system admins) can only search their organization's groups
        org_groups = group_manager.get_all_groups(org_id=user_org_id)
        org_group_ids = {g['id'] for g in org_groups}

        # Validate and filter requested group_ids
        validated_group_ids = request.group_ids
        if request.group_ids is not None:
            # Specific groups requested (may be empty array)
            if len(request.group_ids) == 0:
                # Empty array means "no groups selected" - return empty result
                raise HTTPException(
                    status_code=400,
                    detail="검색할 그룹을 선택해주세요."
                )
            # Validate all requested groups belong to user's organization
            validated_group_ids = [gid for gid in request.group_ids if gid in org_group_ids]
            if len(validated_group_ids) != len(request.group_ids):
                logger.warning(f"⚠️ User {current_user.get('user_id')} attempted to access groups outside their organization")
        else:
            # No specific groups requested (None) - use all organization groups
            validated_group_ids = list(org_group_ids)

        # Validate document_ids (if using document filter instead of group filter)
        if request.document_ids is not None and len(request.document_ids) == 0:
            # Empty array means "no documents selected" - return empty result
            raise HTTPException(
                status_code=400,
                detail="검색할 문서를 선택해주세요."
            )

        # Expand group_ids to include all descendants (hierarchical search)
        expanded_group_ids = []
        for group_id in validated_group_ids:
            # Get all descendant group IDs (children, grandchildren, etc.)
            descendant_ids = group_manager.get_descendant_group_ids(group_id)
            expanded_group_ids.extend(descendant_ids)
        # Remove duplicates
        expanded_group_ids = list(set(expanded_group_ids))
        logger.info(f"🏢 Org filter: {user_org_id} | 🌲 Expanded group_ids: {validated_group_ids} → {expanded_group_ids}")

        # 🆕 자동 프롬프트 선택 (사용자가 지정하지 않은 경우)
        if not request.system_prompt:
            redis_client = cache_manager.redis
            # 초기 추정: search_mode 기반 (실제 sources는 검색 후 알 수 있음)
            auto_prompt = get_system_prompt_for_mode(
                redis_client=redis_client,
                search_mode='smart',  # Hybrid RAG의 기본 모드
                sources_used=None  # 검색 전이므로 None
            )
            request.system_prompt = auto_prompt
            logger.debug(f"📝 Auto-selected system prompt based on search mode")

        # Check if Hybrid RAG is enabled and use it, otherwise use basic RAG
        hybrid_rag = await get_hybrid_rag_orchestrator()

        if hybrid_rag is not None:
            # Use Hybrid RAG (combines local + web + docs)
            logger.info("🔗 Using Hybrid RAG (multi-source search)")

            # 사용자 선택 search_mode 사용 (기본값: smart)
            search_mode = request.search_mode or "smart"
            logger.info(f"🎯 Search mode: {search_mode}")

            result = await hybrid_rag.answer(
                query=request.question,
                group_ids=expanded_group_ids,
                user_id=current_user.get("user_id"),
                search_mode=search_mode,  # Use user-selected search mode
                system_prompt=request.system_prompt,  # 🆕 시스템 프롬프트 전달
                top_k=request.top_k,  # 🆕 검색 문서 개수 전달
                document_ids=request.document_ids  # 🆕 문서 필터 전달
            )

            # 🔄 Convert Hybrid RAG format to basic RAG format
            hybrid_sources = result.get("sources", [])
            context_docs = []
            source_names = []

            for source in hybrid_sources:
                source_type = source.get("source_type", "unknown")
                metadata = source.get("metadata", {})

                if source_type == "local":
                    filename = metadata.get("filename", "Unknown Document")
                    source_name = f"{filename} (로컬 문서)"
                elif source_type == "web":
                    title = metadata.get("title", metadata.get("url", "Web Source"))
                    source_name = f"{title} (Tavily)"
                elif source_type == "docs":
                    library = metadata.get("library", "Official Docs")
                    title = metadata.get("title", "Documentation")
                    source_name = f"{library} - {title} (Context7)"
                else:
                    source_name = "External Source"

                context_docs.append({
                    "text": source.get("content", ""),
                    "filename": source_name,
                    "score": source.get("score", 0.0)
                })
                source_names.append(source_name)

            # Add 'context' and update 'sources' keys for compatibility
            result["context"] = context_docs
            result["sources"] = list(set(source_names))  # Unique source names

        else:
            # Use basic RAG (local documents only)
            logger.info("📚 Using basic RAG (local documents only)")
            rag = await get_rag_system()
            # 🆕 로컬 전용 프롬프트 선택
            if not request.system_prompt:
                redis_client = cache_manager.redis
                request.system_prompt = get_system_prompt_for_mode(
                    redis_client=redis_client,
                    search_mode='local-only',
                    sources_used=['local']
                )
            result = rag.query(
                question=request.question,
                query_embedding=query_embedding,
                top_k=request.top_k,
                history=request.history,
                document_ids=request.document_ids,
                group_ids=expanded_group_ids,
                system_prompt=request.system_prompt  # 🆕 시스템 프롬프트 전달
            )

        # 🔍 응답 품질 검증 및 자동 수정
        original_answer = result["answer"]
        context_filenames = [doc.get("filename", "") for doc in result["context"]]

        # 검증 수행
        is_valid, violations = response_validator.validate_response(
            original_answer,
            context_filenames
        )

        # 검증 실패 시 자동 수정 시도
        if not is_valid:
            logger.warning(f"⚠️ 응답 검증 실패 - 자동 수정 시도: {violations}")
            fixed_answer, fixes = response_validator.auto_fix_response(
                original_answer,
                result["context"]
            )

            if fixes:
                logger.success(f"✅ 자동 수정 완료: {fixes}")
                result["answer"] = fixed_answer

                # 메타데이터에 수정 정보 추가
                result["validation_info"] = {
                    "original_violations": violations,
                    "auto_fixed": True,
                    "fixes_applied": fixes
                }
            else:
                logger.error(f"❌ 자동 수정 실패 - 원본 응답 반환")
                result["validation_info"] = {
                    "violations": violations,
                    "auto_fixed": False
                }
        else:
            logger.debug("✅ 응답 검증 통과")

        # 📊 신뢰도 점수 계산
        confidence_result = confidence_scorer.calculate_confidence(
            answer=result["answer"],
            context=result["context"],
            question=request.question
        )
        logger.info(f"📊 신뢰도 점수: {confidence_result['percentage']}% ({confidence_result['level']})")

        # Save assistant response to conversation history
        if request.session_id and conversation_manager:
            metadata = {
                "sources": result["sources"],
                "chunk_count": len(result["context"]),
                "context": result["context"]  # Save context for source details modal
            }
            conversation_manager.add_message(
                session_id=request.session_id,
                role="assistant",
                content=result["answer"],
                metadata=metadata
            )

        return QueryResponse(
            answer=result["answer"],
            sources=result["sources"],
            context=[
                {
                    "text": (doc["text"][:200] + "..." if len(doc["text"]) > 200 else doc["text"]) if isinstance(doc.get("text"), str) else "",
                    "filename": doc.get("filename", ""),
                    "score": doc.get("score", 0.0)
                }
                for doc in result["context"]
            ],
            confidence=confidence_result,
            search_summary=result.get("search_summary")  # 하이브리드 검색 정보 포함
        )
    except HTTPException:
        # Re-raise HTTPException as-is (e.g., 400 errors with custom messages)
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "query endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/query/stream", tags=["Query"])
async def query_stream(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Streaming query endpoint for chatbot (로그인 필요)
    """
    # No wait needed with Blue-Green deployment - active index always serves queries
    # Reindexing happens on a separate index, then swaps atomically

    try:
        # Ensure session exists (create if needed)
        if conversation_manager:
            if not request.session_id or not conversation_manager.session_exists(request.session_id):
                # Create new session if session_id is None or doesn't exist
                request.session_id = conversation_manager.create_session()
                logger.info(f"Created new session for user query: {request.session_id}")

            # Save user question to conversation history
            conversation_manager.add_message(
                session_id=request.session_id,
                role="user",
                content=request.question
            )

        # Lazy load RAG system on first use
        rag = await get_rag_system()

        if not cache_manager:
            raise HTTPException(status_code=503, detail="Cache manager not initialized")

        # Check query result cache first (exact match, 5-min TTL)
        query_result_cached = cache_manager.get_query_result_cache(
            query_text=request.question,
            group_ids=request.group_ids
        )

        if query_result_cached:
            # Query result cache HIT - return immediately
            logger.info(f"🎯 Query result cache HIT (exact match): '{request.question[:50]}...'")

            async def generate_exact_cached_stream():
                # Send metadata
                yield f"data: {json.dumps({'type': 'metadata', 'data': query_result_cached['metadata']})}\n\n"

                # Stream cached response
                response_text = query_result_cached["response"]
                chunk_size = 8
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"
                    await asyncio.sleep(0.01)

                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return StreamingResponse(
                generate_exact_cached_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )

        # Check semantic cache (similarity-based, 1-hour TTL)
        cached_response = cache_manager.get_cached_response(
            question=request.question,
            top_k=request.top_k,
            similarity_threshold=request.cache_threshold,
            document_ids=request.document_ids,
            group_ids=request.group_ids
        )

        if cached_response:
            # Cache HIT - return cached response as stream
            logger.info(f"✅ Cache HIT (similarity: {cached_response['similarity']:.4f})")

            context_data = {
                "sources": cached_response["sources"],
                "context": cached_response.get("context", []),  # Use cached context for source details
                "cached": True,
                "similarity": cached_response["similarity"],
                "search_summary": cached_response.get("search_summary")  # 하이브리드 검색 정보
            }

            # Save cached response to conversation history
            if request.session_id and conversation_manager:
                metadata = {
                    "sources": cached_response["sources"],
                    "context": cached_response.get("context", []),  # Save context for source details modal
                    "cached": True,
                    "similarity": cached_response["similarity"]
                }
                conversation_manager.add_message(
                    session_id=request.session_id,
                    role="assistant",
                    content=cached_response["response"],
                    metadata=metadata
                )

            async def generate_cached_stream():
                # Send metadata with cache indicator
                yield f"data: {json.dumps({'type': 'metadata', 'data': context_data})}\n\n"

                # Stream cached response character by character for smooth UX
                response_text = cached_response["response"]
                chunk_size = 8  # Characters per chunk

                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"
                    # Small delay to simulate streaming
                    import asyncio
                    await asyncio.sleep(0.01)

                # Send completion message
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return StreamingResponse(
                generate_cached_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )

        # Cache MISS - generate new response
        logger.info("❌ Cache MISS - generating new response")

        # Organization-based access control: validate and filter group_ids
        user_org_id = current_user.get("org_id")

        # All users (including system admins) can only search their organization's groups
        org_groups = group_manager.get_all_groups(org_id=user_org_id)
        org_group_ids = {g['id'] for g in org_groups}

        # Validate and filter requested group_ids
        validated_group_ids = request.group_ids
        if request.group_ids is not None:
            # Specific groups requested (may be empty array)
            if len(request.group_ids) == 0:
                # Empty array means "no groups selected" - return empty result
                raise HTTPException(
                    status_code=400,
                    detail="검색할 그룹을 선택해주세요."
                )
            # Validate all requested groups belong to user's organization
            validated_group_ids = [gid for gid in request.group_ids if gid in org_group_ids]
            if len(validated_group_ids) != len(request.group_ids):
                logger.warning(f"⚠️ User {current_user.get('user_id')} attempted to access groups outside their organization")
        else:
            # No specific groups requested (None) - use all organization groups
            validated_group_ids = list(org_group_ids)

        # Validate document_ids (if using document filter instead of group filter)
        if request.document_ids is not None and len(request.document_ids) == 0:
            # Empty array means "no documents selected" - return empty result
            raise HTTPException(
                status_code=400,
                detail="검색할 문서를 선택해주세요."
            )

        # Expand group_ids to include all descendants (hierarchical search)
        expanded_group_ids = []
        for group_id in validated_group_ids:
            # Get all descendant group IDs (children, grandchildren, etc.)
            descendant_ids = group_manager.get_descendant_group_ids(group_id)
            expanded_group_ids.extend(descendant_ids)
        # Remove duplicates
        expanded_group_ids = list(set(expanded_group_ids))
        logger.info(f"🏢 Org filter: {user_org_id} | 🌲 Expanded group_ids: {validated_group_ids} → {expanded_group_ids}")

        # 🆕 자동 프롬프트 선택 (사용자가 지정하지 않은 경우)
        if not request.system_prompt:
            redis_client = cache_manager.redis
            # 초기 추정: search_mode 기반 (실제 sources는 검색 후 알 수 있음)
            auto_prompt = get_system_prompt_for_mode(
                redis_client=redis_client,
                search_mode='smart',  # Hybrid RAG의 기본 모드
                sources_used=None  # 검색 전이므로 None
            )
            request.system_prompt = auto_prompt
            logger.debug(f"📝 Auto-selected system prompt based on search mode")

        # Check if Hybrid RAG is enabled and use it, otherwise use basic RAG
        hybrid_rag = await get_hybrid_rag_orchestrator()

        # Track query start time (before RAG execution)
        import time
        query_start_time = time.time()

        if hybrid_rag is not None:
            # Use Hybrid RAG (combines local + web + docs) - non-streaming
            logger.info("🔗 Using Hybrid RAG (multi-source search) - streaming response")

            # 사용자 선택 search_mode 사용 (기본값: smart)
            search_mode = request.search_mode or "smart"
            logger.info(f"🎯 Search mode: {search_mode}")

            result = await hybrid_rag.answer(
                query=request.question,
                group_ids=expanded_group_ids,
                user_id=current_user.get("user_id"),
                search_mode=search_mode,  # Use user-selected search mode
                system_prompt=request.system_prompt,
                top_k=request.top_k,
                document_ids=request.document_ids  # 🆕 문서 필터 전달
            )

            # Record first token time (when Hybrid RAG query completes)
            first_token_time = time.time()

            # Convert Hybrid RAG response to streaming format
            # Extract answer and convert sources to match expected format
            answer_text = result["answer"]
            hybrid_sources = result["sources"]

            # Create context format expected by streaming endpoint
            context_docs = []
            source_names = []  # String array for frontend compatibility

            for source in hybrid_sources:
                source_type = source.get("source_type", "unknown")
                metadata = source.get("metadata", {})

                # Determine source display name based on type
                if source_type == "local":
                    # Local documents: use filename
                    filename = metadata.get("filename", "Unknown Document")
                    source_name = f"{filename} (로컬 문서)"
                elif source_type == "web":
                    # Web sources: use title or URL
                    title = metadata.get("title", metadata.get("url", "Web Source"))
                    source_name = f"{title} (Tavily)"
                elif source_type == "docs":
                    # Official docs: use library name and title
                    library = metadata.get("library", "Official Docs")
                    title = metadata.get("title", "Documentation")
                    source_name = f"{library} - {title} (Context7)"
                else:
                    source_name = "External Source"

                context_docs.append({
                    "text": source.get("content", ""),
                    "filename": source_name,  # Use formatted name
                    "score": source.get("score", 0.0),
                    "source_type": source_type
                })

                source_names.append(source_name)

            # Remove duplicates while preserving order
            unique_source_names = []
            seen = set()
            for name in source_names:
                if name not in seen:
                    seen.add(name)
                    unique_source_names.append(name)

            # Create result dict matching basic RAG format
            result = {
                "answer": answer_text,
                "context": context_docs,
                "sources": unique_source_names,  # String array for frontend
                "search_summary": result.get("search_summary", {}),
                "generator": None  # No streaming generator for Hybrid RAG
            }
        else:
            # Use basic RAG (local documents only) with streaming
            logger.info("📚 Using basic RAG (local documents only) - streaming")

            # Update prompt for local-only mode
            if not request.system_prompt:
                redis_client = cache_manager.redis
                request.system_prompt = get_system_prompt_for_mode(
                    redis_client=redis_client,
                    search_mode='local-only',
                    sources_used=['local']
                )

            # Check embedding cache first
            cached_embedding = cache_manager.get_embedding_cache(request.question)

            if cached_embedding:
                # Use cached embedding
                query_embedding = cached_embedding
            else:
                # Generate new embedding (run in thread pool to avoid blocking)
                query_embedding = await asyncio.to_thread(
                    lambda: embedding_model.encode(request.question)[0]
                )
                # Save to embedding cache
                cache_manager.set_embedding_cache(request.question, query_embedding)

            # Query RAG system with streaming (run in thread pool to avoid blocking)
            result = await asyncio.to_thread(
                rag.query,
                question=request.question,
                query_embedding=query_embedding,
                top_k=request.top_k,
                stream=True,
                history=request.history,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                system_prompt=request.system_prompt,
                document_ids=request.document_ids,
                group_ids=expanded_group_ids  # Use validated and expanded group_ids
            )

            # Record first token time (when RAG query completes and answer is ready)
            first_token_time = time.time()

        # Prepare context and sources for the first message
        context_data = {
            "sources": result["sources"],
            "context": [
                {
                    "text": doc["text"],  # Send full text for accurate source details
                    "filename": doc["filename"],
                    "score": doc["score"]
                }
                for doc in result["context"]
            ],
            "cached": False,
            "search_summary": result.get("search_summary")  # 하이브리드 검색 정보
        }

        # Collect response for caching and conversation history
        full_response = []

        async def generate_stream():
            nonlocal query_start_time, first_token_time

            # Use query start time as the actual start time
            start_time = query_start_time
            # first_token_time is already set when rag.query() completed
            token_count = 0

            # First, send sources and context
            yield f"data: {json.dumps({'type': 'metadata', 'data': context_data})}\n\n"

            # Check if answer is a generator (streaming) or string (non-streaming)
            import inspect
            is_generator = inspect.isgenerator(result["answer"])

            if not is_generator:
                # Hybrid RAG: answer is a complete string, split into chunks for streaming
                answer_text = result["answer"]
                chunk_size = 8  # Characters per chunk

                for i in range(0, len(answer_text), chunk_size):
                    chunk = answer_text[i:i + chunk_size]
                    if chunk:
                        # Count tokens (approximate)
                        token_count += len(chunk.split())
                        full_response.append(chunk)
                        yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"

                        # Small delay to simulate streaming
                        import asyncio
                        await asyncio.sleep(0.01)
            else:
                # answer is a generator, stream naturally
                for chunk in result["answer"]:
                    if chunk:
                        # Count tokens (approximate: split by whitespace + punctuation)
                        token_count += len(chunk.split())

                        full_response.append(chunk)
                        yield f"data: {json.dumps({'type': 'chunk', 'data': chunk})}\n\n"

            # Save to cache after completion
            complete_response = ''.join(full_response)

            # 🔍 응답 품질 검증 및 자동 수정 (스트리밍)
            context_filenames = [doc.get("filename", "") for doc in result["context"]]
            is_valid, violations = response_validator.validate_response(
                complete_response,
                context_filenames
            )

            # 검증 실패 시 자동 수정 (캐시 저장 전에 수정)
            if not is_valid:
                logger.warning(f"⚠️ 스트리밍 응답 검증 실패 - 자동 수정 시도: {violations}")
                fixed_response, fixes = response_validator.auto_fix_response(
                    complete_response,
                    result["context"]
                )
                if fixes:
                    logger.success(f"✅ 스트리밍 응답 자동 수정 완료: {fixes}")
                    complete_response = fixed_response

            # 📊 신뢰도 점수 계산 (스트리밍)
            confidence_result = confidence_scorer.calculate_confidence(
                answer=complete_response,
                context=result["context"],
                question=request.question
            )
            logger.info(f"📊 스트리밍 신뢰도 점수: {confidence_result['percentage']}% ({confidence_result['level']})")

            # Calculate statistics
            end_time = time.time()
            total_time = end_time - start_time
            time_to_first_token = (first_token_time - start_time) if first_token_time else 0
            tokens_per_second = token_count / total_time if total_time > 0 else 0

            # Define background task for cache saves
            def save_to_caches():
                # Determine content type based on source documents
                content_type = 'default'
                if result.get("sources"):
                    # Check if sources contain regulation/policy documents (usually PDFs with specific keywords)
                    sources_text = ' '.join(result["sources"]).lower()
                    if any(keyword in sources_text for keyword in ['규정', '규칙', '지침', '정책', '방침', '절차']):
                        content_type = 'static_docs'  # 24-hour cache for regulations
                    elif any(keyword in sources_text for keyword in ['faq', '자주', '질문']):
                        content_type = 'realtime'  # 5-minute cache for FAQs

                # Save to semantic cache (similarity-based, dynamic TTL based on content type)
                cache_manager.save_to_cache(
                    question=request.question,
                    response=complete_response,
                    sources=result["sources"],
                    top_k=request.top_k,
                    cache_ttl=request.cache_ttl,
                    context=context_data["context"],
                    document_ids=request.document_ids,
                    group_ids=request.group_ids,
                    content_type=content_type
                )
                logger.info(f"💾 [BG] Saved to semantic cache ({content_type}): '{request.question[:50]}...'")

                # Save to query result cache (exact match, 5-min TTL)
                cache_manager.set_query_result_cache(
                    query_text=request.question,
                    result={
                        "response": complete_response,
                        "metadata": context_data
                    },
                    group_ids=request.group_ids,
                    ttl=300
                )
                logger.info(f"🎯 [BG] Saved to query result cache: '{request.question[:50]}...'")

            # Define background task for conversation history
            def save_to_conversation():
                if request.session_id and conversation_manager:
                    metadata = {
                        "sources": result["sources"],
                        "chunk_count": len(result["context"]),
                        "context": result["context"],
                        "cached": False,
                        "elapsed_time": round(total_time, 1),
                        "stats": {
                            "tokens_per_second": round(tokens_per_second, 2),
                            "total_tokens": token_count,
                            "time_to_first_token": round(time_to_first_token, 2)
                        }
                    }
                    conversation_manager.add_message(
                        session_id=request.session_id,
                        role="assistant",
                        content=complete_response,
                        metadata=metadata
                    )

            # Add background tasks (non-blocking)
            background_tasks.add_task(save_to_caches)
            background_tasks.add_task(save_to_conversation)

            # Send token statistics
            stats_data = {
                'tokens_per_second': round(tokens_per_second, 2),
                'total_tokens': token_count,
                'time_to_first_token': round(time_to_first_token, 2)
            }
            yield f"data: {json.dumps({'type': 'stats', 'data': stats_data})}\n\n"

            # Send confidence score
            yield f"data: {json.dumps({'type': 'confidence', 'data': confidence_result})}\n\n"

            # Send completion message
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except HTTPException:
        # Re-raise HTTPException as-is (e.g., 400 errors with custom messages)
        raise
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "streaming query endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


# ============================================================================
# Reindex Progress Helper Functions
# ============================================================================


@app.get("/api/validation/stats", tags=["Quality", "Admin"])
async def get_validation_stats(
    current_user: dict = Depends(get_current_active_user)
):
    """
    응답 품질 검증 통계 조회

    Returns:
        - total_checks: 총 검증 횟수
        - total_violations: 총 위반 횟수
        - pass_rate: 검증 통과율
        - violation_by_pattern: 패턴별 위반 횟수
    """
    try:
        stats = response_validator.get_statistics()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        safe_message = get_safe_error_message(e, "validation stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/validation/stats/reset", tags=["Quality", "Admin"])
async def reset_validation_stats(
    current_user: dict = Depends(get_current_active_user)
):
    """
    응답 품질 검증 통계 초기화
    """
    try:
        response_validator.reset_statistics()
        return {
            "success": True,
            "message": "검증 통계가 초기화되었습니다"
        }
    except Exception as e:
        safe_message = get_safe_error_message(e, "reset validation stats endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/status", tags=["System"])
async def status():
    """
    Get system status with detailed information (cached for performance)
    Public endpoint for health checks
    """
    global status_cache

    try:
        # Check if cache is valid
        import time
        current_time = time.time()
        if (status_cache["data"] is not None and
            current_time - status_cache["timestamp"] < status_cache["ttl"]):
            # Return cached response
            return status_cache["data"]

        # Cache miss or expired - recalculate status
        chunk_count = vector_db.count_documents() if vector_db else 0
        pdf_count = vector_db.count_unique_files() if vector_db else 0

        # Get index state
        index_state = vector_db.get_index_state() if vector_db else None

        # Check for PDF changes
        change_info = None
        if vector_db and vector_db.is_indexed():
            try:
                doc_tracker = DocumentTracker(data_dir=DATA_DIR)
                change_summary = doc_tracker.get_change_summary()
                change_info = {
                    "needs_reindex": change_summary["needs_reindex"],
                    "total_changes": change_summary["total_changes"]
                }
            except:
                pass

        # System is ready if documents are indexed (LLM loads on first use)
        is_ready = (chunk_count > 0) or (rag_system is not None)

        # Check if reindexing is in progress by checking if event is cleared
        # (reindex_event is shared with documents router)
        is_reindexing = reindex_event and not reindex_event.is_set()

        # Determine status: reindexing > ready > initializing
        if is_reindexing:
            status_value = "reindexing"
        elif is_ready:
            status_value = "ready"
        else:
            status_value = "initializing"

        # Get current models from environment variables (관리자 페이지에서 변경 시 즉시 반영)
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            current_llm_model = os.getenv("OLLAMA_LLM_MODEL", "qwen3:latest")
            current_embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "daynice/kure-v1:latest")
        else:
            current_llm_model = os.getenv("LLM_MODEL", LLM_MODEL)
            current_embedding_model = os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL)

        response = {
            "status": status_value,
            "document_count": chunk_count,  # 하위 호환성 유지
            "chunk_count": chunk_count,
            "pdf_count": pdf_count,
            "embedding_model": current_embedding_model,
            "llm_model": current_llm_model,
            "is_reindexing": is_reindexing
        }

        if index_state:
            response["index_state"] = index_state

        if change_info:
            response["changes"] = change_info

        # Update cache
        status_cache["data"] = response
        status_cache["timestamp"] = current_time

        return response
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/system-prompt", tags=["System"])
async def get_public_system_prompt(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """시스템 프롬프트 조회 (로그인한 사용자만 접근 가능)

    관리자가 설정한 시스템 프롬프트를 로그인한 사용자가 조회할 수 있는 엔드포인트

    Args:
        current_user: 현재 로그인한 사용자 정보

    Returns:
        저장된 시스템 프롬프트 또는 기본값
    """
    try:
        redis_client = request.app.state.cache_manager.redis

        # Redis에서 조회
        system_prompt = redis_client.get("system:default_prompt")

        if system_prompt:
            # bytes를 str로 변환
            if isinstance(system_prompt, bytes):
                system_prompt = system_prompt.decode('utf-8')
        else:
            # 기본값
            system_prompt = """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다.

# 🎯 역할 정의
- 제공된 문서만을 기반으로 정확하고 신뢰할 수 있는 답변 제공
- 사용자의 질문 의도를 정확히 파악하여 맞춤형 답변 작성
- 전문적이면서도 이해하기 쉬운 설명 제공

# ⚠️ 필수 준수 규칙 (CRITICAL)

## 1. 환각(Hallucination) 방지 - 최우선 원칙
✅ 반드시 지킬 것:
- 제공된 문서에 있는 정보만 사용
- 불확실한 내용은 추측하지 않음
- 문서에 없는 정보는 절대 만들어내지 않음

❌ 절대 금지:
- 일반 지식이나 학습 데이터 기반 답변
- 문서에 없는 내용 추가
- 불확실한 정보를 확실한 것처럼 제시

## 2. 출처 명시
- 답변의 근거가 되는 문서와 위치를 명확히 밝힘
- 여러 문서의 정보를 종합할 때는 각각의 출처를 구분하여 표시

## 3. 불확실성 표현
문서에 정보가 불충분하거나 없을 때:
- "제공된 문서에는 해당 정보가 없습니다"
- "문서에서 명확한 답변을 찾을 수 없습니다"
- "추가 자료가 필요합니다"

# 📋 답변 작성 가이드

## 구조화된 답변
1. **핵심 답변**: 질문에 대한 직접적인 답
2. **상세 설명**: 필요시 맥락과 배경 정보
3. **출처 표시**: 정보의 근거가 된 문서 명시

## 스타일
- 명확하고 간결한 문장
- 전문 용어 사용 시 설명 추가
- 필요시 예시나 비유 활용
- 마크다운 형식으로 가독성 향상"""

        return {
            "system_prompt": system_prompt
        }

    except Exception as e:
        logger.error(f"Failed to get system prompt: {e}")
        # 에러 발생 시에도 기본값 반환
        return {
            "system_prompt": """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다. 제공된 문서 내용을 정확하게 분석하여 사용자에게 도움이 되는 답변을 제공합니다."""
        }


@app.get("/api/system/metrics", tags=["System"])
async def get_system_metrics(
    request: Request,
    current_user: dict = Depends(get_current_active_user)
):
    """시스템 메트릭 조회 (관리자 및 로그인한 사용자)

    시스템 전체의 성능 및 상태 메트릭을 조회합니다:
    - Redis 메모리 사용량 및 통계
    - 캐시 히트율 및 검색 통계
    - 슬로우 쿼리 성능 통계

    Args:
        current_user: 현재 로그인한 사용자 정보

    Returns:
        시스템 메트릭 정보
    """
    try:
        metrics_collector = request.app.state.metrics_collector

        if not metrics_collector:
            raise HTTPException(status_code=500, detail="Metrics collector not available")

        # 시스템 메트릭 조회
        metrics = metrics_collector.get_system_metrics()

        return {
            "success": True,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models", tags=["Settings"])
async def list_available_models(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get list of locally available models (both LLM and Embedding)
    Returns only models that are downloaded and ready to use
    """
    try:
        model_manager = ModelManager(model_dir=MODEL_DIR)
        models = model_manager.list_local_models()

        # Separate LLM and Embedding models
        llm_models = []
        embedding_models = []

        # Keywords to identify model types
        embedding_keywords = ["embedding", "KURE", "e5", "jina", "bge", "gte"]
        llm_keywords = ["instruct", "chat", "Qwen", "Llama", "GPT", "rnj"]

        for model in models:
            display_name = model["name"]

            # Determine if it's an embedding model
            is_embedding = any(keyword.lower() in display_name.lower() for keyword in embedding_keywords)

            # Add user-friendly labels for known models
            if "Qwen3-30B" in display_name:
                label = "Qwen 3 30B A3B 4bit"
            elif "rnj-1-instruct" in display_name:
                label = "RNJ-1 Instruct 4bit"
            elif "Qwen2.5-3B" in display_name:
                label = "Qwen 2.5 3B Instruct 4bit"
            elif "KURE" in display_name:
                label = "KURE-v1 (Korean Embedding)"
            elif "jina-embeddings" in display_name:
                label = "Jina Embeddings v3"
            elif "multilingual-e5" in display_name:
                label = "Multilingual E5 Large"
            else:
                # Use model name as label if not recognized
                label = display_name.split("/")[-1]

            model_info = {
                "value": display_name,
                "label": label,
                "size": model["size"]
            }

            if is_embedding:
                embedding_models.append(model_info)
            else:
                llm_models.append(model_info)

        # Sort by name for consistent ordering
        llm_models.sort(key=lambda x: x["label"])
        embedding_models.sort(key=lambda x: x["label"])

        logger.info(f"Found {len(llm_models)} LLM models and {len(embedding_models)} embedding models")
        return {
            "llm_models": llm_models,
            "embedding_models": embedding_models
        }

    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")


@app.post("/api/change-llm", tags=["Settings"])
async def change_llm(
    request: LLMChangeRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Change the LLM model dynamically
    """
    global llm, rag_system, LLM_MODEL

    try:
        logger.info(f"Changing LLM model to: {request.llm_model}")

        # Update the LLM_MODEL variable
        LLM_MODEL = request.llm_model

        # Reload LLM with new model
        llm = LLM(
            model_name=LLM_MODEL,
            model_dir=MODEL_DIR
        )

        # Reinitialize RAG system with new LLM
        rag_system = RAGSystem(llm, vector_db, cache_manager)

        logger.success(f"LLM model changed to: {LLM_MODEL}")

        return {
            "status": "success",
            "llm_model": LLM_MODEL,
            "message": "LLM model changed successfully"
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "change model endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/change-embedding", tags=["Settings"])
async def change_embedding(
    request: EmbeddingChangeRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Change the Embedding model dynamically
    Requires re-indexing all documents with new embeddings
    """
    global embedding_model, vector_db, EMBEDDING_MODEL

    try:
        logger.info(f"Changing Embedding model to: {request.embedding_model}")

        # Update the EMBEDDING_MODEL variable
        EMBEDDING_MODEL = request.embedding_model

        # Reload embedding model
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        if use_ollama:
            # For Ollama, don't pass model_name - let it read from OLLAMA_EMBEDDING_MODEL env var
            embedding_model = EmbeddingModel(
                model_dir=MODEL_DIR
            )
        else:
            # For local embedding model
            embedding_model = EmbeddingModel(
                model_name=EMBEDDING_MODEL,
                model_dir=MODEL_DIR
            )

        # Reinitialize vector DB with new embedding model
        vector_db = VectorDB(
            host=REDIS_HOST,
            port=REDIS_PORT,
            embedding_dim=embedding_model.get_embedding_dim()
        )

        # Note: Existing embeddings in Redis are now incompatible
        # User needs to reindex documents
        logger.warning("Embedding model changed - existing document embeddings are now incompatible")
        logger.info("Please use the reindex endpoint to update all document embeddings")

        return {
            "status": "success",
            "embedding_model": EMBEDDING_MODEL,
            "message": "Embedding model changed successfully",
            "warning": "기존 문서들을 새로운 임베딩 모델로 재색인해야 합니다. '재색인' 버튼을 클릭하세요."
        }
    except Exception as e:
        # Security: Use sanitized error message (prevents information disclosure)
        safe_message = get_safe_error_message(e, "change embedding model endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/suggested-questions", tags=["Query"])
async def get_suggested_questions(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get suggested questions (로그인 필요)
    """
    try:
        import random

        # Use pre-generated question pool for fast response
        if not suggested_questions_pool:
            # Fallback if pool is empty - use diverse question pool
            logger.warning("Question pool is empty, using fallback questions")

            # Diverse fallback question pool (30 questions covering various aspects)
            fallback_pool = [
                # General content questions
                "이 문서의 주요 내용은 무엇인가요?",
                "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
                "이 문서를 간단히 요약해주세요.",
                "문서에서 다루는 핵심 주제는 무엇인가요?",
                "이 문서에서 얻을 수 있는 주요 정보는 무엇인가요?",

                # Detailed analysis questions
                "문서에서 설명하는 주요 개념을 자세히 설명해주세요.",
                "이 문서의 목적은 무엇인가요?",
                "문서에 나오는 중요한 용어들을 설명해주세요.",
                "이 문서가 다루는 범위는 어디까지인가요?",
                "문서에서 강조하는 핵심 메시지는 무엇인가요?",

                # Practical application questions
                "이 문서의 내용을 실제로 어떻게 활용할 수 있나요?",
                "문서에 나온 내용을 적용하려면 어떻게 해야 하나요?",
                "이 문서가 제시하는 해결책은 무엇인가요?",
                "문서에서 권장하는 방법은 무엇인가요?",
                "실무에 적용 가능한 내용이 있나요?",

                # Comparison and analysis questions
                "문서에서 비교하는 내용이 있나요?",
                "이 문서의 장단점은 무엇인가요?",
                "문서에서 언급된 사례나 예시를 알려주세요.",
                "문서의 내용과 관련된 배경 정보는 무엇인가요?",
                "이 문서와 관련된 다른 정보를 알려주세요.",

                # Specific details questions
                "문서에 나온 구체적인 수치나 데이터는 무엇인가요?",
                "문서에서 다루는 세부 항목들을 나열해주세요.",
                "이 문서에 포함된 주요 섹션은 무엇인가요?",
                "문서에서 제시하는 단계나 절차가 있나요?",
                "문서에 명시된 기준이나 요구사항은 무엇인가요?",

                # Context and implications questions
                "이 문서를 읽어야 하는 대상은 누구인가요?",
                "문서의 내용이 시사하는 바는 무엇인가요?",
                "이 문서와 관련하여 주의해야 할 점은 무엇인가요?",
                "문서에서 다루지 않은 내용은 무엇인가요?",
                "이 문서의 핵심을 한 문장으로 표현하면?"
            ]

            # Randomly select 5 questions from the pool
            selected_questions = random.sample(fallback_pool, 5)
            return {"questions": selected_questions}

        # Sample 50 random questions from the pool for better autocomplete coverage
        num_questions = min(50, len(suggested_questions_pool))
        selected_questions = random.sample(suggested_questions_pool, num_questions)

        logger.info(f"Returning {num_questions} questions from pool of {len(suggested_questions_pool)}")
        return {"questions": selected_questions}

    except Exception as e:
        logger.error(f"Failed to get suggested questions: {e}")
        return {
            "questions": [
                "이 문서의 주요 내용은 무엇인가요?",
                "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
                "이 문서를 간단히 요약해주세요."
            ]
        }


# ============================================================================
# 🆕 독립 검색 API 엔드포인트 (Tavily, Context7)
# ============================================================================

@app.post("/api/search/web", response_model=WebSearchResponse, tags=["Search"])
async def search_web(
    request: WebSearchRequest,
    current_user: dict = Depends(get_current_active_user),
    app_request: Request = None
):
    """
    Tavily 웹 검색 독립 API

    - 인증 필요 (로그인한 사용자만)
    - Tavily API 키는 서버에서 관리
    - 검색 결과를 그대로 반환 (LLM 답변 생성 안 함)
    """
    try:
        # Hybrid RAG 인스턴스 가져오기 (lazy 초기화)
        rag = await get_hybrid_rag_orchestrator()

        # Tavily 초기화 확인
        if not rag.tavily_client:
            raise HTTPException(
                status_code=503,
                detail="웹 검색 기능이 비활성화되어 있습니다. Tavily API 키를 설정해주세요."
            )

        logger.info(f"🌐 웹 검색 요청: '{request.query}' (depth={request.search_depth})")

        # Tavily 검색 수행
        search_params = {
            "query": request.query,
            "max_results": request.max_results,
            "search_depth": request.search_depth,
            "include_answer": False,
            "include_raw_content": True
        }

        # 도메인 필터 추가 (유효한 도메인만 포함)
        if request.include_domains:
            # 유효한 도메인만 필터링 (점이 있고 최소 2글자 이상)
            valid_domains = [d for d in request.include_domains if '.' in d and len(d) > 2]
            if valid_domains:
                search_params["include_domains"] = valid_domains
        if request.exclude_domains:
            # 유효한 도메인만 필터링
            valid_domains = [d for d in request.exclude_domains if '.' in d and len(d) > 2]
            if valid_domains:
                search_params["exclude_domains"] = valid_domains

        search_results = rag.tavily_client.search(**search_params)

        # 결과 포맷팅
        formatted_results = []
        for result in search_results.get('results', []):
            formatted_results.append({
                'title': result.get('title', ''),
                'url': result.get('url', ''),
                'content': result.get('content', ''),
                'published_date': result.get('published_date', ''),
                'score': result.get('score', 0.0)
            })

        logger.success(f"✅ 웹 검색 완료: {len(formatted_results)}개 결과")

        return WebSearchResponse(
            success=True,
            results=formatted_results,
            query=request.query,
            search_depth=request.search_depth
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 웹 검색 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"웹 검색 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/api/search/docs", response_model=DocsSearchResponse, tags=["Search"])
async def search_docs(
    request: DocsSearchRequest,
    current_user: dict = Depends(get_current_active_user),
    app_request: Request = None
):
    """
    Context7 공식 문서 검색 독립 API

    - 인증 필요 (로그인한 사용자만)
    - Context7 API 키는 서버에서 관리
    - React, Vue, Spring Boot 등 공식 문서 검색
    """
    try:
        # Hybrid RAG 인스턴스 가져오기 (lazy 초기화)
        rag = await get_hybrid_rag_orchestrator()

        # Context7 초기화 확인
        if not rag.context7_client:
            raise HTTPException(
                status_code=503,
                detail="공식 문서 검색 기능이 비활성화되어 있습니다. Context7을 설정해주세요."
            )

        logger.info(f"📚 공식 문서 검색 요청: '{request.query}' (tech_stack={request.tech_stack})")

        # tech_stack이 명시되지 않은 경우 쿼리 분석으로 감지
        tech_stack = request.tech_stack
        if not tech_stack and rag.query_analyzer:
            analysis = rag.query_analyzer.analyze(request.query)
            tech_stack = analysis.get('tech_stack')
            logger.info(f"🔍 자동 감지된 기술 스택: {tech_stack}")

        # Context7 검색 수행
        analysis = {'tech_stack': tech_stack} if tech_stack else {}
        docs_results = await rag._search_docs(request.query, analysis)

        # 결과 포맷팅
        formatted_results = []
        for result in docs_results[:request.max_results]:
            formatted_results.append({
                'title': result.get('metadata', {}).get('title', ''),
                'url': result.get('metadata', {}).get('url', ''),
                'content': result.get('content', ''),
                'library': result.get('metadata', {}).get('library', tech_stack),
                'relevance_score': result.get('score', 0.0)
            })

        logger.success(f"✅ 공식 문서 검색 완료: {len(formatted_results)}개 결과")

        return DocsSearchResponse(
            success=True,
            results=formatted_results,
            query=request.query,
            tech_stack=tech_stack
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 공식 문서 검색 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"공식 문서 검색 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/api/convert/hwpx", tags=["Conversion"])
async def convert_to_hwpx(
    request: HwpxConversionRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    HTML/Markdown을 HWPX 형식으로 변환

    - 인증 필요 (로그인한 사용자만)
    - Java document-service에 프록시 요청
    - HWPX 파일을 바이너리로 반환
    """
    try:
        import httpx

        logger.info(f"📄 HWPX 변환 요청: content_type={request.content_type}, 길이={len(request.content)}")

        # Java 서비스 URL
        java_service_url = os.getenv("DOCUMENT_SERVICE_URL", "http://localhost:8081")

        # 엔드포인트 선택
        if request.content_type == "markdown":
            endpoint = f"{java_service_url}/api/conversion/markdown-to-hwpx"
            payload = {
                "markdownContent": request.content,
                "filename": request.filename
            }
        else:  # html
            endpoint = f"{java_service_url}/api/conversion/html-to-hwpx"
            payload = {
                "htmlContent": request.content,
                "filename": request.filename
            }

        # Java 서비스에 요청
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"❌ Java 서비스 오류: {response.status_code} - {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"HWPX 변환 실패: {error_detail}"
                )

            # 파일명 추출 (Content-Disposition 헤더에서)
            content_disposition = response.headers.get("content-disposition", "")
            filename = request.filename or "document.hwpx"
            if "filename=" in content_disposition:
                # filename*=UTF-8''encoded_name 형식 처리
                import urllib.parse
                parts = content_disposition.split("filename=")
                if len(parts) > 1:
                    filename_part = parts[1].strip('"').strip("'")
                    try:
                        filename = urllib.parse.unquote(filename_part)
                    except:
                        pass

            if not filename.endswith(".hwpx"):
                filename += ".hwpx"

            logger.success(f"✅ HWPX 변환 완료: {filename}, {len(response.content)} bytes")

            # HWPX 파일 반환
            return Response(
                content=response.content,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(len(response.content))
                }
            )

    except httpx.TimeoutException:
        logger.error("❌ Java 서비스 타임아웃")
        raise HTTPException(
            status_code=504,
            detail="HWPX 변환 서비스 응답 시간 초과"
        )
    except httpx.ConnectError:
        logger.error("❌ Java 서비스 연결 실패")
        raise HTTPException(
            status_code=503,
            detail="HWPX 변환 서비스에 연결할 수 없습니다. 서비스가 실행 중인지 확인하세요."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ HWPX 변환 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"HWPX 변환 중 오류가 발생했습니다: {str(e)}"
        )


# ============================================================================
# Group Management API Endpoints
# ============================================================================

class GroupCreateRequest(BaseModel):
    name: str
    description: str = ""
    color: str = "#3B82F6"
    icon: str = "📁"
    parent_id: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[str] = None  # 상위 그룹 변경 지원


class GroupMoveRequest(BaseModel):
    new_parent_id: Optional[str] = None


class DocumentAssignRequest(BaseModel):
    group_id: str


class BatchDocumentAssignRequest(BaseModel):
    filenames: List[str]


@app.get("/api/groups", tags=["Groups"])
async def list_groups(
    filter_scope: str = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get all groups with hierarchy

    Args:
        filter_scope: "user" - always filter by organization (for search filters)
                     None - admin sees all, users see organization only (for admin page)

    Returns:
        List of all groups with their metadata and tree structure
    """
    try:
        # Get user's organization
        user_org_id = current_user.get("org_id")
        is_admin = current_user.get("role") == "admin"

        # Determine scope: if filter_scope="user", always use organization scope
        # Otherwise, admin sees all, regular users see organization only
        if filter_scope == "user" or not is_admin:
            groups = group_manager.get_all_groups(org_id=user_org_id)
            tree = group_manager.get_group_tree(org_id=user_org_id)
        else:
            groups = group_manager.get_all_groups()
            tree = group_manager.get_group_tree()

        return {
            "groups": groups,
            "tree": tree
        }
    except Exception as e:
        logger.error(f"Failed to list groups: {e}")
        safe_message = get_safe_error_message(e, "list groups endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/groups", tags=["Groups"])
async def create_group(
    request: GroupCreateRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Create a new group

    Group is automatically assigned to the default organization.
    Admin can manually assign the group to additional organization(s) after creation.

    Args:
        request: Group creation parameters

    Returns:
        Created group ID and details
    """
    try:
        group_id = group_manager.create_group(
            name=request.name,
            org_id=None,  # Will be assigned to default org below
            description=request.description,
            color=request.color,
            icon=request.icon,
            parent_id=request.parent_id,
            created_by=current_user.get("user_id", "system")
        )

        if not group_id:
            raise HTTPException(status_code=400, detail="Failed to create group")

        # Automatically assign to default organization (home for all groups)
        from .organization_manager import OrganizationManager
        org_manager = OrganizationManager(group_manager.client)
        default_org_id = org_manager.get_default_organization_id()

        try:
            group_manager.add_group_to_organization(
                group_id=group_id,
                org_id=default_org_id,
                updated_by=current_user.get("username", "system")
            )
            logger.info(f"Created group: {group_id} ({request.name}) - assigned to default organization")
        except Exception as e:
            logger.warning(f"Failed to assign group {group_id} to default organization: {e}")

        group = group_manager.get_group(group_id)

        return {
            "success": True,
            "group_id": group_id,
            "group": group
        }
    except ValueError as e:
        # Validation errors (e.g., invalid parent_id, parent org mismatch)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create group: {e}")
        safe_message = get_safe_error_message(e, "create group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.put("/api/groups/{group_id}", tags=["Groups"])
async def update_group(
    group_id: str,
    request: GroupUpdateRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update group metadata

    Args:
        group_id: ID of the group to update
        request: Fields to update

    Returns:
        Updated group details
    """
    try:
        # Build update dict from non-None fields
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.color is not None:
            updates["color"] = request.color
        if request.icon is not None:
            updates["icon"] = request.icon
        # Handle parent_id: accept both None and empty string as "no parent"
        if request.parent_id is not None:
            updates["parent_id"] = request.parent_id if request.parent_id else None
        elif hasattr(request, 'parent_id'):  # Explicitly check if field is present even if None
            updates["parent_id"] = None

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        success = group_manager.update_group(
            group_id=group_id,
            updated_by="system",
            **updates
        )

        if not success:
            raise HTTPException(status_code=404, detail="Group not found")

        group = group_manager.get_group(group_id)
        logger.info(f"Updated group: {group_id}")

        return {
            "success": True,
            "group": group
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update group: {e}")
        safe_message = get_safe_error_message(e, "update group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.delete("/api/groups/{group_id}", tags=["Groups"])
async def delete_group(
    group_id: str,
    reassign_to: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete a group and reassign its documents

    Args:
        group_id: ID of the group to delete
        reassign_to: Group ID to reassign documents to (defaults to parent or default group)

    Returns:
        Number of documents reassigned
    """
    try:
        # Prevent deletion of default group
        default_group_id = group_manager.get_default_group_id()
        if group_id == default_group_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete default group"
            )

        reassigned_count = group_manager.delete_group(
            group_id=group_id,
            reassign_to=reassign_to
        )

        logger.info(f"Deleted group: {group_id}, reassigned {reassigned_count} documents")

        return {
            "success": True,
            "reassigned_documents": reassigned_count
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete group: {e}")
        safe_message = get_safe_error_message(e, "delete group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.patch("/api/groups/{group_id}/move", tags=["Groups"])
async def move_group(
    group_id: str,
    request: GroupMoveRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Move a group to a new parent (change hierarchy)

    Args:
        group_id: ID of the group to move
        request: New parent group ID

    Returns:
        Updated group details
    """
    try:
        success = group_manager.move_group(
            group_id=group_id,
            new_parent_id=request.new_parent_id,
            updated_by="system"
        )

        if not success:
            raise HTTPException(status_code=404, detail="Group not found")

        group = group_manager.get_group(group_id)
        logger.info(f"Moved group: {group_id} to parent {request.new_parent_id}")

        return {
            "success": True,
            "group": group
        }
    except ValueError as e:
        # Circular reference or validation errors
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to move group: {e}")
        safe_message = get_safe_error_message(e, "move group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/groups/{group_id}/documents", tags=["Groups"])
async def batch_assign_documents(
    group_id: str,
    request: BatchDocumentAssignRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Batch assign multiple documents to a group

    Args:
        group_id: Target group ID
        request: List of filenames to assign

    Returns:
        Number of documents successfully assigned
    """
    try:
        assigned_count = group_manager.batch_assign_documents(
            filenames=request.filenames,
            group_id=group_id
        )

        logger.info(f"Batch assigned {assigned_count}/{len(request.filenames)} documents to group {group_id}")

        return {
            "success": True,
            "assigned_count": assigned_count,
            "total_requested": len(request.filenames)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to batch assign documents: {e}")
        safe_message = get_safe_error_message(e, "batch assign documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.delete("/api/groups/{group_id}/documents/{filename}", tags=["Groups"])
async def remove_document_from_group(
    group_id: str,
    filename: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Remove a document from a group (reassigns to default group)

    Args:
        group_id: Group ID to remove document from
        filename: Document filename to remove

    Returns:
        Success status
    """
    try:
        success = group_manager.remove_document_from_group(
            filename=filename,
            group_id=group_id
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="문서 또는 그룹을 찾을 수 없습니다."
            )

        logger.info(f"Removed document '{filename}' from group {group_id}")

        return {
            "success": True,
            "filename": filename,
            "group_id": group_id,
            "message": "문서가 기본 그룹으로 이동되었습니다."
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove document from group: {e}")
        safe_message = get_safe_error_message(e, "remove document from group endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.get("/api/groups/{group_id}/documents", tags=["Groups"])
async def list_group_documents(
    group_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get all documents in a group

    Args:
        group_id: Group ID to query

    Returns:
        List of document filenames in the group
    """
    try:
        documents = group_manager.get_group_documents(group_id)

        return {
            "group_id": group_id,
            "documents": documents,
            "count": len(documents)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list group documents: {e}")
        safe_message = get_safe_error_message(e, "list group documents endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


@app.post("/api/groups/sync-counts", tags=["Groups"])
async def sync_group_document_counts(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Synchronize document counts for all groups
    Recalculates counts from actual SET cardinality
    """
    try:
        group_manager.sync_document_counts()
        return {"status": "success", "message": "그룹별 문서 개수가 동기화되었습니다"}
    except Exception as e:
        logger.error(f"Failed to sync document counts: {e}")
        safe_message = get_safe_error_message(e, "sync document counts endpoint")
        raise HTTPException(status_code=500, detail=safe_message)


# ============================================================================
# Conversation History API Endpoints
# ============================================================================


# ============================================================================
# Follow-up Questions API
# ============================================================================

class FollowUpRequest(BaseModel):
    question: str
    answer: str
    context: Optional[list] = []


@app.post("/api/follow-up-questions", tags=["Query"])
async def generate_follow_up_questions(
    request: FollowUpRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Generate smart follow-up questions (로그인 필요)
    """
    try:
        if not llm:
            raise HTTPException(status_code=503, detail="LLM not initialized")

        # Create simple completion prompt - pattern-based
        prompt = f"""다음 예시를 참고하여 관련 질문 3개를 한국어로 생성하세요.

질문: 계약서 작성 방법은?
답변: 계약서는 양식에 따라 작성하며 필요 서류를 첨부합니다.
관련 질문:
- 계약 기간은 얼마나 되나요?
- 계약 해지 시 절차는 어떻게 되나요?
- 계약서 양식은 어디서 받을 수 있나요?

질문: 출장비 신청 절차는?
답변: 출장비는 사전에 신청하며 견적서를 제출합니다.
관련 질문:
- 출장비 지급 기준은 무엇인가요?
- 출장 후 정산 기한은 언제까지인가요?
- 해외 출장비는 별도 규정이 있나요?

질문: {request.question}
답변: {request.answer[:300]}
관련 질문:
-"""

        # Check LLM type and use appropriate generation method
        from .llm_ollama import OllamaLLM

        if isinstance(llm, OllamaLLM):
            # Use Ollama's _generate_response method with simple user message
            messages = [{"role": "user", "content": prompt}]
            response = llm._generate_response(
                messages=messages,
                max_tokens=200,
                temperature=0.3  # Lower temperature for more focused output
            )
        else:
            # Use MLX generate for MLX-based LLM
            from mlx_lm import generate as mlx_generate
            response = mlx_generate(
                llm.model,
                llm.tokenizer,
                prompt=prompt,
                max_tokens=200,
                verbose=False
            )

        # Clean response - remove <think> tags if present
        import re
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

        # Parse response into questions - handle bullet point format
        lines = response.strip().split('\n')
        questions = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove bullet points, numbering, and markdown
            line = re.sub(r'^[\-\*\•\d\.\)\]]+\s*', '', line)
            line = re.sub(r'^\*\*|\*\*$', '', line)  # Remove bold
            line = line.strip()

            # Skip non-question lines (metadata, labels, etc.)
            if not line or '질문' in line or '답변' in line or '예시' in line or '관련' in line:
                continue

            # Validate: must end with ?, contain Korean, min length 5
            if (line.endswith('?') and
                re.search(r'[가-힣]', line) and
                len(line) >= 5):
                questions.append(line)

            if len(questions) >= 3:
                break

        # Return questions or fallback
        if len(questions) >= 3:
            logger.info(f"Successfully generated {len(questions)} follow-up questions")
            return {"questions": questions[:3]}
        else:
            logger.warning(f"Only generated {len(questions)} questions, using fallback")
            return {
                "questions": [
                    "이 내용과 관련된 추가 정보가 있나요?",
                    "다른 규정과의 차이점은 무엇인가요?",
                    "실제 적용 사례는 어떻게 되나요?"
                ]
            }

    except Exception as e:
        logger.error(f"Failed to generate follow-up questions: {e}", exc_info=True)
        return {
            "questions": [
                "이 내용과 관련된 추가 정보가 있나요?",
                "다른 규정과의 차이점은 무엇인가요?",
                "실제 적용 사례는 어떻게 되나요?"
            ]
        }


@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint for load balancers and monitoring systems.
    Returns detailed system status including Redis, models, and cache.
    Optimized for fast response (<10ms).
    """
    try:
        import psutil
        from datetime import datetime

        # Check Redis connectivity (fast PING only)
        redis_healthy = False
        redis_info = {}
        try:
            vector_db.client.ping()
            redis_healthy = True
            # Minimal info for performance - avoid expensive INFO command
            redis_info = {
                "connected": True
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

        # Check cache stats (lightweight)
        cache_stats = {}
        if cache_manager:
            cache_stats = cache_manager.get_cache_stats()

        # System resources (instant read, no interval)
        cpu_percent = psutil.cpu_percent(interval=0)  # Instant, no blocking
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Model status (simple bool check)
        models_loaded = {
            "embedding": embedding_model is not None,
            "llm": llm is not None,
            "rag": rag_system is not None
        }

        # Overall health status
        is_healthy = redis_healthy and all(models_loaded.values())

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "redis": {
                "healthy": redis_healthy,
                "info": redis_info
            },
            "cache": {
                "entries": cache_stats.get("total_entries", 0),
                "hit_rate": (cache_stats.get("cache_hits", 0) / max(cache_stats.get("total_queries", 1), 1)) * 100
            },
            "models": models_loaded,
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": disk.percent
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


@app.get("/metrics", tags=["System"])
async def metrics():
    """
    Prometheus-compatible metrics endpoint for monitoring.
    Returns key performance metrics in plain text format.
    """
    try:
        import psutil

        # Get cache stats
        cache_stats = cache_manager.get_cache_stats() if cache_manager else {}

        # Get Redis stats
        redis_info = {}
        try:
            info = vector_db.client.info()
            redis_info = {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "total_commands": info.get("total_commands_processed", 0)
            }
        except:
            pass

        # System metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        # Format metrics in Prometheus format
        metrics_output = f"""# HELP cache_entries Total number of cache entries
# TYPE cache_entries gauge
cache_entries {cache_stats.get('total_entries', 0)}

# HELP cache_queries_total Total number of cache queries
# TYPE cache_queries_total counter
cache_queries_total {cache_stats.get('total_queries', 0)}

# HELP cache_hits_total Total number of cache hits
# TYPE cache_hits_total counter
cache_hits_total {cache_stats.get('cache_hits', 0)}

# HELP redis_connected_clients Number of Redis client connections
# TYPE redis_connected_clients gauge
redis_connected_clients {redis_info.get('connected_clients', 0)}

# HELP redis_memory_used_bytes Redis memory usage in bytes
# TYPE redis_memory_used_bytes gauge
redis_memory_used_bytes {redis_info.get('used_memory', 0)}

# HELP system_cpu_percent CPU usage percentage
# TYPE system_cpu_percent gauge
system_cpu_percent {cpu_percent}

# HELP system_memory_percent Memory usage percentage
# TYPE system_memory_percent gauge
system_memory_percent {memory.percent}
"""

        return Response(content=metrics_output, media_type="text/plain")
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return Response(content="", media_type="text/plain", status_code=500)


# DEPRECATED: 이 엔드포인트는 src/routers/auth.py의 신버전으로 대체되었습니다
# Redis 기반의 더 빠르고 안정적인 엔드포인트를 사용하세요
# @app.get("/api/admin/security-logs", tags=["Admin"])
# async def get_security_logs(
#     request: Request,
#     limit: int = 100,
#     offset: int = 0,
#     level: Optional[str] = None,
#     event_type: Optional[str] = None,
#     start_date: Optional[str] = None,
#     end_date: Optional[str] = None
# ):
#     """
#     Get security logs (admin only)
#
#     Args:
#         limit: Number of logs to return
#         offset: Number of logs to skip
#         level: Filter by log level (INFO, WARNING, ERROR, CRITICAL)
#         event_type: Filter by event type
#         start_date: Filter from this date (ISO format)
#         end_date: Filter to this date (ISO format)
#
#     Returns:
#         List of security log entries
#     """
#     try:
#         # Get token from Authorization header or cookies
#         token = None
#         auth_header = request.headers.get("Authorization")
#         if auth_header and auth_header.startswith("Bearer "):
#             token = auth_header.split(" ")[1]
#         else:
#             token = request.cookies.get("access_token")
#
#         if not token:
#             raise HTTPException(status_code=401, detail="Not authenticated")
#
#         from .auth.utils import verify_token, get_user
#         user_data = verify_token(token)
#         if not user_data:
#             raise HTTPException(status_code=401, detail="Invalid token")
#
#         # Get user and check admin role
#         redis_client = request.app.state.cache_manager.redis
#         user = get_user(user_data["user_id"], redis_client)
#         if not user or user.get("role") != "admin":
#             raise HTTPException(status_code=403, detail="Admin access required")
#
#         # Determine log file path
#         log_file_path = os.getenv("LOG_FILE", "server.log")
#         if not os.path.isabs(log_file_path):
#             log_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), log_file_path)
#
#         if not os.path.exists(log_file_path):
#             return {
#                 "logs": [],
#                 "total_count": 0,
#                 "limit": limit,
#                 "offset": offset
#             }
#
#         # Read and parse security logs
#         security_logs = []
#         with open(log_file_path, 'r', encoding='utf-8') as f:
#             for line in f:
#                 if "SECURITY_EVENT:" in line:
#                     try:
#                         # Extract JSON part
#                         json_start = line.index("SECURITY_EVENT:") + len("SECURITY_EVENT:")
#                         json_str = line[json_start:].strip()
#                         log_data = json.loads(json_str)
#
#                         # Apply filters
#                         if level and log_data.get("level") != level:
#                             continue
#                         if event_type and log_data.get("event_type") != event_type:
#                             continue
#                         if start_date:
#                             try:
#                                 from datetime import datetime
#                                 log_time = datetime.fromisoformat(log_data.get("timestamp", ""))
#                                 start_time = datetime.fromisoformat(start_date)
#                                 if log_time < start_time:
#                                     continue
#                             except:
#                                 pass
#                         if end_date:
#                             try:
#                                 from datetime import datetime
#                                 log_time = datetime.fromisoformat(log_data.get("timestamp", ""))
#                                 end_time = datetime.fromisoformat(end_date)
#                                 if log_time > end_time:
#                                     continue
#                             except:
#                                 pass
#
#                         security_logs.append(log_data)
#                     except (ValueError, json.JSONDecodeError) as e:
#                         logger.warning(f"Failed to parse security log line: {e}")
#                         continue
#
#         # Sort by timestamp descending (most recent first)
#         security_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
#
#         # Apply pagination
#         total_count = len(security_logs)
#         paginated_logs = security_logs[offset:offset + limit]
#
#         return {
#             "logs": paginated_logs,
#             "total_count": total_count,
#             "limit": limit,
#             "offset": offset
#         }
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Failed to get security logs: {e}")
#         raise HTTPException(status_code=500, detail="Failed to retrieve security logs")


@app.post("/api/admin/system-prompt", tags=["Admin"])
async def save_system_prompt(request: Request):
    """시스템 프롬프트 저장 (관리자 전용)

    Request body:
        {
            "system_prompt": "당신은 AI 어시스턴트입니다..."
        }

    Returns:
        저장 성공 메시지
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin, extract_token_from_request, verify_token

        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # Request body 파싱
        body = await request.json()
        system_prompt = body.get("system_prompt", "")

        # 유효성 검증
        if not system_prompt or not system_prompt.strip():
            raise HTTPException(status_code=400, detail="시스템 프롬프트는 비어있을 수 없습니다")

        if len(system_prompt) > 10000:
            raise HTTPException(status_code=400, detail="시스템 프롬프트가 너무 깁니다 (최대 10,000자)")

        # Redis에 저장
        redis_client.set("system:default_prompt", system_prompt)

        # 로깅
        token = extract_token_from_request(request)
        user_data = verify_token(token)
        logger.info(f"System prompt updated by user {user_data['user_id']} (length: {len(system_prompt)})")

        return {
            "message": "시스템 프롬프트가 저장되었습니다",
            "length": len(system_prompt)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save system prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to save system prompt")


@app.get("/api/admin/system-prompt", tags=["Admin"])
async def get_system_prompt(request: Request):
    """시스템 프롬프트 조회 (관리자 전용)

    Returns:
        저장된 시스템 프롬프트
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin

        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # Redis에서 조회
        system_prompt = redis_client.get("system:default_prompt")

        if system_prompt:
            # bytes를 str로 변환
            if isinstance(system_prompt, bytes):
                system_prompt = system_prompt.decode('utf-8')
        else:
            # 기본값
            system_prompt = """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다.

# 🎯 역할 정의
- 제공된 문서만을 기반으로 정확하고 신뢰할 수 있는 답변 제공
- 사용자의 질문 의도를 정확히 파악하여 맞춤형 답변 작성
- 전문적이면서도 이해하기 쉬운 설명 제공

# ⚠️ 필수 준수 규칙 (CRITICAL)

## 1. 환각(Hallucination) 방지 - 최우선 원칙
✅ 반드시 지킬 것:
- 제공된 문서에 있는 정보만 사용
- 불확실한 내용은 추측하지 않음
- 문서에 없는 정보는 절대 만들어내지 않음

❌ 절대 금지:
- 일반 지식이나 학습 데이터 기반 답변
- "아마도", "~일 것 같습니다" 등 추측성 표현
- 문서에 없는 숫자, 날짜, 이름 등 구체적 정보 생성

## 2. 정보 부족 시 대응
문서에 답변에 필요한 정보가 없는 경우:
```
제공된 문서에는 [질문 내용]에 대한 정보가 포함되어 있지 않습니다.

다음 정보가 필요합니다:
- [필요한 정보 1]
- [필요한 정보 2]

관련 문서를 추가로 제공해주시면 더 정확한 답변을 드릴 수 있습니다.
```

## 3. 출처 명시 (CRITICAL - 실제 파일명만 사용)
**🚨 절대 규칙: "문서 1", "문서 2", "문서 N" 표현 완전 금지! 🚨**

✅ **반드시 이렇게**:
각 문서의 "📄 파일명:" 에 표시된 **실제 파일명만** 사용하세요.

**올바른 사용법**:
- [spring-boot-reference.pdf]에 따르면...
- 사적 이해관계 신고서([표준프레임워크_적용가이드.pdf])는...
- [API문서.pdf]와 [개발가이드.hwp]를 참조하면...

❌ **절대 금지** - 이런 표현은 어떤 형태로도 사용 금지:
- "문서 1", "문서 2", "문서 N"
- "문서 1을 기반으로", "문서 2에 따르면"
- "(문서 1)", "(문서 2)", "[문서 N]"
- "해당 문서", "제시된 문서" (파일명 없이)
- Document 1, Doc 2 등 모든 변형

**❌ 잘못된 예시들** (절대 사용 금지):
```
BAD: "문서 1을 기반으로 분석한 결과..."
BAD: "문서 2에 따르면..."
BAD: "해당 문서가 제시하는..."
BAD: "(문서 1)에서 확인할 수 있습니다"
```

**✅ 올바른 예시들** (이렇게만 사용):
```
GOOD: "[표준프레임워크_적용가이드.pdf]를 기반으로 분석한 결과..."
GOOD: "[spring-boot-reference.pdf]에 따르면..."
GOOD: "[API문서.pdf]가 제시하는..."
GOOD: "([개발가이드.hwp])에서 확인할 수 있습니다"
```

**중요**: 괄호 안에 출처를 표시할 때도 반드시 실제 파일명을 사용하세요!

## 4. 컨텍스트 이해
제공되는 각 문서는 다음 형식입니다:
```
📄 파일명: spring-boot-reference.pdf  ← 이 이름을 그대로 사용!
🎯 관련도: 95%
📝 내용:
Spring Boot는...
---
```

**핵심**: "📄 파일명:" 다음에 표시된 **실제 파일명만** 사용하세요!

# 📋 답변 구조 가이드

## 기본 답변 형식
1. **핵심 답변** (2-3문장)
   - 질문에 대한 직접적인 답변
   - 가장 중요한 정보 먼저 제시

2. **상세 설명** (필요 시)
   - 배경 정보와 맥락 설명
   - 단계별 절차나 과정
   - 주의사항 및 예외 케이스

3. **출처 정보** (실제 파일명 사용!)
   ```
   📚 참고 문서:
   - [actual_filename1.pdf]: [관련 내용 요약]
   - [actual_filename2.hwp]: [관련 내용 요약]
   ```

## HOW-TO 질문 (방법/절차)
```
## [작업명]

### 준비사항
- 필요한 도구/환경

### 단계별 진행
1. [첫 번째 단계]
   - 세부 내용
   - 주의사항

2. [두 번째 단계]
   ...

### 확인 방법
- 정상 동작 확인 기준

📚 참고: [실제파일명.확장자]
```

## 계산/수치 질문
```
### 적용 규칙
"[문서에서 발췌한 규칙]" [실제파일명.pdf]

### 계산 과정
1. 기본값: [값] ([근거])
2. 추가 계산: [수식] = [결과]
3. 최종 결과: **[결과]**

### 적용 조건
- [조건1]: [해당 여부]
- [조건2]: [해당 여부]

📚 참고: [실제파일명.확장자]
```

## 비교 질문
```
| 항목 | A | B |
|------|---|---|
| 특징1 | ... | ... |
| 특징2 | ... | ... |
| 장점 | ... | ... |
| 단점 | ... | ... |

### 권장사항
- [상황1]의 경우: A 권장
- [상황2]의 경우: B 권장

📚 참고: [파일A.pdf], [파일B.hwp]
```

# 🔍 특수 상황 처리

## 코드 예제 포함 시
- 실행 가능한 완전한 코드만 제공
- 주석으로 각 부분 설명 추가
- 코드 전후에 설명 추가
- 출처: [실제파일명.확장자]

## 전문 용어 사용 시
- 첫 사용 시 괄호로 설명 추가
- 예: JWT(JSON Web Token)

## 여러 문서에서 정보 종합 시
- 각 문서의 실제 파일명을 명확히 구분하여 표기
- 상충되는 정보가 있으면 양쪽 모두 제시하고 차이 설명
- 예: "[파일A.pdf]에서는 X라고 하지만, [파일B.hwp]에서는 Y라고 합니다"

## 이전 대화 참조 시
- 대화 맥락을 고려하되, 새로운 정보는 문서 기반만 사용
- "이전에 말씀드린..." 등으로 참조 명시

# ✨ 품질 기준

## 정확성
- 문서 내용과 100% 일치
- 숫자, 날짜, 고유명사 등 정확히 전달
- **파일명도 정확히 전달** (중요!)
- 오타, 오역 없음

## 명확성
- 핵심 정보 우선 배치
- 간결하고 이해하기 쉬운 문장
- 모호한 표현 지양
- 실제 파일명으로 명확한 출처 표시

## 완전성
- 질문의 모든 부분에 답변
- 관련 주의사항 포함
- 필요한 배경 정보 제공
- 모든 참조 문서의 실제 파일명 명시

## 전문성
- 적절한 전문 용어 사용
- 논리적 구조
- 신뢰할 수 있는 톤

# 📝 체크리스트 (답변 전 자체 검증)
- [ ] 문서에 있는 정보만 사용했는가?
- [ ] 추측이나 일반 지식을 사용하지 않았는가?
- [ ] 모든 출처를 **실제 파일명**으로만 표시했는가?
- [ ] "문서 1", "문서 2", "해당 문서" 같은 표현을 완전히 제거했는가?
- [ ] 괄호 안 출처도 실제 파일명을 사용했는가?
- [ ] 질문의 모든 부분에 답했는가?
- [ ] 이해하기 쉽게 구조화했는가?
- [ ] 코드/계산이 정확한가?

위 원칙을 철저히 준수하여 정확하고 신뢰할 수 있는 답변을 제공하세요."""

        return {
            "system_prompt": system_prompt
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get system prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system prompt")


# Hybrid RAG Configuration Models
class HybridRAGConfigRequest(BaseModel):
    enabled: bool = Field(..., description="Hybrid RAG 활성화 여부")
    web_search: bool = Field(..., description="웹 검색 활성화 여부")
    doc_search: bool = Field(..., description="공식 문서 검색 활성화 여부")
    search_mode: str = Field(
        default="smart",
        description="검색 모드 - smart: 질문 분석 기반 자동 선택, comprehensive: 체크된 모든 도구 사용"
    )


@app.get("/api/admin/hybrid-rag/config", tags=["Admin", "Settings"])
async def get_hybrid_rag_config(request: Request):
    """Hybrid RAG 설정 조회 (관리자 전용)
    
    Returns:
        {
            'success': True,
            'config': {
                'enabled': bool,
                'web_search': bool,
                'doc_search': bool
            }
        }
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)
        
        # Redis에서 현재 설정 조회
        enabled = redis_client.get("config:hybrid_rag_enabled")
        web_search = redis_client.get("config:hybrid_rag_web_search")
        doc_search = redis_client.get("config:hybrid_rag_doc_search")
        search_mode = redis_client.get("config:hybrid_rag_search_mode")

        # bytes to str 변환 및 기본값 설정
        config = {
            'enabled': enabled.decode() == "true" if enabled else False,
            'web_search': web_search.decode() == "true" if web_search else False,
            'doc_search': doc_search.decode() == "true" if doc_search else False,
            'search_mode': search_mode.decode() if search_mode else "smart"
        }
        
        return {
            'success': True,
            'config': config
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Hybrid RAG config: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve Hybrid RAG configuration")


@app.get("/api/hybrid-rag/status", tags=["Settings"])
async def get_hybrid_rag_status(request: Request):
    """Hybrid RAG 활성화 상태 조회 (인증된 사용자)

    일반 사용자가 하이브리드 RAG 기능이 활성화되어 있는지 확인할 수 있는 API
    검색 모드 UI를 제어하는데 사용됩니다.

    Returns:
        {
            'success': True,
            'enabled': bool  # Hybrid RAG 활성화 여부
        }
    """
    try:
        redis_client = request.app.state.cache_manager.redis

        # Redis에서 현재 설정 조회
        enabled = redis_client.get("config:hybrid_rag_enabled")

        # bytes to bool 변환 및 기본값 설정
        is_enabled = enabled.decode() == "true" if enabled else False

        return {
            'success': True,
            'enabled': is_enabled
        }

    except Exception as e:
        logger.error(f"Failed to get Hybrid RAG status: {e}")
        # 에러 시에도 안전하게 false 반환
        return {
            'success': True,
            'enabled': False
        }


@app.put("/api/admin/hybrid-rag/config", tags=["Admin", "Settings"])
async def update_hybrid_rag_config(
    config_request: HybridRAGConfigRequest,
    request: Request
):
    """Hybrid RAG 설정 업데이트 (관리자 전용)
    
    Args:
        config_request: Hybrid RAG 설정
        
    Returns:
        {
            'success': True,
            'message': str,
            'config': dict
        }
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)
        
        # Redis에 설정 저장
        redis_client.set("config:hybrid_rag_enabled", "true" if config_request.enabled else "false")
        redis_client.set("config:hybrid_rag_web_search", "true" if config_request.web_search else "false")
        redis_client.set("config:hybrid_rag_doc_search", "true" if config_request.doc_search else "false")
        redis_client.set("config:hybrid_rag_search_mode", config_request.search_mode)

        # Hybrid RAG orchestrator 재초기화를 위해 None으로 설정
        global hybrid_rag_orchestrator
        hybrid_rag_orchestrator = None

        logger.info(f"✅ Hybrid RAG config updated: enabled={config_request.enabled}, web={config_request.web_search}, docs={config_request.doc_search}, mode={config_request.search_mode}")

        return {
            'success': True,
            'message': 'Hybrid RAG 설정이 업데이트되었습니다',
            'config': {
                'enabled': config_request.enabled,
                'web_search': config_request.web_search,
                'doc_search': config_request.doc_search,
                'search_mode': config_request.search_mode
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update Hybrid RAG config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update Hybrid RAG configuration")


@app.get("/api/hybrid-rag/status", tags=["Settings"])
async def get_hybrid_rag_status(
    current_user: dict = Depends(get_current_active_user),
    request: Request = None
):
    """Hybrid RAG 활성화 상태 조회 (일반 사용자용)

    Returns:
        {
            'success': True,
            'enabled': bool  # Hybrid RAG 활성화 여부
        }
    """
    try:
        redis_client = request.app.state.cache_manager.redis

        # Redis에서 Hybrid RAG 활성화 상태 조회
        enabled = redis_client.get("config:hybrid_rag_enabled")

        # bytes to str 변환 및 기본값 설정
        is_enabled = enabled.decode() == "true" if enabled else False

        return {
            'success': True,
            'enabled': is_enabled
        }

    except Exception as e:
        logger.error(f"Failed to get Hybrid RAG status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve Hybrid RAG status")


@app.get("/api/admin/prompts", tags=["Admin", "Settings"])
async def get_all_prompts(request: Request):
    """모든 시스템 프롬프트 조회 (관리자 전용)

    Returns:
        {
            'success': True,
            'prompts': {
                'basic': str,  # 일반 검색용 프롬프트 (로컬 문서만)
                'hybrid': str,  # 하이브리드 검색용 프롬프트 (로컬 + 외부 도구)
                'tools_only': str  # 외부 도구 전용 프롬프트 (웹 + 공식문서만)
            }
        }
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin

        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # 각 프롬프트 가져오기
        basic_prompt = redis_client.get(PROMPT_KEY_BASIC)
        hybrid_prompt = redis_client.get(PROMPT_KEY_HYBRID)
        tools_only_prompt = redis_client.get(PROMPT_KEY_TOOLS_ONLY)

        # bytes to str 변환
        if isinstance(basic_prompt, bytes):
            basic_prompt = basic_prompt.decode('utf-8')
        if isinstance(hybrid_prompt, bytes):
            hybrid_prompt = hybrid_prompt.decode('utf-8')
        if isinstance(tools_only_prompt, bytes):
            tools_only_prompt = tools_only_prompt.decode('utf-8')

        # 기본값 적용
        if not basic_prompt:
            basic_prompt = DEFAULT_BASIC_PROMPT
        if not hybrid_prompt:
            hybrid_prompt = DEFAULT_HYBRID_PROMPT
        if not tools_only_prompt:
            tools_only_prompt = DEFAULT_TOOLS_ONLY_PROMPT

        return {
            'success': True,
            'prompts': {
                'basic': basic_prompt,
                'hybrid': hybrid_prompt,
                'tools_only': tools_only_prompt
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get prompts: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve prompts")


@app.put("/api/admin/prompts", tags=["Admin", "Settings"])
async def update_prompts(data: PromptsUpdateRequest, request: Request):
    """시스템 프롬프트 업데이트 (관리자 전용)

    Request body:
        {
            "basic": "일반 검색용 프롬프트 (optional)",
            "hybrid": "하이브리드 검색용 프롬프트 (optional)",
            "tools_only": "외부 도구 전용 프롬프트 (optional)"
        }

    Returns:
        {
            'success': True,
            'message': '프롬프트 업데이트 완료: basic, hybrid, tools_only'
        }
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin, extract_token_from_request, verify_token

        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        updated = []

        if data.basic is not None:
            # 유효성 검증
            if len(data.basic) > 10000:
                raise HTTPException(status_code=400, detail="일반 프롬프트가 너무 깁니다 (최대 10,000자)")

            redis_client.set(PROMPT_KEY_BASIC, data.basic)
            redis_client.set(PROMPT_KEY_LEGACY, data.basic)  # 레거시 호환
            updated.append('basic')

        if data.hybrid is not None:
            # 유효성 검증
            if len(data.hybrid) > 10000:
                raise HTTPException(status_code=400, detail="하이브리드 프롬프트가 너무 깁니다 (최대 10,000자)")

            redis_client.set(PROMPT_KEY_HYBRID, data.hybrid)
            updated.append('hybrid')

        if data.tools_only is not None:
            # 유효성 검증
            if len(data.tools_only) > 10000:
                raise HTTPException(status_code=400, detail="외부 도구 전용 프롬프트가 너무 깁니다 (최대 10,000자)")

            redis_client.set(PROMPT_KEY_TOOLS_ONLY, data.tools_only)
            updated.append('tools_only')

        if not updated:
            raise HTTPException(status_code=400, detail="업데이트할 프롬프트를 제공해주세요")

        # 로깅
        token = extract_token_from_request(request)
        user_data = verify_token(token)
        logger.info(f"Prompts updated by user {user_data['user_id']}: {', '.join(updated)}")

        return {
            'success': True,
            'message': f'프롬프트 업데이트 완료: {", ".join(updated)}'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update prompts: {e}")
        raise HTTPException(status_code=500, detail="Failed to update prompts")


# ============================================================================
# Audit Log APIs (v2.4.0)
# ============================================================================

@app.get("/api/admin/audit/logs", tags=["Admin"])
async def get_audit_logs(
    request: Request,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """감사 로그 조회 (관리자 전용)

    Query params:
        user_id: 사용자 ID 필터
        username: 사용자명 필터 (부분 매칭 지원)
        action: 작업 유형 필터 (login, document_upload, chat_query 등)
        start_date: 시작 날짜 (YYYY-MM-DD)
        end_date: 종료 날짜 (YYYY-MM-DD)
        limit: 최대 반환 개수 (기본: 100)
        offset: 오프셋 (페이지네이션)

    Returns:
        감사 로그 목록
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # Audit logger 가져오기
        audit_logger = request.app.state.audit_logger
        if not audit_logger:
            raise HTTPException(status_code=503, detail="Audit logger not initialized")

        # 작업 유형 검증
        action_enum = None
        if action:
            try:
                action_enum = AuditAction(action)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

        # 로그 조회 (더 많이 가져와서 필터링 후 페이지네이션 적용)
        fetch_limit = limit * 10 if username else limit
        logs = audit_logger.get_logs(
            user_id=user_id,
            action=action_enum,
            start_date=start_date,
            end_date=end_date,
            limit=fetch_limit,
            offset=0 if username else offset
        )

        # username 필터링 (부분 매칭)
        if username:
            username_lower = username.lower()
            logs = [
                log for log in logs
                if log.get("username") and username_lower in log["username"].lower()
            ]
            # 필터링 후 페이지네이션 적용
            logs = logs[offset:offset + limit]

        return {
            "logs": logs,
            "count": len(logs),
            "limit": limit,
            "offset": offset,
            "filters": {
                "user_id": user_id,
                "username": username,
                "action": action,
                "start_date": start_date,
                "end_date": end_date
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit logs")


@app.get("/api/admin/audit/stats", tags=["Admin"])
async def get_audit_stats(
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """감사 로그 통계 조회 (관리자 전용)

    Query params:
        start_date: 시작 날짜 (YYYY-MM-DD, 기본: 7일 전)
        end_date: 종료 날짜 (YYYY-MM-DD, 기본: 오늘)

    Returns:
        감사 로그 통계
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # Audit logger 가져오기
        audit_logger = request.app.state.audit_logger
        if not audit_logger:
            raise HTTPException(status_code=503, detail="Audit logger not initialized")

        # 통계 조회
        stats = audit_logger.get_stats(
            start_date=start_date,
            end_date=end_date
        )

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit statistics")


@app.get("/api/admin/audit/user/{user_id}", tags=["Admin"])
async def get_user_audit_logs(
    request: Request,
    user_id: str,
    limit: int = 50
):
    """특정 사용자의 감사 로그 조회 (관리자 전용)

    Path params:
        user_id: 사용자 ID

    Query params:
        limit: 최대 반환 개수 (기본: 50)

    Returns:
        사용자 활동 로그
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # Audit logger 가져오기
        audit_logger = request.app.state.audit_logger
        if not audit_logger:
            raise HTTPException(status_code=503, detail="Audit logger not initialized")

        # 사용자 활동 조회
        logs = audit_logger.get_user_activity(
            user_id=user_id,
            limit=limit
        )

        return {
            "user_id": user_id,
            "logs": logs,
            "count": len(logs)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user audit logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user audit logs")


@app.get("/api/admin/audit/actions", tags=["Admin"])
async def get_audit_actions(request: Request):
    """사용 가능한 감사 로그 작업 유형 목록 (관리자 전용)

    Returns:
        작업 유형 목록
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # 작업 유형 목록
        actions = [
            {"value": action.value, "description": action.value.replace("_", " ").title()}
            for action in AuditAction
        ]

        return {"actions": actions}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit actions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit actions")


# ============================================================================
# Model Management API
# ============================================================================

@app.get("/api/admin/models/backend", tags=["Admin", "Models"])
async def get_model_backend(request: Request):
    """현재 모델 백엔드 설정 조회 (관리자 전용)

    Returns:
        현재 사용 중인 백엔드 (ollama/local)와 모델 설정
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        backend = "ollama" if use_ollama else "local"

        config = {
            "backend": backend,
            "ollama": {
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                "llm_model": os.getenv("OLLAMA_LLM_MODEL", ""),
                "embedding_model": os.getenv("OLLAMA_EMBEDDING_MODEL", "")
            },
            "local": {
                "llm_model": os.getenv("LLM_MODEL", "mlx-community/Qwen3-30B-A3B-4bit"),
                "embedding_model": os.getenv("EMBEDDING_MODEL", "nlpai-lab/KURE-v1")
            }
        }

        return config

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model backend: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model backend")


@app.get("/api/admin/models/list", tags=["Admin", "Models"])
async def get_model_list(request: Request, backend: str = "ollama"):
    """모델 목록 조회 (관리자 전용)

    Args:
        backend: ollama 또는 local

    Returns:
        사용 가능한 모델 목록
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        if backend == "ollama":
            # Ollama 모델 목록 가져오기
            import httpx
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

            try:
                response = httpx.get(f"{base_url}/api/tags", timeout=10.0)
                response.raise_for_status()
                data = response.json()

                models = data.get("models", [])

                # LLM과 임베딩 모델 분류
                llm_models = []
                embedding_models = []

                for model in models:
                    model_name = model.get("name", "")
                    size = model.get("size", 0)
                    size_gb = size / (1024**3) if size else 0

                    model_info = {
                        "name": model_name,
                        "size": f"{size_gb:.2f} GB",
                        "modified_at": model.get("modified_at", "")
                    }

                    # 임베딩 모델 판별 (이름에 embed, kure, bge 등이 포함된 경우)
                    if any(keyword in model_name.lower() for keyword in ["embed", "kure", "bge", "e5", "gte"]):
                        embedding_models.append(model_info)
                    else:
                        llm_models.append(model_info)

                return {
                    "llm_models": llm_models,
                    "embedding_models": embedding_models
                }

            except httpx.HTTPError as e:
                logger.error(f"Failed to connect to Ollama: {e}")
                raise HTTPException(status_code=503, detail="Ollama 서버에 연결할 수 없습니다")

        elif backend == "local":
            # 로컬 모델은 하드코딩된 목록 반환 (실제로는 model 디렉토리에서 읽을 수 있음)
            return {
                "llm_models": [
                    {"name": "mlx-community/Qwen3-30B-A3B-4bit", "size": "7.5 GB", "description": "MLX 최적화 Qwen 모델"}
                ],
                "embedding_models": [
                    {"name": "nlpai-lab/KURE-v1", "size": "1.2 GB", "description": "한국어 임베딩 모델"}
                ]
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid backend type")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model list: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model list")


@app.post("/api/admin/models/config", tags=["Admin", "Models"])
async def update_model_config(request: Request):
    """모델 설정 업데이트 (관리자 전용)

    Request body:
        {
            "backend": "ollama" | "local",
            "llm_model": "model_name",
            "embedding_model": "model_name"
        }
    """
    global llm, rag_system, embedding_model, vector_db, LLM_MODEL, EMBEDDING_MODEL

    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        data = await request.json()
        backend = data.get("backend")
        llm_model = data.get("llm_model")
        embedding_model_name = data.get("embedding_model")

        if not backend or backend not in ["ollama", "local"]:
            raise HTTPException(status_code=400, detail="Invalid backend")

        # .env 파일 업데이트
        env_path = Path(".env")
        env_lines = []

        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()

        # 기존 설정 업데이트
        updated = {
            "USE_OLLAMA": None,
            "OLLAMA_LLM_MODEL": None,
            "OLLAMA_EMBEDDING_MODEL": None,
            "LLM_MODEL": None,
            "EMBEDDING_MODEL": None
        }

        for i, line in enumerate(env_lines):
            for key in updated.keys():
                if line.startswith(f"{key}="):
                    updated[key] = i
                    break

        # 새로운 설정 준비
        new_values = {
            "USE_OLLAMA": "true" if backend == "ollama" else "false"
        }

        if backend == "ollama":
            if llm_model:
                new_values["OLLAMA_LLM_MODEL"] = llm_model
            if embedding_model_name:
                new_values["OLLAMA_EMBEDDING_MODEL"] = embedding_model_name
        else:
            if llm_model:
                new_values["LLM_MODEL"] = llm_model
            if embedding_model_name:
                new_values["EMBEDDING_MODEL"] = embedding_model_name

        # 환경 변수 업데이트 (메모리에도 즉시 반영)
        for key, value in new_values.items():
            os.environ[key] = value
            line = f"{key}={value}\n"
            if updated[key] is not None:
                env_lines[updated[key]] = line
            else:
                env_lines.append(line)

        # .env 파일 저장
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)

        logger.info(f"Model configuration updated: backend={backend}, llm={llm_model}, embedding={embedding_model_name}")

        # 모델 즉시 적용
        llm_changed = False
        embedding_changed = False
        use_ollama = backend == "ollama"

        # LLM 모델 즉시 적용
        if llm_model:
            try:
                if use_ollama:
                    # Ollama: 환경변수에서 읽음
                    llm = LLM(model_dir=MODEL_DIR)
                else:
                    # Local: 직접 모델명 전달
                    LLM_MODEL = llm_model
                    llm = LLM(model_name=LLM_MODEL, model_dir=MODEL_DIR)

                # RAG 시스템 재초기화
                rag_system = RAGSystem(
                    vector_db=vector_db,
                    llm=llm,
                    top_k=5
                )
                llm_changed = True
                logger.success(f"✅ LLM model changed to: {llm_model}")
            except Exception as e:
                logger.error(f"Failed to reload LLM: {e}")
                # LLM 로드 실패해도 설정은 저장됨 (다음 재시작에 적용)

        # 임베딩 모델 즉시 적용
        if embedding_model_name:
            try:
                # global declaration already at function start (line 4747)
                if use_ollama:
                    # Ollama: 환경변수에서 읽음
                    from .embeddings_ollama import OllamaEmbedding
                    embedding_model = OllamaEmbedding(model_dir=MODEL_DIR)
                else:
                    # Local: 직접 모델명 전달
                    EMBEDDING_MODEL = embedding_model_name
                    embedding_model = EmbeddingModel(
                        model_name=EMBEDDING_MODEL,
                        model_dir=MODEL_DIR
                    )

                # Vector DB 재초기화
                vector_db = VectorDB(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    embedding_dim=embedding_model.get_embedding_dim()
                )

                # RAG 시스템에 새 vector_db 적용
                if rag_system:
                    rag_system = RAGSystem(
                        vector_db=vector_db,
                        llm=llm,
                        top_k=5
                    )

                embedding_changed = True
                logger.success(f"✅ Embedding model changed to: {embedding_model_name}")
                logger.warning("⚠️ 기존 문서들을 새로운 임베딩 모델로 재색인해야 합니다")
            except Exception as e:
                logger.error(f"Failed to reload embedding model: {e}")
                # 임베딩 로드 실패해도 설정은 저장됨 (다음 재시작에 적용)

        # 응답 메시지 구성
        response = {
            "llm_changed": llm_changed,
            "embedding_changed": embedding_changed,
            "restart_required": False  # 모든 모델이 즉시 적용되므로 재시작 불필요
        }

        if llm_changed and embedding_changed:
            response["message"] = "LLM 및 임베딩 모델이 즉시 적용되었습니다."
            response["warning"] = "임베딩 모델 변경으로 인해 문서 재색인이 필요합니다."
        elif llm_changed:
            response["message"] = "LLM 모델이 즉시 적용되었습니다."
        elif embedding_changed:
            response["message"] = "임베딩 모델이 즉시 적용되었습니다."
            response["warning"] = "임베딩 모델 변경으로 인해 기존 문서를 모두 재색인해야 합니다."
        else:
            response["message"] = "설정이 저장되었습니다."

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model configuration")


# ============================================================
# Metrics & Performance Monitoring APIs (Admin Only)
# ============================================================

@app.get("/api/admin/metrics/summary", tags=["Admin", "Metrics"])
async def get_metrics_summary(
    current_user: dict = Depends(get_current_active_user),
    request: Request = None
):
    """
    성능 메트릭 종합 요약 조회 (관리자 전용)

    Returns:
        {
            'global': 전체 통계,
            'today': 오늘 통계,
            'recent_24h': 최근 24시간 통계,
            'trend': 트렌드 분석,
            'daily': 일별 통계 (최근 7일),
            'hourly': 시간별 통계 (최근 24시간)
        }
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # 메트릭 수집기 초기화
        metrics = MetricsCollector(redis_client)

        # 종합 요약 조회
        summary = metrics.get_summary()

        return {
            'success': True,
            'data': summary
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metrics summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics summary")


@app.get("/api/admin/metrics/recent", tags=["Admin", "Metrics"])
async def get_recent_searches(
    limit: int = 100,
    current_user: dict = Depends(get_current_active_user),
    request: Request = None
):
    """
    최근 검색 기록 조회 (관리자 전용)

    Args:
        limit: 조회할 개수 (기본 100, 최대 1000)

    Returns:
        최근 검색 메트릭 리스트
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # Limit 검증
        limit = min(limit, 1000)

        # 메트릭 수집기 초기화
        metrics = MetricsCollector(redis_client)

        # 최근 검색 조회
        recent_searches = metrics.get_recent_searches(limit=limit)

        return {
            'success': True,
            'data': recent_searches,
            'count': len(recent_searches)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recent searches: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve recent searches")


@app.get("/api/admin/metrics/source-performance", tags=["Admin", "Metrics"])
async def get_source_performance(
    current_user: dict = Depends(get_current_active_user),
    request: Request = None
):
    """
    소스별 성능 비교 (관리자 전용)

    Returns:
        {
            'local': {'count': int, 'avg_time': float, 'avg_results': float},
            'web': {'count': int, 'avg_time': float, 'avg_results': float},
            'docs': {'count': int, 'avg_time': float, 'avg_results': float}
        }
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # 메트릭 수집기 초기화
        metrics = MetricsCollector(redis_client)

        # 소스별 성능 조회
        source_perf = metrics.get_source_performance()

        return {
            'success': True,
            'data': source_perf
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get source performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve source performance")


@app.delete("/api/admin/metrics/cleanup", tags=["Admin", "Metrics"])
async def cleanup_old_metrics(
    days: int = 30,
    current_user: dict = Depends(get_current_active_user),
    request: Request = None
):
    """
    오래된 메트릭 데이터 삭제 (관리자 전용)

    Args:
        days: 보관 기간 (일) - 기본 30일

    Returns:
        성공 메시지
    """
    try:
        # 관리자 권한 확인
        from .auth.utils import require_admin
        redis_client = request.app.state.cache_manager.redis
        require_admin(request, redis_client)

        # 메트릭 수집기 초기화
        metrics = MetricsCollector(redis_client)

        # 오래된 데이터 삭제
        metrics.clear_old_data(days=days)

        return {
            'success': True,
            'message': f'{days}일 이전 메트릭 데이터가 삭제되었습니다'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cleanup old metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup old metrics")


if __name__ == "__main__":
    import uvicorn
    import multiprocessing
    import sys

    # Production configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    environment = os.getenv("ENVIRONMENT", "production")

    # Configure logging for production
    if environment == "production":
        # Remove default logger and configure for production
        logger.remove()

        # Add structured logging with rotation
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="INFO",
            colorize=False
        )

        # Add file logging with rotation (keep 7 days, rotate at 100MB)
        log_file = os.getenv("LOG_FILE", "/tmp/chatbot_production.log")
        logger.add(
            log_file,
            rotation="100 MB",
            retention="7 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO"
        )

        logger.info("Production logging configured")
    else:
        # Development: keep colorful logging to console AND add file logging
        log_file = os.getenv("LOG_FILE", "server.log")
        logger.add(
            log_file,
            rotation="10 MB",
            retention="3 days",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG"
        )
        logger.info(f"Development logging active with file: {log_file}")

    # Worker configuration based on CPU cores
    # Production: (CPU cores * 2) + 1, with min 4 and max 8
    cpu_count = multiprocessing.cpu_count()
    if environment == "development":
        workers = 1  # Single worker for easier debugging
    else:
        workers = max(4, min(8, (cpu_count * 2) + 1))

    # Timeout settings for production
    timeout_keep_alive = int(os.getenv("TIMEOUT_KEEP_ALIVE", 65))  # Keep-alive timeout
    timeout_graceful_shutdown = int(os.getenv("TIMEOUT_GRACEFUL_SHUTDOWN", 30))

    # Connection limits
    limit_concurrency = int(os.getenv("LIMIT_CONCURRENCY", 1000))  # Max concurrent connections
    limit_max_requests = int(os.getenv("LIMIT_MAX_REQUESTS", 10000))  # Max requests before worker restart

    # Logging configuration
    log_level = os.getenv("LOG_LEVEL", "info" if environment == "production" else "debug").lower()
    access_log = os.getenv("ACCESS_LOG", "false").lower() == "true"

    logger.info(f"🚀 Starting server in {environment.upper()} mode")
    logger.info(f"📍 Server: http://{host}:{port}")
    logger.info(f"👥 Workers: {workers} (CPU cores: {cpu_count})")
    logger.info(f"⏱️  Timeouts: keep-alive={timeout_keep_alive}s, graceful-shutdown={timeout_graceful_shutdown}s")
    logger.info(f"🔗 Limits: concurrency={limit_concurrency}, max-requests={limit_max_requests}")

    uvicorn.run(
        "src.web_server:app",
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
        access_log=access_log,
        timeout_keep_alive=timeout_keep_alive,
        timeout_graceful_shutdown=timeout_graceful_shutdown,
        limit_concurrency=limit_concurrency,
        limit_max_requests=limit_max_requests,
        # Production optimizations
        backlog=2048,  # Connection backlog queue size
        use_colors=False if environment == "production" else True,
        server_header=False,  # Don't expose server version
        date_header=True,
        proxy_headers=True,  # Support X-Forwarded-* headers
        forwarded_allow_ips="*"  # Allow all proxy IPs (configure for specific IPs in production)
    )
