"""Data Helper Utilities

Centralized utilities for data type conversions.
This module re-exports functions from utils.data_helpers for backwards compatibility.
"""

from typing import Dict, Optional, Any

# Re-export from utils.data_helpers
from src.utils.data_helpers import (
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
decode_hash = decode_dict
to_int = safe_int
to_bool = safe_bool


def to_bytes(value: Any) -> bytes:
    """
    Convert a value to bytes.

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
    'decode_hash',
    'decode_dict',
    'decode_list',
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
