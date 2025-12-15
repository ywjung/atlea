"""
LLM Response Cache Manager
Caches LLM responses based on question similarity using embeddings.
"""
import json
import hashlib
import numpy as np
from typing import Optional, Dict, List, Tuple
from loguru import logger


class CacheManager:
    """
    Manages caching of LLM responses with similarity-based retrieval.

    Uses Redis for storage and embedding similarity for question matching.
    """

    def __init__(
        self,
        redis_client,
        embedding_model,
        similarity_threshold: float = 0.95,
        cache_ttl: int = 3600  # 1 hour in seconds
    ):
        """
        Initialize cache manager.

        Args:
            redis_client: Redis client instance
            embedding_model: Embedding model for question similarity
            similarity_threshold: Minimum similarity score to use cached response (0-1)
            cache_ttl: Time-to-live for cached responses in seconds
        """
        self.redis = redis_client
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.cache_ttl = cache_ttl

        # Cache key prefix
        self.cache_prefix = "llm_cache"
        self.index_key = f"{self.cache_prefix}:index"

        # Statistics tracking keys
        self.stats_queries_key = f"{self.cache_prefix}:stats:total_queries"
        self.stats_hits_key = f"{self.cache_prefix}:stats:cache_hits"

        logger.info(f"CacheManager initialized (threshold={similarity_threshold}, TTL={cache_ttl}s)")

    def _generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding vector for text."""
        try:
            embedding = self.embedding_model.encode(text, convert_to_numpy=True)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
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

    def _get_cache_key(self, question_hash: str) -> str:
        """Generate cache key for a question hash."""
        return f"{self.cache_prefix}:question:{question_hash}"

    def _hash_question(self, question: str, top_k: int, document_ids: Optional[List[str]] = None) -> str:
        """
        Generate hash for question + parameters.

        Includes top_k and document_ids in hash to differentiate cache entries
        with different retrieval settings.
        """
        # Sort document_ids for consistent hashing
        doc_filter = "all" if not document_ids else "|".join(sorted(document_ids))
        content = f"{question}|top_k={top_k}|docs={doc_filter}"
        return hashlib.md5(content.encode()).hexdigest()

    def get_cached_response(
        self,
        question: str,
        top_k: int,
        similarity_threshold: Optional[float] = None,
        document_ids: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Check if similar question exists in cache and return cached response.

        Args:
            question: User question
            top_k: Number of documents to retrieve (part of cache key)
            similarity_threshold: Custom similarity threshold (defaults to instance threshold)
            document_ids: Optional list of document IDs to filter by (part of cache key)

        Returns:
            Cached response dict if found, None otherwise
            Dict contains: {"response": str, "sources": List[str], "similarity": float}
        """
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

            # Get all cached question hashes
            cached_hashes = self.redis.smembers(self.index_key)
            if not cached_hashes:
                logger.debug("Cache is empty")
                return None

            best_match = None
            best_similarity = 0.0

            # Check similarity with each cached question
            for cached_hash in cached_hashes:
                cache_key = self._get_cache_key(cached_hash.decode() if isinstance(cached_hash, bytes) else cached_hash)
                cached_data_str = self.redis.get(cache_key)

                if not cached_data_str:
                    # Cache entry expired, remove from index
                    self.redis.srem(self.index_key, cached_hash)
                    continue

                cached_data = json.loads(cached_data_str)

                # Check if top_k matches
                if cached_data.get("top_k") != top_k:
                    continue

                # Check if document_ids matches (normalize None to empty list for comparison)
                cached_doc_ids = cached_data.get("document_ids") or []
                current_doc_ids = document_ids or []
                if sorted(cached_doc_ids) != sorted(current_doc_ids):
                    continue

                # Calculate similarity
                cached_emb = np.array(cached_data["embedding"])
                similarity = self._calculate_similarity(question_emb, cached_emb)

                logger.debug(
                    f"Similarity with cached question '{cached_data['question'][:50]}...': {similarity:.4f}"
                )

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = {
                        "response": cached_data["response"],
                        "sources": cached_data["sources"],
                        "context": cached_data.get("context", []),  # Include context for source details
                        "similarity": similarity,
                        "cached_question": cached_data["question"]
                    }

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

            logger.debug(f"Cache MISS. Best similarity: {best_similarity:.4f}")
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
        document_ids: Optional[List[str]] = None
    ) -> bool:
        """
        Save question-response pair to cache.

        Args:
            question: User question
            response: LLM response
            sources: List of source documents
            top_k: Number of documents retrieved
            cache_ttl: Custom cache TTL in seconds (defaults to instance TTL)
            context: List of context documents with text, filename, score
            document_ids: Optional list of document IDs that were filtered

        Returns:
            True if saved successfully, False otherwise
        """
        # Use provided TTL or fall back to instance default (convert minutes to seconds)
        ttl_seconds = (cache_ttl * 60) if cache_ttl is not None else self.cache_ttl
        try:
            # Generate embedding for question
            question_emb = self._generate_embedding(question)
            if question_emb is None:
                return False

            # Generate hash for this question (including document_ids)
            question_hash = self._hash_question(question, top_k, document_ids)
            cache_key = self._get_cache_key(question_hash)

            # Prepare cache data
            cache_data = {
                "question": question,
                "response": response,
                "sources": sources,
                "top_k": top_k,
                "embedding": question_emb.tolist(),  # Convert numpy array to list for JSON
                "context": context or [],  # Store context for source details
                "document_ids": document_ids or []  # Store document filter
            }

            # Save to Redis with TTL
            self.redis.setex(
                cache_key,
                ttl_seconds,
                json.dumps(cache_data, ensure_ascii=False)
            )

            # Add to index
            self.redis.sadd(self.index_key, question_hash)

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
            # Get all cached hashes
            cached_hashes = self.redis.smembers(self.index_key)
            count = 0

            # Delete each cache entry
            for cached_hash in cached_hashes:
                cache_key = self._get_cache_key(cached_hash.decode() if isinstance(cached_hash, bytes) else cached_hash)
                self.redis.delete(cache_key)
                count += 1

            # Clear index
            self.redis.delete(self.index_key)

            # Reset statistics counters
            self.redis.delete(self.stats_queries_key)
            self.redis.delete(self.stats_hits_key)

            logger.info(f"Cleared {count} cache entries and reset statistics")
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
                "total_queries": int,
                "cache_hits": int,
                "similarity_threshold": float,
                "cache_ttl": int
            }
        """
        try:
            cached_hashes = self.redis.smembers(self.index_key)

            # Count valid entries (not expired)
            valid_count = 0
            for cached_hash in cached_hashes:
                cache_key = self._get_cache_key(cached_hash.decode() if isinstance(cached_hash, bytes) else cached_hash)
                if self.redis.exists(cache_key):
                    valid_count += 1

            # Get query statistics
            total_queries = self.redis.get(self.stats_queries_key)
            cache_hits = self.redis.get(self.stats_hits_key)

            total_queries = int(total_queries) if total_queries else 0
            cache_hits = int(cache_hits) if cache_hits else 0

            return {
                "total_entries": valid_count,
                "total_queries": total_queries,
                "cache_hits": cache_hits,
                "similarity_threshold": self.similarity_threshold,
                "cache_ttl": self.cache_ttl
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {
                "total_entries": 0,
                "total_queries": 0,
                "cache_hits": 0,
                "similarity_threshold": self.similarity_threshold,
                "cache_ttl": self.cache_ttl
            }
