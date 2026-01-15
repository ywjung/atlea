"""
Ollama Embedding Module - OpenAI-compatible API integration

📝 Changelog:
- 2025-12-28: Created Ollama embeddings integration
  - Uses /api/embed endpoint
  - Same interface as EmbeddingModel class
  - Caching support for performance
"""

import os
import hashlib
import httpx
from typing import List, Union, Dict
from loguru import logger


class OllamaEmbedding:
    """
    Ollama Embeddings using /api/embed endpoint

    Compatible with daynice/kure-v1 and other Ollama embedding models
    """

    def __init__(
        self,
        model_name: str = None,
        base_url: str = None,
        model_dir: str = None,  # For compatibility with EmbeddingModel
        device: str = "auto",   # For compatibility
        cache_size: int = 1000,
        **kwargs  # Accept any other arguments for compatibility
    ):
        """
        Initialize Ollama Embedding

        Args:
            model_name: Ollama model name (e.g., "daynice/kure-v1:latest")
            base_url: Ollama API base URL (default: http://localhost:11434)
            cache_size: LRU cache size for embeddings (default: 1000)
        """
        # Get configuration from environment or use defaults
        self.model_name = model_name or os.getenv("OLLAMA_EMBEDDING_MODEL", "daynice/kure-v1:latest")
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.cache_size = cache_size
        self._embedding_cache: Dict[str, List[float]] = {}
        self._embedding_dim = None  # Will be determined on first use

        # For compatibility with code that accesses embedding_model.model
        self.model = self

        logger.info(f"Initializing Ollama Embedding: {self.model_name}")
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

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        return hashlib.md5(text.encode()).hexdigest()

    def _get_from_cache(self, text: str) -> List[float]:
        """Get embedding from cache"""
        key = self._get_cache_key(text)
        return self._embedding_cache.get(key)

    def _add_to_cache(self, text: str, embedding: List[float]):
        """Add embedding to cache with LRU eviction"""
        if len(self._embedding_cache) >= self.cache_size:
            # Simple FIFO eviction
            first_key = next(iter(self._embedding_cache))
            del self._embedding_cache[first_key]

        key = self._get_cache_key(text)
        self._embedding_cache[key] = embedding

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,  # For compatibility, not used in Ollama API
        show_progress_bar: bool = False,  # For compatibility
        normalize: bool = True,  # Ollama returns normalized embeddings
        use_cache: bool = True
    ) -> List[List[float]]:
        """
        Encode texts to embeddings with caching

        Args:
            texts: Single text or list of texts
            batch_size: Not used (Ollama handles batching internally)
            show_progress_bar: Not used
            normalize: Not used (Ollama returns L2-normalized embeddings)
            use_cache: Use embedding cache (default: True)

        Returns:
            List of embeddings (each embedding is a list of floats)
        """
        single_text = isinstance(texts, str)
        if single_text:
            texts = [texts]

        # Check cache for single queries (most common case)
        if use_cache and len(texts) == 1:
            cached = self._get_from_cache(texts[0])
            if cached is not None:
                return [cached]

        try:
            # Ollama /api/embed endpoint
            payload = {
                "model": self.model_name,
                "input": texts  # Ollama accepts array directly
            }

            response = httpx.post(
                f"{self.base_url}/api/embed",
                json=payload,
                timeout=60.0
            )
            response.raise_for_status()

            result_data = response.json()
            embeddings = result_data.get("embeddings", [])

            # Store embedding dimension on first use
            if self._embedding_dim is None and len(embeddings) > 0:
                self._embedding_dim = len(embeddings[0])

            # Cache single query embeddings
            if use_cache and len(texts) == 1:
                self._add_to_cache(texts[0], embeddings[0])

            return embeddings

        except Exception as e:
            logger.error(f"Ollama embedding failed: {e}")
            raise

    def get_embedding_dim(self) -> int:
        """Get embedding dimension"""
        if self._embedding_dim is None:
            # Get dimension by encoding a test string
            test_embedding = self.encode("test", use_cache=False)
            self._embedding_dim = len(test_embedding[0])
        return self._embedding_dim

    def __call__(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Shorthand for encode"""
        return self.encode(texts)
