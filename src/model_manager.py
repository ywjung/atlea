"""
Model Manager - Automatic model download and management
"""

import os
from pathlib import Path
from typing import Optional
from loguru import logger
from huggingface_hub import snapshot_download, hf_hub_download


class ModelManager:
    """Manages model downloads and paths"""

    def __init__(self, model_dir: str = "./model"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Model directory: {self.model_dir.absolute()}")

    def get_model_path(self, model_name: str, download: bool = True) -> str:
        """
        Get local path to model, downloading if necessary

        Args:
            model_name: HuggingFace model name (e.g., 'jinaai/jina-embeddings-v3')
            download: Whether to download if not found locally

        Returns:
            Local path to model directory
        """
        # Convert model name to safe directory name
        safe_name = model_name.replace("/", "--")
        local_path = self.model_dir / safe_name

        # Check if model exists locally
        if local_path.exists() and any(local_path.iterdir()):
            logger.info(f"Model found locally: {local_path}")
            return str(local_path)

        if not download:
            raise FileNotFoundError(f"Model not found: {local_path}")

        # Download model
        logger.info(f"Downloading model: {model_name}")
        try:
            snapshot_download(
                repo_id=model_name,
                local_dir=str(local_path),
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            logger.success(f"Model downloaded successfully: {local_path}")
            return str(local_path)
        except Exception as e:
            logger.error(f"Failed to download model {model_name}: {e}")
            raise

    def download_if_needed(self, model_name: str) -> str:
        """
        Ensure model is downloaded and return path

        Args:
            model_name: HuggingFace model name

        Returns:
            Local path to model
        """
        return self.get_model_path(model_name, download=True)

    def list_local_models(self) -> list:
        """List all locally downloaded models"""
        if not self.model_dir.exists():
            return []

        models = []
        for item in self.model_dir.iterdir():
            if item.is_dir() and any(item.iterdir()):
                # Convert back from safe name
                original_name = item.name.replace("--", "/")
                models.append({
                    "name": original_name,
                    "path": str(item),
                    "size": sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                })
        return models
