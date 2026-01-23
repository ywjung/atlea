"""Redis Helper Utilities

Centralized utilities for Redis data type conversions.
This module re-exports functions from utils.redis_helpers for backwards compatibility.
"""

from typing import Dict, Optional, Any

# Re-export from utils.redis_helpers
from src.utils.redis_helpers import (
    decode_bytes,
    decode_dict,
    decode_list,
    parse_iso_datetime,
    parse_naive_datetime,
    safe_int,
    safe_float,
    safe_bool,
    utc_now,
    utc_now_iso,
)

# Backwards compatibility aliases
decode_redis_hash = decode_dict
decode_redis_set = lambda s: set(decode_list(list(s))) if s else set()
decode_redis_list = decode_list
get_hash_field = lambda d, f, default=None: decode_bytes(d.get(f.encode()) or d.get(f)) if d and (d.get(f.encode()) or d.get(f)) else default
to_int = safe_int
to_bool = safe_bool


def to_bytes(value: Any) -> bytes:
    """
    Convert a value to bytes for Redis storage.

    Args:
        value: Value to convert (str, bytes, int, etc.)

    Returns:
        Bytes representation
    """
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode('utf-8')
    return str(value).encode('utf-8')


# Explicit exports for IDE autocompletion
__all__ = [
    'decode_bytes',
    'decode_redis_hash',
    'decode_redis_set',
    'decode_redis_list',
    'decode_dict',
    'decode_list',
    'get_hash_field',
    'parse_iso_datetime',
    'parse_naive_datetime',
    'safe_int',
    'safe_float',
    'safe_bool',
    'to_int',
    'to_bool',
    'to_bytes',
    'utc_now',
    'utc_now_iso',
]
