"""
LLM Module - Multi-platform support (MLX for Mac, Transformers for NVIDIA/CPU)
"""

import re
from typing import List, Dict, Optional, Generator
from loguru import logger
from .model_manager import ModelManager
from .platform_utils import get_platform_detector


class LLM:
    """
    Multi-platform LLM with automatic backend selection:
    - MLX for Apple Silicon (optimized)
    - Transformers + CUDA for NVIDIA GPU
    - Transformers + CPU for other platforms
    """

    def __init__(
        self,
        model_name: str = "mlx-community/Qwen2.5-3B-Instruct-4bit",
        model_dir: str = "./model",
        max_tokens: int = 2048,
        temperature: float = 0.7
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
        self.system_prompt = "당신은 문서 내용을 기반으로 질문에 답변하는 AI 어시스턴트입니다. 제공된 문서 내용을 바탕으로 정확하고 상세하게 답변해주세요. 이전 대화 내용을 참고하여 맥락에 맞는 답변을 제공하세요."
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
        # Format context
        context_text = "\n\n".join([
            f"[문서: {doc['filename']}]\n{doc['text']}"
            for doc in context
        ])

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

        # Add current query with context
        messages.append({
            "role": "user",
            "content": f"다음 문서들을 참고하여 질문에 답변해주세요.\n\n"
                      f"=== 참고 문서 ===\n{context_text}\n\n"
                      f"=== 질문 ===\n{query}\n\n"
                      f"=== 답변 ===\n"
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

        if stream:
            return self._stream_response_mlx(prompt, max_tokens, temperature)
        else:
            response = generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                temp=temperature
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
        top_k: int = 5
    ):
        """
        Initialize RAG system

        Args:
            vector_db: Vector database instance
            llm: LLM instance
            top_k: Number of documents to retrieve
        """
        self.vector_db = vector_db
        self.llm = llm
        self.top_k = top_k
        logger.info("RAG system initialized")

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

            # Increase top_k when using filters to ensure we find relevant docs within filtered set
            # Filters apply AFTER vector search, so we need more candidates
            search_k = k
            if group_ids or document_ids:
                search_k = min(k * 20, 100)  # Increase by 20x, max 100
                logger.info(f"Using expanded search_k={search_k} for filtered search (returning top {k})")

            # Retrieve relevant documents (use native vector_db filtering)
            logger.warning(f"LLM QUERY: Retrieving top {k} documents")
            logger.warning(f"LLM QUERY: document_ids={document_ids}")
            logger.warning(f"LLM QUERY: group_ids={group_ids}")
            logger.warning(f"LLM QUERY: search_k={search_k}")
            context_docs = self.vector_db.search(
                query_embedding,
                top_k=search_k,
                group_ids=group_ids,
                document_ids=document_ids
            )
            logger.warning(f"LLM QUERY: Got {len(context_docs)} documents from vector_db")

            # Limit to requested k after filtering
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
