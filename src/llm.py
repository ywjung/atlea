"""
LLM Module - Qwen with MLX for Apple GPU
"""

import re
from typing import List, Dict, Optional, Generator
from loguru import logger
from mlx_lm import load, generate, stream_generate
from .model_manager import ModelManager


class LLM:
    """Qwen LLM with Apple GPU acceleration via MLX"""

    def __init__(
        self,
        model_name: str = "mlx-community/Qwen2.5-3B-Instruct-4bit",
        model_dir: str = "./model",
        max_tokens: int = 2048,
        temperature: float = 0.7
    ):
        """
        Initialize LLM

        Args:
            model_name: Model name (MLX-compatible)
            model_dir: Directory to store models
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
        """
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = "당신은 문서 내용을 기반으로 질문에 답변하는 AI 어시스턴트입니다. 제공된 문서 내용을 바탕으로 정확하고 상세하게 답변해주세요. 이전 대화 내용을 참고하여 맥락에 맞는 답변을 제공하세요."
        self.model_manager = ModelManager(model_dir)

        logger.info(f"Loading LLM: {model_name}")
        try:
            # Download model if needed
            local_path = self.model_manager.download_if_needed(model_name)

            # Load model with MLX
            self.model, self.tokenizer = load(local_path)
            logger.success(f"LLM loaded successfully (using Apple GPU via MLX)")
        except Exception as e:
            logger.error(f"Failed to load LLM: {e}")
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

        # Create prompt using Qwen's chat template
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

            # Generate response
            logger.debug(f"Generating response for query: {query[:50]}...")

            if stream:
                # Stream generation
                return self._stream_response(prompt, max_tokens=max_tok, temperature=temp)
            else:
                # Non-streaming generation
                response = generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=max_tok
                )

                # Clean response to remove <think> tags
                cleaned_response = self._clean_response(response)
                logger.success("Response generated successfully")
                return cleaned_response
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            raise

    def _stream_response(self, prompt: str, max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """
        Stream response generation with real-time display

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Yields:
            Response chunks (individual tokens), with <think> tags filtered
            Optimized for fastest initial response
        """
        buffer = ""
        inside_think = False

        # Potential tag prefixes to watch for
        tag_prefixes = ['<', '<t', '<th', '<thi', '<thin', '<think', '</', '</t', '</th', '</thi', '</thin', '</think']

        for response in stream_generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens
        ):
            if hasattr(response, 'text') and response.text:
                token = response.text
                buffer += token

                # Limit buffer size
                if len(buffer) > 100:
                    buffer = buffer[-100:]

                # Check for complete opening tag
                if '<think>' in buffer and not inside_think:
                    inside_think = True
                    think_pos = buffer.find('<think>')
                    buffer = buffer[think_pos + 7:]
                    continue

                # Check for complete closing tag
                if inside_think and '</think>' in buffer:
                    inside_think = False
                    think_end_pos = buffer.find('</think>')
                    buffer = buffer[think_end_pos + 8:]
                    if buffer:
                        yield buffer
                        buffer = ""
                    continue

                # Skip content inside thinking blocks
                if inside_think:
                    continue

                # Outside thinking - aggressive streaming
                # Only hold back if buffer ends with potential tag prefix
                should_hold = False
                for prefix in tag_prefixes:
                    if buffer.endswith(prefix):
                        should_hold = True
                        break

                if not should_hold and len(buffer) > 0:
                    # Yield everything - no tag is forming
                    yield buffer
                    buffer = ""
                elif should_hold and len(buffer) > 8:
                    # Tag might be forming, but buffer is large
                    # Yield everything except the potential tag prefix
                    to_yield = buffer[:-8]
                    buffer = buffer[-8:]
                    if to_yield:
                        yield to_yield

        # Yield remaining buffer
        if buffer and not inside_think:
            yield buffer

        logger.success("Streaming response completed")

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
        document_ids: Optional[List[str]] = None
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

        Returns:
            Dictionary with answer and context (or generator if streaming)
        """
        k = top_k or self.top_k

        try:
            # Build filter expression for document filtering
            filter_expr = None
            if document_ids:
                # Create OR condition for multiple documents
                # Escape special characters for Redis Search TAG fields
                def escape_redis_tag(value):
                    # For TAG fields, escape: , . < > { } [ ] " ' : ; ! @ # $ % ^ & * ( ) - + = ~ `
                    # Replace problematic characters with escaped versions
                    import re
                    # For TAG fields in Redis, we need to match exactly
                    # Use double quotes and escape internal quotes
                    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                    return f'"{escaped}"'

                filters = [f"@filename:{escape_redis_tag(doc_id)}" for doc_id in document_ids]
                filter_expr = "|".join(filters)
                if len(filters) > 1:
                    filter_expr = f"({filter_expr})"
                logger.info(f"Filtering by documents: {document_ids}")
                logger.debug(f"Filter expression: {filter_expr}")

            # Retrieve relevant documents
            logger.info(f"Retrieving top {k} documents")
            context_docs = self.vector_db.search(query_embedding, top_k=k, filter_expr=filter_expr)

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
                # Return streaming generator
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
                # Generate complete answer
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
