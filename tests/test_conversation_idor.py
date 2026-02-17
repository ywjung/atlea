"""Tests for conversation IDOR protection.

Verifies that user_id ownership filtering works correctly in ConversationManager.
"""

import uuid
import pytest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite @compiles hooks registered in tests/conftest.py
from src.database.base import Base


@pytest.fixture(autouse=True)
def _setup_test_db(monkeypatch):
    """In-memory SQLite + patch SyncSessionFactory.

    conversation_manager.py imports SyncSessionFactory at module level,
    so we must patch it directly on that module (not just on connection).
    """
    import src.database.models  # noqa: F401
    from src.database import connection as conn_mod
    import src.conversation_manager as conv_mod

    engine = create_engine(
        "sqlite:///file:conv_testdb?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_fk(dbapi_conn, _):
        dbapi_conn.cursor().execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    # Patch both the source module and the already-imported reference
    monkeypatch.setattr(conn_mod, "SyncSessionFactory", factory)
    monkeypatch.setattr(conv_mod, "SyncSessionFactory", factory)

    yield

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def cm():
    from src.conversation_manager import ConversationManager
    return ConversationManager()


USER_A = "user-aaa-111"
USER_B = "user-bbb-222"


class TestConversationOwnership:
    """Test that user_id ownership is enforced."""

    def test_create_session_stores_user_id(self, cm):
        sid = cm.create_session(title="Test", user_id=USER_A)
        session = cm.get_session(sid, user_id=USER_A)
        assert session is not None
        assert session["title"] == "Test"

    def test_get_session_blocked_for_other_user(self, cm):
        sid = cm.create_session(title="Private", user_id=USER_A)
        assert cm.get_session(sid, user_id=USER_A) is not None
        assert cm.get_session(sid, user_id=USER_B) is None

    def test_get_messages_blocked_for_other_user(self, cm):
        sid = cm.create_session(user_id=USER_A)
        cm.add_message(sid, "user", "hello", user_id=USER_A)
        assert len(cm.get_messages(sid, user_id=USER_A)) == 1
        assert cm.get_messages(sid, user_id=USER_B) == []

    def test_add_message_blocked_for_other_user(self, cm):
        sid = cm.create_session(user_id=USER_A)
        assert cm.add_message(sid, "user", "hack", user_id=USER_B) is False
        assert cm.get_messages(sid, user_id=USER_A) == []

    def test_delete_session_blocked_for_other_user(self, cm):
        sid = cm.create_session(user_id=USER_A)
        assert cm.delete_session(sid, user_id=USER_B) is False
        assert cm.get_session(sid, user_id=USER_A) is not None

    def test_list_sessions_filtered_by_user(self, cm):
        cm.create_session(title="A1", user_id=USER_A)
        cm.create_session(title="A2", user_id=USER_A)
        cm.create_session(title="B1", user_id=USER_B)

        assert len(cm.list_sessions(user_id=USER_A)) == 2
        assert len(cm.list_sessions(user_id=USER_B)) == 1

    def test_session_count_filtered_by_user(self, cm):
        cm.create_session(user_id=USER_A)
        cm.create_session(user_id=USER_A)
        cm.create_session(user_id=USER_B)

        assert cm.get_session_count(user_id=USER_A) == 2
        assert cm.get_session_count(user_id=USER_B) == 1

    def test_clear_all_sessions_scoped_to_user(self, cm):
        cm.create_session(user_id=USER_A)
        cm.create_session(user_id=USER_A)
        cm.create_session(user_id=USER_B)

        assert cm.clear_all_sessions(user_id=USER_A) == 2
        assert cm.get_session_count(user_id=USER_B) == 1

    def test_toggle_bookmark_blocked_for_other_user(self, cm):
        sid = cm.create_session(user_id=USER_A)
        assert cm.toggle_bookmark(sid, user_id=USER_B) is False
        assert cm.toggle_bookmark(sid, user_id=USER_A) is True

    def test_bookmarked_sessions_filtered_by_user(self, cm):
        sid_a = cm.create_session(user_id=USER_A)
        sid_b = cm.create_session(user_id=USER_B)
        cm.toggle_bookmark(sid_a, user_id=USER_A)
        cm.toggle_bookmark(sid_b, user_id=USER_B)

        assert len(cm.list_bookmarked_sessions(user_id=USER_A)) == 1

    def test_session_exists_with_user_id(self, cm):
        sid = cm.create_session(user_id=USER_A)
        assert cm.session_exists(sid, user_id=USER_A) is True
        assert cm.session_exists(sid, user_id=USER_B) is False

    def test_get_last_message_blocked_for_other_user(self, cm):
        sid = cm.create_session(user_id=USER_A)
        cm.add_message(sid, "user", "hello", user_id=USER_A)
        assert cm.get_last_message(sid, user_id=USER_A) is not None
        assert cm.get_last_message(sid, user_id=USER_B) is None

    def test_update_metadata_blocked_for_other_user(self, cm):
        sid = cm.create_session(user_id=USER_A)
        cm.add_message(sid, "assistant", "hi", user_id=USER_A)
        assert cm.update_last_message_metadata(sid, {"key": "val"}, user_id=USER_B) is False
        assert cm.update_last_message_metadata(sid, {"key": "val"}, user_id=USER_A) is True


class TestLegacyConversations:
    """Test backward compatibility for conversations with no user_id (NULL)."""

    def test_legacy_session_accessible_when_no_user_filter(self, cm):
        sid = cm.create_session(title="Legacy")
        assert cm.get_session(sid) is not None

    def test_legacy_session_accessible_to_any_user(self, cm):
        sid = cm.create_session(title="Legacy")
        assert cm.get_session(sid, user_id=USER_A) is not None
        assert cm.get_session(sid, user_id=USER_B) is not None

    def test_list_sessions_without_user_id_shows_all(self, cm):
        cm.create_session(user_id=USER_A)
        cm.create_session(user_id=USER_B)
        cm.create_session()  # Legacy
        assert len(cm.list_sessions()) == 3
