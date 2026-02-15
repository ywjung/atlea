"""문서 버전 관리 시스템

업로드된 파일의 버전 이력을 관리합니다 (PostgreSQL 기반).
- 버전 목록 조회
- 특정 버전으로 복원
- 버전 간 비교
- 버전별 메타데이터 저장
- 최근 N개 버전 보관 정책
"""

from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import shutil
import json
import difflib
import numpy as np
from loguru import logger

from sqlalchemy import select, delete, func

from .database.connection import SyncSessionFactory
from .database.models.document_version import DocumentVersion as DocumentVersionModel
from .database.models.document_version import DocumentLatestVersion


class DocumentVersion:
    """문서 버전 관리 클래스 (PostgreSQL 기반)"""

    # 기본 설정
    DEFAULT_MAX_VERSIONS = 10  # 최근 10개 버전만 보관

    def __init__(self, data_dir: str = "data", max_versions: int = DEFAULT_MAX_VERSIONS):
        """
        Args:
            data_dir: 데이터 디렉토리 경로
            max_versions: 보관할 최대 버전 수 (기본 10개)
        """
        self.data_dir = Path(data_dir)
        self.versions_dir = self.data_dir / "versions"
        self.max_versions = max_versions

        # 버전 디렉토리 생성
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    def _get_version_dir(self, filename: str) -> Path:
        """파일별 버전 디렉토리 경로 반환"""
        return self.versions_dir / filename

    def _get_version_filename(self, filename: str, version: int, timestamp: str) -> str:
        """버전 파일명 생성"""
        return f"v{version}_{timestamp}_{filename}"

    def _calculate_file_hash(self, file_path: Path) -> str:
        """파일 MD5 해시 계산"""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def get_latest_version(self, filename: str) -> Optional[int]:
        """최신 버전 번호 조회"""
        with SyncSessionFactory() as db:
            row = db.get(DocumentLatestVersion, filename)
            if row:
                return row.latest_version
            return None

    def create_version(
        self,
        source_path: Path,
        filename: str,
        user_id: Optional[str] = None,
        comment: Optional[str] = None,
        chunk_count: int = 0
    ) -> Dict[str, Any]:
        """새 버전 생성"""
        # 최신 버전 번호 조회
        latest_version = self.get_latest_version(filename)
        new_version = (latest_version or 0) + 1

        # 타임스탬프 생성
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S")

        # 버전 디렉토리 생성
        version_dir = self._get_version_dir(filename)
        version_dir.mkdir(parents=True, exist_ok=True)

        # 버전 파일 경로
        version_filename = self._get_version_filename(filename, new_version, timestamp)
        version_path = version_dir / version_filename

        # 파일 복사
        shutil.copy2(source_path, version_path)
        logger.info(f"Created version {new_version} for {filename}: {version_path}")

        # 파일 해시 및 메타데이터 계산
        file_hash = self._calculate_file_hash(version_path)
        file_size = version_path.stat().st_size

        # 버전 메타데이터 (반환용)
        metadata = {
            "version": new_version,
            "filename": filename,
            "original_filename": filename,
            "stored_path": str(version_path),
            "file_hash": file_hash,
            "file_size": file_size,
            "created_at": now.isoformat(),
            "created_by": user_id or "system",
            "chunk_count": chunk_count,
            "indexed": chunk_count > 0,
            "comment": comment or ""
        }

        # PG에 메타데이터 저장
        with SyncSessionFactory() as db:
            version_row = DocumentVersionModel(
                filename=filename,
                version_number=new_version,
                file_hash=file_hash,
                file_size=file_size,
                chunk_count=chunk_count,
                user_id=user_id or "system",
                comment=comment or "",
                metadata_={
                    "stored_path": str(version_path),
                    "original_filename": filename,
                    "indexed": chunk_count > 0,
                },
            )
            db.add(version_row)

            # 최신 버전 업데이트
            latest = db.get(DocumentLatestVersion, filename)
            if latest:
                latest.latest_version = new_version
            else:
                db.add(DocumentLatestVersion(filename=filename, latest_version=new_version))

            db.commit()

        logger.success(f"Stored version metadata for {filename} v{new_version}")

        # 버전 보관 정책 적용 (오래된 버전 삭제)
        self._cleanup_old_versions(filename)

        return metadata

    def _row_to_metadata(self, row: DocumentVersionModel) -> Dict[str, Any]:
        """Convert a PG row to the metadata dict format expected by callers."""
        extra = row.metadata_ or {}
        return {
            "version": row.version_number,
            "filename": row.filename,
            "original_filename": extra.get("original_filename", row.filename),
            "stored_path": extra.get("stored_path", ""),
            "file_hash": row.file_hash or "",
            "file_size": row.file_size or 0,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "created_by": row.user_id or "system",
            "chunk_count": row.chunk_count,
            "indexed": extra.get("indexed", row.chunk_count > 0),
            "comment": row.comment or "",
        }

    def list_versions(self, filename: str) -> List[Dict[str, Any]]:
        """파일의 모든 버전 목록 조회 (최신순)"""
        with SyncSessionFactory() as db:
            stmt = (
                select(DocumentVersionModel)
                .where(DocumentVersionModel.filename == filename)
                .order_by(DocumentVersionModel.version_number.desc())
            )
            result = db.execute(stmt)
            rows = result.scalars().all()

        return [self._row_to_metadata(row) for row in rows]

    def get_version(self, filename: str, version: int) -> Optional[Dict[str, Any]]:
        """특정 버전의 메타데이터 조회"""
        with SyncSessionFactory() as db:
            stmt = select(DocumentVersionModel).where(
                DocumentVersionModel.filename == filename,
                DocumentVersionModel.version_number == version,
            )
            result = db.execute(stmt)
            row = result.scalar_one_or_none()

        if not row:
            return None

        return self._row_to_metadata(row)

    def batch_get_latest_version_metadata(self, filenames: list) -> dict:
        """여러 파일의 최신 버전 메타데이터를 배치로 조회"""
        if not filenames:
            return {}

        result = {filename: None for filename in filenames}

        with SyncSessionFactory() as db:
            # Get latest version numbers for all files
            stmt = select(DocumentLatestVersion).where(
                DocumentLatestVersion.filename.in_(filenames)
            )
            latest_rows = db.execute(stmt).scalars().all()

            if not latest_rows:
                return result

            # Build (filename, version_number) pairs for lookup
            pairs = [(row.filename, row.latest_version) for row in latest_rows]

            # Fetch version metadata for all latest versions
            for fn, vn in pairs:
                stmt2 = select(DocumentVersionModel).where(
                    DocumentVersionModel.filename == fn,
                    DocumentVersionModel.version_number == vn,
                )
                row = db.execute(stmt2).scalar_one_or_none()
                if row:
                    result[fn] = self._row_to_metadata(row)

        return result

    def restore_version(self, filename: str, version: int, target_path: Path) -> bool:
        """특정 버전을 복원"""
        metadata = self.get_version(filename, version)
        if not metadata:
            logger.error(f"Version {version} not found for {filename}")
            return False

        version_path = Path(metadata['stored_path'])
        if not version_path.exists():
            logger.error(f"Version file not found: {version_path}")
            return False

        shutil.copy2(version_path, target_path)
        logger.success(f"Restored {filename} v{version} to {target_path}")
        return True

    def _extract_text_from_file(self, file_path: Path) -> str:
        """파일에서 텍스트 추출"""
        try:
            file_ext = file_path.suffix.lower()

            if file_ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()

            elif file_ext == '.pdf':
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(file_path)
                    text = ""
                    for page in doc:
                        text += page.get_text()
                    doc.close()
                    return text
                except Exception as e:
                    logger.warning(f"PyMuPDF extraction failed, trying pdfplumber: {e}")
                    import pdfplumber
                    text = ""
                    with pdfplumber.open(file_path) as pdf:
                        for page in pdf.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text + "\n"
                    return text

            elif file_ext in ['.hwp', '.hwpx']:
                logger.warning(f"HWP file comparison not supported: {file_path}")
                return ""

            else:
                logger.warning(f"Unsupported file type for comparison: {file_ext}")
                return ""

        except Exception as e:
            logger.error(f"Failed to extract text from {file_path}: {e}")
            return ""

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """텍스트 기반 유사도 계산 (difflib SequenceMatcher)"""
        if not text1 or not text2:
            return 0.0

        matcher = difflib.SequenceMatcher(None, text1, text2)
        ratio = matcher.ratio()
        return round(ratio * 100, 1)

    def _calculate_embedding_similarity(self, text1: str, text2: str) -> Optional[float]:
        """임베딩 기반 유사도 계산 (코사인 유사도)"""
        try:
            from .embeddings_ollama import OllamaEmbedding

            embedding_model = OllamaEmbedding()

            max_length = 2000
            text1_sample = text1[:max_length] if len(text1) > max_length else text1
            text2_sample = text2[:max_length] if len(text2) > max_length else text2

            emb1 = embedding_model.encode(text1_sample)
            emb2 = embedding_model.encode(text2_sample)

            if not emb1 or not emb2:
                return None

            emb1_array = np.array(emb1[0], dtype=np.float32)
            emb2_array = np.array(emb2[0], dtype=np.float32)

            dot_product = np.dot(emb1_array, emb2_array)
            norm1 = np.linalg.norm(emb1_array)
            norm2 = np.linalg.norm(emb2_array)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            cosine_sim = dot_product / (norm1 * norm2)
            similarity = ((cosine_sim + 1) / 2) * 100

            return round(float(similarity), 1)

        except Exception as e:
            logger.warning(f"Embedding similarity calculation failed: {e}")
            return None

    def _calculate_llm_similarity(self, text1: str, text2: str) -> Optional[Dict[str, Any]]:
        """LLM 기반 유사도 분석 (상세한 차이점 분석 포함)"""
        try:
            from .llm_ollama import OllamaLLM

            llm = OllamaLLM()

            max_length = 1500
            text1_sample = text1[:max_length] if len(text1) > max_length else text1
            text2_sample = text2[:max_length] if len(text2) > max_length else text2

            prompt = f"""다음 두 문서를 비교하고 분석해주세요.

**문서 버전 1:**
{text1_sample}

**문서 버전 2:**
{text2_sample}

다음 형식으로 JSON 응답을 생성해주세요:
{{
    "similarity": <0-100 사이의 유사도 점수>,
    "summary": "<간단한 차이점 요약>",
    "added": ["<추가된 내용 1>", "<추가된 내용 2>"],
    "removed": ["<삭제된 내용 1>", "<삭제된 내용 2>"],
    "modified": ["<변경된 내용 1>", "<변경된 내용 2>"]
}}

JSON 형식만 응답하고 다른 텍스트는 포함하지 마세요."""

            messages = [{"role": "user", "content": prompt}]
            response = llm._generate_response(
                messages=messages,
                max_tokens=500,
                temperature=0.1
            )

            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                if "similarity" in result:
                    result["similarity"] = max(0.0, min(100.0, float(result["similarity"])))
                return result
            else:
                logger.warning("LLM response is not valid JSON")
                return None

        except Exception as e:
            logger.warning(f"LLM similarity calculation failed: {e}")
            return None

    def compare_versions(
        self,
        filename: str,
        version1: int,
        version2: int,
        method: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """두 버전 간 비교 정보 반환"""
        meta1 = self.get_version(filename, version1)
        meta2 = self.get_version(filename, version2)

        if not meta1 or not meta2:
            return None

        chunk_count1 = int(meta1.get('chunk_count', 0) or 0)
        chunk_count2 = int(meta2.get('chunk_count', 0) or 0)

        similarity = 0.0
        similarity_method = "hash"

        if meta1['file_hash'] == meta2['file_hash']:
            similarity = 100.0
            similarity_method = "hash"
        else:
            if method == "hash":
                similarity = 0.0
                similarity_method = "hash"
            else:
                path1 = Path(meta1['stored_path'])
                path2 = Path(meta2['stored_path'])

                if not path1.exists() or not path2.exists():
                    logger.warning(f"Version files not found for comparison")
                    similarity = 0.0
                    similarity_method = "hash"
                else:
                    text1 = self._extract_text_from_file(path1)
                    text2 = self._extract_text_from_file(path2)

                    if text1 and text2:
                        if method == "auto":
                            file_size = int(meta1['file_size'])
                            if file_size < 100 * 1024:
                                method = "text"
                            else:
                                method = "embedding"

                        if method == "text":
                            similarity = self._calculate_text_similarity(text1, text2)
                            similarity_method = "text"
                        elif method == "embedding":
                            emb_sim = self._calculate_embedding_similarity(text1, text2)
                            if emb_sim is not None:
                                similarity = emb_sim
                                similarity_method = "embedding"
                            else:
                                similarity = self._calculate_text_similarity(text1, text2)
                                similarity_method = "text"
                        elif method == "llm":
                            llm_result = self._calculate_llm_similarity(text1, text2)
                            if llm_result is not None:
                                similarity = llm_result.get("similarity", 0.0)
                                similarity_method = "llm"
                            else:
                                emb_sim = self._calculate_embedding_similarity(text1, text2)
                                if emb_sim is not None:
                                    similarity = emb_sim
                                    similarity_method = "embedding"
                                else:
                                    similarity = self._calculate_text_similarity(text1, text2)
                                    similarity_method = "text"
                    else:
                        similarity = 0.0
                        similarity_method = "hash"

        comparison = {
            "filename": filename,
            "version1": {
                "version": version1,
                "created_at": meta1['created_at'],
                "created_by": meta1.get('created_by', 'system'),
                "file_size": int(meta1['file_size']),
                "file_hash": meta1['file_hash'],
                "chunk_count": chunk_count1,
                "comment": meta1.get('comment', '')
            },
            "version2": {
                "version": version2,
                "created_at": meta2['created_at'],
                "created_by": meta2.get('created_by', 'system'),
                "file_size": int(meta2['file_size']),
                "file_hash": meta2['file_hash'],
                "chunk_count": chunk_count2,
                "comment": meta2.get('comment', '')
            },
            "differences": {
                "size_changed": meta1['file_size'] != meta2['file_size'],
                "size_diff": int(meta2['file_size']) - int(meta1['file_size']),
                "content_changed": meta1['file_hash'] != meta2['file_hash'],
                "chunk_diff": chunk_count2 - chunk_count1,
                "chunk_count_diff": chunk_count2 - chunk_count1,
                "similarity_percentage": round(similarity, 1),
                "similarity_method": similarity_method
            }
        }

        return comparison

    def delete_version(self, filename: str, version: int) -> bool:
        """특정 버전 삭제"""
        metadata = self.get_version(filename, version)
        if not metadata:
            logger.warning(f"Version {version} not found for {filename}")
            return False

        # 파일 삭제
        version_path = Path(metadata['stored_path'])
        if version_path.exists():
            version_path.unlink()
            logger.info(f"Deleted version file: {version_path}")

        # PG 메타데이터 삭제
        with SyncSessionFactory() as db:
            stmt = select(DocumentVersionModel).where(
                DocumentVersionModel.filename == filename,
                DocumentVersionModel.version_number == version,
            )
            row = db.execute(stmt).scalar_one_or_none()
            if row:
                db.delete(row)
                db.commit()

        logger.success(f"Deleted {filename} v{version}")
        return True

    def _cleanup_old_versions(self, filename: str):
        """오래된 버전 정리 (보관 정책 적용)"""
        with SyncSessionFactory() as db:
            count_stmt = (
                select(func.count())
                .select_from(DocumentVersionModel)
                .where(DocumentVersionModel.filename == filename)
            )
            version_count = db.execute(count_stmt).scalar_one()

        if version_count <= self.max_versions:
            return

        # 가장 오래된 버전부터 삭제
        with SyncSessionFactory() as db:
            stmt = (
                select(DocumentVersionModel.version_number)
                .where(DocumentVersionModel.filename == filename)
                .order_by(DocumentVersionModel.version_number.asc())
                .limit(version_count - self.max_versions)
            )
            old_versions = [row for row in db.execute(stmt).scalars().all()]

        for version in old_versions:
            self.delete_version(filename, version)
            logger.info(f"Cleaned up old version: {filename} v{version}")

        logger.info(f"Kept {self.max_versions} most recent versions for {filename}")

    def delete_all_versions(self, filename: str) -> int:
        """파일의 모든 버전 삭제"""
        versions = self.list_versions(filename)
        deleted_count = 0

        for version_meta in versions:
            version = version_meta['version']
            if self.delete_version(filename, version):
                deleted_count += 1

        # 버전 디렉토리 삭제
        version_dir = self._get_version_dir(filename)
        if version_dir.exists():
            shutil.rmtree(version_dir)
            logger.info(f"Deleted version directory: {version_dir}")

        # 최신 버전 키 삭제
        with SyncSessionFactory() as db:
            latest = db.get(DocumentLatestVersion, filename)
            if latest:
                db.delete(latest)
                db.commit()

        logger.success(f"Deleted all {deleted_count} versions for {filename}")
        return deleted_count
