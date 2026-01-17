"""문서 버전 관리 시스템

업로드된 파일의 버전 이력을 관리합니다.
- 버전 목록 조회
- 특정 버전으로 복원
- 버전 간 비교
- 버전별 메타데이터 저장
- 최근 N개 버전 보관 정책
"""

from typing import Optional, Dict, List, Any
from datetime import datetime
from pathlib import Path
import hashlib
import shutil
import json
from redis import Redis
from loguru import logger
import difflib
import numpy as np


class DocumentVersion:
    """문서 버전 관리 클래스"""

    # Redis 키 패턴
    VERSION_LATEST_KEY = "doc:version:{filename}:latest"
    VERSION_META_KEY = "doc:version:{filename}:v{version}"
    VERSION_LIST_KEY = "doc:version:{filename}:list"

    # 기본 설정
    DEFAULT_MAX_VERSIONS = 10  # 최근 10개 버전만 보관

    def __init__(self, redis_client: Redis, data_dir: str, max_versions: int = DEFAULT_MAX_VERSIONS):
        """
        Args:
            redis_client: Redis 클라이언트
            data_dir: 데이터 디렉토리 경로
            max_versions: 보관할 최대 버전 수 (기본 10개)
        """
        self.redis = redis_client
        self.data_dir = Path(data_dir)
        self.versions_dir = self.data_dir / "versions"
        self.max_versions = max_versions

        # 버전 디렉토리 생성
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    def _get_version_dir(self, filename: str) -> Path:
        """파일별 버전 디렉토리 경로 반환

        Args:
            filename: 원본 파일명

        Returns:
            버전 디렉토리 경로 (data/versions/filename/)
        """
        return self.versions_dir / filename

    def _get_version_filename(self, filename: str, version: int, timestamp: str) -> str:
        """버전 파일명 생성

        Args:
            filename: 원본 파일명
            version: 버전 번호
            timestamp: 타임스탬프 (YYYYMMDDHHmmss)

        Returns:
            버전 파일명 (v1_20231225120000_filename.pdf)
        """
        return f"v{version}_{timestamp}_{filename}"

    def _calculate_file_hash(self, file_path: Path) -> str:
        """파일 MD5 해시 계산

        Args:
            file_path: 파일 경로

        Returns:
            MD5 해시 (hex)
        """
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def get_latest_version(self, filename: str) -> Optional[int]:
        """최신 버전 번호 조회

        Args:
            filename: 파일명

        Returns:
            최신 버전 번호 (없으면 None)
        """
        key = self.VERSION_LATEST_KEY.format(filename=filename)
        version = self.redis.get(key)
        if version:
            return int(version)
        return None

    def create_version(
        self,
        source_path: Path,
        filename: str,
        user_id: Optional[str] = None,
        comment: Optional[str] = None,
        chunk_count: int = 0
    ) -> Dict[str, Any]:
        """새 버전 생성

        Args:
            source_path: 원본 파일 경로
            filename: 파일명
            user_id: 생성자 사용자 ID
            comment: 버전 변경 사유
            chunk_count: 청크 개수

        Returns:
            생성된 버전 메타데이터
        """
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

        # 버전 메타데이터
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

        # Redis에 메타데이터 저장
        meta_key = self.VERSION_META_KEY.format(filename=filename, version=new_version)
        self.redis.hset(meta_key, mapping={k: str(v) for k, v in metadata.items()})

        # 버전 목록에 추가 (Sorted Set)
        list_key = self.VERSION_LIST_KEY.format(filename=filename)
        self.redis.zadd(list_key, {str(new_version): new_version})

        # 최신 버전 업데이트
        latest_key = self.VERSION_LATEST_KEY.format(filename=filename)
        self.redis.set(latest_key, new_version)

        logger.success(f"Stored version metadata for {filename} v{new_version}")

        # 버전 보관 정책 적용 (오래된 버전 삭제)
        self._cleanup_old_versions(filename)

        return metadata

    def list_versions(self, filename: str) -> List[Dict[str, Any]]:
        """파일의 모든 버전 목록 조회

        Args:
            filename: 파일명

        Returns:
            버전 메타데이터 리스트 (최신순)
        """
        list_key = self.VERSION_LIST_KEY.format(filename=filename)

        # 버전 번호 목록 조회 (최신순)
        versions = self.redis.zrevrange(list_key, 0, -1)

        if not versions:
            return []

        # 각 버전의 메타데이터 조회
        result = []
        for version_bytes in versions:
            version = int(version_bytes)
            meta_key = self.VERSION_META_KEY.format(filename=filename, version=version)
            meta = self.redis.hgetall(meta_key)

            if meta:
                # bytes → str 변환
                metadata = {
                    k.decode('utf-8') if isinstance(k, bytes) else k:
                    v.decode('utf-8') if isinstance(v, bytes) else v
                    for k, v in meta.items()
                }

                # 타입 변환
                metadata['version'] = int(metadata['version'])
                metadata['file_size'] = int(metadata['file_size'])
                metadata['chunk_count'] = int(metadata['chunk_count'])
                metadata['indexed'] = metadata['indexed'] == 'True'

                result.append(metadata)

        return result

    def get_version(self, filename: str, version: int) -> Optional[Dict[str, Any]]:
        """특정 버전의 메타데이터 조회

        Args:
            filename: 파일명
            version: 버전 번호

        Returns:
            버전 메타데이터 (없으면 None)
        """
        meta_key = self.VERSION_META_KEY.format(filename=filename, version=version)
        meta = self.redis.hgetall(meta_key)

        if not meta:
            return None

        # bytes → str 변환
        metadata = {
            k.decode('utf-8') if isinstance(k, bytes) else k:
            v.decode('utf-8') if isinstance(v, bytes) else v
            for k, v in meta.items()
        }

        # 타입 변환
        metadata['version'] = int(metadata['version'])
        metadata['file_size'] = int(metadata['file_size'])
        metadata['chunk_count'] = int(metadata['chunk_count'])
        metadata['indexed'] = metadata['indexed'] == 'True'

        return metadata

    def batch_get_latest_version_metadata(self, filenames: list) -> dict:
        """여러 파일의 최신 버전 메타데이터를 배치로 조회 (Pipeline 사용)

        Args:
            filenames: 파일명 목록

        Returns:
            {filename: {chunk_count: int, ...} or None} 딕셔너리
        """
        if not filenames:
            return {}

        # Step 1: 모든 파일의 최신 버전 번호를 한 번에 조회
        pipe = self.redis.pipeline()
        for filename in filenames:
            key = self.VERSION_LATEST_KEY.format(filename=filename)
            pipe.get(key)
        version_results = pipe.execute()

        # Step 2: 버전이 있는 파일의 메타데이터를 한 번에 조회
        files_with_versions = []
        for filename, version in zip(filenames, version_results):
            if version:
                version_num = int(version)
                files_with_versions.append((filename, version_num))

        if not files_with_versions:
            return {filename: None for filename in filenames}

        pipe = self.redis.pipeline()
        for filename, version in files_with_versions:
            meta_key = self.VERSION_META_KEY.format(filename=filename, version=version)
            pipe.hgetall(meta_key)
        meta_results = pipe.execute()

        # Step 3: 결과 매핑
        result = {filename: None for filename in filenames}
        for (filename, version), meta in zip(files_with_versions, meta_results):
            if meta:
                try:
                    metadata = {
                        k.decode('utf-8') if isinstance(k, bytes) else k:
                        v.decode('utf-8') if isinstance(v, bytes) else v
                        for k, v in meta.items()
                    }
                    metadata['version'] = int(metadata.get('version', version))
                    metadata['file_size'] = int(metadata.get('file_size', 0))
                    metadata['chunk_count'] = int(metadata.get('chunk_count', 0))
                    metadata['indexed'] = metadata.get('indexed') == 'True'
                    result[filename] = metadata
                except Exception:
                    result[filename] = None

        return result

    def restore_version(self, filename: str, version: int, target_path: Path) -> bool:
        """특정 버전을 복원

        Args:
            filename: 파일명
            version: 복원할 버전 번호
            target_path: 복원할 위치

        Returns:
            성공 여부
        """
        # 버전 메타데이터 조회
        metadata = self.get_version(filename, version)
        if not metadata:
            logger.error(f"Version {version} not found for {filename}")
            return False

        # 버전 파일 경로
        version_path = Path(metadata['stored_path'])
        if not version_path.exists():
            logger.error(f"Version file not found: {version_path}")
            return False

        # 파일 복원
        shutil.copy2(version_path, target_path)
        logger.success(f"Restored {filename} v{version} to {target_path}")

        return True

    def _extract_text_from_file(self, file_path: Path) -> str:
        """파일에서 텍스트 추출

        Args:
            file_path: 파일 경로

        Returns:
            추출된 텍스트
        """
        try:
            file_ext = file_path.suffix.lower()

            if file_ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()

            elif file_ext == '.pdf':
                # PDF 텍스트 추출 (기존 PDF 처리 로직 사용)
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
                    # Fallback to pdfplumber
                    import pdfplumber
                    text = ""
                    with pdfplumber.open(file_path) as pdf:
                        for page in pdf.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text + "\n"
                    return text

            elif file_ext in ['.hwp', '.hwpx']:
                # HWP는 Java 서비스 사용해야 함 - 여기서는 스킵
                logger.warning(f"HWP file comparison not supported: {file_path}")
                return ""

            else:
                logger.warning(f"Unsupported file type for comparison: {file_ext}")
                return ""

        except Exception as e:
            logger.error(f"Failed to extract text from {file_path}: {e}")
            return ""

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """텍스트 기반 유사도 계산 (difflib SequenceMatcher)

        Args:
            text1: 첫 번째 텍스트
            text2: 두 번째 텍스트

        Returns:
            유사도 (0.0 ~ 100.0)
        """
        if not text1 or not text2:
            return 0.0

        # SequenceMatcher를 사용한 유사도 계산
        matcher = difflib.SequenceMatcher(None, text1, text2)
        ratio = matcher.ratio()
        return round(ratio * 100, 1)

    def _calculate_embedding_similarity(self, text1: str, text2: str) -> Optional[float]:
        """임베딩 기반 유사도 계산 (코사인 유사도)

        Args:
            text1: 첫 번째 텍스트
            text2: 두 번째 텍스트

        Returns:
            유사도 (0.0 ~ 100.0) 또는 None (실패 시)
        """
        try:
            # 임베딩 모델 가져오기 (전역 변수에서)
            from .embeddings_ollama import OllamaEmbedding

            # 임베딩 모델 초기화 (캐시됨)
            embedding_model = OllamaEmbedding()

            # 텍스트가 너무 길면 앞부분만 사용 (토큰 제한)
            max_length = 2000
            text1_sample = text1[:max_length] if len(text1) > max_length else text1
            text2_sample = text2[:max_length] if len(text2) > max_length else text2

            # 임베딩 생성
            emb1 = embedding_model.encode(text1_sample)
            emb2 = embedding_model.encode(text2_sample)

            if not emb1 or not emb2:
                return None

            # List[List[float]] -> np.ndarray 변환
            emb1_array = np.array(emb1[0], dtype=np.float32)
            emb2_array = np.array(emb2[0], dtype=np.float32)

            # 코사인 유사도 계산
            dot_product = np.dot(emb1_array, emb2_array)
            norm1 = np.linalg.norm(emb1_array)
            norm2 = np.linalg.norm(emb2_array)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            cosine_sim = dot_product / (norm1 * norm2)
            # 코사인 유사도는 -1 ~ 1 범위, 0 ~ 100으로 변환
            similarity = ((cosine_sim + 1) / 2) * 100

            # numpy 타입을 Python float로 변환 (JSON 직렬화를 위해)
            return round(float(similarity), 1)

        except Exception as e:
            logger.warning(f"Embedding similarity calculation failed: {e}")
            return None

    def _calculate_llm_similarity(self, text1: str, text2: str) -> Optional[Dict[str, Any]]:
        """LLM 기반 유사도 분석 (상세한 차이점 분석 포함)

        Args:
            text1: 첫 번째 텍스트
            text2: 두 번째 텍스트

        Returns:
            유사도 정보 딕셔너리 또는 None
            {
                "similarity": float (0-100),
                "summary": str,  # 차이점 요약
                "added": List[str],  # 추가된 내용
                "removed": List[str],  # 삭제된 내용
                "modified": List[str]  # 변경된 내용
            }
        """
        try:
            from .llm_ollama import OllamaLLM

            # LLM 초기화 (전역 변수에서 가져오는 것이 더 좋지만, 여기서는 직접 생성)
            llm = OllamaLLM()

            # 텍스트가 너무 길면 샘플링
            max_length = 1500
            text1_sample = text1[:max_length] if len(text1) > max_length else text1
            text2_sample = text2[:max_length] if len(text2) > max_length else text2

            # LLM에게 비교 요청
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

            # LLM 호출
            messages = [{"role": "user", "content": prompt}]
            response = llm._generate_response(
                messages=messages,
                max_tokens=500,
                temperature=0.1  # 낮은 temperature로 일관성 있는 결과
            )

            # JSON 파싱
            import re
            # JSON 추출 (코드 블록이나 다른 텍스트가 포함될 수 있음)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                # 유사도 값 검증
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
        method: str = "auto"  # "hash", "text", "embedding", "auto"
    ) -> Optional[Dict[str, Any]]:
        """두 버전 간 비교 정보 반환

        Args:
            filename: 파일명
            version1: 첫 번째 버전
            version2: 두 번째 버전
            method: 유사도 계산 방법
                - "hash": 해시 기반 (빠름, 같으면 100% 다르면 0%)
                - "text": 텍스트 기반 (중간 속도, 편집 거리 기반)
                - "embedding": 임베딩 기반 (느림, 의미적 유사도)
                - "auto": 자동 선택 (기본값)

        Returns:
            비교 정보 (메타데이터 차이)
        """
        meta1 = self.get_version(filename, version1)
        meta2 = self.get_version(filename, version2)

        if not meta1 or not meta2:
            return None

        # 청크 수 안전하게 변환 (None일 수 있음)
        chunk_count1 = int(meta1.get('chunk_count', 0) or 0)
        chunk_count2 = int(meta2.get('chunk_count', 0) or 0)

        # 내용 유사도 계산
        similarity = 0.0
        similarity_method = "hash"

        # 해시가 같으면 무조건 100%
        if meta1['file_hash'] == meta2['file_hash']:
            similarity = 100.0
            similarity_method = "hash"
        else:
            # 해시가 다른 경우 - 실제 비교 수행
            if method == "hash":
                similarity = 0.0
                similarity_method = "hash"
            else:
                # 파일 경로 가져오기
                path1 = Path(meta1['stored_path'])
                path2 = Path(meta2['stored_path'])

                if not path1.exists() or not path2.exists():
                    logger.warning(f"Version files not found for comparison")
                    similarity = 0.0
                    similarity_method = "hash"
                else:
                    # 텍스트 추출
                    text1 = self._extract_text_from_file(path1)
                    text2 = self._extract_text_from_file(path2)

                    if text1 and text2:
                        # Auto 모드: 파일 크기에 따라 방법 선택
                        if method == "auto":
                            # 작은 파일(<100KB)은 텍스트 비교, 큰 파일은 임베딩
                            file_size = int(meta1['file_size'])
                            if file_size < 100 * 1024:  # 100KB
                                method = "text"
                            else:
                                method = "embedding"

                        # 선택된 방법으로 유사도 계산
                        if method == "text":
                            similarity = self._calculate_text_similarity(text1, text2)
                            similarity_method = "text"
                        elif method == "embedding":
                            emb_sim = self._calculate_embedding_similarity(text1, text2)
                            if emb_sim is not None:
                                similarity = emb_sim
                                similarity_method = "embedding"
                            else:
                                # Fallback to text comparison
                                similarity = self._calculate_text_similarity(text1, text2)
                                similarity_method = "text"
                        elif method == "llm":
                            llm_result = self._calculate_llm_similarity(text1, text2)
                            if llm_result is not None:
                                similarity = llm_result.get("similarity", 0.0)
                                similarity_method = "llm"
                                # LLM 분석 결과를 comparison에 추가 (나중에)
                            else:
                                # Fallback to embedding
                                emb_sim = self._calculate_embedding_similarity(text1, text2)
                                if emb_sim is not None:
                                    similarity = emb_sim
                                    similarity_method = "embedding"
                                else:
                                    similarity = self._calculate_text_similarity(text1, text2)
                                    similarity_method = "text"
                    else:
                        # 텍스트 추출 실패 시 해시 기반
                        similarity = 0.0
                        similarity_method = "hash"

        # 메타데이터 차이 계산
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
                "chunk_diff": chunk_count2 - chunk_count1,  # 프론트엔드가 기대하는 필드명
                "chunk_count_diff": chunk_count2 - chunk_count1,  # 하위 호환성
                "similarity_percentage": round(similarity, 1),
                "similarity_method": similarity_method  # 사용된 유사도 계산 방법
            }
        }

        return comparison

    def delete_version(self, filename: str, version: int) -> bool:
        """특정 버전 삭제

        Args:
            filename: 파일명
            version: 삭제할 버전 번호

        Returns:
            성공 여부
        """
        # 버전 메타데이터 조회
        metadata = self.get_version(filename, version)
        if not metadata:
            logger.warning(f"Version {version} not found for {filename}")
            return False

        # 파일 삭제
        version_path = Path(metadata['stored_path'])
        if version_path.exists():
            version_path.unlink()
            logger.info(f"Deleted version file: {version_path}")

        # Redis 메타데이터 삭제
        meta_key = self.VERSION_META_KEY.format(filename=filename, version=version)
        self.redis.delete(meta_key)

        # 버전 목록에서 제거
        list_key = self.VERSION_LIST_KEY.format(filename=filename)
        self.redis.zrem(list_key, str(version))

        logger.success(f"Deleted {filename} v{version}")
        return True

    def _cleanup_old_versions(self, filename: str):
        """오래된 버전 정리 (보관 정책 적용)

        Args:
            filename: 파일명
        """
        list_key = self.VERSION_LIST_KEY.format(filename=filename)

        # 현재 버전 개수
        version_count = self.redis.zcard(list_key)

        if version_count <= self.max_versions:
            return  # 보관 정책 범위 내

        # 삭제할 버전 개수
        delete_count = version_count - self.max_versions

        # 가장 오래된 버전부터 삭제
        old_versions = self.redis.zrange(list_key, 0, delete_count - 1)

        for version_bytes in old_versions:
            version = int(version_bytes)
            self.delete_version(filename, version)
            logger.info(f"Cleaned up old version: {filename} v{version}")

        logger.info(f"Kept {self.max_versions} most recent versions for {filename}")

    def delete_all_versions(self, filename: str) -> int:
        """파일의 모든 버전 삭제

        Args:
            filename: 파일명

        Returns:
            삭제된 버전 개수
        """
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
        latest_key = self.VERSION_LATEST_KEY.format(filename=filename)
        self.redis.delete(latest_key)

        # 버전 목록 키 삭제
        list_key = self.VERSION_LIST_KEY.format(filename=filename)
        self.redis.delete(list_key)

        logger.success(f"Deleted all {deleted_count} versions for {filename}")
        return deleted_count
