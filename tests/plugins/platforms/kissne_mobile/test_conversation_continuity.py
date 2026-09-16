"""KB1-MOBILE-ADAPTER / RED — Mobile source must join an ALREADY EXISTING Runtime Conversation.

Ticket §0.3.14: Android → same Hermes Runtime → same Conversation; Conversation truth stays in the
existing ``SessionStore`` / ``state.db`` (``gateway_routing`` is the routing index), ``installation_id``
is only a stable SOURCE identity — the plugin must not build a second installation→conversation store.

Contract frozen here (adapter surface GREEN must deliver):

* ``KissneMobileAdapter`` is wired by the runner via ``BasePlatformAdapter.set_session_store(store)``
  (``gateway/run_adapters.py:1047``; setter at ``gateway/platforms/base.py:2248``) and reads it back as
  ``self._session_store``.
* ``adapter.source_for_installation(installation_id) -> SessionSource``      — the mobile routing source
  (built through ``BasePlatformAdapter.build_source``, base.py:4276).
* ``adapter.bind_conversation(installation_id, session_key) -> bool``        — points the mobile routing
  key at an existing conversation. Public API available for this: ``SessionStore.get_or_create_session``
  (gateway/session.py:858) + ``SessionStore.switch_session`` (gateway/session.py:1127, "Point a session
  key at an existing session ID"), both persisted to ``state.db``.

RED reason: the plugin package does not exist yet — assertions fail explicitly, no ``importorskip``.
"""

import importlib
import tempfile
from pathlib import Path

PRESENT_KEY = "agent:main:telegram:dm:existing-chat"  # informational only; the key is derived, not hardcoded


def _build_session_store(tmpdir):
    from gateway.config import GatewayConfig
    from gateway.session import SessionStore
    return SessionStore(Path(tmpdir), GatewayConfig())


def _pre_existing_conversation(store):
    """Pre-create an existing Runtime Conversation through the normal public path."""
    from gateway.config import Platform
    from gateway.session import SessionSource
    source = SessionSource(platform=Platform.TELEGRAM, chat_id="existing-chat", chat_type="dm",
                           user_id="user-existing")
    return store.get_or_create_session(source)


def _adapter():
    try:
        module = importlib.import_module("plugins.platforms.kissne_mobile.adapter")
    except Exception as exc:
        return None, None, f"cannot import plugins.platforms.kissne_mobile.adapter: {exc!r}"
    cls = getattr(module, "KissneMobileAdapter", None)
    if cls is None:
        return None, None, "adapter.py must export KissneMobileAdapter"
    from gateway.config import Platform, PlatformConfig
    try:
        adapter = cls(PlatformConfig(enabled=True), Platform("kissne_mobile"))
    except Exception as exc:
        return None, None, f"cannot construct KissneMobileAdapter(config, platform): {exc!r}"
    return adapter, module, None


def test_mobile_source_resolves_into_the_preexisting_conversation():
    adapter, _module, error = _adapter()
    assert adapter is not None, f"kb1-mobile-adapter: {error}"
    assert callable(getattr(adapter, "source_for_installation", None)), (
        "KissneMobileAdapter must expose source_for_installation(installation_id)")
    assert callable(getattr(adapter, "bind_conversation", None)), (
        "KissneMobileAdapter must expose bind_conversation(installation_id, session_key)")

    with tempfile.TemporaryDirectory(prefix="kb1m-sessions-") as tmpdir:
        store = _build_session_store(tmpdir)
        existing = _pre_existing_conversation(store)
        adapter.set_session_store(store)

        assert adapter.bind_conversation("inst-1", existing.session_key) is True, (
            "bind_conversation() refused to bind the mobile installation to the existing conversation")

        mobile_source = adapter.source_for_installation("inst-1")
        resolved = store.get_or_create_session(mobile_source)
        assert resolved.session_id == existing.session_id, (
            "the mobile source did not resolve into the existing conversation: "
            f"got {resolved.session_id}, expected {existing.session_id}")



def test_mobile_inbound_creates_no_second_mobile_only_conversation():
    adapter, _module, error = _adapter()
    assert adapter is not None, f"kb1-mobile-adapter: {error}"

    with tempfile.TemporaryDirectory(prefix="kb1m-sessions-") as tmpdir:
        store = _build_session_store(tmpdir)
        existing = _pre_existing_conversation(store)
        adapter.set_session_store(store)
        adapter.bind_conversation("inst-1", existing.session_key)

        first = store.get_or_create_session(adapter.source_for_installation("inst-1"))
        again = store.get_or_create_session(adapter.source_for_installation("inst-1"))
        assert first.session_id == again.session_id == existing.session_id, (
            "repeated Mobile inbound must stay on the same conversation id")

        mobile_entries = [e for e in store.list_sessions() if "kissne_mobile" in e.session_key]
        assert len(mobile_entries) == 1, (
            f"expected exactly one routable mobile conversation, found {len(mobile_entries)}: "
            f"{[(e.session_key, e.session_id) for e in mobile_entries]}")
        assert mobile_entries[0].session_id == existing.session_id, (
            "the mobile routing entry points at a different (mobile-only) conversation")

        # The original platform's routing must stay intact (no conversation-theft).
        still_there = store.lookup_by_session_key(existing.session_key)
        assert still_there is not None and still_there.session_id == existing.session_id, (
            "binding the mobile installation stole/voided the original conversation's routing key")



