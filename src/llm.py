"""
LLM Module - Multi-platform support (MLX for Mac, Transformers for NVIDIA/CPU)

📝 Changelog:
- 2025-12-28: Enhanced system prompt with structured guidelines and anti-hallucination rules
  - Added comprehensive answer structure templates
  - Improved context formatting with metadata (filename, relevance score)
  - Added quality checklist and special case handling
"""

import os
import re
import numpy as np
from typing import List, Dict, Optional, Generator
from loguru import logger
from dotenv import load_dotenv
from .model_manager import ModelManager
from .platform_utils import get_platform_detector

# Load environment variables
load_dotenv()


class LLM:
    """
    Multi-platform LLM with automatic backend selection:
    - MLX for Apple Silicon (optimized)
    - Transformers + CUDA for NVIDIA GPU
    - Transformers + CPU for other platforms
    """

    def __init__(
        self,
        model_name: str = "mlx-community/Qwen3-30B-A3B-4bit",
        model_dir: str = "./model",
        max_tokens: int = 1000,
        temperature: float = 0.5
    ):
        """
        Initialize LLM with automatic platform detection

        Args:
            model_name: Model name (MLX or HuggingFace format)
            model_dir: Directory to store models
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
        """
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
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

## 4. 문서 개수 표기 규칙 ⚠️ CRITICAL
**중요**: 문서 개수를 언급할 때는 반드시 **고유한 파일명 개수**를 기준으로 합니다.

✅ 올바른 표현:
- 제공된 문서에서 파일명을 확인: [파일A.pdf], [파일B.txt] → "2개 문서"
- 같은 파일에서 여러 청크가 제공되어도 1개 문서로 카운트
- 예: 5개 청크가 모두 "S2B FaQ1.pdf"에서 왔다면 → "1개 문서"
- 예: 3개 청크가 "문서A.pdf", 2개 청크가 "문서B.pdf" → "2개 문서"

❌ 잘못된 표현:
- 청크 개수를 문서 개수로 언급
- "5개 문서"라고 하면서 실제로는 2개 파일만 참조
- 정확한 파일 개수를 세지 않고 추측

**실제 사용 예시**:
```
잘못된 답변: "이 답변은 제공된 5개 문서의 내용을 요약한 것입니다."
(실제 파일: file1.pdf, file2.txt만 사용)

올바른 답변: "이 답변은 제공된 2개 문서(file1.pdf, file2.txt)의 내용을 요약한 것입니다."
```

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

[문서명 출처]
```

## 계산/수치 질문
```
### 적용 규칙
"[문서에서 발췌한 규칙]" [문서명]

### 계산 과정
1. 기본값: [값] ([근거])
2. 추가 계산: [수식] = [결과]
3. 최종 결과: **[결과]**

### 적용 조건
- [조건1]: [해당 여부]
- [조건2]: [해당 여부]

[문서명 출처]
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

