"""Redis Helper Utilities

Centralized utilities for Redis data type conversions.
This module provides consistent, safe methods for handling Redis byte data.
"""

from typing import Dict, Union, Optional, Any


def decode_bytes(value: Any) -> Any:
    """
    Safely decode bytes to string, or return value as-is if not bytes.

    Args:
        value: Value to decode (bytes, str, or other)

    Returns:
        Decoded string if value was bytes, otherwise original value

    Example:
        >>> decode_bytes(b'hello')
        'hello'
        >>> decode_bytes('hello')
        'hello'
        >>> decode_bytes(123)
        123
    """
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value


def decode_redis_hash(hash_data: Optional[Dict]) -> Dict[str, str]:
    """
    Decode all keys and values in a Redis hash from bytes to strings.

    Args:
        hash_data: Dictionary from redis.hgetall() or None

    Returns:
        Dictionary with all keys and values decoded to strings

    Example:
        >>> data = {b'name': b'John', b'age': b'30'}
        >>> decode_redis_hash(data)
        {'name': 'John', 'age': '30'}
    """
    if not hash_data:
        return {}

    return {
        decode_bytes(k): decode_bytes(v)
        for k, v in hash_data.items()
    }


def decode_redis_set(set_data: Optional[set]) -> set:
    """
    Decode all values in a Redis set from bytes to strings.

    Args:
        set_data: Set from redis.smembers() or None

    Returns:
        Set with all values decoded to strings

    Example:
        >>> data = {b'user1', b'user2'}
        >>> decode_redis_set(data)
        {'user1', 'user2'}
    """
    if not set_data:
        return set()

    return {decode_bytes(v) for v in set_data}


def decode_redis_list(list_data: Optional[list]) -> list:
    """
    Decode all values in a Redis list from bytes to strings.

    Args:
        list_data: List from redis.lrange() or None

    Returns:
        List with all values decoded to strings

    Example:
        >>> data = [b'item1', b'item2']
        >>> decode_redis_list(data)
        ['item1', 'item2']
    """
    if not list_data:
        return []

    return [decode_bytes(v) for v in list_data]


def get_hash_field(hash_data: Dict, field: str, default: Any = None) -> Any:
    """
    Get a field from a Redis hash, handling both bytes and string keys.

    Args:
        hash_data: Dictionary from redis.hgetall()
        field: Field name to retrieve
        default: Default value if field not found

    Returns:
        Decoded field value or default

    Example:
        >>> data = {b'name': b'John', b'age': b'30'}
        >>> get_hash_field(data, 'name')
        'John'
    """
    if not hash_data:
        return default

    # Try both bytes and string keys
    value = hash_data.get(field.encode()) or hash_data.get(field)
    if value is None:
        return default

    return decode_bytes(value)


def to_int(value: Any, default: int = 0) -> int:
    """
    Convert a value to integer, handling bytes and strings.

    Args:
        value: Value to convert (bytes, str, int, None)
        default: Default value if conversion fails

    Returns:
        Integer value or default

    Example:
        >>> to_int(b'42')
        42
        >>> to_int('42')
        42
        >>> to_int(None, 0)
        0
    """
    if value is None:
        return default
    try:
        decoded = decode_bytes(value)
        return int(decoded) if decoded else default
    except (ValueError, TypeError):
        return default


def to_bool(value: Any, default: bool = False) -> bool:
    """
    Convert a value to boolean, handling bytes and strings.

    Args:
        value: Value to convert (bytes, str, bool, None)
        default: Default value if conversion fails

    Returns:
        Boolean value

    Example:
        >>> to_bool(b'true')
        True
        >>> to_bool('True')
        True
        >>> to_bool('1')
        True
        >>> to_bool(b'false')
        False
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    decoded = decode_bytes(value)
    if isinstance(decoded, str):
        return decoded.lower() in ('true', '1', 'yes')
    return default


def to_bytes(value: Any) -> bytes:
    """
    Convert a value to bytes for Redis storage.

    Args:
        value: Value to convert (str, bytes, int, etc.)

    Returns:
        Bytes representation

    Example:
        >>> to_bytes('hello')
        b'hello'
        >>> to_bytes(42)
        b'42'
    """
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode('utf-8')
    return str(value).encode('utf-8')