def test_binding_survives_a_runtime_restart():
    adapter, _module, error = _adapter()
    assert adapter is not None, f"kb1-mobile-adapter: {error}"

    with tempfile.TemporaryDirectory(prefix="kb1m-sessions-") as tmpdir:
        store = _build_session_store(tmpdir)
        existing = _pre_existing_conversation(store)
        adapter.set_session_store(store)
        adapter.bind_conversation("inst-1", existing.session_key)
        bound_id = store.get_or_create_session(adapter.source_for_installation("inst-1")).session_id
        _release(store)

        restarted = _build_session_store(tmpdir)  # restart: fresh store over the same state.db
        after = restarted.get_or_create_session(adapter.source_for_installation("inst-1"))
        assert after.session_id == bound_id == existing.session_id, (
            "after a Runtime restart the Mobile source no longer joins the existing conversation: "
            f"got {after.session_id}, expected {existing.session_id}")
        _release(restarted)


def _release(store):
    """Best-effort close of the store's SQLite handle (no public close() on SessionStore)."""
    db = getattr(store, "_db", None)
    closer = getattr(db, "close", None) or getattr(getattr(db, "_db", None), "close", None)
    if callable(closer):
        closer()


def _persisted_sessions(_home=None):
    """Persisted Conversation truth: the ``sessions`` rows of the isolated ``state.db``.

    The path is resolved exactly the way ``SessionStore`` resolves it
    (``hermes_state._default_db_path()``), so this reads the same file the store writes.
    """
    import sqlite3

    from hermes_state import _default_db_path

    db = Path(_default_db_path())
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT id, source, user_id, ended_at, end_reason, session_key FROM sessions"
        ).fetchall()
    finally:
        con.close()


def test_binding_creates_no_temporary_mobile_only_conversation(tmp_path):
    """Regression: joining an existing Conversation must not manufacture (and then end) a throwaway
    mobile-only Conversation, and must not rewrite the identity of the Conversation it joins.

    Why this assertion exists: ``get_or_create_session`` first materialises a session row for the
    mobile routing key, and ``switch_session`` ends that row (``end_reason='session_switch'``)
    before reopening the target. The routing index then *looks* correct while the persisted truth
    still shows a second, mobile-only Conversation that existed and was discarded — the exact thing
    ticket §0.3.14 forbids. Counting current routing entries cannot see it; the DB rows must be read.
    """
    adapter, _module, error = _adapter()
    assert adapter is not None, f"kb1-mobile-adapter: {error}"

    store = _build_session_store(str(tmp_path / "sessions"))
    existing = _pre_existing_conversation(store)
    adapter.set_session_store(store)

    before = _persisted_sessions()
    assert len(before) == 1, f"expected exactly one pre-existing conversation row, got {before}"

    assert adapter.bind_conversation("inst-1", existing.session_key) is True, (
        "bind_conversation() refused to bind the mobile installation to the existing conversation")

    after = _persisted_sessions()
    before_ids = {row[0] for row in before}

    created = [row for row in after if row[0] not in before_ids]
    assert created == [], (
        "binding created a NEW persisted conversation row; §0.3.14 forbids a second (mobile-only) "
        f"Conversation, even a temporary one: {created}")

    ended = [row for row in after if row[3] is not None or row[4] is not None]
    assert ended == [], f"binding ended a persisted conversation row: {ended}"

    _release(store)


def test_binding_does_not_rewrite_the_joined_conversation_identity(tmp_path):
    """Regression: joining must leave the existing Conversation's persisted identity untouched.

    A binding that rewrites ``source``/``user_id``/``session_key`` on an existing row is not a join,
    it is a mutation of someone else's Conversation truth (§0.3.14).
    """
    adapter, _module, error = _adapter()
    assert adapter is not None, f"kb1-mobile-adapter: {error}"

    store = _build_session_store(str(tmp_path / "sessions"))
    existing = _pre_existing_conversation(store)
    adapter.set_session_store(store)

    assert adapter.bind_conversation("inst-1", existing.session_key) is True, (
        "bind_conversation() refused to bind the mobile installation to the existing conversation")

    joined = [row for row in _persisted_sessions() if row[0] == existing.session_id]
    assert len(joined) == 1, f"the joined conversation row is gone: {after}"
    source, user_id, session_key = joined[0][1], joined[0][2], joined[0][5]
    assert (source, user_id, session_key) == ("telegram", "user-existing", existing.session_key), (
        "binding rewrote the identity of the existing Conversation row (source/user_id/session_key): "
        f"{joined[0]}")

    _release(store)


