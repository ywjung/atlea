"""
Ollama LLM Module - OpenAI-compatible API integration

📝 Changelog:
- 2025-12-28: Created Ollama integration for local LLM inference
  - OpenAI-compatible API support
  - Streaming and non-streaming responses
  - Same interface as original LLM class
"""

import os
import re
from typing import List, Dict, Optional, Generator
from loguru import logger
import httpx


class OllamaLLM:
    """
    Ollama LLM using OpenAI-compatible API

    Supports local inference with Ollama-hosted models
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.5,
        model_dir: Optional[str] = None,  # For compatibility with LLM class
        **kwargs  # Accept any other arguments for compatibility
    ):
        """
        Initialize Ollama LLM

        Args:
            model_name: Ollama model name (e.g., "alibayram/Qwen3-30B-A3B-Instruct-2507:latest")
            base_url: Ollama API base URL (default: http://localhost:11434)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
        """
        # Get configuration from environment or use defaults
        self.model_name = model_name or os.getenv("OLLAMA_LLM_MODEL", "alibayram/Qwen3-30B-A3B-Instruct-2507:latest")
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Enhanced system prompt (same as original LLM)
        self.system_prompt = """당신은 문서 기반 질의응답 전문 AI 어시스턴트입니다.

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

## 3. 출처 명시
- 답변의 각 주장마다 출처 문서명 표시: [문서명]
- 직접 인용 시 따옴표 사용: "원문 내용" [문서명]
- 여러 문서에서 정보를 종합한 경우 모두 표시

# 📋 답변 구조 가이드

## 기본 답변 형식
1. **핵심 답변** (2-3문장)
   - 질문에 대한 직접적인 답변
   - 가장 중요한 정보 먼저 제시

2. **상세 설명** (필요 시)
   - 배경 정보와 맥락 설명
   - 단계별 절차나 과정
   - 주의사항 및 예외 케이스

3. **출처 정보**
   ```
   📚 참고 문서:
   - [문서명1]: [관련 내용 요약]
   - [문서명2]: [관련 내용 요약]
   ```

# 📝 체크리스트 (답변 전 자체 검증)
- [ ] 문서에 있는 정보만 사용했는가?
- [ ] 추측이나 일반 지식을 사용하지 않았는가?
- [ ] 출처를 명확히 표시했는가?
- [ ] 질문의 모든 부분에 답했는가?
- [ ] 이해하기 쉽게 구조화했는가?

위 원칙을 철저히 준수하여 정확하고 신뢰할 수 있는 답변을 제공하세요."""

        logger.info(f"Initializing Ollama LLM: {self.model_name}")
        logger.info(f"Base URL: {self.base_url}")

        # Verify Ollama is running
        try:
            self._verify_connection()
            logger.success("Connected to Ollama successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            logger.error("Please ensure Ollama is running: 'ollama serve'")
            raise

    def _verify_connection(self):
        """Verify Ollama API is accessible"""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            models = response.json().get("models", [])
            logger.info(f"Found {len(models)} Ollama models")

            # Check if our model is available
            model_names = [m["name"] for m in models]
            if self.model_name not in model_names:
                logger.warning(f"Model {self.model_name} not found in Ollama")
                logger.info(f"Available models: {model_names}")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}: {e}")

    def create_prompt(
        self,
        query: str,
        context: List[Dict],
        history: Optional[List[Dict]] = None,
        system_prompt: Optional[str] = None
    ) -> List[Dict]:
        """
        Create chat messages with context and conversation history

        Args:
            query: User query
            context: List of context documents
            history: Conversation history
            system_prompt: Custom system prompt

        Returns:
            List of messages for Ollama API
        """
        # Format context with metadata
        context_parts = []
        for idx, doc in enumerate(context, 1):
            score = doc.get('score', 0)
            score_percent = int(score * 100) if isinstance(score, float) else score

            context_part = f"""📄 파일명: {doc['filename']}
🎯 관련도: {score_percent}%
📝 내용:
{doc['text']}
---"""
            context_parts.append(context_part)

        context_text = "\n\n".join(context_parts)

        # Use provided system prompt or default
        sys_prompt = system_prompt if system_prompt is not None else self.system_prompt

        # Create messages
        messages = [
            {
                "role": "system",
                "content": sys_prompt
            }
        ]

        # Add conversation history
        if history:
            for msg in history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        # Add current query with context
        messages.append({
            "role": "user",
            "content": f"""아래 제공된 문서들을 참고하여 질문에 답변해주세요.

=== 📚 참고 문서 ({len(context)}개) ===

{context_text}

=== ❓ 사용자 질문 ===
{query}

=== ✍️ 답변 작성 ===
위 문서의 정보만을 사용하여 정확하고 구조화된 답변을 작성하세요.
"""
        })

        return messages

    def _clean_response(self, text: str) -> str:
        """
        Remove <think> tags and their content from response

        Args:
            text: Raw response text

        Returns:
            Cleaned response text
        """
        # Remove <think>...</think> blocks (including multiline)
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Remove any remaining tags
        cleaned = re.sub(r'</?think>', '', cleaned)
        # Clean up extra whitespace
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
        return cleaned.strip()

    def generate_response(
        self,
        query: str,
        context: List[Dict],
        stream: bool = False,
        history: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ):
        """
        Generate response using Ollama API

        Args:
            query: User query
            context: Retrieved context documents
            stream: Whether to stream response
            history: Conversation history
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            system_prompt: Custom system prompt

        Returns:
            Generated response (string) or generator (if streaming)
        """
        # Use provided values or defaults
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_tokens if max_tokens is not None else self.max_tokens

        try:
            # Create messages
            messages = self.create_prompt(query, context, history, system_prompt)

            if stream:
                return self._stream_response(messages, max_tok, temp)
            else:
                return self._generate_response(messages, max_tok, temp)

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            raise

    def _generate_response(self, messages: List[Dict], max_tokens: int, temperature: float) -> str:
        """Generate non-streaming response"""
        try:
            payload = {
                "model": self.model_name,
                "messages": messages,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                },
                "stream": False
            }

            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=300.0
            )
            response.raise_for_status()

            result = response.json()
            content = result.get("message", {}).get("content", "")

            cleaned_response = self._clean_response(content)
            logger.success("Response generated successfully (Ollama)")
            return cleaned_response

        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise

    def _stream_response(self, messages: List[Dict], max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """Stream response from Ollama"""
        try:
            payload = {
                "model": self.model_name,
                "messages": messages,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                },
                "stream": True
            }

            buffer = ""
            inside_think = False
            tag_prefixes = ['<', '<t', '<th', '<thi', '<thin', '<think', '</', '</t', '</th', '</thi', '</thin', '</think']

            headers = {"Content-Type": "application/json"}

            with httpx.Client(timeout=300.0) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                    headers=headers
                ) as response:
                    response.raise_for_status()

                    for line in response.iter_lines():
                        if not line:
                            continue

                        try:
                            import json
                            data = json.loads(line)

                            if data.get("done"):
                                break

                            token = data.get("message", {}).get("content", "")
                            if not token:
                                continue

                            buffer += token

                            # Keep buffer manageable
                            if len(buffer) > 100:
                                buffer = buffer[-100:]

                            # Handle think tags
                            if '<think>' in buffer and not inside_think:
                                inside_think = True
                                think_pos = buffer.find('<think>')
                                buffer = buffer[think_pos + 7:]
                                continue

                            if inside_think and '</think>' in buffer:
                                inside_think = False
                                think_end_pos = buffer.find('</think>')
                                buffer = buffer[think_end_pos + 8:]
                                if buffer:
                                    yield buffer
                                    buffer = ""
                                continue

                            if inside_think:
                                continue

                            # Stream aggressively
                            should_hold = False
                            for prefix in tag_prefixes:
                                if buffer.endswith(prefix):
                                    should_hold = True
                                    break

                            if not should_hold and len(buffer) > 0:
                                yield buffer
                                buffer = ""
                            elif should_hold and len(buffer) > 8:
                                to_yield = buffer[:-8]
                                buffer = buffer[-8:]
                                if to_yield:
                                    yield to_yield

                        except json.JSONDecodeError:
                            continue

                    # Yield remaining buffer
                    if buffer and not inside_think:
                        yield buffer

            logger.success("Streaming response completed (Ollama)")

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Ollama HTTP error: {e}")
            logger.error(f"  Status: {e.response.status_code}")
            logger.error(f"  URL: {e.request.url}")
            try:
                # Try to read response body if available
                error_text = e.response.read().decode('utf-8') if hasattr(e.response, 'read') else str(e.response)
                logger.error(f"  Response: {error_text[:500]}")
            except:
                logger.error(f"  Response: <unable to read streaming response>")
            raise
        except Exception as e:
            logger.error(f"❌ Ollama streaming error: {e}")
            logger.error(f"  Error type: {type(e).__name__}")
            raise

    def __call__(self, query: str, context: List[Dict]) -> str:
        """Shorthand for generate_response"""
        return self.generate_response(query, context)
