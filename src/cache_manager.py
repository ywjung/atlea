"""
LLM Response Cache Manager
Caches LLM responses based on question similarity using embeddings.
"""
import json
import hashlib
import numpy as np
from typing import Optional, Dict, List, Tuple
from functools import lru_cache
from collections import OrderedDict
from loguru import logger
from datetime import datetime

from src.redis_helpers import (
    decode_bytes as _decode_bytes,
    decode_redis_hash as _decode_redis_hash,
)
from src.constants import CacheTTL

# Module load timestamp for debugging
logger.debug(f"🔄 cache_manager.py loaded at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Version: FIXED_OLLAMA_ENCODE")


class CacheManager:
    """
    Manages caching of LLM responses with similarity-based retrieval.

    Uses Redis for storage and embedding similarity for question matching.
    """

    def __init__(
        self,
        redis_client,
        embedding_model,
        similarity_threshold: float = 0.90,  # Lowered from 0.95 to 0.90 for better hit rate
        cache_ttl: int = CacheTTL.LONG,  # 1 hour in seconds (default for dynamic data)
        memory_cache_size: int = 50  # Number of entries to keep in memory
    ):
        """
        Initialize cache manager.

        Args:
            redis_client: Redis client instance
            embedding_model: Embedding model for question similarity
            similarity_threshold: Minimum similarity score to use cached response (0-1)
            cache_ttl: Time-to-live for cached responses in seconds
            memory_cache_size: Maximum number of cache entries to keep in memory (LRU)
        """
        # TTL configuration by content type (in seconds)
        self.ttl_config = {
            'static_docs': CacheTTL.VERY_LONG,  # 24 hours for regulations, policies
            'dynamic_data': CacheTTL.LONG,       # 1 hour for frequently changing content
            'realtime': CacheTTL.STANDARD,       # 5 minutes for time-sensitive data
            'default': CacheTTL.LONG             # Default: 1 hour
        }
        self.redis = redis_client
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.cache_ttl = cache_ttl

        # In-memory LRU cache for frequently accessed responses
        self.memory_cache = OrderedDict()
        self.memory_cache_size = memory_cache_size

        # Cache key prefix
        self.cache_prefix = "llm_cache"
        self.index_key = f"{self.cache_prefix}:index"

        # Statistics tracking keys
        self.stats_queries_key = f"{self.cache_prefix}:stats:total_queries"
        self.stats_hits_key = f"{self.cache_prefix}:stats:cache_hits"
        self.stats_memory_hits_key = f"{self.cache_prefix}:stats:memory_hits"

        # Cache enabled state key
        self.enabled_key = f"{self.cache_prefix}:enabled"

        # Initialize enabled state from Redis (default: True)
        try:
            enabled_value = self.redis.get(self.enabled_key)
            self.enabled = enabled_value != "0" if enabled_value else True
            if enabled_value is None:
                # Set default enabled state
                self.redis.set(self.enabled_key, "1")
        except Exception as e:
            logger.warning(f"Failed to load cache enabled state: {e}, defaulting to enabled")
            self.enabled = True

        logger.info(f"CacheManager initialized (threshold={similarity_threshold}, TTL={cache_ttl}s, memory_cache={memory_cache_size}, enabled={self.enabled})")

    def _generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding vector for text."""
        try:
            # OllamaEmbedding returns List[List[float]], need to convert to numpy
            # FIXED: Removed convert_to_numpy parameter (not supported by OllamaEmbedding)
            logger.debug("🔧 Using FIXED version: encode() without convert_to_numpy parameter")
            embeddings = self.embedding_model.encode(text)
            if embeddings and len(embeddings) > 0:
                # Get first embedding (for single text input)
                embedding = np.array(embeddings[0], dtype=np.float32)
                return embedding
            return None
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            logger.error(f"Error type: {type(e).__name__}, Module version: FIXED_OLLAMA_ENCODE")
            return None

    def _calculate_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Returns:
            Similarity score (0-1), where 1 is identical
        """
        try:
            # Cosine similarity
            dot_product = np.dot(emb1, emb2)
            norm_product = np.linalg.norm(emb1) * np.linalg.norm(emb2)

            if norm_product == 0:
                return 0.0

            similarity = dot_product / norm_product
            return float(similarity)
        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}")
            return 0.0

    def safe_scan_keys(self, pattern: str, count: int = 100) -> List[bytes]:
        """
        Safely scan Redis keys using SCAN instead of blocking KEYS command.

        Args:
            pattern: Redis key pattern (e.g., "session:*", "chunk:*")
            count: Number of keys to scan per iteration (default: 100)

        Returns:
            List of matching keys as bytes

        Note:
            This method uses SCAN to avoid blocking Redis during key iteration.
            SCAN is non-blocking and production-safe, unlike KEYS which blocks
            the entire Redis instance.
        """
        try:
            keys = []
            cursor = 0
            while True:
                cursor, batch = self.redis.scan(cursor, match=pattern, count=count)
                keys.extend(batch)
                if cursor == 0:
                    break
            return keys
        except Exception as e:
            logger.error(f"Failed to scan keys with pattern {pattern}: {e}")
            return []

    @staticmethod
    def decode_bytes(value):
        """
        Safely decode bytes to string, or return value as-is if not bytes.
        Delegates to redis_helpers.decode_bytes for consistency.
        """
        return _decode_bytes(value)

    @staticmethod
    def decode_redis_hash(hash_data: Dict) -> Dict[str, str]:
        """
        Decode all keys and values in a Redis hash from bytes to strings.
        Delegates to redis_helpers.decode_redis_hash for consistency.
        """
        return _decode_redis_hash(hash_data)

    def _get_cache_key(self, question_hash: str) -> str:
        """Generate cache key for a question hash."""
        return f"{self.cache_prefix}:question:{question_hash}"

    def _hash_question(self, question: str, top_k: int, document_ids: Optional[List[str]] = None, group_ids: Optional[List[str]] = None) -> str:
        """
        Generate hash for question + parameters.

        Includes top_k, document_ids, and group_ids in hash to differentiate cache entries
        with different retrieval settings.
        """
        # Sort document_ids and group_ids for consistent hashing
        doc_filter = "all" if not document_ids else "|".join(sorted(document_ids))
        group_filter = "all" if not group_ids else "|".join(sorted(group_ids))
        content = f"{question}|top_k={top_k}|docs={doc_filter}|groups={group_filter}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_from_memory_cache(self, cache_key: str) -> Optional[Dict]:
        """Get entry from memory cache (LRU)"""
        if cache_key in self.memory_cache:
            # Move to end (most recently used)
            self.memory_cache.move_to_end(cache_key)
            return self.memory_cache[cache_key]
        return None

    def _set_to_memory_cache(self, cache_key: str, data: Dict) -> None:
        """Set entry in memory cache with LRU eviction"""
        # Add to cache
        self.memory_cache[cache_key] = data
        self.memory_cache.move_to_end(cache_key)

        # Evict oldest if size exceeded
        if len(self.memory_cache) > self.memory_cache_size:
            self.memory_cache.popitem(last=False)  # Remove oldest (first item)

    def get_cached_response(
        self,
        question: str,
        top_k: int,
        similarity_threshold: Optional[float] = None,
        document_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Check if similar question exists in cache and return cached response.

        Args:
            question: User question
            top_k: Number of documents to retrieve (part of cache key)
            similarity_threshold: Custom similarity threshold (defaults to instance threshold)
            document_ids: Optional list of document IDs to filter by (part of cache key)
            group_ids: Optional list of group IDs to filter by (part of cache key)

        Returns:
            Cached response dict if found, None otherwise
            Dict contains: {"response": str, "sources": List[str], "similarity": float}
        """
        # Check if cache is enabled
        if not self.enabled:
            return None

        # Use provided threshold or fall back to instance default
        threshold = similarity_threshold if similarity_threshold is not None else self.similarity_threshold

        # Track total queries
        try:
            self.redis.incr(self.stats_queries_key)
        except Exception as e:
            logger.error(f"Failed to increment total queries: {e}")

        try:
            # Generate embedding for current question
            question_emb = self._generate_embedding(question)
            if question_emb is None:
                return None

            # Check memory cache first (O(1) lookup)
            question_hash = self._hash_question(question, top_k, document_ids, group_ids)
            cache_key = self._get_cache_key(question_hash)
            memory_cached = self._get_from_memory_cache(cache_key)

            if memory_cached:
                # Verify it's not expired and matches parameters
                try:
                    self.redis.incr(self.stats_memory_hits_key)
                    self.redis.incr(self.stats_hits_key)
                except Exception:
                    pass

                logger.info(f"Memory cache HIT! Question: '{question[:50]}...'")
                return {
                    "response": memory_cached["response"],
                    "sources": memory_cached["sources"],
                    "context": memory_cached.get("context", []),
                    "similarity": 1.0,  # Exact match from memory
                    "cached_question": memory_cached["question"]
                }

            # Get all cached question hashes (using SSCAN to avoid blocking)
            cached_hashes = []
            cursor = 0

            while True:
                cursor, hashes = self.redis.sscan(
                    self.index_key,
                    cursor=cursor,
                    count=100
                )
                cached_hashes.extend(hashes)

                if cursor == 0:
                    break

            if not cached_hashes:
                return None

            best_match = None
            best_similarity = 0.0

            # Limit cache lookup to most recent entries for performance
            # Convert to list and limit to prevent O(N) scaling issues
            MAX_CACHE_CHECK = 100  # Only check last 100 cached questions
            cached_hashes_list = cached_hashes[:MAX_CACHE_CHECK]

            # Use pipeline to fetch all cache entries at once (performance optimization)
            pipe = self.redis.pipeline()
            cache_keys = []
            for cached_hash in cached_hashes_list:
                cache_key = self._get_cache_key(cached_hash.decode() if isinstance(cached_hash, bytes) else cached_hash)
                cache_keys.append((cached_hash, cache_key))
                pipe.get(cache_key)

            # Execute pipeline and get all results at once
            cached_results = pipe.execute()

            # Process results
            for (cached_hash, cache_key), cached_data_str in zip(cache_keys, cached_results):
                if not cached_data_str:
                    # Cache entry expired, remove from index
                    self.redis.srem(self.index_key, cached_hash)
                    continue

                cached_data = json.loads(cached_data_str)

                # Early filter: Check if top_k matches (cheap comparison first)
                if cached_data.get("top_k") != top_k:
                    continue

                # Early filter: Check if document_ids matches (normalize None to empty list)
                cached_doc_ids = cached_data.get("document_ids") or []
                current_doc_ids = document_ids or []
                if sorted(cached_doc_ids) != sorted(current_doc_ids):
                    continue

                # Early filter: Check if group_ids matches (normalize None to empty list)
                cached_group_ids = cached_data.get("group_ids") or []
                current_group_ids = group_ids or []
                if sorted(cached_group_ids) != sorted(current_group_ids):
                    continue

                # Calculate similarity (expensive operation, done last)
                cached_emb = np.array(cached_data["embedding"])
                similarity = self._calculate_similarity(question_emb, cached_emb)


                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = {
                        "response": cached_data["response"],
                        "sources": cached_data["sources"],
                        "context": cached_data.get("context", []),  # Include context for source details
                        "similarity": similarity,
                        "cached_question": cached_data["question"]
                    }

                    # Early exit: If we found near-perfect match, no need to check more
                    if best_similarity >= 0.9999:  # Essentially identical
                        break

            # Return cached response if similarity is above threshold
            if best_match and best_similarity >= threshold:
                # Track cache hit
                try:
                    self.redis.incr(self.stats_hits_key)
                except Exception as e:
                    logger.error(f"Failed to increment cache hits: {e}")

                logger.info(
                    f"Cache HIT! Similarity: {best_similarity:.4f}, "
                    f"Question: '{best_match['cached_question'][:50]}...'"
                )
                return best_match

            return None

        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None

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
        content_type: str = 'default'
    ) -> bool:
        """
        Save question-response pair to cache.

        Args:
            question: User question
            response: LLM response
            sources: List of source documents
            top_k: Number of documents retrieved
            cache_ttl: Custom cache TTL in seconds (overrides content_type)
            context: List of context documents with text, filename, score
            document_ids: Optional list of document IDs that were filtered
            group_ids: Optional list of group IDs that were filtered
            content_type: Type of content ('static_docs', 'dynamic_data', 'realtime', 'default')

        Returns:
            True if saved successfully, False otherwise
        """
        # Check if cache is enabled
        if not self.enabled:
            return False

        # Determine TTL based on priority: custom TTL > content_type > instance default
        if cache_ttl is not None:
            ttl_seconds = cache_ttl * 60  # Convert minutes to seconds
        else:
            ttl_seconds = self.ttl_config.get(content_type, self.cache_ttl)
        try:
            # Generate embedding for question
            question_emb = self._generate_embedding(question)
            if question_emb is None:
                return False

            # Generate hash for this question (including document_ids and group_ids)
            question_hash = self._hash_question(question, top_k, document_ids, group_ids)
            cache_key = self._get_cache_key(question_hash)

            # Prepare cache data
            cache_data = {
                "question": question,
                "response": response,
                "sources": sources,
                "top_k": top_k,
                "embedding": question_emb.tolist(),  # Convert numpy array to list for JSON
                "context": context or [],  # Store context for source details
                "document_ids": document_ids or [],  # Store document filter
                "group_ids": group_ids or []  # Store group filter
            }

            # Save to Redis with TTL
            self.redis.setex(
                cache_key,
                ttl_seconds,
                json.dumps(cache_data, ensure_ascii=False)
            )

            # Add to index
            self.redis.sadd(self.index_key, question_hash)

            # Also save to memory cache for faster access
            self._set_to_memory_cache(cache_key, cache_data)

            logger.info(f"Saved to cache: '{question[:50]}...' (hash={question_hash})")
            return True

        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
            return False

    def clear_cache(self) -> int:
        """
        Clear all cached responses.

        Returns:
            Number of entries cleared
        """
        try:
            # Get all cached hashes (using SSCAN to avoid blocking)
            cached_hashes = []
            cursor = 0

            while True:
                cursor, hashes = self.redis.sscan(
                    self.index_key,
                    cursor=cursor,
                    count=100
                )
                cached_hashes.extend(hashes)

                if cursor == 0:
                    break

            count = 0

            # Delete each cache entry
            for cached_hash in cached_hashes:
                cache_key = self._get_cache_key(cached_hash.decode() if isinstance(cached_hash, bytes) else cached_hash)
                self.redis.delete(cache_key)
                count += 1

            # Clear index
            self.redis.delete(self.index_key)

            # Clear memory cache
            self.memory_cache.clear()

            # Reset statistics counters
            self.redis.delete(self.stats_queries_key)
            self.redis.delete(self.stats_hits_key)
            self.redis.delete(self.stats_memory_hits_key)

            logger.info(f"Cleared {count} cache entries, memory cache, and reset statistics")
            return count

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0

    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats: {
                "total_entries": int,
                "memory_cache_entries": int,
                "total_queries": int,
                "cache_hits": int,
                "memory_cache_hits": int,
                "hit_rate": float,
                "similarity_threshold": float,
                "cache_ttl": int
            }
        """
        try:
            # Get all cached hashes (using SSCAN to avoid blocking)
            cached_hashes = []
            cursor = 0

            while True:
                cursor, hashes = self.redis.sscan(
                    self.index_key,
                    cursor=cursor,
                    count=100
                )
                cached_hashes.extend(hashes)

                if cursor == 0:
                    break

            # Count valid entries using Pipeline (O(N) → O(1) round trips)
            valid_count = 0
            if cached_hashes:
                hash_list = [h.decode() if isinstance(h, bytes) else h for h in cached_hashes]
                cache_keys = [self._get_cache_key(h) for h in hash_list]

                # Batch check existence with pipeline
                pipe = self.redis.pipeline()
                for key in cache_keys:
                    pipe.exists(key)
                exists_results = pipe.execute()
                valid_count = sum(1 for exists in exists_results if exists)

            # Get query statistics with pipeline (3 queries → 1 round trip)
            pipe = self.redis.pipeline()
            pipe.get(self.stats_queries_key)
            pipe.get(self.stats_hits_key)
            pipe.get(self.stats_memory_hits_key)
            total_queries, cache_hits, memory_hits = pipe.execute()

            total_queries = int(total_queries) if total_queries else 0
            cache_hits = int(cache_hits) if cache_hits else 0
            memory_hits = int(memory_hits) if memory_hits else 0

            # Calculate hit rate (return as ratio 0.0-1.0, not percentage)
            hit_rate = (cache_hits / total_queries) if total_queries > 0 else 0.0

            return {
                "total_entries": valid_count,
                "memory_cache_entries": len(self.memory_cache),
                "total_queries": total_queries,
                "cache_hits": cache_hits,
                "memory_cache_hits": memory_hits,
                "hit_rate": round(hit_rate, 2),
                "similarity_threshold": self.similarity_threshold,
                "cache_ttl": self.cache_ttl
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
                "cache_ttl": self.cache_ttl
            }

    def is_enabled(self) -> bool:
        """
        Check if cache is enabled.

        Returns:
            True if cache is enabled, False otherwise
        """
        return self.enabled

    def set_enabled(self, enabled: bool) -> bool:
        """
        Enable or disable cache.

        Args:
            enabled: True to enable cache, False to disable

        Returns:
            True if successfully set, False otherwise
        """
        try:
            self.enabled = enabled
            self.redis.set(self.enabled_key, "1" if enabled else "0")
            logger.info(f"Cache {'enabled' if enabled else 'disabled'}")
            return True
        except Exception as e:
            logger.error(f"Failed to set cache enabled state: {e}")
            return False

    def get_embedding_cache(self, query_text: str) -> Optional[List[float]]:
        """
        Get cached embedding for query text.

        Args:
            query_text: Query text to get embedding for

        Returns:
            Cached embedding as list of floats, or None if not found
        """
        try:
            cache_key = f"embedding:{hashlib.md5(query_text.encode()).hexdigest()}"
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.error(f"Error getting embedding cache: {e}")
            return None

    def set_embedding_cache(self, query_text: str, embedding: List[float]) -> bool:
        """
        Save embedding to cache with 1-hour TTL.

        Args:
            query_text: Query text
            embedding: Embedding vector as list of floats

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            cache_key = f"embedding:{hashlib.md5(query_text.encode()).hexdigest()}"
            self.redis.setex(
                cache_key,
                3600,  # 1 hour TTL
                json.dumps(embedding)
            )
            return True
        except Exception as e:
            logger.error(f"Error saving embedding cache: {e}")
            return False

    def get_query_result_cache(self, query_text: str, group_ids: Optional[List[str]] = None) -> Optional[Dict]:
        """
        Get cached complete query result for exact query match.

        This is different from semantic cache - it's for popular/repeated exact queries.
        Uses 5-minute TTL for frequently asked questions.

        Args:
            query_text: Exact query text
            group_ids: Optional list of group IDs for cache key

        Returns:
            Cached result dict with response, sources, context, or None if not found
        """
        try:
            # Create cache key from query + groups
            group_filter = "all" if not group_ids else "|".join(sorted(group_ids))
            cache_key = f"qresult:{hashlib.md5((query_text + group_filter).encode()).hexdigest()}"

            cached = self.redis.get(cache_key)
            if cached:
                logger.info(f"Query result cache HIT for: '{query_text[:50]}...'")
                return json.loads(cached)

            return None
        except Exception as e:
            logger.error(f"Error getting query result cache: {e}")
            return None

    def set_query_result_cache(
        self,
        query_text: str,
        result: Dict,
        group_ids: Optional[List[str]] = None,
        ttl: int = 300  # 5 minutes default
    ) -> bool:
        """
        Save complete query result to cache for exact query matches.

        Args:
            query_text: Query text
            result: Complete result dict with response, sources, context
            group_ids: Optional list of group IDs for cache key
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Create cache key from query + groups
            group_filter = "all" if not group_ids else "|".join(sorted(group_ids))
            cache_key = f"qresult:{hashlib.md5((query_text + group_filter).encode()).hexdigest()}"

            self.redis.setex(
                cache_key,
                ttl,
                json.dumps(result, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.error(f"Error saving query result cache: {e}")
            return False

    def get_follow_up_questions_cache(self, question: str, answer: str) -> Optional[List[str]]:
        """
        Get cached follow-up questions based on question and answer hash.

        Args:
            question: Original user question
            answer: Generated answer

        Returns:
            Cached follow-up questions list, or None if not found
        """
        try:
            # Create cache key from question + answer hash
            cache_input = f"{question}|{answer[:500]}"  # Use first 500 chars of answer
            cache_key = f"followup:{hashlib.md5(cache_input.encode()).hexdigest()}"

            cached = self.redis.get(cache_key)
            if cached:
                logger.info(f"💬 Follow-up cache HIT for: '{question[:50]}...'")
                return json.loads(cached)

            return None
        except Exception as e:
            logger.error(f"Error getting follow-up questions cache: {e}")
            return None

    def set_follow_up_questions_cache(
        self,
        question: str,
        answer: str,
        questions: List[str],
        ttl: int = 3600  # 1 hour default
    ) -> bool:
        """
        Save follow-up questions to cache.

        Args:
            question: Original user question
            answer: Generated answer
            questions: List of follow-up questions
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Create cache key from question + answer hash
            cache_input = f"{question}|{answer[:500]}"  # Use first 500 chars of answer
            cache_key = f"followup:{hashlib.md5(cache_input.encode()).hexdigest()}"

            self.redis.setex(
                cache_key,
                ttl,
                json.dumps(questions, ensure_ascii=False)
            )
            logger.debug(f"💬 Follow-up cache SAVED for: '{question[:50]}...'")
            return True
        except Exception as e:
            logger.error(f"Error saving follow-up questions cache: {e}")
            return False
