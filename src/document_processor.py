"""
Document Processor - Extract and chunk documents (PDF, HWP)
"""

import os
import struct
import zlib
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
from langchain_text_splitters import RecursiveCharacterTextSplitter
import olefile

from .hwp_processor import HWPProcessor
from .pdf_service import PDFService


class DocumentProcessor:
    """Process documents (PDF, HWP) and create chunks"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50,
                 hwp_service_url: str = None, pdf_service_url: str = None):
        """
        Initialize document processor

        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
            hwp_service_url: URL of Java HWP service (optional)
            pdf_service_url: URL of Java PDF service (optional)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

        # Initialize HWP processor with Java service
        self.hwp_processor = HWPProcessor(hwp_service_url)
        self.use_java_hwp = False  # Default to Python fallback

        # Check if Java HWP service is available
        if self.hwp_processor.check_service_health():
            self.use_java_hwp = True
            logger.success("Java HWP service is available - using Java-based extraction")
        else:
            logger.warning("Java HWP service not available - falling back to Python extraction")

        # Initialize PDF service with Java service
        self.pdf_service = PDFService(pdf_service_url)
        self.use_java_pdf = False  # Default to Python fallback

        # Check if Java PDF service is available
        if self.pdf_service.check_service_health():
            self.use_java_pdf = True
            logger.success("Java PDF service is available - using Java-based extraction")
        else:
            logger.warning("Java PDF service not available - Python extraction not available")

        logger.info(f"Document Processor initialized (chunk_size={chunk_size}, overlap={chunk_overlap})")

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF file using Java PDF service

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        # Use Java-based extraction
        if self.use_java_pdf:
            try:
                logger.info(f"Using Java PDF service for {Path(pdf_path).name}")
                result = self.pdf_service.extract_text_from_file(pdf_path)
                if result and result.get('text'):
                    text = result['text']
                    logger.success(f"Java extraction successful: {len(text)} characters")
                    return text
                else:
                    logger.error("Java extraction returned no text")
                    raise RuntimeError(f"Failed to extract text from PDF: {pdf_path}")
            except Exception as e:
                logger.error(f"Java extraction failed: {e}")
                raise
        else:
            raise RuntimeError("PDF extraction not available - Java PDF service is not running")

    def extract_text_from_hwp(self, hwp_path: str) -> str:
        """
        Extract text from HWP file (한글 문서)
        Uses Java HWP service if available, falls back to Python extraction

        Args:
            hwp_path: Path to HWP file

        Returns:
            Extracted text
        """
        # Try Java-based extraction first (more reliable)
        if self.use_java_hwp:
            try:
                logger.info(f"Using Java HWP service for {Path(hwp_path).name}")
                text = self.hwp_processor.extract_text_from_file(hwp_path)
                if text:
                    logger.success(f"Java extraction successful: {len(text)} characters")
                    return text
                else:
                    logger.warning("Java extraction returned no text, falling back to Python")
            except Exception as e:
                logger.warning(f"Java extraction failed, falling back to Python: {e}")

        # Fallback to Python-based extraction
        logger.info(f"Using Python fallback extraction for {Path(hwp_path).name}")
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
                    except:
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
            except:
                decompressed = data

            # UTF-16 LE로 디코딩 시도
            try:
                text = decompressed.decode('utf-16le', errors='ignore')
            except:
                # UTF-8 시도
                try:
                    text = decompressed.decode('utf-8', errors='ignore')
                except:
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
                except:
                    continue
            return ""
        except:
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

        Args:
            doc_path: Path to document file (PDF or HWP)

        Returns:
            List of chunk dictionaries with metadata
        """
        try:
            file_ext = Path(doc_path).suffix.lower()

            # 파일 형식에 따라 텍스트 추출
            if file_ext == '.pdf':
                text = self.extract_text_from_pdf(doc_path)
            elif file_ext == '.hwp':
                text = self.extract_text_from_hwp(doc_path)
            else:
                raise ValueError(f"Unsupported file format: {file_ext}")

            if not text.strip():
                logger.warning(f"No text extracted from {doc_path}")
                return []

            # Create metadata
            file_name = Path(doc_path).name
            metadata = {
                "source": doc_path,
                "filename": file_name,
                "file_type": file_ext[1:]  # Remove dot from extension
            }

            # Create chunks
            chunks = self.create_chunks(text, metadata)
            logger.success(f"Processed {file_name}: {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Failed to process document {doc_path}: {e}")
            raise

    def process_directory(self, directory_path: str, patterns: List[str] = None) -> List[Dict]:
        """
        Process all document files in directory

        Args:
            directory_path: Path to directory
            patterns: File patterns to match (default: ["*.pdf", "*.hwp"])

        Returns:
            List of all chunks from all documents
        """
        if patterns is None:
            patterns = ["*.pdf", "*.hwp"]

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

        logger.info(f"Found {len(all_files)} document files")
        all_chunks = []

        for doc_file in all_files:
            try:
                chunks = self.process_document(str(doc_file))
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(f"Skipping {doc_file.name}: {e}")
                continue

        logger.success(f"Processed {len(all_files)} documents -> {len(all_chunks)} total chunks")
        return all_chunks


# Backward compatibility alias
PDFProcessor = DocumentProcessor
