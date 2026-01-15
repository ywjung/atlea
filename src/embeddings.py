"""
Embedding Module - KURE-v1 (Korean Universal Representation Embeddings) with optimization and caching
"""

import os
import torch
import hashlib
from typing import List, Union, Dict
from functools import lru_cache
from loguru import logger
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from .model_manager import ModelManager

# Load environment variables
load_dotenv()


class EmbeddingModel:
    """KURE-v1 (Korean Universal Representation Embeddings) with Apple GPU optimization and query caching"""

    def __init__(
        self,
        model_name: str = "nlpai-lab/KURE-v1",
        model_dir: str = "./model",
        device: str = "auto",
        cache_size: int = 1000
    ):
        """
        Initialize embedding model

        Args:
            model_name: HuggingFace model name
            model_dir: Directory to store models
            device: Device to use ('auto', 'mps', 'cpu')
            cache_size: LRU cache size for embeddings (default: 1000)
        """
        self.model_name = model_name
        self.model_manager = ModelManager(model_dir)
        self.cache_size = cache_size
        self._embedding_cache: Dict[str, List[float]] = {}

        # Download model if needed
        logger.info("Initializing embedding model...")
        local_path = self.model_manager.download_if_needed(model_name)

        # Determine device (use Apple MPS if available)
        if device == "auto":
            if torch.backends.mps.is_available():
                self.device = "mps"
                logger.info("Using Apple Metal Performance Shaders (MPS)")
            elif torch.cuda.is_available():
                self.device = "cuda"
                logger.info("Using CUDA")
            else:
                self.device = "cpu"
                logger.info("Using CPU")
        else:
            self.device = device

        # Load model
        try:
            self.model = SentenceTransformer(
                local_path,
                device=self.device,
                trust_remote_code=True
            )
            logger.success(f"Embedding model loaded: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

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
            # Simple FIFO eviction (LRU would need OrderedDict)
            first_key = next(iter(self._embedding_cache))
            del self._embedding_cache[first_key]

        key = self._get_cache_key(text)
        self._embedding_cache[key] = embedding

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        show_progress_bar: bool = False,
        normalize: bool = True,
        use_cache: bool = True
    ) -> List[List[float]]:
        """
        Encode texts to embeddings with caching

        Args:
            texts: Single text or list of texts
            batch_size: Batch size for encoding
            show_progress_bar: Show progress bar
            normalize: Normalize embeddings to unit vectors
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
                logger.debug(f"Embedding cache HIT for query: {texts[0][:50]}...")
                return [cached]

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress_bar,
                normalize_embeddings=normalize,
                convert_to_numpy=True
            )
            result = embeddings.tolist()

            # Cache single query embeddings
            if use_cache and len(texts) == 1:
                self._add_to_cache(texts[0], result[0])
                logger.debug(f"Embedding cached for: {texts[0][:50]}...")

            return result
        except Exception as e:
            logger.error(f"Encoding failed: {e}")
            raise

    def get_embedding_dim(self) -> int:
        """Get embedding dimension"""
        return self.model.get_sentence_embedding_dimension()

    def __call__(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Shorthand for encode"""
        return self.encode(texts)


# ============================================
# Ollama Integration
# ============================================

USE_OLLAMA = os.getenv("USE_OLLAMA", "false").lower() == "true"

if USE_OLLAMA:
    from .embeddings_ollama import OllamaEmbedding
    # Replace EmbeddingModel with OllamaEmbedding for transparent integration
    EmbeddingModel = OllamaEmbedding
    logger.info("🚀 Using Ollama Embedding backend")
else:
    logger.info("🚀 Using local Embedding backend (SentenceTransformers)")
