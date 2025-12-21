"""
HWP Processor - Extracts text from HWP files using Java HWP Service
"""

import os
import base64
import requests
from pathlib import Path
from typing import Optional, Dict
from loguru import logger


class HWPProcessor:
    """Process HWP files by calling Java HWP extraction service with connection pooling"""

    def __init__(self, hwp_service_url: str = None):
        """
        Initialize HWP Processor

        Args:
            hwp_service_url: URL of the Java HWP service (default: http://localhost:8081)
        """
        self.hwp_service_url = hwp_service_url or os.getenv(
            "HWP_SERVICE_URL", "http://localhost:8081"
        )
        self.api_url = f"{self.hwp_service_url}/api/hwp"

        # Connection pooling for better performance
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5,
            pool_maxsize=10,
            max_retries=2
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        logger.info(f"HWP Processor initialized with service URL: {self.hwp_service_url}")

    def check_service_health(self) -> bool:
        """
        Check if HWP service is running

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.api_url}/health",
                timeout=5
            )
            if response.status_code == 200:
                logger.debug("HWP service is healthy")
                return True
            else:
                logger.warning(f"HWP service health check failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to connect to HWP service: {e}")
            return False

    def extract_text_from_file(self, file_path: str) -> Optional[str]:
        """
        Extract text from HWP file using file path

        Args:
            file_path: Path to HWP file

        Returns:
            Extracted text content or None if extraction fails
        """
        file_path = Path(file_path)

        if not file_path.exists():
            logger.error(f"HWP file not found: {file_path}")
            return None

        if not file_path.suffix.lower() == '.hwp':
            logger.error(f"Not an HWP file: {file_path}")
            return None

        try:
            logger.info(f"Extracting text from HWP file: {file_path.name}")

            # Read file and send as multipart
            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f, 'application/octet-stream')}
                response = self.session.post(
                    f"{self.api_url}/extract",
                    files=files,
                    timeout=60
                )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    text = result.get('text', '')
                    paragraph_count = result.get('paragraphCount', 0)
                    processing_time = result.get('processingTimeMs', 0)

                    logger.success(
                        f"Successfully extracted text from {file_path.name}: "
                        f"{paragraph_count} paragraphs in {processing_time}ms"
                    )
                    return text
                else:
                    error = result.get('error', 'Unknown error')
                    logger.error(f"HWP extraction failed: {error}")
                    return None
            else:
                logger.error(
                    f"HWP service returned error: {response.status_code} - {response.text}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to call HWP service: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during HWP extraction: {e}")
            return None

    def extract_text_from_bytes(self, file_bytes: bytes, filename: str = "unknown.hwp") -> Optional[str]:
        """
        Extract text from HWP file bytes using base64 encoding

        Args:
            file_bytes: HWP file content as bytes
            filename: Original filename (for logging)

        Returns:
            Extracted text content or None if extraction fails
        """
        try:
            logger.info(f"Extracting text from HWP bytes: {filename}")

            # Encode to base64
            base64_content = base64.b64encode(file_bytes).decode('utf-8')

            # Send to service
            response = self.session.post(
                f"{self.api_url}/extract/base64",
                json={
                    'fileContent': base64_content,
                    'filename': filename
                },
                headers={'Content-Type': 'application/json'},
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    text = result.get('text', '')
                    paragraph_count = result.get('paragraphCount', 0)
                    processing_time = result.get('processingTimeMs', 0)

                    logger.success(
                        f"Successfully extracted text from {filename}: "
                        f"{paragraph_count} paragraphs in {processing_time}ms"
                    )
                    return text
                else:
                    error = result.get('error', 'Unknown error')
                    logger.error(f"HWP extraction failed: {error}")
                    return None
            else:
                logger.error(
                    f"HWP service returned error: {response.status_code} - {response.text}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to call HWP service: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during HWP extraction: {e}")
            return None

    def is_hwp_file(self, filename: str) -> bool:
        """
        Check if file is HWP format

        Args:
            filename: File name to check

        Returns:
            True if filename has .hwp extension
        """
        return filename.lower().endswith('.hwp')
