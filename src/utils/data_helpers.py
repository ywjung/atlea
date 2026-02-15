"""
Data Helper Utilities

Common utility functions for data type conversions used across the application.
"""

from typing import Any, Dict, Optional, List
from datetime import datetime, timezone


def decode_bytes(value: Any) -> str:
    """
    Decode bytes to string if necessary.

    Args:
        value: Value that may be bytes or string

    Returns:
        Decoded string value
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return str(value)


def decode_dict(data: Dict[Any, Any]) -> Dict[str, str]:
    """
    Decode a dictionary with potentially bytes keys and values.

    Args:
        data: Dictionary with bytes or string keys/values

    Returns:
        Dictionary with string keys and values
    """
    if not data:
        return {}
    return {decode_bytes(k): decode_bytes(v) for k, v in data.items()}


def decode_list(items: list) -> List[str]:
    """
    Decode a list of potentially bytes items.

    Args:
        items: List with bytes or string items

    Returns:
        List with string items
    """
    if not items:
        return []
    return [decode_bytes(item) for item in items]


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO datetime string, handling 'Z' suffix.

    Args:
        dt_str: ISO format datetime string (with or without 'Z')

    Returns:
        datetime object or None if parsing fails
    """
    if not dt_str:
        return None
    try:
        if dt_str.endswith('Z'):
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return datetime.fromisoformat(dt_str)
    except (ValueError, AttributeError, TypeError):
        return None


def parse_naive_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO datetime string to naive datetime (timezone removed).

    Args:
        dt_str: ISO format datetime string

    Returns:
        Naive datetime object or None if parsing fails
    """
    dt = parse_iso_datetime(dt_str)
    if dt and dt.tzinfo:
        return dt.replace(tzinfo=None)
    return dt


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to int.

    Args:
        value: Value to convert (bytes, str, int, etc.)
        default: Default value if conversion fails

    Returns:
        Integer value
    """
    if value is None:
        return default
    try:
        if isinstance(value, bytes):
            return int(value.decode('utf-8'))
        return int(value)
    except (ValueError, TypeError, AttributeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float.

    Args:
        value: Value to convert (bytes, str, float, etc.)
        default: Default value if conversion fails

    Returns:
        Float value
    """
    if value is None:
        return default
    try:
        if isinstance(value, bytes):
            return float(value.decode('utf-8'))
        return float(value)
    except (ValueError, TypeError, AttributeError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    """
    Safely convert value to bool.

    Args:
        value: Value to convert (bytes, str, bool, etc.)
        default: Default value if conversion fails

    Returns:
        Boolean value
    """
    if value is None:
        return default
    try:
        str_val = decode_bytes(value).lower()
        if str_val in ('true', '1', 'yes', 'on'):
            return True
        if str_val in ('false', '0', 'no', 'off', ''):
            return False
        return default
    except (ValueError, TypeError, AttributeError):
        return default


def utc_now() -> datetime:
    """
    Get current UTC datetime (timezone-aware).

    Returns:
        Current UTC datetime
    """
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """
    Get current UTC datetime as ISO string.

    Returns:
        ISO format datetime string
    """
    return datetime.now(timezone.utc).isoformat()
