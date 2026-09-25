"""SessionStore public deletion lifecycle tests."""

import threading
from datetime import datetime

import pytest

from gateway.session import SessionDeleteError, SessionEntry, SessionStore


class FakeSessionDB:
    def __init__(self, session_id):
        self.rows = {session_id: {"end_reason": None}}

    def get_session(self, session_id):
        return self.rows.get(session_id)

    def promote_to_session_reset(self, session_id, reason):
        self.rows[session_id]["end_reason"] = reason

    def end_session(self, session_id, reason):
        self.promote_to_session_reset(session_id, reason)

    def reopen_session(self, session_id):
        self.rows[session_id]["end_reason"] = None


def make_store(*, active=False, save=None):
    session_id = "session-1"
    db = FakeSessionDB(session_id)
    store = object.__new__(SessionStore)
    now = datetime.now()
    store._entries = {
        "canonical:key": SessionEntry(
            session_key="canonical:key", session_id=session_id,
            created_at=now, updated_at=now,
        ),
        "kissne_mobile:device-b": SessionEntry(
            session_key="kissne_mobile:device-b", session_id=session_id,
            created_at=now, updated_at=now,
            active_turn_token="lease-1" if active else None,
        ),
    }
    store._lock = threading.Lock()
    store._session_owner_hints = {}
    store._has_active_processes_fn = None
    store._ensure_loaded_locked = lambda: None
    store._db_for_key = lambda _key: db
    store._save = save or (lambda: None)
    return store, db, session_id


def test_delete_removes_all_aliases_and_ends_the_durable_row():
    store, db, session_id = make_store()

    assert store.delete_session(session_id) is True
    assert store._entries == {}
    assert db.rows[session_id]["end_reason"] == "session_deleted"


def test_delete_refuses_requesters_bound_to_the_target():
    store, db, session_id = make_store()

    with pytest.raises(SessionDeleteError) as exc:
        store.delete_session(session_id, requester_session_key="canonical:key")

    assert exc.value.code == "active"
    assert set(store._entries) == {"canonical:key", "kissne_mobile:device-b"}
    assert db.rows[session_id]["end_reason"] is None


def test_delete_refuses_an_active_alias_lease():
    store, db, session_id = make_store(active=True)

    with pytest.raises(SessionDeleteError) as exc:
        store.delete_session(session_id)

    assert exc.value.code == "active"
    assert db.rows[session_id]["end_reason"] is None


def test_delete_rolls_back_route_and_db_when_routing_persist_fails():
    calls = {"count": 0}

    def failing_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("routing write failed")

    store, db, session_id = make_store(save=failing_once)

    with pytest.raises(SessionDeleteError) as exc:
        store.delete_session(session_id)

    assert exc.value.code == "persistence"
    assert set(store._entries) == {"canonical:key", "kissne_mobile:device-b"}
    assert db.rows[session_id]["end_reason"] is None
