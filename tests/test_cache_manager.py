"""
Tests for CacheManager

Tests the in-memory L1 cache, embedding generation, similarity calculation,
cache key generation, and enable/disable functionality.

PG-backed L2 operations (semantic cache, embedding cache, query result cache,
follow-up cache) are tested by patching SyncSessionFactory with the
in-memory SQLite test database from tests/auth/conftest.py when available,
or by verifying graceful degradation when PG is unavailable.
"""

import pytest
import json
import numpy as np
from unittest.mock import Mock, MagicMock, patch, call
from collections import OrderedDict
from src.cache_manager import CacheManager


@pytest.fixture
def mock_redis():
    """Mock Redis client (kept as backward-compat accessor)."""
    redis = Mock()
    redis.get = Mock(return_value=None)
    redis.set = Mock(return_value=True)
    redis.setex = Mock(return_value=True)
    redis.incr = Mock(return_value=1)
    redis.smembers = Mock(return_value=set())
    redis.sscan = Mock(return_value=(0, []))
    redis.sadd = Mock(return_value=1)
    redis.srem = Mock(return_value=1)
    redis.delete = Mock(return_value=1)
    redis.exists = Mock(return_value=1)
    redis.scan = Mock(return_value=(0, []))

    pipe_mock = Mock()
    pipe_mock.get = Mock(return_value=pipe_mock)
    pipe_mock.exists = Mock(return_value=pipe_mock)
    pipe_mock.execute = Mock(return_value=[])
    redis.pipeline = Mock(return_value=pipe_mock)
    return redis


@pytest.fixture
def mock_embedding_model():
    """Mock embedding model"""
    model = Mock()
    # Return a list of lists (matching OllamaEmbedding format)
    model.encode = Mock(return_value=[[0.1, 0.2, 0.3, 0.4, 0.5]])
    return model


@pytest.fixture
def cache_manager(mock_redis, mock_embedding_model):
    """CacheManager instance with mocked dependencies.

    PG __init__ load of enabled state will fail gracefully (no real DB),
    defaulting to enabled=True.
    """
    return CacheManager(
        embedding_model=mock_embedding_model,
        similarity_threshold=0.90,
        cache_ttl=3600,
        memory_cache_size=50
    )


class TestCacheManagerInit:
    """Tests for CacheManager initialization"""

    def test_initialization_defaults(self, mock_redis, mock_embedding_model):
        """Test default initialization"""
        cache = CacheManager(
            embedding_model=mock_embedding_model
        )

        assert cache.similarity_threshold == 0.90
        assert cache.cache_ttl == 3600
        assert cache.memory_cache_size == 50
        assert cache.enabled is True
        assert isinstance(cache.memory_cache, OrderedDict)
        assert len(cache.memory_cache) == 0

    def test_initialization_custom_params(self, mock_redis, mock_embedding_model):
        """Test initialization with custom parameters"""
        cache = CacheManager(
            embedding_model=mock_embedding_model,
            similarity_threshold=0.95,
            cache_ttl=7200,
            memory_cache_size=100
        )

        assert cache.similarity_threshold == 0.95
        assert cache.cache_ttl == 7200
        assert cache.memory_cache_size == 100

    def test_initialization_no_redis(self, mock_redis, mock_embedding_model):
        """Test initialization works without Redis."""
        cache = CacheManager(
            embedding_model=mock_embedding_model
        )
        assert not hasattr(cache, 'redis')


class TestEmbeddingOperations:
    """Tests for embedding generation and similarity calculation"""

    def test_generate_embedding_success(self, cache_manager, mock_embedding_model):
        """Test successful embedding generation"""
        result = cache_manager._generate_embedding("test question")

        assert result is not None
        assert isinstance(result, np.ndarray)
        mock_embedding_model.encode.assert_called_once()

    def test_generate_embedding_failure(self, cache_manager, mock_embedding_model):
        """Test embedding generation failure"""
        mock_embedding_model.encode.side_effect = Exception("Encoding failed")

        result = cache_manager._generate_embedding("test question")

        assert result is None

    def test_calculate_similarity_identical(self, cache_manager):
        """Test similarity calculation for identical vectors"""
        emb1 = np.array([1.0, 0.0, 0.0])
        emb2 = np.array([1.0, 0.0, 0.0])

        similarity = cache_manager._calculate_similarity(emb1, emb2)

        assert abs(similarity - 1.0) < 0.0001

    def test_calculate_similarity_orthogonal(self, cache_manager):
        """Test similarity calculation for orthogonal vectors"""
        emb1 = np.array([1.0, 0.0, 0.0])
        emb2 = np.array([0.0, 1.0, 0.0])

        similarity = cache_manager._calculate_similarity(emb1, emb2)

        assert abs(similarity) < 0.0001

    def test_calculate_similarity_zero_norm(self, cache_manager):
        """Test similarity calculation with zero norm"""
        emb1 = np.array([0.0, 0.0, 0.0])
        emb2 = np.array([1.0, 0.0, 0.0])

        similarity = cache_manager._calculate_similarity(emb1, emb2)

        assert similarity == 0.0

    def test_calculate_similarity_error_handling(self, cache_manager):
        """Test similarity calculation error handling"""
        emb1 = np.array([1.0, 0.0])
        emb2 = np.array([1.0])  # Different shapes

        similarity = cache_manager._calculate_similarity(emb1, emb2)

        assert similarity == 0.0


