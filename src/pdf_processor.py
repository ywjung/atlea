"""
PDF Processor - Extract and chunk PDF documents
"""

import os
from pathlib import Path
from typing import List, Dict
from loguru import logger
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter


class PDFProcessor:
    """Process PDF documents and create chunks"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        """
        Initialize PDF processor

        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        logger.info(f"PDF Processor initialized (chunk_size={chunk_size}, overlap={chunk_overlap})")

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF file

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        try:
            reader = PdfReader(pdf_path)
            text_parts = []

            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text.strip():
                    text_parts.append(text)

            full_text = "\n\n".join(text_parts)
            logger.debug(f"Extracted {len(full_text)} characters from {pdf_path}")
            return full_text
        except Exception as e:
            logger.error(f"Failed to extract text from {pdf_path}: {e}")
            raise

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

    def process_pdf(self, pdf_path: str) -> List[Dict]:
        """
        Process PDF file: extract text and create chunks

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of chunk dictionaries with metadata
        """
        try:
            # Extract text
            text = self.extract_text_from_pdf(pdf_path)

            if not text.strip():
                logger.warning(f"No text extracted from {pdf_path}")
                return []

            # Create metadata
            file_name = Path(pdf_path).name
            metadata = {
                "source": pdf_path,
                "filename": file_name,
            }

            # Create chunks
            chunks = self.create_chunks(text, metadata)
            logger.success(f"Processed {file_name}: {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Failed to process PDF {pdf_path}: {e}")
            raise

    def process_directory(self, directory_path: str, pattern: str = "*.pdf") -> List[Dict]:
        """
        Process all PDF files in directory

        Args:
            directory_path: Path to directory
            pattern: File pattern to match

        Returns:
            List of all chunks from all PDFs
        """
        directory = Path(directory_path)
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        pdf_files = list(directory.glob(pattern))
        if not pdf_files:
            logger.warning(f"No PDF files found in {directory_path}")
            return []

        logger.info(f"Found {len(pdf_files)} PDF files")
        all_chunks = []

        for pdf_file in pdf_files:
            try:
                chunks = self.process_pdf(str(pdf_file))
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(f"Skipping {pdf_file.name}: {e}")
                continue

        logger.success(f"Processed {len(pdf_files)} PDFs -> {len(all_chunks)} total chunks")
        return all_chunks
