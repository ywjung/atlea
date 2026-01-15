"""
Performance Optimization Utilities for Backend
"""

import functools
import hashlib
import time
from typing import Any, Callable, Dict, Optional
from loguru import logger


class QueryCache:
    """
    In-memory query result cache with TTL
    """
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        self.ttl = ttl  # seconds

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from function arguments"""
        key_str = f"{args}{sorted(kwargs.items())}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry['timestamp'] < self.ttl:
                return entry['value']
            else:
                # Expired entry
                del self.cache[key]
        return None

    def set(self, key: str, value: Any):
        """Set value in cache with timestamp"""
        # Implement simple LRU by removing oldest if at max size
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.items(), key=lambda x: x[1]['timestamp'])[0]
            del self.cache[oldest_key]

        self.cache[key] = {
            'value': value,
            'timestamp': time.time()
        }

    def clear(self):
        """Clear all cache entries"""
        self.cache.clear()
        logger.info("Cache CLEARED")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'ttl': self.ttl
        }


# Global query cache instance
query_cache = QueryCache(max_size=500, ttl=600)  # 10 minutes TTL


def cached_query(ttl: Optional[int] = None):
    """
    Decorator for caching query results

    Usage:
        @cached_query(ttl=300)
        async def expensive_query(param1, param2):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = query_cache._generate_key(func.__name__, *args, **kwargs)

            # Try to get from cache
            cached_result = query_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = (time.time() - start_time) * 1000  # ms

            # Cache result
            query_cache.set(cache_key, result)

            return result
        return wrapper
    return decorator


class PerformanceMonitor:
    """
    Monitor and track performance metrics
    """
    def __init__(self):
        self.metrics: Dict[str, Dict[str, Any]] = {}

    def track(self, name: str, duration: float, success: bool = True):
        """Track a performance metric"""
        if name not in self.metrics:
            self.metrics[name] = {
                'count': 0,
                'total_time': 0,
                'min_time': float('inf'),
                'max_time': 0,
                'failures': 0,
                'avg_time': 0
            }

        metric = self.metrics[name]
        metric['count'] += 1
        metric['total_time'] += duration
        metric['min_time'] = min(metric['min_time'], duration)
        metric['max_time'] = max(metric['max_time'], duration)
        metric['avg_time'] = metric['total_time'] / metric['count']

        if not success:
            metric['failures'] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get all performance statistics"""
        return self.metrics

    def reset(self):
        """Reset all metrics"""
        self.metrics.clear()


# Global performance monitor
perf_monitor = PerformanceMonitor()


def monitor_performance(name: Optional[str] = None):
    """
    Decorator for monitoring function performance

    Usage:
        @monitor_performance("my_function")
        async def my_function():
            ...
    """
    def decorator(func: Callable):
        metric_name = name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                duration = (time.time() - start_time) * 1000  # ms
                perf_monitor.track(metric_name, duration, success)

        return wrapper
    return decorator


class BatchProcessor:
    """
    Batch multiple operations for efficiency
    """
    def __init__(self, batch_size: int = 10, max_wait: float = 0.1):
        self.batch_size = batch_size
        self.max_wait = max_wait
        self.queue = []
        self.last_process_time = time.time()

    async def add(self, item: Any) -> Any:
        """Add item to batch queue"""
        self.queue.append(item)

        # Process if batch is full or max wait time exceeded
        if (len(self.queue) >= self.batch_size or
            time.time() - self.last_process_time > self.max_wait):
            return await self.process_batch()

    async def process_batch(self):
        """Process all queued items"""
        if not self.queue:
            return []

        batch = self.queue.copy()
        self.queue.clear()
        self.last_process_time = time.time()

        # Process batch here
        logger.info(f"Processing batch of {len(batch)} items")
        return batch


def optimize_query_parameters(func: Callable):
    """
    Decorator to optimize query parameters
    Removes None values, limits array sizes, etc.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Remove None values
        cleaned_kwargs = {k: v for k, v in kwargs.items() if v is not None}

        # Limit list/array sizes to prevent excessive queries
        for key, value in cleaned_kwargs.items():
            if isinstance(value, list) and len(value) > 100:
                logger.warning(f"Limiting {key} from {len(value)} to 100 items")
                cleaned_kwargs[key] = value[:100]

        return await func(*args, **cleaned_kwargs)
    return wrapper


# Export commonly used utilities
__all__ = [
    'QueryCache',
    'query_cache',
    'cached_query',
    'PerformanceMonitor',
    'perf_monitor',
    'monitor_performance',
    'BatchProcessor',
    'optimize_query_parameters'
]
