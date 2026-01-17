"""
Document Processor - Extract and chunk documents
Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT
"""

import os
import struct
import zlib
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
from langchain_text_splitters import RecursiveCharacterTextSplitter
import olefile

from .document_service import DocumentService
from .hwp_processor import HWPProcessor


class DocumentProcessor:
    """Process documents and create chunks - supports multiple formats via Java Document Service"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50,
                 document_service_url: str = None):
        """
        Initialize document processor

        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
            document_service_url: URL of Java document service (default: http://localhost:8081)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

        # Initialize unified document service
        self.document_service = DocumentService(document_service_url)
        self.use_java_service = False

        # Check if Java document service is available
        if self.document_service.check_service_health():
            self.use_java_service = True
            logger.success("✅ Java Document Service available - supports PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX")
        else:
            logger.warning("⚠️ Java Document Service not available - falling back to Python extraction (HWP only)")

        # Keep HWP fallback processor for legacy support
        self.hwp_processor = HWPProcessor(document_service_url)

        logger.info(f"Document Processor initialized (chunk_size={chunk_size}, overlap={chunk_overlap})")

    def extract_text_from_document(self, doc_path: str) -> str:
        """
        Extract text from document file using Java Document Service
        Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT

        Args:
            doc_path: Path to document file

        Returns:
            Extracted text
        """
        filename = Path(doc_path).name
        file_ext = Path(doc_path).suffix.lower()

        # Handle TXT files directly - simple UTF-8 text reading
        if file_ext == '.txt':
            try:
                logger.info(f"📄 Reading TXT file: {filename}")
                with open(doc_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                logger.success(f"✅ TXT file read successful: {len(text)} chars")
                return text
            except UnicodeDecodeError:
                # Try with different encodings if UTF-8 fails
                logger.warning("UTF-8 decoding failed, trying cp949 encoding")
                try:
                    with open(doc_path, 'r', encoding='cp949') as f:
                        text = f.read()
                    logger.success(f"✅ TXT file read successful (cp949): {len(text)} chars")
                    return text
                except Exception as e:
                    logger.error(f"❌ Failed to read TXT file: {e}")
                    raise

        # Use Java Document Service for all supported formats
        if self.use_java_service:
            try:
                logger.info(f"📄 Extracting text from {filename}")
                result = self.document_service.extract_text_from_file(doc_path)

                if result and result.get('text'):
                    text = result['text']
                    file_type = result.get('fileType', file_ext[1:].upper())
                    processing_time = result.get('processingTimeMs', 0)

                    logger.success(
                        f"✅ Extraction successful: {len(text)} chars, "
                        f"type={file_type}, time={processing_time}ms"
                    )
                    return text
                else:
                    logger.error("❌ Document service returned no text")
                    raise RuntimeError(f"Failed to extract text from {filename}")
            except Exception as e:
                logger.error(f"❌ Document service extraction failed: {e}")

                # Fallback to Python HWP extraction for .hwp files only
                if file_ext == '.hwp':
                    logger.info("🔄 Attempting Python fallback for HWP file")
                    return self._extract_hwp_fallback(doc_path)
                else:
                    raise
        else:
            # Java service not available - only HWP fallback possible
            if file_ext == '.hwp':
                logger.info(f"📄 Using Python fallback extraction for {filename}")
                return self._extract_hwp_fallback(doc_path)
            else:
                raise RuntimeError(
                    f"Document extraction not available for {file_ext} files - "
                    "Java Document Service is not running"
                )

    def _extract_hwp_fallback(self, hwp_path: str) -> str:
        """
        Python fallback for HWP extraction using HWPProcessor

        Args:
            hwp_path: Path to HWP file

        Returns:
            Extracted text
        """
        try:
            logger.info("🔄 Using Python HWP fallback extraction")

            # Try HWPProcessor first (calls Java service /api/hwp/extract)
            text = self.hwp_processor.extract_text_from_file(hwp_path)
            if text:
                logger.success(f"✅ HWP fallback successful: {len(text)} chars")
                return text

            # If HWPProcessor fails, try direct Python extraction
            logger.warning("HWPProcessor failed, attempting direct Python extraction")
            return self._extract_hwp_direct(hwp_path)

        except Exception as e:
            logger.error(f"❌ HWP fallback failed: {e}")
            raise

    def _extract_hwp_direct(self, hwp_path: str) -> str:
        """
        Direct Python HWP extraction (last resort)

        Args:
            hwp_path: Path to HWP file

        Returns:
            Extracted text
        """
        try:
            if not olefile.isOleFile(hwp_path):
                raise ValueError(f"{hwp_path} is not a valid HWP file")

            ole = olefile.OleFileIO(hwp_path)
            text_parts = []

            # HWP 파일 구조: BodyText/Section* 스트림에 텍스트 저장
            for stream in ole.listdir():
                stream_name = "/".join(stream)

                # BodyText 섹션에서 텍스트 추출
                if stream_name.startswith("BodyText/Section"):
                    try:
                        data = ole.openstream(stream).read()
                        # HWP 5.0+ 형식의 텍스트 추출
                        text = self._parse_hwp_text(data)
                        if text.strip():
                            text_parts.append(text)
                    except Exception as e:
                        logger.warning(f"Failed to extract from stream {stream_name}: {e}")
                        continue

            ole.close()

            if not text_parts:
                # 대체 방법: 모든 스트림에서 텍스트 추출 시도
                logger.warning(f"No text found in BodyText sections, trying alternative extraction")
                ole = olefile.OleFileIO(hwp_path)
                for stream in ole.listdir():
                    try:
                        stream_name = "/".join(stream)
                        data = ole.openstream(stream).read()
                        text = self._extract_readable_text(data)
                        if text.strip():
                            text_parts.append(text)
                    except Exception:
                        continue
                ole.close()

            full_text = "\n\n".join(text_parts)
            logger.debug(f"Extracted {len(full_text)} characters from {hwp_path}")
            return full_text
        except Exception as e:
            logger.error(f"Failed to extract text from HWP {hwp_path}: {e}")
            raise

    def _parse_hwp_text(self, data: bytes) -> str:
        """
        Parse HWP binary data to extract text

        Args:
            data: Binary data from HWP stream

        Returns:
            Extracted text
        """
        try:
            # HWP 파일은 압축되어 있을 수 있음
            try:
                decompressed = zlib.decompress(data)
            except Exception:
                decompressed = data

            # UTF-16 LE로 디코딩 시도
            try:
                text = decompressed.decode('utf-16le', errors='ignore')
            except Exception:
                # UTF-8 시도
                try:
                    text = decompressed.decode('utf-8', errors='ignore')
                except Exception:
                    # CP949 (EUC-KR) 시도
                    text = decompressed.decode('cp949', errors='ignore')

            # 제어 문자 제거
            text = ''.join(char for char in text if char.isprintable() or char in '\n\r\t ')
            return text
        except Exception as e:
            logger.debug(f"Failed to parse HWP text: {e}")
            return ""

    def _extract_readable_text(self, data: bytes) -> str:
        """
        Extract readable text from binary data

        Args:
            data: Binary data

        Returns:
            Readable text
        """
        try:
            # 다양한 인코딩으로 시도
            for encoding in ['utf-16le', 'utf-8', 'cp949', 'euc-kr']:
                try:
                    text = data.decode(encoding, errors='ignore')
                    # 읽을 수 있는 한글/영문 문자가 충분히 있는지 확인
                    readable_chars = sum(1 for c in text if c.isprintable() or c in '\n\r\t ')
                    if readable_chars > len(text) * 0.3:  # 30% 이상이 읽을 수 있는 문자
                        text = ''.join(char for char in text if char.isprintable() or char in '\n\r\t ')
                        return text
                except Exception:
                    continue
            return ""
        except Exception:
            return ""

    def create_chunks(self, text: str, metadata: Dict = None) -> List[Dict]:
        """
        Split text into chunks

        Args:
            text: Text to split
            metadata: Additional metadata to include

        Returns:
            List of chunk dictionaries
        """
        try:
            chunks = self.text_splitter.split_text(text)
            result = []

            for idx, chunk in enumerate(chunks):
                chunk_data = {
                    "text": chunk,
                    "chunk_index": idx,
                    "total_chunks": len(chunks)
                }
                if metadata:
                    chunk_data.update(metadata)
                result.append(chunk_data)

            logger.debug(f"Created {len(result)} chunks")
            return result
        except Exception as e:
            logger.error(f"Failed to create chunks: {e}")
            raise

    def process_document(self, doc_path: str) -> List[Dict]:
        """
        Process document file: extract text and create chunks
        Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX

        Args:
            doc_path: Path to document file

        Returns:
            List of chunk dictionaries with metadata
        """
        try:
            file_name = Path(doc_path).name
            file_ext = Path(doc_path).suffix.lower()

            # Check if format is supported
            if not self.document_service.is_supported_format(file_name):
                raise ValueError(f"Unsupported file format: {file_ext}")

            # Extract text from document
            text = self.extract_text_from_document(doc_path)

            if not text.strip():
                logger.warning(f"No text extracted from {doc_path}")
                return []

            # Create metadata
            metadata = {
                "source": doc_path,
                "filename": file_name,
                "file_type": file_ext[1:]  # Remove dot from extension
            }

            # Create chunks
            chunks = self.create_chunks(text, metadata)
            logger.success(f"✅ Processed {file_name}: {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"❌ Failed to process document {doc_path}: {e}")
            raise

    def process_directory(self, directory_path: str, patterns: List[str] = None) -> List[Dict]:
        """
        Process all document files in directory
        Supports: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT

        Args:
            directory_path: Path to directory
            patterns: File patterns to match (default: all supported formats)

        Returns:
            List of all chunks from all documents
        """
        if patterns is None:
            # Default: all supported formats
            patterns = [
                "*.pdf",
                "*.hwp", "*.hwpx",
                "*.doc", "*.docx",
                "*.xls", "*.xlsx",
                "*.ppt", "*.pptx",
                "*.txt"
            ]

        directory = Path(directory_path)
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        # 모든 패턴에 맞는 파일 찾기
        all_files = []
        for pattern in patterns:
            all_files.extend(directory.glob(pattern))

        if not all_files:
            logger.warning(f"No document files found in {directory_path}")
            return []

        logger.info(f"📚 Found {len(all_files)} document files")
        all_chunks = []

        for doc_file in all_files:
            try:
                chunks = self.process_document(str(doc_file))
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(f"⚠️ Skipping {doc_file.name}: {e}")
                continue

        logger.success(f"✅ Processed {len(all_files)} documents → {len(all_chunks)} total chunks")
        return all_chunks


# Backward compatibility alias
PDFProcessor = DocumentProcessor
