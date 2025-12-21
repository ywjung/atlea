"""
Platform Detection Utility
Automatically detects the best ML framework based on available hardware
"""

import platform
import sys
from loguru import logger


class PlatformDetector:
    """Detect platform and determine best ML framework"""

    def __init__(self):
        self.system = platform.system()
        self.machine = platform.machine()
        self._detect_capabilities()

    def _detect_capabilities(self):
        """Detect hardware capabilities"""
        self.has_cuda = False
        self.has_mps = False
        self.has_mlx = False

        # Check for PyTorch and its capabilities
        try:
            import torch
            self.has_cuda = torch.cuda.is_available()
            self.has_mps = torch.backends.mps.is_available()
            logger.info(f"PyTorch detected - CUDA: {self.has_cuda}, MPS: {self.has_mps}")
        except ImportError:
            logger.warning("PyTorch not installed")

        # Check for MLX (Apple Silicon only)
        if self.system == "Darwin" and self.machine == "arm64":
            try:
                import mlx
                self.has_mlx = True
                logger.info("MLX available (Apple Silicon)")
            except ImportError:
                logger.warning("MLX not installed on Apple Silicon")

    def get_llm_backend(self) -> str:
        """
        Determine best LLM backend

        Returns:
            'mlx' for Apple Silicon with MLX
            'transformers' for CUDA/CPU
        """
        if self.has_mlx:
            logger.info("Using MLX backend for LLM (Apple Silicon)")
            return "mlx"
        elif self.has_cuda or True:  # Always fall back to transformers
            logger.info("Using Transformers backend for LLM")
            return "transformers"
        else:
            logger.warning("No optimal backend found, using Transformers with CPU")
            return "transformers"

    def get_device(self) -> str:
        """
        Get device for PyTorch models

        Returns:
            'cuda' for NVIDIA GPU
            'mps' for Apple Silicon
            'cpu' for CPU
        """
        if self.has_cuda:
            return "cuda"
        elif self.has_mps:
            return "mps"
        else:
            return "cpu"

    def get_model_dtype(self):
        """
        Get appropriate dtype for models

        Returns:
            torch dtype or None for MLX
        """
        if self.get_llm_backend() == "mlx":
            return None  # MLX handles dtype automatically

        try:
            import torch
            if self.has_cuda:
                # NVIDIA: use float16 for speed
                return torch.float16
            elif self.has_mps:
                # Apple MPS: use float32 (better compatibility)
                return torch.float32
            else:
                # CPU: use float32
                return torch.float32
        except ImportError:
            return None

    def print_info(self):
        """Print platform information"""
        logger.info("="*50)
        logger.info("Platform Information:")
        logger.info(f"  System: {self.system}")
        logger.info(f"  Machine: {self.machine}")
        logger.info(f"  Python: {sys.version.split()[0]}")
        logger.info(f"  CUDA Available: {self.has_cuda}")
        logger.info(f"  MPS Available: {self.has_mps}")
        logger.info(f"  MLX Available: {self.has_mlx}")
        logger.info(f"  Recommended LLM Backend: {self.get_llm_backend()}")
        logger.info(f"  Recommended Device: {self.get_device()}")
        logger.info("="*50)


# Global instance
_detector = None

def get_platform_detector() -> PlatformDetector:
    """Get global platform detector instance"""
    global _detector
    if _detector is None:
        _detector = PlatformDetector()
        _detector.print_info()
    return _detector
