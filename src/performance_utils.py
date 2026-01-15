"""
Performance Monitoring Utilities
Provides decorators and utilities for performance tracking and slow query detection.
"""

import time
import functools
import asyncio
from typing import Callable, Any
from loguru import logger


def log_slow_query(threshold_seconds: float = 1.0):
    """
    Decorator to log slow queries/operations.

    Args:
        threshold_seconds: Time threshold in seconds. Operations exceeding this will be logged.

    Example:
        @log_slow_query(threshold_seconds=2.0)
        def expensive_operation():
            # operation code
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                if duration > threshold_seconds:
                    # Extract meaningful context from args
                    context = _extract_context(args, kwargs)
                    logger.warning(
                        f"⚠️ SLOW QUERY: {func.__module__}.{func.__name__} "
                        f"took {duration:.2f}s (threshold: {threshold_seconds}s) | "
                        f"Context: {context}"
                    )
                else:
                    logger.debug(f"✓ {func.__name__} completed in {duration:.2f}s")

                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"❌ ERROR in {func.__module__}.{func.__name__} "
                    f"after {duration:.2f}s: {e}"
                )
                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                if duration > threshold_seconds:
                    context = _extract_context(args, kwargs)
                    logger.warning(
                        f"⚠️ SLOW QUERY: {func.__module__}.{func.__name__} "
                        f"took {duration:.2f}s (threshold: {threshold_seconds}s) | "
                        f"Context: {context}"
                    )
                else:
                    logger.debug(f"✓ {func.__name__} completed in {duration:.2f}s")

                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"❌ ERROR in {func.__module__}.{func.__name__} "
                    f"after {duration:.2f}s: {e}"
                )
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def _extract_context(args: tuple, kwargs: dict) -> str:
    """
    Extract meaningful context from function arguments for logging.

    Args:
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        String representation of relevant context
    """
    context_parts = []

    # Extract common parameters
    if 'query' in kwargs:
        query = kwargs['query']
        context_parts.append(f"query='{query[:50]}...'")
    elif len(args) > 1 and isinstance(args[1], str):
        # Assume second arg might be query text
        query = args[1]
        if len(query) > 10:
            context_parts.append(f"query='{query[:50]}...'")

    if 'top_k' in kwargs:
        context_parts.append(f"top_k={kwargs['top_k']}")

    if 'document_ids' in kwargs and kwargs['document_ids']:
        count = len(kwargs['document_ids'])
        context_parts.append(f"docs={count}")

    if 'group_ids' in kwargs and kwargs['group_ids']:
        count = len(kwargs['group_ids'])
        context_parts.append(f"groups={count}")

    return ', '.join(context_parts) if context_parts else 'no context'


class PerformanceTracker:
    """
    Simple performance tracker for aggregating metrics.
    """

    def __init__(self):
        self.metrics = {
            'total_queries': 0,
            'slow_queries': 0,
            'total_duration': 0.0,
            'max_duration': 0.0,
            'min_duration': float('inf')
        }

    def record_query(self, duration: float, threshold: float = 1.0):
        """
        Record a query execution time.

        Args:
            duration: Query duration in seconds
            threshold: Slow query threshold
        """
        self.metrics['total_queries'] += 1
        self.metrics['total_duration'] += duration

        if duration > threshold:
            self.metrics['slow_queries'] += 1

        if duration > self.metrics['max_duration']:
            self.metrics['max_duration'] = duration

        if duration < self.metrics['min_duration']:
            self.metrics['min_duration'] = duration

    def get_stats(self) -> dict:
        """
        Get performance statistics.

        Returns:
            Dictionary with performance metrics
        """
        total = self.metrics['total_queries']

        return {
            'total_queries': total,
            'slow_queries': self.metrics['slow_queries'],
            'slow_query_rate': (self.metrics['slow_queries'] / total * 100) if total > 0 else 0,
            'avg_duration': (self.metrics['total_duration'] / total) if total > 0 else 0,
            'max_duration': self.metrics['max_duration'] if total > 0 else 0,
            'min_duration': self.metrics['min_duration'] if total > 0 and self.metrics['min_duration'] != float('inf') else 0
        }

    def reset(self):
        """Reset all metrics."""
        self.metrics = {
            'total_queries': 0,
            'slow_queries': 0,
            'total_duration': 0.0,
            'max_duration': 0.0,
            'min_duration': float('inf')
        }


# Global performance tracker instance
performance_tracker = PerformanceTracker()
