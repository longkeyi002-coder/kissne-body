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


