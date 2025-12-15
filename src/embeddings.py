"""
Embedding Module - Jina Embeddings v3 with optimization
"""

import torch
from typing import List, Union
from loguru import logger
from sentence_transformers import SentenceTransformer
from .model_manager import ModelManager


class EmbeddingModel:
    """Jina Embeddings v3 with Apple GPU optimization"""

    def __init__(
        self,
        model_name: str = "jinaai/jina-embeddings-v3",
        model_dir: str = "./model",
        device: str = "auto"
    ):
        """
        Initialize embedding model

        Args:
            model_name: HuggingFace model name
            model_dir: Directory to store models
            device: Device to use ('auto', 'mps', 'cpu')
        """
        self.model_name = model_name
        self.model_manager = ModelManager(model_dir)

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

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        show_progress_bar: bool = False,
        normalize: bool = True
    ) -> List[List[float]]:
        """
        Encode texts to embeddings

        Args:
            texts: Single text or list of texts
            batch_size: Batch size for encoding
            show_progress_bar: Show progress bar
            normalize: Normalize embeddings to unit vectors

        Returns:
            List of embeddings (each embedding is a list of floats)
        """
        if isinstance(texts, str):
            texts = [texts]

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress_bar,
                normalize_embeddings=normalize,
                convert_to_numpy=True
            )
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Encoding failed: {e}")
            raise

    def get_embedding_dim(self) -> int:
        """Get embedding dimension"""
        return self.model.get_sentence_embedding_dimension()

    def __call__(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """Shorthand for encode"""
        return self.encode(texts)
