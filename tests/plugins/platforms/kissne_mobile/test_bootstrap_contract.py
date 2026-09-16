"""KB1-MOBILE-CHAT-TRANSPORT / RED — first-pairing bootstrap (Soul §0.3.16 ②, 裁决 3).

Contract frozen here:

* ``POST /bootstrap`` (device token) answers **which Conversation this installation is on**, plus a
  **bounded** slice of its history. It never creates a Conversation: an installation that was paired
  without joining one gets ``bound=false``, ``conversation=null`` and an empty history.
* Conversation identity is read from the Runtime session store on every call (the plugin keeps no
  installation→conversation mapping of its own — §0.3.14), and nothing credential-shaped is echoed.
* History is the TAIL of the Conversation, capped, and flagged truncated when the cap bites.

RED reason: ``/bootstrap`` does not exist yet (only ``/pair`` answers ``conversation_bound``), so the
first assertion fails on a 404/405 instead of a documented payload. Nothing is skipped.
"""

from _transport_harness import (
    build_session_store,
    http,
    isolated_runtime,
    make_adapter,
    pair,
    preexisting_conversation,
    run,
    seed_transcript,
    start,
    stop,
)

HISTORY_CAP = 50  # frozen upper bound of one bootstrap history slice
KEYISH_FIELDS = ("api_key", "api_server_key", "provider_key", "runtime_key", "management_key")


def test_bootstrap_reports_the_current_conversation_and_its_tail(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            seed_transcript(store, existing.session_id, turns=3)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                status, payload, _ = await http(port, "POST", "/bootstrap", token=token)
            finally:
                await stop(adapter)
        return existing, status, payload

    existing, status, payload = run(scenario())
    assert status == 200, f"bootstrap must answer 200 for a paired device, got {status}: {payload}"
    conversation = payload.get("conversation")
    assert isinstance(conversation, dict), (
        f"bootstrap must describe the current Conversation (the app must not open a new chat): {payload}")
    assert conversation.get("session_id") == existing.session_id, (
        "bootstrap reported a different Conversation than the one this installation joined: "
        f"{conversation} vs {existing.session_id}")
    assert conversation.get("session_key") == existing.session_key, (
        f"bootstrap must report the joined routing key: {conversation}")

    history = payload.get("history")
    assert isinstance(history, list) and history, f"bootstrap must return the Conversation history: {payload}"
    for item in history:
        assert isinstance(item, dict), f"history entries must be objects: {item!r}"
        assert item.get("role") in {"user", "assistant"}, f"history role missing: {item!r}"
        assert isinstance(item.get("text"), str), f"history text missing: {item!r}"
    assert history[-1]["text"] == "seeded answer 2", (
        f"history must be the tail of the Conversation (newest last), got {history[-1]!r}")


def test_bootstrap_history_is_bounded_and_flags_truncation(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            seed_transcript(store, existing.session_id, turns=HISTORY_CAP * 3)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                _, payload, _ = await http(port, "POST", "/bootstrap", token=token)
            finally:
                await stop(adapter)
        return payload

    payload = run(scenario())
    history = payload.get("history") or []
    assert 0 < len(history) <= HISTORY_CAP, (
        f"bootstrap history must be a bounded tail (<= {HISTORY_CAP} messages), got {len(history)}")
    assert payload.get("history_truncated") is True, (
        f"a capped history must be flagged as truncated: {sorted(payload)}")


def test_bootstrap_for_an_unbound_installation_creates_nothing(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter)  # paired, but joined no Conversation
                before = len(store.list_sessions())
                status, payload, _ = await http(port, "POST", "/bootstrap", token=token)
                after = len(store.list_sessions())
            finally:
                await stop(adapter)
        return status, payload, before, after

    status, payload, before, after = run(scenario())
    assert status == 200, f"bootstrap on an unbound installation must answer, got {status}: {payload}"
    assert payload.get("bound") is False, f"an unbound installation must report bound=false: {payload}"
    assert payload.get("conversation") in (None, {}), (
        f"an unbound installation has no current Conversation to report: {payload}")
    assert not payload.get("history"), f"an unbound installation has no history: {payload}"
    assert after == before, (
        "bootstrap created a Runtime Conversation; §0.3.14 forbids the adapter from opening one "
        f"({before} -> {after})")


def test_bootstrap_refuses_unknown_and_revoked_tokens(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                forged, _, _ = await http(port, "POST", "/bootstrap", token="kbm1_d_forged")
                ok, payload, _ = await http(port, "POST", "/bootstrap", token=token)
                _, _, _ = await http(port, "POST", "/revoke", token=token)
                revoked, _, _ = await http(port, "POST", "/bootstrap", token=token)
            finally:
                await stop(adapter)
        return forged, ok, payload, revoked

    forged, ok, payload, revoked = run(scenario())
    assert forged == 401, f"a forged token must be refused, got {forged}"
    assert ok == 200, f"a live token must bootstrap, got {ok}: {payload}"
    assert revoked == 401, f"a revoked token must stop bootstrapping immediately, got {revoked}"


def test_bootstrap_payload_carries_no_credentials(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                status, payload, _ = await http(port, "POST", "/bootstrap", token=token)
            finally:
                await stop(adapter)
        return status, payload

    status, payload = run(scenario())
    assert status == 200, f"bootstrap must answer 200, got {status}: {payload}"
    offenders = sorted(set(payload) & set(KEYISH_FIELDS))
    assert not offenders, f"bootstrap leaked a credential-shaped field: {offenders}"
    conversation = payload.get("conversation") or {}
    forbidden = set(KEYISH_FIELDS) | {"provider", "provider_key"}
    offenders = sorted(set(conversation) & forbidden)
    assert not offenders, f"the reported Conversation leaked provider truth: {offenders}"
    assert "device_token" not in payload, (
        "bootstrap must not hand back a device token (the device already holds it)")
