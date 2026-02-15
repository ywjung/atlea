"""
SQLAlchemy Declarative Base

All ORM models inherit from this base class.
"""

from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass
