"""
Document Tracker - Detect PDF file changes and manage indexing state
"""

import os
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple
from loguru import logger
from datetime import datetime


class DocumentTracker:
    """Track PDF documents and detect changes"""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.metadata_file = self.data_dir / ".document_metadata.json"

    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate MD5 hash of file

        Args:
            file_path: Path to file

        Returns:
            MD5 hash string
        """
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _get_file_metadata(self, file_path: Path) -> Dict:
        """
        Get metadata for a file

        Args:
            file_path: Path to file

        Returns:
            Dictionary with file metadata
        """
        stat = file_path.stat()
        return {
            "path": str(file_path),
            "name": file_path.name,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "hash": self._calculate_file_hash(file_path)
        }

    def get_current_pdfs(self, pattern: str = "*.pdf") -> Dict[str, Dict]:
        """
        Get metadata for all current PDF files

        Args:
            pattern: File pattern to match

        Returns:
            Dictionary mapping filenames to metadata
        """
        if not self.data_dir.exists():
            logger.warning(f"Data directory does not exist: {self.data_dir}")
            return {}

        pdf_files = list(self.data_dir.glob(pattern))
        current_metadata = {}

        for pdf_file in pdf_files:
            try:
                metadata = self._get_file_metadata(pdf_file)
                current_metadata[pdf_file.name] = metadata
            except Exception as e:
                logger.error(f"Failed to get metadata for {pdf_file}: {e}")
                continue

        return current_metadata

    def load_saved_metadata(self) -> Dict[str, Dict]:
        """
        Load previously saved metadata

        Returns:
            Dictionary of saved metadata
        """
        if not self.metadata_file.exists():
            logger.info("No saved metadata found")
            return {}

        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Loaded metadata for {len(data.get('files', {}))} files")
                return data.get('files', {})
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            return {}

    def save_metadata(self, metadata: Dict[str, Dict]):
        """
        Save metadata to file

        Args:
            metadata: Dictionary of file metadata
        """
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "last_indexed": datetime.now().isoformat(),
                "files": metadata
            }

            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.success(f"Saved metadata for {len(metadata)} files")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
            raise

    def detect_changes(self) -> Tuple[Set[str], Set[str], Set[str]]:
        """
        Detect changes in PDF files

        Returns:
            Tuple of (new_files, modified_files, deleted_files)
        """
        current_pdfs = self.get_current_pdfs()
        saved_metadata = self.load_saved_metadata()

        current_files = set(current_pdfs.keys())
        saved_files = set(saved_metadata.keys())

        # Detect new and deleted files
        new_files = current_files - saved_files
        deleted_files = saved_files - current_files

        # Detect modified files
        modified_files = set()
        for filename in current_files & saved_files:
            current = current_pdfs[filename]
            saved = saved_metadata[filename]

            # Check if file was modified (compare hash)
            if current['hash'] != saved['hash']:
                modified_files.add(filename)

        return new_files, modified_files, deleted_files

    def needs_reindexing(self) -> bool:
        """
        Check if reindexing is needed

        Returns:
            True if any changes detected
        """
        new_files, modified_files, deleted_files = self.detect_changes()
        return bool(new_files or modified_files or deleted_files)

    def get_change_summary(self) -> Dict:
        """
        Get summary of changes

        Returns:
            Dictionary with change details
        """
        new_files, modified_files, deleted_files = self.detect_changes()

        return {
            "needs_reindex": bool(new_files or modified_files or deleted_files),
            "new_files": sorted(list(new_files)),
            "modified_files": sorted(list(modified_files)),
            "deleted_files": sorted(list(deleted_files)),
            "total_changes": len(new_files) + len(modified_files) + len(deleted_files)
        }

    def update_metadata(self):
        """
        Update saved metadata with current state
        """
        current_pdfs = self.get_current_pdfs()
        self.save_metadata(current_pdfs)

    def clear_metadata(self):
        """
        Clear saved metadata
        """
        if self.metadata_file.exists():
            self.metadata_file.unlink()
            logger.info("Metadata cleared")
