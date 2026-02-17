"""Shared test infrastructure.

Registers SQLite type compilation hooks once for all tests.
Individual test fixtures handle engine/session setup.
"""

import uuid
import sqlite3

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID, ARRAY as PG_ARRAY

try:
    from pgvector.sqlalchemy import Vector as PG_VECTOR
except ImportError:
    PG_VECTOR = None


# ── SQLite type compilation hooks (registered once globally) ────
# These allow Base.metadata.create_all() to work with SQLite
# even though models use PostgreSQL-specific column types.

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(32)"

@compiles(PG_ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"

if PG_VECTOR is not None:
    @compiles(PG_VECTOR, "sqlite")
    def _compile_vector_sqlite(type_, compiler, **kw):
        return "BLOB"


# ── SQLite UUID adapters ──────────────────────────────────────
sqlite3.register_adapter(uuid.UUID, lambda u: u.hex)
sqlite3.register_converter("UUID", lambda b: uuid.UUID(b.decode()))
sqlite3.register_converter("uuid", lambda b: uuid.UUID(b.decode()))