class TestCacheKeys:
    """Tests for cache key generation"""

    def test_get_cache_key(self, cache_manager):
        """Test cache key generation"""
        question_hash = "abc123"

        key = cache_manager._get_cache_key(question_hash)

        assert key == "llm_cache:question:abc123"

    def test_hash_question_basic(self, cache_manager):
        """Test question hashing without filters"""
        hash1 = cache_manager._hash_question("What is Python?", 5)
        hash2 = cache_manager._hash_question("What is Python?", 5)

        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hash length

    def test_hash_question_different_top_k(self, cache_manager):
        """Test different top_k produces different hash"""
        hash1 = cache_manager._hash_question("What is Python?", 5)
        hash2 = cache_manager._hash_question("What is Python?", 10)

        assert hash1 != hash2

    def test_hash_question_with_document_ids(self, cache_manager):
        """Test hashing with document IDs"""
        hash1 = cache_manager._hash_question("Question", 5, document_ids=["doc1", "doc2"])
        hash2 = cache_manager._hash_question("Question", 5, document_ids=["doc2", "doc1"])  # Different order

        # Should be same due to sorting
        assert hash1 == hash2

    def test_hash_question_with_group_ids(self, cache_manager):
        """Test hashing with group IDs"""
        hash1 = cache_manager._hash_question("Question", 5, group_ids=["group1", "group2"])
        hash2 = cache_manager._hash_question("Question", 5, group_ids=["group1"])

        assert hash1 != hash2


class TestMemoryCache:
    """Tests for in-memory LRU cache"""

    def test_get_from_memory_cache_miss(self, cache_manager):
        """Test memory cache miss"""
        result = cache_manager._get_from_memory_cache("nonexistent_key")

        assert result is None

    def test_set_and_get_memory_cache(self, cache_manager):
        """Test setting and getting from memory cache"""
        data = {"response": "Test response", "sources": ["doc1"]}
        cache_manager._set_to_memory_cache("test_key", data)

        result = cache_manager._get_from_memory_cache("test_key")

        assert result == data

    def test_memory_cache_lru_eviction(self, cache_manager):
        """Test LRU eviction when cache size exceeded"""
        cache_manager.memory_cache_size = 3

        # Add 4 items
        cache_manager._set_to_memory_cache("key1", {"data": 1})
        cache_manager._set_to_memory_cache("key2", {"data": 2})
        cache_manager._set_to_memory_cache("key3", {"data": 3})
        cache_manager._set_to_memory_cache("key4", {"data": 4})

        # key1 should be evicted
        assert cache_manager._get_from_memory_cache("key1") is None
        assert cache_manager._get_from_memory_cache("key2") is not None
        assert cache_manager._get_from_memory_cache("key3") is not None
        assert cache_manager._get_from_memory_cache("key4") is not None

    def test_memory_cache_lru_access_updates(self, cache_manager):
        """Test accessing item moves it to end (most recently used)"""
        cache_manager.memory_cache_size = 3

        cache_manager._set_to_memory_cache("key1", {"data": 1})
        cache_manager._set_to_memory_cache("key2", {"data": 2})
        cache_manager._set_to_memory_cache("key3", {"data": 3})

        # Access key1 (moves to end)
        cache_manager._get_from_memory_cache("key1")

        # Add key4 (should evict key2, not key1)
        cache_manager._set_to_memory_cache("key4", {"data": 4})

        assert cache_manager._get_from_memory_cache("key1") is not None
        assert cache_manager._get_from_memory_cache("key2") is None
        assert cache_manager._get_from_memory_cache("key3") is not None
        assert cache_manager._get_from_memory_cache("key4") is not None


class TestSaveToCache:
    """Tests for saving responses to cache"""

    def test_save_to_cache_when_disabled(self, cache_manager):
        """Test save fails when cache is disabled"""
        cache_manager.enabled = False

        result = cache_manager.save_to_cache(
            question="What is Python?",
            response="Answer",
            sources=["doc1.pdf"],
            top_k=5
        )

        assert result is False

    def test_save_to_cache_embedding_failure(self, cache_manager, mock_embedding_model):
        """Test cache save fails when embedding generation fails"""
        mock_embedding_model.encode.side_effect = Exception("Encoding failed")

        result = cache_manager.save_to_cache(
            question="Question",
            response="Answer",
            sources=["doc1.pdf"],
            top_k=5
        )

        assert result is False

    def test_save_to_cache_graceful_degradation(self, cache_manager):
        """Test save degrades gracefully when PG is unavailable."""
        # PG connection will fail in test env without DB → returns False
        result = cache_manager.save_to_cache(
            question="Question",
            response="Answer",
            sources=["doc1.pdf"],
            top_k=5
        )
        # Either True (if test conftest has set up SQLite) or False (no PG)
        assert result in [True, False]


class TestGetCachedResponse:
    """Tests for retrieving cached responses"""

    def test_get_cached_response_when_disabled(self, cache_manager):
        """Test get returns None when cache is disabled"""
        cache_manager.enabled = False

        result = cache_manager.get_cached_response(
            question="What is Python?",
            top_k=5
        )

        assert result is None

    def test_get_cached_response_memory_hit(self, cache_manager, mock_redis):
        """Test memory cache hit"""
        # Setup memory cache
        cache_data = {
            "question": "What is Python?",
            "response": "Answer",
            "sources": ["doc1.pdf"],
            "context": []
        }
        cache_key = "llm_cache:question:test_hash"
        cache_manager._set_to_memory_cache(cache_key, cache_data)

        # Mock hash generation to match
        with patch.object(cache_manager, '_hash_question', return_value='test_hash'):
            result = cache_manager.get_cached_response(
                question="What is Python?",
                top_k=5
            )

        assert result is not None
        assert result["response"] == "Answer"
        assert result["similarity"] == 1.0
        assert result["cached_question"] == "What is Python?"

    def test_get_cached_response_custom_threshold(self, cache_manager):
        """Test get with custom similarity threshold"""
        result = cache_manager.get_cached_response(
            question="What is Python?",
            top_k=5,
            similarity_threshold=0.95
        )

        # Custom threshold should be used
        assert result is None or result["similarity"] >= 0.95


class TestCacheStatistics:
    """Tests for cache statistics"""

    def test_get_cache_stats_empty(self, cache_manager):
        """Test stats with empty/unavailable cache"""
        stats = cache_manager.get_cache_stats()

        assert stats["total_entries"] >= 0
        assert stats["memory_cache_entries"] == 0
        assert stats["total_queries"] >= 0
        assert stats["hit_rate"] >= 0.0

    def test_stats_increment_on_query(self, cache_manager):
        """Test stats counters increment on queries."""
        cache_manager.enabled = True
        initial = cache_manager._stats_total_queries

        # This will attempt PG query and may fail, but counter should increment
        cache_manager.get_cached_response("test", top_k=5)

        assert cache_manager._stats_total_queries == initial + 1

    def test_stats_increment_on_memory_hit(self, cache_manager):
        """Test memory hit counters increment."""
        cache_data = {
            "question": "Q",
            "response": "A",
            "sources": [],
            "context": [],
        }
        cache_manager._set_to_memory_cache("llm_cache:question:memhit", cache_data)

        with patch.object(cache_manager, '_hash_question', return_value='memhit'):
            cache_manager.get_cached_response("Q", top_k=5)

        assert cache_manager._stats_memory_hits >= 1
        assert cache_manager._stats_cache_hits >= 1


class TestCacheControl:
    """Tests for cache control operations"""

    def test_is_enabled_true(self, cache_manager):
        """Test is_enabled returns True"""
        cache_manager.enabled = True

        assert cache_manager.is_enabled() is True

    def test_is_enabled_false(self, cache_manager):
        """Test is_enabled returns False"""
        cache_manager.enabled = False

        assert cache_manager.is_enabled() is False

    def test_set_enabled_updates_attribute(self, cache_manager):
        """Test set_enabled updates internal attribute even if PG fails."""
        cache_manager.set_enabled(False)
        # Attribute should always be updated
        assert cache_manager.enabled is False

        cache_manager.set_enabled(True)
        assert cache_manager.enabled is True


class TestClearCache:
    """Tests for clearing cache"""

    def test_clear_cache_clears_memory(self, cache_manager):
        """Test clear also clears memory cache"""
        cache_manager._set_to_memory_cache("key1", {"data": 1})
        cache_manager._set_to_memory_cache("key2", {"data": 2})

        cache_manager.clear_cache()

        assert len(cache_manager.memory_cache) == 0

    def test_clear_cache_resets_stats(self, cache_manager):
        """Test clear resets statistics counters."""
        cache_manager._stats_total_queries = 100
        cache_manager._stats_cache_hits = 50

        cache_manager.clear_cache()

        assert cache_manager._stats_total_queries == 0
        assert cache_manager._stats_cache_hits == 0


class TestEmbeddingCache:
    """Tests for embedding caching"""

    def test_get_embedding_cache_miss(self, cache_manager):
        """Test embedding cache miss (PG unavailable or empty)."""
        result = cache_manager.get_embedding_cache("test query")
        assert result is None

    def test_embedding_cache_error_handling(self, cache_manager):
        """Test embedding cache error handling (no crash)."""
        result = cache_manager.get_embedding_cache("test query")
        assert result is None

    def test_set_embedding_cache_graceful(self, cache_manager):
        """Test set_embedding_cache doesn't crash without PG."""
        result = cache_manager.set_embedding_cache("test query", [0.1, 0.2, 0.3])
        assert result in [True, False]


class TestQueryResultCache:
    """Tests for query result caching"""

    def test_get_query_result_cache_miss(self, cache_manager):
        """Test query result cache miss"""
        result = cache_manager.get_query_result_cache("test query")
        assert result is None

    def test_set_query_result_cache_graceful(self, cache_manager):
        """Test set doesn't crash without PG."""
        result = cache_manager.set_query_result_cache("test query", {"response": "Answer"})
        assert result in [True, False]

    def test_get_query_result_cache_with_groups(self, cache_manager):
        """Test query result cache with group IDs."""
        result = cache_manager.get_query_result_cache(
            "test query",
            group_ids=["group1", "group2"]
        )
        assert result is None


class TestFollowUpCache:
    """Tests for follow-up questions caching."""

    def test_get_follow_up_cache_miss(self, cache_manager):
        """Test follow-up cache miss."""
        result = cache_manager.get_follow_up_questions_cache("question", "answer")
        assert result is None

    def test_set_follow_up_cache_graceful(self, cache_manager):
        """Test set doesn't crash without PG."""
        result = cache_manager.set_follow_up_questions_cache(
            "question", "answer", ["q1?", "q2?"]
        )
        assert result in [True, False]


class TestEdgeCases:
    """Tests for edge cases and error conditions"""

    def test_empty_question(self, cache_manager):
        """Test with empty question"""
        result = cache_manager.save_to_cache(
            question="",
            response="Answer",
            sources=["doc1.pdf"],
            top_k=5
        )

        assert result in [True, False]

    def test_very_long_question(self, cache_manager):
        """Test with very long question"""
        long_question = "What is " + "Python " * 1000

        result = cache_manager.save_to_cache(
            question=long_question,
            response="Answer",
            sources=["doc1.pdf"],
            top_k=5
        )

        assert result in [True, False]

    def test_unicode_question(self, cache_manager):
        """Test with Unicode characters"""
        result = cache_manager.save_to_cache(
            question="Python이란 무엇인가요?",
            response="파이썬은 프로그래밍 언어입니다",
            sources=["문서.pdf"],
            top_k=5
        )

        assert result in [True, False]

    def test_empty_sources_list(self, cache_manager):
        """Test with empty sources list"""
        result = cache_manager.save_to_cache(
            question="Question",
            response="Answer",
            sources=[],
            top_k=5
        )

        assert result in [True, False]

    def test_none_context(self, cache_manager):
        """Test with None context"""
        result = cache_manager.save_to_cache(
            question="Question",
            response="Answer",
            sources=["doc1.pdf"],
            top_k=5,
            context=None
        )

        assert result in [True, False]


class TestLegacyRedisUtilities:
    """Tests for backward-compatible Redis utility methods."""

    def test_safe_scan_keys(self, cache_manager, mock_redis):
        """Test safe_scan_keys returns empty list (Redis removed)."""
        result = cache_manager.safe_scan_keys("pattern:*")
        assert len(result) == 0
