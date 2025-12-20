"""
PDF Service - Extracts text from PDF files using Java PDF Service
"""

import os
import requests
from pathlib import Path
from typing import Optional, Dict, List
from loguru import logger


class PDFService:
    """Process PDF files by calling Java PDF extraction service"""

    def __init__(self, pdf_service_url: str = None):
        """
        Initialize PDF Service

        Args:
            pdf_service_url: URL of the Java PDF service (default: http://localhost:8081)
        """
        self.pdf_service_url = pdf_service_url or os.getenv(
            "PDF_SERVICE_URL", "http://localhost:8081"
        )
        self.api_url = f"{self.pdf_service_url}/api/pdf"
        logger.info(f"PDF Service initialized with service URL: {self.pdf_service_url}")

    def check_service_health(self) -> bool:
        """
        Check if PDF service is running

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = requests.get(
                f"{self.api_url}/health",
                timeout=5
            )
            if response.status_code == 200:
                logger.debug("PDF service is healthy")
                return True
            else:
                logger.warning(f"PDF service health check failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to connect to PDF service: {e}")
            return False

    def extract_text_from_file(self, file_path: str, with_chunks: bool = False,
                              chunk_size: int = 512, chunk_overlap: int = 50) -> Optional[Dict]:
        """
        Extract text from PDF file using file path

        Args:
            file_path: Path to PDF file
            with_chunks: Whether to return chunks (default: False)
            chunk_size: Chunk size for text splitting
            chunk_overlap: Overlap between chunks

        Returns:
            Dict with 'text' and optionally 'chunks', or None if extraction fails
        """
        file_path = Path(file_path)

        if not file_path.exists():
            logger.error(f"PDF file not found: {file_path}")
            return None

        if not file_path.suffix.lower() == '.pdf':
            logger.error(f"Not a PDF file: {file_path}")
            return None

        try:
            logger.info(f"Extracting text from PDF file: {file_path.name}")

            # Prepare request data
            data = {}
            if with_chunks:
                data['chunkSize'] = chunk_size
                data['chunkOverlap'] = chunk_overlap

            # Read file and send as multipart
            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f, 'application/pdf')}
                response = requests.post(
                    f"{self.api_url}/extract",
                    files=files,
                    data=data,
                    timeout=60
                )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    text = result.get('text', '')
                    page_count = result.get('pageCount', 0)
                    processing_time = result.get('processingTimeMs', 0)
                    chunks = result.get('chunks', [])

                    logger.success(
                        f"Successfully extracted text from {file_path.name}: "
                        f"{page_count} pages, {len(text)} chars in {processing_time}ms"
                    )

                    return {
                        'text': text,
                        'chunks': chunks,
                        'pageCount': page_count,
                        'processingTimeMs': processing_time
                    }
                else:
                    error = result.get('error', 'Unknown error')
                    logger.error(f"PDF extraction failed: {error}")
                    return None
            else:
                logger.error(
                    f"PDF service returned error: {response.status_code} - {response.text[:200]}"
                )
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Timeout while extracting text from {file_path.name}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during PDF extraction: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during PDF extraction: {e}")
            return None