[문서명 출처]
```

# 🔍 특수 상황 처리

## 코드 예제 포함 시
- 실행 가능한 완전한 코드만 제공
- 주석으로 각 부분 설명 추가
- 코드 전후에 설명 추가

## 전문 용어 사용 시
- 첫 사용 시 괄호로 설명 추가
- 예: JWT(JSON Web Token)

## 여러 문서에서 정보 종합 시
- 각 문서의 정보를 명확히 구분
- 상충되는 정보가 있으면 양쪽 모두 제시하고 차이 설명

## 이전 대화 참조 시
- 대화 맥락을 고려하되, 새로운 정보는 문서 기반만 사용
- "이전에 말씀드린..." 등으로 참조 명시

# ✨ 품질 기준

## 정확성
- 문서 내용과 100% 일치
- 숫자, 날짜, 고유명사 등 정확히 전달
- 오타, 오역 없음

## 명확성
- 핵심 정보 우선 배치
- 간결하고 이해하기 쉬운 문장
- 모호한 표현 지양

## 완전성
- 질문의 모든 부분에 답변
- 관련 주의사항 포함
- 필요한 배경 정보 제공

## 전문성
- 적절한 전문 용어 사용
- 논리적 구조
- 신뢰할 수 있는 톤

# 📝 체크리스트 (답변 전 자체 검증)
- [ ] 문서에 있는 정보만 사용했는가?
- [ ] 추측이나 일반 지식을 사용하지 않았는가?
- [ ] 출처를 명확히 표시했는가?
- [ ] **문서 개수를 언급할 때 고유한 파일명 개수로 정확히 세었는가?** (청크 개수 아님!)
- [ ] 질문의 모든 부분에 답했는가?
- [ ] 이해하기 쉽게 구조화했는가?
- [ ] 코드/계산이 정확한가?

위 원칙을 철저히 준수하여 정확하고 신뢰할 수 있는 답변을 제공하세요."""
        self.model_manager = ModelManager(model_dir)

        # Detect platform and select backend
        self.platform = get_platform_detector()
        self.backend = self.platform.get_llm_backend()

        logger.info(f"Loading LLM: {model_name} (backend: {self.backend})")

        try:
            # Download model if needed
            local_path = self.model_manager.download_if_needed(model_name)

            if self.backend == "mlx":
                self._load_mlx(local_path)
            else:
                self._load_transformers(local_path)

            logger.success(f"LLM loaded successfully (backend: {self.backend})")
        except Exception as e:
            logger.error(f"Failed to load LLM: {e}")
            raise

    def _load_mlx(self, local_path: str):
        """Load model using MLX (Apple Silicon)"""
        try:
            from mlx_lm import load
            self.model, self.tokenizer = load(local_path)
            logger.info("Using MLX backend (Apple GPU acceleration)")
        except ImportError as e:
            logger.error("MLX not available. Install with: pip install mlx-lm")
            raise

    def _load_transformers(self, local_path: str):
        """Load model using Transformers (NVIDIA/CPU)"""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch

            device = self.platform.get_device()
            dtype = self.platform.get_model_dtype()

            logger.info(f"Loading model on device: {device} with dtype: {dtype}")

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                local_path,
                trust_remote_code=True
            )

            # Load model with appropriate settings
            if device == "cuda":
                # NVIDIA GPU: use float16 and device_map
                self.model = AutoModelForCausalLM.from_pretrained(
                    local_path,
                    torch_dtype=dtype,
                    device_map="auto",
                    trust_remote_code=True
                )
                logger.info("Using CUDA backend (NVIDIA GPU acceleration)")
            else:
                # CPU or MPS
                self.model = AutoModelForCausalLM.from_pretrained(
                    local_path,
                    torch_dtype=dtype,
                    trust_remote_code=True
                )
                self.model = self.model.to(device)
                logger.info(f"Using Transformers backend ({device})")

            self.device = device
            self.model.eval()  # Set to evaluation mode

        except ImportError as e:
            logger.error("Transformers not available. Install with: pip install transformers torch")
            raise

    def create_prompt(self, query: str, context: List[Dict], history: Optional[List[Dict]] = None, system_prompt: Optional[str] = None) -> str:
        """
        Create prompt with context and conversation history

        Args:
            query: User query
            context: List of context documents
            history: Conversation history [{"role": "user/assistant", "content": "..."}]
            system_prompt: Custom system prompt (defaults to instance prompt)

        Returns:
            Formatted prompt
        """
        # Format context with enhanced metadata
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

        # Calculate unique document count (by filename)
        unique_filenames = list(set([doc.get('filename', '') for doc in context if doc.get('filename')]))
        num_unique_docs = len(unique_filenames)
        num_chunks = len(context)

        # Use provided system prompt or fall back to instance default
        sys_prompt = system_prompt if system_prompt is not None else self.system_prompt

        # Create messages using chat template
        messages = [
            {
                "role": "system",
                "content": sys_prompt
            }
        ]

        # Add conversation history if provided
        if history:
            for msg in history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        # Add current query with enhanced context
        messages.append({
            "role": "user",
            "content": f"""아래 제공된 문서들을 참고하여 질문에 답변해주세요.

=== 📚 참고 문서 ({num_unique_docs}개 파일, {num_chunks}개 청크) ===
고유 파일: {', '.join(unique_filenames)}

{context_text}

=== ❓ 사용자 질문 ===
{query}

=== ✍️ 답변 작성 ===
위 문서의 정보만을 사용하여 정확하고 구조화된 답변을 작성하세요.

⚠️ 중요: 답변에서 문서 개수를 언급할 때는 반드시 **{num_unique_docs}개 문서**라고 표현하세요 (청크 개수 {num_chunks}개가 아님).
파일명: {', '.join(unique_filenames)}
"""
        })

        # Use tokenizer's chat template
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        return prompt

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
        Generate response based on query and context

        Args:
            query: User query
            context: Retrieved context documents
            stream: Whether to stream response
            history: Conversation history
            temperature: Sampling temperature (defaults to instance value)
            max_tokens: Maximum tokens to generate (defaults to instance value)
            system_prompt: Custom system prompt (defaults to instance value)

        Returns:
            Generated response (string) or generator (if streaming)
        """
        # Use provided values or fall back to instance defaults
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_tokens if max_tokens is not None else self.max_tokens
        sys_prompt = system_prompt if system_prompt is not None else self.system_prompt

        try:
            # Create prompt with history and custom system prompt
            prompt = self.create_prompt(query, context, history, system_prompt=sys_prompt)

            logger.debug(f"Generating response for query: {query[:50]}...")

            if self.backend == "mlx":
                return self._generate_mlx(prompt, max_tok, temp, stream)
            else:
                return self._generate_transformers(prompt, max_tok, temp, stream)

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            raise

    def _generate_mlx(self, prompt: str, max_tokens: int, temperature: float, stream: bool):
        """Generate using MLX backend"""
        from mlx_lm import generate, stream_generate
        from mlx_lm.sample_utils import make_sampler

        if stream:
            return self._stream_response_mlx(prompt, max_tokens, temperature)
        else:
            # Create sampler with temperature (new MLX-LM API)
            sampler = make_sampler(temp=temperature)

            response = generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler
            )
            cleaned_response = self._clean_response(response)
            logger.success("Response generated successfully (MLX)")
            return cleaned_response

    def _generate_transformers(self, prompt: str, max_tokens: int, temperature: float, stream: bool):
        """Generate using Transformers backend"""
        import torch

        # Tokenize input
        inputs = self.tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Generation parameters
        gen_kwargs = {
            "max_new_tokens": max_tokens,
            "temperature": temperature,
            "do_sample": temperature > 0,
            "pad_token_id": self.tokenizer.eos_token_id,
        }

        if stream:
            return self._stream_response_transformers(inputs, gen_kwargs)
        else:
            with torch.no_grad():
                outputs = self.model.generate(**inputs, **gen_kwargs)

            # Decode response
            response = self.tokenizer.decode(
                outputs[0][inputs['input_ids'].shape[1]:],
                skip_special_tokens=True
            )
            cleaned_response = self._clean_response(response)
            logger.success("Response generated successfully (Transformers)")
            return cleaned_response

    def _stream_response_mlx(self, prompt: str, max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """Stream response using MLX backend"""
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        buffer = ""
        inside_think = False
        tag_prefixes = ['<', '<t', '<th', '<thi', '<thin', '<think', '</', '</t', '</th', '</thi', '</thin', '</think']

        # Create sampler with temperature (new MLX-LM API)
        sampler = make_sampler(temp=temperature)

        for response in stream_generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=sampler
        ):
            if hasattr(response, 'text') and response.text:
                token = response.text
                buffer += token

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

        if buffer and not inside_think:
            yield buffer

        logger.success("Streaming response completed (MLX)")

    def _stream_response_transformers(self, inputs: dict, gen_kwargs: dict) -> Generator[str, None, None]:
        """Stream response using Transformers backend"""
        import torch
        from transformers import TextIteratorStreamer
        from threading import Thread

        # Create streamer
        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True
        )

        # Update generation kwargs with streamer
        gen_kwargs["streamer"] = streamer

        # Start generation in a separate thread
        generation_kwargs = {**inputs, **gen_kwargs}
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        # Stream tokens with think tag filtering
        buffer = ""
        inside_think = False
        tag_prefixes = ['<', '<t', '<th', '<thi', '<thin', '<think', '</', '</t', '</th', '</thi', '</thin', '</think']

        for token in streamer:
            buffer += token

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

        if buffer and not inside_think:
            yield buffer

        thread.join()
        logger.success("Streaming response completed (Transformers)")

    def __call__(self, query: str, context: List[Dict]) -> str:
        """Shorthand for generate_response"""
        return self.generate_response(query, context)


class RAGSystem:
    """Complete RAG system combining retrieval and generation"""

    def __init__(
        self,
        vector_db,
        llm: LLM,
        top_k: int = 5,
        use_reranker: bool = True
    ):
        """
        Initialize RAG system

        Args:
            vector_db: Vector database instance
            llm: LLM instance
            top_k: Number of documents to retrieve
            use_reranker: Whether to use reranker (default: True)
        """
        self.vector_db = vector_db
        self.llm = llm
        self.top_k = top_k
        self.use_reranker = use_reranker
        self._reranker = None  # Lazy loading
        logger.info(f"RAG system initialized (reranker: {'enabled' if use_reranker else 'disabled'})")

    @property
    def reranker(self):
        """Lazy loading of reranker"""
        if self.use_reranker and self._reranker is None:
            logger.info("🔄 Initializing reranker on first use...")
            self._reranker = Reranker()
        return self._reranker

    def query(
        self,
        question: str,
        query_embedding: List[float],
        top_k: Optional[int] = None,
        stream: bool = False,
        history: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None
    ):
        """
        Query RAG system

        Args:
            question: User question
            query_embedding: Question embedding
            top_k: Number of documents to retrieve (override default)
            stream: Whether to stream the response
            history: Conversation history
            document_ids: Optional list of document IDs/filenames to filter by
            group_ids: Optional list of group IDs to filter by (OR logic)

        Returns:
            Dictionary with answer and context (or generator if streaming)
        """
        k = top_k or self.top_k

        try:
            # Log filtering info
            if group_ids:
                logger.info(f"Filtering by groups: {group_ids}")
            if document_ids:
                logger.info(f"Filtering by documents: {document_ids}")

            # Determine retrieval_k for hybrid search
            # If using reranker: retrieve more candidates (20) for reranking
            # If not using reranker: retrieve exact amount needed
            if self.use_reranker:
                retrieval_k = max(k * 4, 20)  # At least 20 for good reranking
                logger.info(f"Reranker enabled: retrieving {retrieval_k} candidates for reranking")
            else:
                retrieval_k = k
                logger.info(f"Reranker disabled: retrieving {retrieval_k} documents")

            # Increase retrieval_k when using filters
            if group_ids or document_ids:
                retrieval_k = min(retrieval_k * 3, 100)  # Increase by 3x, max 100
                logger.info(f"Using expanded retrieval_k={retrieval_k} for filtered search")

            # Retrieve relevant documents using hybrid search (Vector + BM25)
            logger.info(f"Hybrid search: Query='{question[:100]}...'")
            if document_ids:
                logger.info(f"Document filter: {document_ids}")
            if group_ids:
                logger.info(f"Group filter: {group_ids}")
            
            context_docs = self.vector_db.hybrid_search(
                query_text=question,
                query_embedding=query_embedding,
                top_k=retrieval_k,
                group_ids=group_ids,
                document_ids=document_ids,
                retrieval_k=20  # Retrieve 20 from each method before RRF fusion
            )
            logger.info(f"Hybrid search returned {len(context_docs)} documents")

            # Apply reranking if enabled
            if self.use_reranker and context_docs:
                logger.info(f"🔄 Reranking {len(context_docs)} documents...")
                context_docs = self.reranker.rerank(
                    query=question,
                    documents=context_docs,
                    top_k=k  # Return final k documents
                )
                logger.info(f"✅ Reranking complete. Selected top {len(context_docs)} documents")
            else:
                # Limit to requested k without reranking
                if len(context_docs) > k:
                    context_docs = context_docs[:k]

            if not context_docs:
                logger.warning("No relevant documents found")
                return {
                    "answer": "죄송합니다. 관련된 문서를 찾을 수 없습니다.",
                    "context": [],
                    "sources": []
                }

            # Prepare sources
            sources = list(set([doc['filename'] for doc in context_docs]))

            if stream:
                logger.info("Generating streaming answer")
                return {
                    "answer": self.llm.generate_response(
                        question,
                        context_docs,
                        stream=True,
                        history=history,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        system_prompt=system_prompt
                    ),
                    "context": context_docs,
                    "sources": sources
                }
            else:
                logger.info("Generating answer")
                answer = self.llm.generate_response(
                    question,
                    context_docs,
                    stream=False,
                    history=history,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt
                )

                return {
                    "answer": answer,
                    "context": context_docs,
                    "sources": sources
                }
        except Exception as e:
            logger.error(f"RAG query failed: {e}")
            raise


class Reranker:
    """
    Cross-encoder based reranker for improving search result relevance

    Uses a cross-encoder model to calculate precise relevance scores between
    query and documents, providing more accurate ranking than bi-encoder approaches.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: Optional[str] = None
    ):
        """
        Initialize reranker with cross-encoder model

        Args:
            model_name: Cross-encoder model name from sentence-transformers
            device: Device to run on ('cuda', 'mps', 'cpu'). Auto-detected if None.
        """
        from sentence_transformers import CrossEncoder
        import torch

        self.model_name = model_name

        # Auto-detect device if not specified
        if device is None:
            if torch.cuda.is_available():
                device = 'cuda'
            elif torch.backends.mps.is_available():
                device = 'mps'
            else:
                device = 'cpu'

        self.device = device
        logger.info(f"Initializing Reranker with model: {model_name} on device: {device}")

        # Load cross-encoder model
        try:
            self.model = CrossEncoder(model_name, device=device)
            logger.success(f"Reranker initialized successfully on {device}")
        except Exception as e:
            logger.error(f"Failed to initialize reranker: {e}")
            raise

    def rerank(
        self,
        query: str,
        documents: List[Dict],
        top_k: Optional[int] = None
    ) -> List[Dict]:
        """
        Rerank documents using cross-encoder

        Args:
            query: User query
            documents: List of documents with 'text' field
            top_k: Number of top documents to return (None = return all)

        Returns:
            Reranked list of documents with updated 'score' field
        """
        if not documents:
            return []

        try:
            logger.info(f"Reranking {len(documents)} documents for query: '{query[:50]}...'")

            # Prepare query-document pairs
            pairs = [[query, doc['text']] for doc in documents]

            # Calculate relevance scores (batch processing)
            # Cross-Encoder returns raw logits (can be negative)
            raw_scores = self.model.predict(pairs)

            # Apply sigmoid normalization to convert logits to 0-1 probability range
            # sigmoid(x) = 1 / (1 + e^(-x))
            # This ensures all scores are positive and interpretable as relevance probability
            normalized_scores = 1 / (1 + np.exp(-raw_scores))

            # Add normalized scores to documents
            for doc, raw_score, norm_score in zip(documents, raw_scores, normalized_scores):
                # Store raw logit for debugging
                doc['raw_rerank_score'] = float(raw_score)
                # Store normalized score as main score
                doc['rerank_score'] = float(norm_score)
                # Keep original score as 'original_score' for debugging
                if 'score' in doc:
                    doc['original_score'] = doc['score']
                # Use normalized score (0-1 range, always positive)
                doc['score'] = float(norm_score)

            # Sort by rerank score (descending)
            reranked_docs = sorted(documents, key=lambda x: x['rerank_score'], reverse=True)

            # Return top_k if specified
            if top_k is not None:
                reranked_docs = reranked_docs[:top_k]

            logger.info(f"Reranking complete. Top normalized score: {reranked_docs[0]['rerank_score']:.4f}")
            logger.debug(f"Normalized score range: {reranked_docs[-1]['rerank_score']:.4f} to {reranked_docs[0]['rerank_score']:.4f}")
            logger.debug(f"Raw score range: {reranked_docs[-1].get('raw_rerank_score', 0):.4f} to {reranked_docs[0].get('raw_rerank_score', 0):.4f}")

            return reranked_docs

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Return original documents on failure
            logger.warning("Returning original document order due to reranking failure")
            return documents


# ============================================
# Ollama Integration
# ============================================

USE_OLLAMA = os.getenv("USE_OLLAMA", "false").lower() == "true"

if USE_OLLAMA:
    from .llm_ollama import OllamaLLM
    # Replace LLM with OllamaLLM for transparent integration
    LLM = OllamaLLM
    logger.info("🚀 Using Ollama LLM backend")
else:
    logger.info("🚀 Using local LLM backend (MLX/Transformers)")
