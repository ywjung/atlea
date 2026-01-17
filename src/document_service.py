"""
Document Service - Client for Java Document Extraction API
Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX
"""

import os
import requests
from pathlib import Path
from typing import Optional, Dict
from loguru import logger


class DocumentService:
    """Client for Java Document Extraction Service with connection pooling"""

    def __init__(self, service_url: str = None):
        """
        Initialize document service client

        Args:
            service_url: Base URL of Java document service (default: http://localhost:8081)
        """
        self.service_url = service_url or os.getenv(
            "DOCUMENT_SERVICE_URL", "http://localhost:8081"
        )
        self.extract_endpoint = f"{self.service_url}/api/document/extract"
        self.health_endpoint = f"{self.service_url}/api/document/health"

        # Connection pooling for better performance
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        logger.info(f"Document Service initialized with URL: {self.service_url}")

    def check_service_health(self) -> bool:
        """
        Check if document service is available

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = self.session.get(self.health_endpoint, timeout=2)
            if response.status_code == 200:
                logger.debug("Document service health check: OK")
                return True
            else:
                logger.warning(f"Document service health check failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.debug(f"Document service not available: {e}")
            return False

    def extract_text_from_file(self, file_path: str) -> Optional[Dict]:
        """
        Extract text from document file using Java service

        Args:
            file_path: Path to document file

        Returns:
            Dict with 'text', 'fileType', 'processingTimeMs', or None if extraction fails
        """
        try:
            # Validate file exists
            if not Path(file_path).exists():
                logger.error(f"File not found: {file_path}")
                return None

            # Read file
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # Prepare multipart file upload
            files = {
                'file': (Path(file_path).name, file_content)
            }

            # Send request to Java service
            logger.debug(f"Sending extraction request for {Path(file_path).name}")
            response = self.session.post(
                self.extract_endpoint,
                files=files,
                timeout=60  # 60 seconds timeout
            )

            # Check response
            if response.status_code == 200:
                result = response.json()

                # Validate response structure
                if result.get('success'):
                    text = result.get('text', '')
                    file_type = result.get('fileType', 'UNKNOWN')
                    processing_time = result.get('processingTimeMs', 0)

                    logger.success(
                        f"Extraction successful: {len(text)} chars, "
                        f"type={file_type}, time={processing_time}ms"
                    )

                    return {
                        'text': text,
                        'fileType': file_type,
                        'processingTimeMs': processing_time
                    }
                else:
                    error = result.get('error', 'Unknown error')
                    logger.error(f"Extraction failed: {error}")
                    return None
            else:
                logger.error(f"Service returned error: {response.status_code}")
                try:
                    error_detail = response.json()
                    logger.error(f"Error details: {error_detail}")
                except Exception:
                    logger.error(f"Response: {response.text[:200]}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Extraction timeout for {Path(file_path).name}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during extraction: {e}")
            return None

    def is_supported_format(self, filename: str) -> bool:
        """
        Check if file format is supported

        Args:
            filename: Name of the file

        Returns:
            True if format is supported, False otherwise
        """
        supported_extensions = [
            '.pdf', '.hwp', '.hwpx',
            '.doc', '.docx',
            '.xls', '.xlsx',
            '.ppt', '.pptx',
            '.txt'
        ]

        file_ext = Path(filename).suffix.lower()
        return file_ext in supported_extensions

    def get_file_type(self, filename: str) -> Optional[str]:
        """
        Get file type from filename

        Args:
            filename: Name of the file

        Returns:
            File type string (PDF, HWP, HWPX, DOC, DOCX, etc.) or None
        """
        ext_to_type = {
            '.pdf': 'PDF',
            '.hwp': 'HWP',
            '.hwpx': 'HWPX',
            '.doc': 'DOC',
            '.docx': 'DOCX',
            '.xls': 'XLS',
            '.xlsx': 'XLSX',
            '.ppt': 'PPT',
            '.pptx': 'PPTX'
        }

        file_ext = Path(filename).suffix.lower()
        return ext_to_type.get(file_ext)
