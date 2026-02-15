"""
LLM Response Cache Manager
Caches LLM responses based on question similarity using embeddings.

Storage: PostgreSQL (semantic cache with pgvector, simple caches with TTL).
In-memory L1 LRU cache is kept for fastest access.
"""
import json
import hashlib
import numpy as np
from typing import Optional, Dict, List, Tuple
from collections import OrderedDict
from loguru import logger
from datetime import datetime, timedelta, timezone

from src.constants import CacheTTL

# Module load timestamp for debugging
logger.debug(f"🔄 cache_manager.py loaded at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Version: PG_CACHE")


# ── helper: upsert into SystemConfig ─────────────────────────────────
def _upsert_config(session, key: str, value: str) -> None:
    """Insert or update a SystemConfig row inside an existing session."""
    from src.database.models.system_config import SystemConfig
    from sqlalchemy import select

    row = session.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    ).scalar_one_or_none()
    if row is None:
        session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


class CacheManager:
    """
    Manages caching of LLM responses with similarity-based retrieval.

    Uses PostgreSQL (pgvector for semantic similarity, simple tables for
    embedding / query-result / follow-up caches).  Keeps an in-memory
    OrderedDict as L1 LRU cache.

    """

    def __init__(
        self,
        embedding_model=None,
        similarity_threshold: float = 0.90,
        cache_ttl: int = CacheTTL.LONG,  # 1 hour in seconds
        memory_cache_size: int = 50,
    ):
        # TTL configuration by content type (in seconds)
        self.ttl_config = {
            'static_docs': CacheTTL.VERY_LONG,
            'dynamic_data': CacheTTL.LONG,
            'realtime': CacheTTL.STANDARD,
            'default': CacheTTL.LONG,
        }

        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.cache_ttl = cache_ttl

        # In-memory LRU cache for frequently accessed responses
        self.memory_cache: OrderedDict = OrderedDict()
        self.memory_cache_size = memory_cache_size

        # In-memory stats counters
        self._stats_total_queries = 0
        self._stats_cache_hits = 0
        self._stats_memory_hits = 0

        # Cache enabled state – load from PG SystemConfig
        self.enabled = True
        try:
            from src.database.connection import SyncSessionFactory
            with SyncSessionFactory() as session:
                from src.database.models.system_config import SystemConfig
                from sqlalchemy import select
                row = session.execute(
                    select(SystemConfig).where(SystemConfig.key == "cache:enabled")
                ).scalar_one_or_none()
                if row is not None:
                    self.enabled = row.value != "0"
                else:
                    _upsert_config(session, "cache:enabled", "1")
                    session.commit()
        except Exception as e:
            logger.warning(f"Failed to load cache enabled state from PG: {e}, defaulting to enabled")

        logger.info(
            f"CacheManager initialized (threshold={similarity_threshold}, "
            f"TTL={cache_ttl}s, memory_cache={memory_cache_size}, enabled={self.enabled})"
        )

    # ── embedding helpers ─────────────────────────────────────────────

    def _generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding vector for text."""
        try:
            embeddings = self.embedding_model.encode(text)
            if embeddings and len(embeddings) > 0:
                return np.array(embeddings[0], dtype=np.float32)
            return None
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    def _calculate_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings (0-1)."""
        try:
            dot_product = np.dot(emb1, emb2)
            norm_product = np.linalg.norm(emb1) * np.linalg.norm(emb2)
            if norm_product == 0:
                return 0.0
            return float(dot_product / norm_product)
        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}")
            return 0.0

    # ── data conversion utilities ─────────────────────

    def safe_scan_keys(self, pattern: str, count: int = 100) -> List[bytes]:
        """Kept for backward compat. Always returns empty list."""
        return []

    @staticmethod
    def decode_bytes(value):
        """Safely decode bytes to string."""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @staticmethod
    def decode_hash(hash_data: Dict) -> Dict[str, str]:
        """Decode all keys and values in a hash from bytes to strings."""
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in hash_data.items()
        }

    # ── cache key helpers ─────────────────────────────────────────────

    def _get_cache_key(self, question_hash: str) -> str:
        """Generate cache key for a question hash (kept for memory-cache compat)."""
        return f"llm_cache:question:{question_hash}"

    def _hash_question(
        self,
        question: str,
        top_k: int,
        document_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
    ) -> str:
        """Generate MD5 hash for question + parameters."""
        doc_filter = "all" if not document_ids else "|".join(sorted(document_ids))
        group_filter = "all" if not group_ids else "|".join(sorted(group_ids))
        content = f"{question}|top_k={top_k}|docs={doc_filter}|groups={group_filter}"
        return hashlib.md5(content.encode()).hexdigest()

    # ── L1 memory cache ───────────────────────────────────────────────

    def _get_from_memory_cache(self, cache_key: str) -> Optional[Dict]:
        if cache_key in self.memory_cache:
            self.memory_cache.move_to_end(cache_key)
            return self.memory_cache[cache_key]
        return None

    def _set_to_memory_cache(self, cache_key: str, data: Dict) -> None:
        self.memory_cache[cache_key] = data
        self.memory_cache.move_to_end(cache_key)
        if len(self.memory_cache) > self.memory_cache_size:
            self.memory_cache.popitem(last=False)

    # ── semantic cache: get ────────────────────────────────────────────

    def get_cached_response(
        self,
        question: str,
        top_k: int,
        similarity_threshold: Optional[float] = None,
        document_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        """Check if similar question exists in cache and return cached response."""
        if not self.enabled:
            return None

        threshold = similarity_threshold if similarity_threshold is not None else self.similarity_threshold
        self._stats_total_queries += 1

        try:
            question_emb = self._generate_embedding(question)
            if question_emb is None:
                return None

            # L1 memory cache check (O(1))
            question_hash = self._hash_question(question, top_k, document_ids, group_ids)
            cache_key = self._get_cache_key(question_hash)
            memory_cached = self._get_from_memory_cache(cache_key)

            if memory_cached:
                self._stats_memory_hits += 1
                self._stats_cache_hits += 1
                logger.info(f"Memory cache HIT! Question: '{question[:50]}...'")
                return {
                    "response": memory_cached["response"],
                    "sources": memory_cached["sources"],
                    "context": memory_cached.get("context", []),
                    "similarity": 1.0,
                    "cached_question": memory_cached["question"],
                }

            # L2: PostgreSQL pgvector similarity search
            from src.database.connection import SyncSessionFactory
            from sqlalchemy import text as sa_text

            now = datetime.now(timezone.utc)
            emb_list = question_emb.tolist()

            with SyncSessionFactory() as session:
                # Use cosine distance (<=>); 1 - distance = similarity
                # Filter by top_k, document_ids, group_ids, not expired
                row = session.execute(
                    sa_text("""
                        SELECT question, response, sources, context,
                               document_ids, group_ids, top_k, embedding,
                               1 - (embedding <=> CAST(:vec AS vector)) AS similarity
                        FROM semantic_cache
                        WHERE expires_at > :now
                          AND top_k = :top_k
                        ORDER BY embedding <=> CAST(:vec AS vector)
                        LIMIT 20
                    """),
                    {"vec": str(emb_list), "now": now, "top_k": top_k},
                ).fetchall()

                if not row:
                    return None

                best_match = None
                best_similarity = 0.0

                for r in row:
                    # Filter by document_ids and group_ids
                    cached_doc_ids = r.document_ids or []
                    current_doc_ids = document_ids or []
                    if sorted(cached_doc_ids) != sorted(current_doc_ids):
                        continue

                    cached_group_ids = r.group_ids or []
                    current_group_ids = group_ids or []
                    if sorted(cached_group_ids) != sorted(current_group_ids):
                        continue

                    sim = float(r.similarity)
                    if sim > best_similarity:
                        best_similarity = sim
                        best_match = {
                            "response": r.response,
                            "sources": r.sources if isinstance(r.sources, list) else json.loads(r.sources) if r.sources else [],
                            "context": r.context if isinstance(r.context, list) else json.loads(r.context) if r.context else [],
                            "similarity": sim,
                            "cached_question": r.question,
                        }
                        if best_similarity >= 0.9999:
                            break

            if best_match and best_similarity >= threshold:
                self._stats_cache_hits += 1
                # Promote to L1 memory cache
                mem_data = {
                    "question": best_match["cached_question"],
                    "response": best_match["response"],
                    "sources": best_match["sources"],
                    "context": best_match["context"],
                }
                self._set_to_memory_cache(cache_key, mem_data)

                logger.info(
                    f"Cache HIT! Similarity: {best_similarity:.4f}, "
                    f"Question: '{best_match['cached_question'][:50]}...'"
                )
                return best_match

            return None

        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None

    # ── semantic cache: save ───────────────────────────────────────────

    def save_to_cache(
        self,
        question: str,
        response: str,
        sources: List[str],
        top_k: int,
        cache_ttl: Optional[int] = None,
        context: Optional[List[Dict]] = None,
        document_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        content_type: str = "default",
    ) -> bool:
        """Save question-response pair to semantic cache (PG)."""
        if not self.enabled:
            return False

        if cache_ttl is not None:
            ttl_seconds = cache_ttl * 60
        else:
            ttl_seconds = self.ttl_config.get(content_type, self.cache_ttl)

        try:
            question_emb = self._generate_embedding(question)
            if question_emb is None:
                return False

            question_hash = self._hash_question(question, top_k, document_ids, group_ids)
            cache_key = self._get_cache_key(question_hash)
            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=ttl_seconds)

            from src.database.connection import SyncSessionFactory
            from src.database.models.semantic_cache import SemanticCache
            from sqlalchemy import select
            import uuid

            with SyncSessionFactory() as session:
                # Upsert by question_hash
                existing = session.execute(
                    select(SemanticCache).where(SemanticCache.question_hash == question_hash)
                ).scalar_one_or_none()

                emb_list = question_emb.tolist()

                if existing:
                    existing.question = question
                    existing.response = response
                    existing.sources = sources
                    existing.context = context or []
                    existing.top_k = top_k
                    existing.document_ids = document_ids or []
                    existing.group_ids = group_ids or []
                    existing.embedding = emb_list
                    existing.expires_at = expires
                else:
                    session.add(SemanticCache(
                        id=uuid.uuid4(),
                        question=question,
                        question_hash=question_hash,
                        response=response,
                        sources=sources,
                        context=context or [],
                        top_k=top_k,
                        document_ids=document_ids or [],
                        group_ids=group_ids or [],
                        embedding=emb_list,
                        expires_at=expires,
                    ))
                session.commit()

            # Also save to L1 memory cache
            mem_data = {
                "question": question,
                "response": response,
                "sources": sources,
                "context": context or [],
            }
            self._set_to_memory_cache(cache_key, mem_data)

            logger.info(f"Saved to cache: '{question[:50]}...' (hash={question_hash})")
            return True

        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
            return False

    def set_cached_response(
        self,
        question: str,
        response: str,
        sources: List[str],
        top_k: int = 5,
        context: Optional[List[Dict]] = None,
        document_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        search_summary: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        content_type: str = "default",
    ) -> bool:
        """Alias for save_to_cache, called from query router."""
        return self.save_to_cache(
            question=question,
            response=response,
            sources=sources,
            top_k=top_k,
            cache_ttl=cache_ttl,
            context=context,
            document_ids=document_ids,
            group_ids=group_ids,
            content_type=content_type,
        )

    # ── clear ──────────────────────────────────────────────────────────

    def clear_cache(self) -> int:
        """Clear all cached responses."""
        # Always clear memory cache and reset stats, even if PG fails
        self.memory_cache.clear()
        self._stats_total_queries = 0
        self._stats_cache_hits = 0
        self._stats_memory_hits = 0

        try:
            from src.database.connection import SyncSessionFactory
            from src.database.models.semantic_cache import SemanticCache
            from sqlalchemy import delete

            with SyncSessionFactory() as session:
                result = session.execute(delete(SemanticCache))
                count = result.rowcount
                session.commit()

            logger.info(f"Cleared {count} cache entries, memory cache, and reset statistics")
            return count

        except Exception as e:
            logger.error(f"Error clearing PG cache: {e}")
            return 0

    # ── stats ──────────────────────────────────────────────────────────

    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        try:
            from src.database.connection import SyncSessionFactory
            from src.database.models.semantic_cache import SemanticCache
            from sqlalchemy import select, func
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)

            with SyncSessionFactory() as session:
                valid_count = session.execute(
                    select(func.count()).select_from(SemanticCache).where(
                        SemanticCache.expires_at > now
                    )
                ).scalar() or 0

            total_queries = self._stats_total_queries
            cache_hits = self._stats_cache_hits
            memory_hits = self._stats_memory_hits
            hit_rate = (cache_hits / total_queries) if total_queries > 0 else 0.0

            return {
                "total_entries": valid_count,
                "memory_cache_entries": len(self.memory_cache),
                "total_queries": total_queries,
                "cache_hits": cache_hits,
                "memory_cache_hits": memory_hits,
                "hit_rate": round(hit_rate, 2),
                "similarity_threshold": self.similarity_threshold,
                "cache_ttl": self.cache_ttl,
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {
                "total_entries": 0,
                "memory_cache_entries": 0,
                "total_queries": 0,
                "cache_hits": 0,
                "memory_cache_hits": 0,
                "hit_rate": 0.0,
                "similarity_threshold": self.similarity_threshold,
                "cache_ttl": self.cache_ttl,
            }

    # ── enable / disable ───────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> bool:
        try:
            self.enabled = enabled
            from src.database.connection import SyncSessionFactory
            with SyncSessionFactory() as session:
                _upsert_config(session, "cache:enabled", "1" if enabled else "0")
                session.commit()
            logger.info(f"Cache {'enabled' if enabled else 'disabled'}")
            return True
        except Exception as e:
            logger.error(f"Failed to set cache enabled state: {e}")
            return False

    # ── embedding cache ────────────────────────────────────────────────

    def get_embedding_cache(self, query_text: str) -> Optional[List[float]]:
        """Get cached embedding for query text from PG."""
        try:
            cache_id = hashlib.md5(query_text.encode()).hexdigest()

            from src.database.connection import SyncSessionFactory
            from src.database.models.generic_cache import EmbeddingCache
            from sqlalchemy import select

            now = datetime.now(timezone.utc)

            with SyncSessionFactory() as session:
                row = session.execute(
                    select(EmbeddingCache).where(
                        EmbeddingCache.id == cache_id,
                        EmbeddingCache.expires_at > now,
                    )
                ).scalar_one_or_none()

                if row:
                    return json.loads(row.embedding_data)
            return None
        except Exception as e:
            logger.error(f"Error getting embedding cache: {e}")
            return None

    def set_embedding_cache(self, query_text: str, embedding: List[float]) -> bool:
        """Save embedding to cache with 1-hour TTL."""
        try:
            cache_id = hashlib.md5(query_text.encode()).hexdigest()
            now = datetime.now(timezone.utc)
            expires = now + timedelta(hours=1)

            from src.database.connection import SyncSessionFactory
            from src.database.models.generic_cache import EmbeddingCache
            from sqlalchemy import select

            with SyncSessionFactory() as session:
                existing = session.execute(
                    select(EmbeddingCache).where(EmbeddingCache.id == cache_id)
                ).scalar_one_or_none()

                if existing:
                    existing.embedding_data = json.dumps(embedding)
                    existing.expires_at = expires
                else:
                    session.add(EmbeddingCache(
                        id=cache_id,
                        embedding_data=json.dumps(embedding),
                        expires_at=expires,
                    ))
                session.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving embedding cache: {e}")
            return False

    # ── query result cache ─────────────────────────────────────────────

    def get_query_result_cache(
        self, query_text: str, group_ids: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """Get cached complete query result for exact query match."""
        try:
            group_filter = "all" if not group_ids else "|".join(sorted(group_ids))
            cache_id = hashlib.md5((query_text + group_filter).encode()).hexdigest()

            from src.database.connection import SyncSessionFactory
            from src.database.models.generic_cache import QueryResultCache
            from sqlalchemy import select

            now = datetime.now(timezone.utc)

            with SyncSessionFactory() as session:
                row = session.execute(
                    select(QueryResultCache).where(
                        QueryResultCache.id == cache_id,
                        QueryResultCache.expires_at > now,
                    )
                ).scalar_one_or_none()

                if row:
                    logger.info(f"Query result cache HIT for: '{query_text[:50]}...'")
                    return json.loads(row.result)
            return None
        except Exception as e:
            logger.error(f"Error getting query result cache: {e}")
            return None

    def set_query_result_cache(
        self,
        query_text: str,
        result: Dict,
        group_ids: Optional[List[str]] = None,
        ttl: int = 300,
    ) -> bool:
        """Save complete query result to cache."""
        try:
            group_filter = "all" if not group_ids else "|".join(sorted(group_ids))
            cache_id = hashlib.md5((query_text + group_filter).encode()).hexdigest()
            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=ttl)

            from src.database.connection import SyncSessionFactory
            from src.database.models.generic_cache import QueryResultCache
            from sqlalchemy import select

            with SyncSessionFactory() as session:
                existing = session.execute(
                    select(QueryResultCache).where(QueryResultCache.id == cache_id)
                ).scalar_one_or_none()

                if existing:
                    existing.result = json.dumps(result, ensure_ascii=False)
                    existing.expires_at = expires
                else:
                    session.add(QueryResultCache(
                        id=cache_id,
                        result=json.dumps(result, ensure_ascii=False),
                        expires_at=expires,
                    ))
                session.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving query result cache: {e}")
            return False

    # ── follow-up questions cache ──────────────────────────────────────

    def get_follow_up_questions_cache(
        self, question: str, answer: str
    ) -> Optional[List[str]]:
        """Get cached follow-up questions based on question and answer hash."""
        try:
            cache_input = f"{question}|{answer[:500]}"
            cache_id = hashlib.md5(cache_input.encode()).hexdigest()

            from src.database.connection import SyncSessionFactory
            from src.database.models.generic_cache import FollowupCache
            from sqlalchemy import select

            now = datetime.now(timezone.utc)

            with SyncSessionFactory() as session:
                row = session.execute(
                    select(FollowupCache).where(
                        FollowupCache.id == cache_id,
                        FollowupCache.expires_at > now,
                    )
                ).scalar_one_or_none()

                if row:
                    logger.info(f"Follow-up cache HIT for: '{question[:50]}...'")
                    return json.loads(row.questions)
            return None
        except Exception as e:
            logger.error(f"Error getting follow-up questions cache: {e}")
            return None

    def set_follow_up_questions_cache(
        self,
        question: str,
        answer: str,
        questions: List[str],
        ttl: int = 3600,
    ) -> bool:
        """Save follow-up questions to cache."""
        try:
            cache_input = f"{question}|{answer[:500]}"
            cache_id = hashlib.md5(cache_input.encode()).hexdigest()
            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=ttl)

            from src.database.connection import SyncSessionFactory
            from src.database.models.generic_cache import FollowupCache
            from sqlalchemy import select

            with SyncSessionFactory() as session:
                existing = session.execute(
                    select(FollowupCache).where(FollowupCache.id == cache_id)
                ).scalar_one_or_none()

                if existing:
                    existing.questions = json.dumps(questions, ensure_ascii=False)
                    existing.expires_at = expires
                else:
                    session.add(FollowupCache(
                        id=cache_id,
                        questions=json.dumps(questions, ensure_ascii=False),
                        expires_at=expires,
                    ))
                session.commit()
            logger.debug(f"Follow-up cache SAVED for: '{question[:50]}...'")
            return True
        except Exception as e:
            logger.error(f"Error saving follow-up questions cache: {e}")
            return False
