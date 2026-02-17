"""
Vector Database - PostgreSQL + pgvector

Stores document chunks and embeddings in PostgreSQL with pgvector extension.
Provides vector similarity search (cosine), BM25 text search (tsvector),
and hybrid search combining both via Reciprocal Rank Fusion.
"""

import json
import uuid as _uuid
from typing import List, Dict, Optional
from loguru import logger
from .performance_utils import log_slow_query

from sqlalchemy import select, func, delete, text, distinct
from sqlalchemy.orm import Session

import re as _re

from .database.connection import SyncSessionFactory
from .database.models.document_chunk import DocumentChunk
from .database.models.sentence_embedding import SentenceEmbedding
from .database.models.system_config import SystemConfig


def _upsert_config(db: Session, key: str, value: str) -> None:
    """Upsert a SystemConfig row."""
    row = db.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    ).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SystemConfig(key=key, value=value, value_type="string"))


class VectorDB:
    """PostgreSQL Vector Database with semantic search (pgvector)"""

    def __init__(
        self,
        index_name: str = "pdf_index",
        embedding_dim: int = 1024,
        **kwargs,
    ):
        """
        Initialize Vector Database.

        Vector data is stored in PostgreSQL (pgvector).
        """
        self.base_index_name = index_name
        self.embedding_dim = embedding_dim

        # Initialize active index tracking in PostgreSQL
        self._initialize_active_index()

    def _initialize_active_index(self):
        """Initialize or restore active index tracking from PostgreSQL"""
        try:
            with SyncSessionFactory() as db:
                row = db.execute(
                    select(SystemConfig).where(SystemConfig.key == "vector:active_index")
                ).scalar_one_or_none()

                if row and row.value:
                    self.index_name = row.value
                    logger.info(f"Restored active index from PG: {self.index_name}")
                else:
                    import time
                    version = int(time.time())
                    self.index_name = f"{self.base_index_name}_v{version}"
                    _upsert_config(db, "vector:active_index", self.index_name)
                    db.commit()
                    logger.info(f"Initialized new active index: {self.index_name}")
        except Exception as e:
            # Graceful fallback if PG is unavailable
            import time
            self.index_name = f"{self.base_index_name}_v{int(time.time())}"
            logger.warning(f"PG unavailable for index init, using fallback: {self.index_name} ({e})")

    @property
    def active_index_name(self) -> str:
        """Get the currently active index name"""
        try:
            with SyncSessionFactory() as db:
                row = db.execute(
                    select(SystemConfig).where(SystemConfig.key == "vector:active_index")
                ).scalar_one_or_none()
                if row and row.value:
                    return row.value
        except Exception:
            pass
        return self.index_name

    def create_new_index(self, index_name: str) -> bool:
        """
        Create a new index version for Blue-Green deployment.

        With PostgreSQL, this just registers the version; no schema changes needed.
        """
        try:
            logger.info(f"Registered new index version: {index_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create index '{index_name}': {e}")
            return False

    def swap_indexes(self, new_index_name: str) -> bool:
        """
        Atomically swap the active index (Blue-Green deployment)
        """
        try:
            old_index_name = self.active_index_name

            with SyncSessionFactory() as db:
                _upsert_config(db, "vector:active_index", new_index_name)
                db.commit()

            self.index_name = new_index_name
            logger.success(f"Index swap complete: {old_index_name} → {new_index_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to swap indexes: {e}")
            return False

    def cleanup_old_index(self, index_name: str) -> bool:
        """
        Clean up old index version documents from PostgreSQL
        """
        try:
            logger.info(f"Cleaning up old index: {index_name}")
            with SyncSessionFactory() as db:
                stmt = delete(DocumentChunk).where(
                    DocumentChunk.index_version == index_name
                )
                result = db.execute(stmt)
                deleted = result.rowcount
                db.commit()

            logger.success(f"Cleaned up {deleted} chunks from old index '{index_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup old index '{index_name}': {e}")
            return False

    def _create_index(self):
        """No-op: PostgreSQL indexes are created by Alembic migration."""
        pass

    def add_documents(
        self,
        documents: List[Dict],
        embeddings: List[List[float]],
        target_index: Optional[str] = None,
        embedding_model=None,
        progress_callback=None
    ):
        """
        Add documents with embeddings to PostgreSQL

        Args:
            documents: List of document dicts with text, filename, source, chunk_index, group_id
            embeddings: List of embedding vectors
            target_index: Optional target index version. If None, uses active index.
            embedding_model: Optional embedding model for sentence-level embeddings.
                             If provided, each chunk is split into sentences and embedded.
            progress_callback: Optional callable(current, total, sentences) for progress reporting
        """
        if len(documents) != len(embeddings):
            raise ValueError("Number of documents must match number of embeddings")

        index_version = target_index if target_index else self.active_index_name

        # Get default group ID from PG
        from .group_manager import DEFAULT_GROUP_UUID
        default_group_id = str(DEFAULT_GROUP_UUID)

        # Cache for filename → group_id
        filename_group_cache = {}

        # Track created chunks for sentence embedding generation
        created_chunks = []

        with SyncSessionFactory() as db:
            # Pre-load existing filename→group mappings from PG
            from .database.models.group_document import GroupDocument as _GD
            existing_mappings = db.query(_GD.filename, _GD.group_id).all()
            for fname, gid in existing_mappings:
                filename_group_cache[fname] = str(gid)

            batch = []
            for doc, emb in zip(documents, embeddings):
                filename = doc.get("filename", "")

                # Preserve existing group assignment
                if filename not in filename_group_cache:
                    filename_group_cache[filename] = default_group_id

                assigned_group_id = doc.get("group_id", filename_group_cache[filename])

                chunk = DocumentChunk(
                    id=_uuid.uuid4(),
                    index_version=index_version,
                    text=doc.get("text", ""),
                    filename=filename,
                    source=doc.get("source", ""),
                    chunk_index=doc.get("chunk_index", 0),
                    group_id=assigned_group_id,
                    embedding=emb if isinstance(emb, list) else list(emb),
                )
                batch.append(chunk)

                if embedding_model is not None:
                    created_chunks.append({
                        "id": chunk.id,
                        "text": doc.get("text", ""),
                        "filename": filename,
                        "chunk_index": doc.get("chunk_index", 0),
                        "group_id": assigned_group_id,
                    })

                # Flush in batches of 500
                if len(batch) >= 500:
                    db.add_all(batch)
                    db.flush()
                    batch = []

            if batch:
                db.add_all(batch)
            db.commit()

        logger.success(f"Added {len(documents)} documents to database (index={index_version})")

        # Generate sentence-level embeddings if model is provided
        if embedding_model is not None and created_chunks:
            total_sentences = 0
            total_chunks = len(created_chunks)
            for idx, chunk_info in enumerate(created_chunks):
                count = self.add_sentence_embeddings(
                    chunk_id=chunk_info["id"],
                    chunk_text=chunk_info["text"],
                    filename=chunk_info["filename"],
                    chunk_index=chunk_info["chunk_index"],
                    group_id=chunk_info["group_id"],
                    index_version=index_version,
                    embedding_model=embedding_model,
                )
                total_sentences += count
                if progress_callback and (idx + 1) % 50 == 0:
                    progress_callback(idx + 1, total_chunks, total_sentences)
            if progress_callback:
                progress_callback(total_chunks, total_chunks, total_sentences)
            logger.info(f"Generated {total_sentences} sentence embeddings for {total_chunks} chunks")

    @log_slow_query(threshold_seconds=1.0)
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_expr: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Vector similarity search using pgvector cosine distance
        """
        try:
            if group_ids is not None and len(group_ids) == 0:
                return []
            if document_ids is not None and len(document_ids) == 0:
                return []

            index_version = self.active_index_name
            emb_list = query_embedding if isinstance(query_embedding, list) else list(query_embedding)
            emb_str = "[" + ",".join(str(v) for v in emb_list) + "]"

            with SyncSessionFactory() as db:
                # Build query: SELECT *, embedding <=> :vec AS score
                # Use raw SQL for pgvector operator (not available via ORM natively)
                where_clauses = ["c.index_version = :idx"]
                params: dict = {"idx": index_version, "top_k": top_k, "vec": emb_str}

                if group_ids:
                    placeholders = [f":g{i}" for i in range(len(group_ids))]
                    where_clauses.append(f"c.group_id IN ({','.join(placeholders)})")
                    for i, gid in enumerate(group_ids):
                        params[f"g{i}"] = gid

                if document_ids:
                    placeholders = [f":d{i}" for i in range(len(document_ids))]
                    where_clauses.append(f"c.filename IN ({','.join(placeholders)})")
                    for i, did in enumerate(document_ids):
                        params[f"d{i}"] = did

                where_sql = " AND ".join(where_clauses)

                sql = text(f"""
                    SELECT c.text, c.filename, c.source, c.chunk_index, c.group_id,
                           (c.embedding <=> CAST(:vec AS vector)) AS score
                    FROM document_chunks c
                    WHERE {where_sql}
                    ORDER BY c.embedding <=> CAST(:vec AS vector)
                    LIMIT :top_k
                """)

                rows = db.execute(sql, params).fetchall()

            documents = []
            for row in rows:
                documents.append({
                    "text": row.text,
                    "filename": row.filename,
                    "source": row.source or "",
                    "chunk_index": row.chunk_index,
                    "group_id": row.group_id or "",
                    "score": float(row.score),
                })

            return documents

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def count_documents(self) -> int:
        """Get total number of document chunks in active index"""
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                cnt = db.execute(
                    select(func.count()).select_from(DocumentChunk).where(
                        DocumentChunk.index_version == idx
                    )
                ).scalar_one()
            return cnt
        except Exception as e:
            logger.warning(f"Failed to count documents: {e}")
            return 0

    def count_unique_files(self) -> int:
        """Get total number of unique files in active index"""
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                cnt = db.execute(
                    select(func.count(distinct(DocumentChunk.filename))).where(
                        DocumentChunk.index_version == idx
                    )
                ).scalar_one()
            return cnt
        except Exception as e:
            logger.error(f"Error counting unique files: {e}")
            return 0

    def _process_key_batch(self, keys, filenames):
        """Backward compat stub — no longer needed with PG."""
        pass

    def is_indexed(self) -> bool:
        """Check if database has documents"""
        try:
            return self.count_documents() > 0
        except Exception:
            return False

    def save_index_state(self, metadata: Dict):
        """Save indexing state metadata to PostgreSQL"""
        try:
            with SyncSessionFactory() as db:
                _upsert_config(db, "vector:index_state", json.dumps(metadata, ensure_ascii=False))
                db.commit()
        except Exception as e:
            logger.error(f"Failed to save index state: {e}")

    def get_index_state(self) -> Optional[Dict]:
        """Get indexing state metadata from PostgreSQL"""
        try:
            with SyncSessionFactory() as db:
                row = db.execute(
                    select(SystemConfig).where(SystemConfig.key == "vector:index_state")
                ).scalar_one_or_none()
                if row and row.value:
                    return json.loads(row.value)
            return None
        except Exception as e:
            logger.error(f"Failed to get index state: {e}")
            return None

    def count_documents_by_filename(self, filename: str) -> int:
        """Count chunks for a specific filename"""
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                cnt = db.execute(
                    select(func.count()).select_from(DocumentChunk).where(
                        DocumentChunk.index_version == idx,
                        DocumentChunk.filename == filename,
                    )
                ).scalar_one()
            return cnt
        except Exception as e:
            logger.error(f"Failed to count documents for {filename}: {e}")
            return 0

    def batch_count_documents_by_filenames(self, filenames: List[str]) -> Dict[str, int]:
        """Count chunks for multiple filenames efficiently"""
        if not filenames:
            return {}
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                stmt = (
                    select(DocumentChunk.filename, func.count().label("cnt"))
                    .where(
                        DocumentChunk.index_version == idx,
                        DocumentChunk.filename.in_(filenames),
                    )
                    .group_by(DocumentChunk.filename)
                )
                rows = db.execute(stmt).all()

            result = {fn: 0 for fn in filenames}
            for row in rows:
                result[row.filename] = row.cnt
            return result
        except Exception as e:
            logger.error(f"Failed to batch count documents: {e}")
            return {fn: 0 for fn in filenames}

    def clear_document_count_cache(self):
        """No-op: PG doesn't need a separate count cache."""
        pass

    def _count_all_filenames_in_batch(self, keys, filename_counts):
        """Backward compat stub."""
        pass

    def _count_filenames_in_batch(self, keys, filename_counts, target_filenames):
        """Backward compat stub."""
        pass

    def get_chunks_by_filename(self, filename: str) -> List[Dict]:
        """Get all chunks for a specific filename, sorted by chunk_index"""
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                stmt = (
                    select(DocumentChunk)
                    .where(
                        DocumentChunk.index_version == idx,
                        DocumentChunk.filename == filename,
                    )
                    .order_by(DocumentChunk.chunk_index)
                )
                rows = db.execute(stmt).scalars().all()

            chunks = []
            for row in rows:
                chunks.append({
                    "text": row.text,
                    "filename": row.filename,
                    "source": row.source or "",
                    "chunk_index": row.chunk_index,
                    "page": row.source or "N/A",
                    "metadata": {
                        "chunk_index": row.chunk_index,
                        "source": row.source or "",
                    },
                })
            return chunks
        except Exception as e:
            logger.error(f"Failed to get chunks for {filename}: {e}")
            return []

    def _get_chunks_from_index(self, doc_ids, filename):
        """Backward compat stub."""
        return self.get_chunks_by_filename(filename)

    def _get_chunks_by_scan(self, filename):
        """Backward compat stub."""
        return self.get_chunks_by_filename(filename)

    def _extract_chunks_from_batch(self, keys, target_filename, chunks):
        """Backward compat stub."""
        pass

    def delete_by_filename(self, filename: str) -> int:
        """Delete all chunks for a filename from the active index"""
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                stmt = delete(DocumentChunk).where(
                    DocumentChunk.index_version == idx,
                    DocumentChunk.filename == filename,
                )
                result = db.execute(stmt)
                deleted = result.rowcount
                db.commit()

            logger.info(f"Deleted {deleted} chunks for {filename}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete documents for {filename}: {e}")
            return 0

    def _delete_by_index(self, doc_ids, filename_index_key):
        """Backward compat stub."""
        return 0

    def _delete_by_scan(self, filename):
        """Backward compat stub."""
        return self.delete_by_filename(filename)

    def _find_keys_to_delete(self, keys, target_filename, deleted_keys):
        """Backward compat stub."""
        pass

    def build_filename_index(self) -> Dict[str, int]:
        """No-op with PG: filename queries use SQL WHERE directly."""
        return self.batch_count_documents_by_filenames(
            self._get_all_filenames()
        )

    def _build_index_batch(self, keys, filename_counts):
        """Backward compat stub."""
        pass

    def _get_all_filenames(self) -> List[str]:
        """Get all unique filenames in active index."""
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                rows = db.execute(
                    select(distinct(DocumentChunk.filename)).where(
                        DocumentChunk.index_version == idx
                    )
                ).scalars().all()
            return list(rows)
        except Exception:
            return []

    def sample_documents_by_filename(self, filename: str, limit: int = 3) -> List[Dict]:
        """Get sample of documents for a specific filename"""
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                stmt = (
                    select(DocumentChunk)
                    .where(
                        DocumentChunk.index_version == idx,
                        DocumentChunk.filename == filename,
                    )
                    .limit(limit)
                )
                rows = db.execute(stmt).scalars().all()

            documents = []
            for row in rows:
                documents.append({
                    "text": row.text,
                    "filename": row.filename,
                    "source": row.source or "",
                    "chunk_index": row.chunk_index,
                })
            return documents
        except Exception as e:
            logger.error(f"Failed to sample documents for {filename}: {e}")
            return []

    def clear_index(self):
        """Clear all documents from active index"""
        try:
            with SyncSessionFactory() as db:
                idx = self.active_index_name
                db.execute(
                    delete(DocumentChunk).where(DocumentChunk.index_version == idx)
                )
                # Clear index state
                db.execute(
                    delete(SystemConfig).where(SystemConfig.key == "vector:index_state")
                )
                db.commit()
            logger.info("Index cleared")
        except Exception as e:
            logger.error(f"Failed to clear index: {e}")
            raise

    def close(self):
        """Cleanup resources."""
        pass

    def bm25_search(
        self,
        query_text: str,
        top_k: int = 20,
        group_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        BM25-style full-text search using PostgreSQL tsvector/plainto_tsquery
        """
        try:
            if group_ids is not None and len(group_ids) == 0:
                return []
            if document_ids is not None and len(document_ids) == 0:
                return []

            index_version = self.active_index_name

            with SyncSessionFactory() as db:
                where_clauses = [
                    "c.index_version = :idx",
                    "c.text_search @@ plainto_tsquery('simple', :q)",
                ]
                params: dict = {"idx": index_version, "q": query_text, "top_k": top_k}

                if group_ids:
                    placeholders = [f":g{i}" for i in range(len(group_ids))]
                    where_clauses.append(f"c.group_id IN ({','.join(placeholders)})")
                    for i, gid in enumerate(group_ids):
                        params[f"g{i}"] = gid

                if document_ids:
                    placeholders = [f":d{i}" for i in range(len(document_ids))]
                    where_clauses.append(f"c.filename IN ({','.join(placeholders)})")
                    for i, did in enumerate(document_ids):
                        params[f"d{i}"] = did

                where_sql = " AND ".join(where_clauses)

                sql = text(f"""
                    SELECT c.text, c.filename, c.source, c.chunk_index, c.group_id,
                           ts_rank(c.text_search, plainto_tsquery('simple', :q)) AS rank
                    FROM document_chunks c
                    WHERE {where_sql}
                    ORDER BY rank DESC
                    LIMIT :top_k
                """)

                rows = db.execute(sql, params).fetchall()

            documents = []
            for i, row in enumerate(rows):
                documents.append({
                    "text": row.text,
                    "filename": row.filename,
                    "source": row.source or "",
                    "chunk_index": row.chunk_index,
                    "group_id": row.group_id or "",
                    "score": 1.0 / (i + 1),
                    "rank": i + 1,
                })

            return documents

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    @staticmethod
    def _reciprocal_rank_fusion(
        rankings: List[List[Dict]],
        k: int = 60
    ) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF) to combine multiple rankings

        RRF formula: score = sum(1 / (k + rank_i))
        """
        doc_scores = {}
        doc_data = {}

        for ranking in rankings:
            for rank, doc in enumerate(ranking, start=1):
                doc_id = doc["text"]
                rrf_contribution = 1.0 / (k + rank)

                if doc_id in doc_scores:
                    doc_scores[doc_id] += rrf_contribution
                else:
                    doc_scores[doc_id] = rrf_contribution
                    doc_data[doc_id] = doc

        final_ranking = []
        for doc_id, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True):
            doc = doc_data[doc_id].copy()
            doc["score"] = score
            final_ranking.append(doc)

        return final_ranking

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        top_k: int = 5,
        group_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None,
        retrieval_k: int = 20
    ) -> List[Dict]:
        """
        Hybrid search combining vector (semantic) and BM25 (keyword) using RRF.
        When sentence embeddings exist, adds sentence-level search as a third signal.
        """
        try:
            logger.info(f"Hybrid search: query='{query_text[:50]}...', top_k={top_k}")

            # Chunk-level vector search
            vector_results = self.search(
                query_embedding=query_embedding,
                top_k=retrieval_k,
                group_ids=group_ids,
                document_ids=document_ids
            )

            # BM25 keyword search
            bm25_results = self.bm25_search(
                query_text=query_text,
                top_k=retrieval_k,
                group_ids=group_ids,
                document_ids=document_ids
            )

            result_lists = [vector_results, bm25_results]

            # Sentence-level vector search (if available)
            sentence_results = self.sentence_search(
                query_embedding=query_embedding,
                top_k=retrieval_k,
                group_ids=group_ids,
                document_ids=document_ids
            )
            if sentence_results:
                result_lists.append(sentence_results)
                logger.info(f"📝 Sentence search contributed {len(sentence_results)} results")

            combined_results = self._reciprocal_rank_fusion(result_lists)
            final_results = combined_results[:top_k]
            logger.info(f"Hybrid search returned {len(final_results)} results")

            return final_results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            logger.warning("Falling back to vector search only")
            return self.search(
                query_embedding=query_embedding,
                top_k=top_k,
                group_ids=group_ids,
                document_ids=document_ids
            )

    def get_neighboring_chunks(
        self,
        filename: str,
        chunk_index: int,
        window: int = 1
    ) -> List[Dict]:
        """
        인접 청크 조회 — 지정된 청크의 앞뒤 window개 청크를 반환

        Args:
            filename: 파일명
            chunk_index: 현재 청크 인덱스
            window: 앞뒤로 가져올 청크 수 (기본 1)

        Returns:
            인접 청크 리스트 (chunk_index 오름차순)
        """
        try:
            index_version = self.active_index_name
            min_idx = max(0, chunk_index - window)
            max_idx = chunk_index + window

            with SyncSessionFactory() as db:
                sql = text("""
                    SELECT c.text, c.filename, c.source, c.chunk_index, c.group_id
                    FROM document_chunks c
                    WHERE c.index_version = :idx
                      AND c.filename = :fname
                      AND c.chunk_index >= :min_idx
                      AND c.chunk_index <= :max_idx
                      AND c.chunk_index != :cur_idx
                    ORDER BY c.chunk_index
                """)
                rows = db.execute(sql, {
                    "idx": index_version,
                    "fname": filename,
                    "min_idx": min_idx,
                    "max_idx": max_idx,
                    "cur_idx": chunk_index
                }).fetchall()

            return [
                {
                    "text": row.text,
                    "filename": row.filename,
                    "source": row.source or "",
                    "chunk_index": row.chunk_index,
                    "group_id": row.group_id or "",
                }
                for row in rows
            ]

        except Exception as e:
            logger.debug(f"Failed to get neighboring chunks: {e}")
            return []

    # ── Sentence-level embeddings ──

    @staticmethod
    def split_sentences(text: str, min_length: int = 10) -> List[str]:
        """
        텍스트를 문장 단위로 분할 (한국어 + 영어 지원)

        Args:
            text: 분할할 텍스트
            min_length: 최소 문장 길이 (이보다 짧으면 이전 문장에 병합)

        Returns:
            문장 리스트
        """
        if not text or len(text.strip()) < min_length:
            return [text.strip()] if text and text.strip() else []

        # 문장 경계 패턴: 마침표/물음표/느낌표 + 공백 또는 줄바꿈
        # 한국어는 '다.', '요.', '까?' 등으로 끝남
        raw_sentences = _re.split(r'(?<=[.!?。])\s+|\n+', text.strip())

        sentences = []
        buffer = ""
        for s in raw_sentences:
            s = s.strip()
            if not s:
                continue
            if len(s) < min_length and buffer:
                buffer += " " + s
            elif len(s) < min_length and not buffer:
                buffer = s
            else:
                if buffer:
                    sentences.append(buffer)
                    buffer = ""
                sentences.append(s)

        if buffer:
            if sentences:
                sentences[-1] += " " + buffer
            else:
                sentences.append(buffer)

        return sentences

    def add_sentence_embeddings(
        self,
        chunk_id: _uuid.UUID,
        chunk_text: str,
        filename: str,
        chunk_index: int,
        group_id: str,
        index_version: str,
        embedding_model
    ) -> int:
        """
        청크를 문장으로 분할하고 각 문장의 임베딩을 저장

        Args:
            chunk_id: 부모 청크 ID
            chunk_text: 청크 전체 텍스트
            filename: 파일명
            chunk_index: 청크 인덱스
            group_id: 그룹 ID
            index_version: 인덱스 버전
            embedding_model: 임베딩 모델 인스턴스

        Returns:
            생성된 문장 임베딩 수
        """
        sentences = self.split_sentences(chunk_text)
        if not sentences:
            return 0

        # 배치 임베딩 생성
        try:
            sentence_embeddings = embedding_model.encode(
                sentences, batch_size=32, use_cache=False
            )
        except Exception as e:
            logger.warning(f"Sentence embedding failed for chunk {chunk_id}: {e}")
            return 0

        with SyncSessionFactory() as db:
            batch = []
            for i, (sent, emb) in enumerate(zip(sentences, sentence_embeddings)):
                se = SentenceEmbedding(
                    id=_uuid.uuid4(),
                    chunk_id=chunk_id,
                    index_version=index_version,
                    sentence_index=i,
                    sentence_text=sent,
                    filename=filename,
                    chunk_index=chunk_index,
                    group_id=group_id,
                    embedding=emb if isinstance(emb, list) else list(emb),
                )
                batch.append(se)

            if batch:
                db.add_all(batch)
                db.commit()

        return len(sentences)

    def sentence_search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        group_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        문장 단위 벡터 검색 — 검색 결과를 부모 청크로 매핑하여 반환

        동일 청크에서 여러 문장이 매치되면 최고 점수로 대표.

        Returns:
            청크 단위 결과 리스트 (chunk text, filename, chunk_index, score 등)
        """
        try:
            index_version = self.active_index_name
            emb_list = query_embedding if isinstance(query_embedding, list) else list(query_embedding)
            emb_str = "[" + ",".join(str(v) for v in emb_list) + "]"

            with SyncSessionFactory() as db:
                where_clauses = ["s.index_version = :idx"]
                params: dict = {"idx": index_version, "top_k": top_k * 3, "vec": emb_str}

                if group_ids:
                    placeholders = [f":g{i}" for i in range(len(group_ids))]
                    where_clauses.append(f"s.group_id IN ({','.join(placeholders)})")
                    for i, gid in enumerate(group_ids):
                        params[f"g{i}"] = gid

                if document_ids:
                    placeholders = [f":d{i}" for i in range(len(document_ids))]
                    where_clauses.append(f"s.filename IN ({','.join(placeholders)})")
                    for i, did in enumerate(document_ids):
                        params[f"d{i}"] = did

                where_sql = " AND ".join(where_clauses)

                # 문장 수준 검색 → 부모 청크 JOIN
                sql = text(f"""
                    SELECT c.text, c.filename, c.source, c.chunk_index, c.group_id,
                           MIN(s.embedding <=> CAST(:vec AS vector)) AS score
                    FROM sentence_embeddings s
                    JOIN document_chunks c ON c.id = s.chunk_id
                    WHERE {where_sql}
                    GROUP BY c.id, c.text, c.filename, c.source, c.chunk_index, c.group_id
                    ORDER BY score
                    LIMIT :top_k
                """)

                rows = db.execute(sql, params).fetchall()

            documents = []
            for row in rows:
                documents.append({
                    "text": row.text,
                    "filename": row.filename,
                    "source": row.source or "",
                    "chunk_index": row.chunk_index,
                    "group_id": row.group_id or "",
                    "score": float(row.score),
                })

            logger.info(f"Sentence search returned {len(documents)} chunks")
            return documents

        except Exception as e:
            logger.warning(f"Sentence search failed (falling back to chunk search): {e}")
            return []

    def has_sentence_embeddings(self) -> bool:
        """현재 인덱스에 문장 임베딩이 존재하는지 확인"""
        try:
            with SyncSessionFactory() as db:
                cnt = db.execute(
                    select(func.count()).select_from(SentenceEmbedding).where(
                        SentenceEmbedding.index_version == self.active_index_name
                    )
                ).scalar_one()
            return cnt > 0
        except Exception:
            return False

    def delete_sentence_embeddings(self, index_version: Optional[str] = None):
        """문장 임베딩 삭제"""
        idx = index_version or self.active_index_name
        try:
            with SyncSessionFactory() as db:
                db.execute(
                    delete(SentenceEmbedding).where(
                        SentenceEmbedding.index_version == idx
                    )
                )
                db.commit()
            logger.info(f"Deleted sentence embeddings for index {idx}")
        except Exception as e:
            logger.error(f"Failed to delete sentence embeddings: {e}")

    # ── Static helpers ──

    @staticmethod
    def escape_query(value: str) -> str:
        """Escape search query special characters"""
        return value.replace('\\', '\\\\').replace('"', '\\"')

    @staticmethod
    def escape_tag_value(value: str) -> str:
        """Escape tag field special characters"""
        special_chars = r',.<>{}[]"\':;!@#$%^&*()-+=~ '
        escaped = ''
        for char in value:
            if char in special_chars:
                escaped += '\\' + char
            else:
                escaped += char
        return escaped
