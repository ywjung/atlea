"""Pagination Utilities

Centralized utilities for consistent pagination across the application.
"""

from typing import TypeVar, Generic, List, Any, Dict
from pydantic import BaseModel, Field


def calculate_total_pages(total: int, page_size: int) -> int:
    """Calculate total pages from total count and page size.

    Args:
        total: Total number of items
        page_size: Items per page

    Returns:
        Total number of pages (0 if page_size is 0 or negative)

    Example:
        >>> calculate_total_pages(25, 10)
        3
        >>> calculate_total_pages(20, 10)
        2
        >>> calculate_total_pages(0, 10)
        0
    """
    if page_size <= 0:
        return 0
    return (total + page_size - 1) // page_size


def paginate_list(items: List[Any], page: int, page_size: int) -> List[Any]:
    """Paginate a list of items.

    Args:
        items: List of items to paginate
        page: Current page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Sliced list for the requested page

    Example:
        >>> paginate_list([1, 2, 3, 4, 5], page=2, page_size=2)
        [3, 4]
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    return items[start_idx:end_idx]


class PaginationMeta(BaseModel):
    """Standard pagination metadata model."""
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, description="Items per page")
    total: int = Field(..., ge=0, description="Total number of items")
    total_pages: int = Field(..., ge=0, description="Total number of pages")

    @classmethod
    def create(cls, page: int, page_size: int, total: int) -> "PaginationMeta":
        """Create pagination metadata with calculated total_pages.

        Args:
            page: Current page number
            page_size: Items per page
            total: Total number of items

        Returns:
            PaginationMeta instance
        """
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=calculate_total_pages(total, page_size)
        )


def create_paginated_response(
    items: List[Any],
    page: int,
    page_size: int,
    total: int,
    items_key: str = "items"
) -> Dict[str, Any]:
    """Create a standardized paginated response dictionary.

    Args:
        items: List of items for current page
        page: Current page number
        page_size: Items per page
        total: Total number of items
        items_key: Key name for the items list (default: "items")

    Returns:
        Dictionary with items and pagination metadata

    Example:
        >>> create_paginated_response([1, 2], page=1, page_size=2, total=5)
        {
            "items": [1, 2],
            "page": 1,
            "page_size": 2,
            "total": 5,
            "total_pages": 3
        }
    """
    return {
        items_key: items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": calculate_total_pages(total, page_size)
    }
