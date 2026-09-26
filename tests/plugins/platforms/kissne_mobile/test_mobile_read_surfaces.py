"""Regression coverage for Android read surfaces."""
from _transport_harness import (
    PAIRED_INSTALLATION, build_session_store, http, isolated_runtime, make_adapter, pair,
    preexisting_conversation, run, seed_transcript, start, stop,
)


def test_paired_device_can_read_deduplicated_session_index_and_status(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                session_result = await http(port, "GET", "/admin/sessions", token=token)
                status_result = await http(port, "GET", "/admin/status", token=token)
                unauth = await http(port, "GET", "/admin/sessions")
                return conversation, session_result, status_result, unauth
            finally:
                await stop(adapter)

    conversation, session_result, status_result, unauth = run(scenario())
    assert session_result[0] == 200, session_result
    rows = session_result[1]["sessions"]
    assert sum(row["session_id"] == conversation.session_id for row in rows) == 1
    assert session_result[1]["active_session_id"] == conversation.session_id
    assert status_result[0] == 200, status_result
    assert status_result[1]["mobile"]["connected"] is True
    assert unauth[0] == 401


def test_paired_device_can_delete_inactive_session_but_not_active_session(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            active = preexisting_conversation(sessions)
            inactive = preexisting_conversation(
                sessions, chat_id="delete-me", user_id="user-delete-me"
            )
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=active)
                deleted = await http(port, "DELETE", "/admin/sessions", token=token, body={"session_id": inactive.session_id})
                listed = await http(port, "GET", "/admin/sessions", token=token)
                protected = await http(port, "DELETE", "/admin/sessions", token=token, body={"session_id": active.session_id})
                return inactive.session_id, deleted, listed, protected
            finally:
                await stop(adapter)

    inactive_id, deleted, listed, protected = run(scenario())
    assert deleted[0] == 200, deleted
    assert deleted[1]["deleted"] is True
    assert all(row["session_id"] != inactive_id for row in listed[1]["sessions"])
    assert protected[0] == 409, protected
    assert protected[1]["error"] == "active_session_delete_forbidden"


def test_session_select_by_id_uses_authenticated_route_and_preserves_token(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            first = preexisting_conversation(sessions)
            second = preexisting_conversation(
                sessions, chat_id="select-me", user_id="user-select-me"
            )
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=first)
                selected = await http(
                    port, "POST", "/admin/sessions", token=token,
                    body={"session_id": second.session_id},
                )
                bootstrap = await http(port, "POST", "/bootstrap", token=token, body={"cursor": 0})
                unauth = await http(
                    port, "POST", "/admin/sessions",
                    body={"session_id": first.session_id},
                )
                return second, selected, bootstrap, unauth
            finally:
                await stop(adapter)

    second, selected, bootstrap, unauth = run(scenario())
    assert selected[0] == 200, selected
    assert selected[1]["conversation"]["session_id"] == second.session_id
    assert bootstrap[0] == 200, bootstrap
    assert bootstrap[1]["conversation"]["session_id"] == second.session_id
    assert unauth[0] == 401


def test_picker_lists_the_devices_own_conversations_with_their_titles(tmp_path):
    """The picker is device-scoped and names each row after its own conversation.

    Reading the host-wide routing index instead returned one row per routing alias —
    labelled with the installation — and hid every conversation the device had
    already used, so the Android picker had nothing readable to offer.
    """
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            device_row = sessions.get_or_create_session(
                adapter.source_for_installation(PAIRED_INSTALLATION)
            )
            sessions._db_for_key(device_row.session_key).set_session_title(
                device_row.session_id, "哥哥我今天想你了"
            )
            seed_transcript(sessions, device_row.session_id, 2)
            foreign = preexisting_conversation(sessions, chat_id="someone-else", user_id="user-else")
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=device_row)
                listed = await http(port, "GET", "/admin/sessions", token=token)
                return device_row, foreign, listed
            finally:
                await stop(adapter)

    device_row, foreign, listed = run(scenario())
    assert listed[0] == 200, listed
    rows = {row["session_id"]: row for row in listed[1]["sessions"]}
    assert foreign.session_id not in rows, "another lane's conversation is not this device's to pick"
    assert device_row.session_id in rows
    assert rows[device_row.session_id]["title"] == "哥哥我今天想你了"
    assert rows[device_row.session_id]["active"] is True
    assert listed[1]["active_session_id"] == device_row.session_id


def test_picker_rejoins_a_conversation_whose_routing_alias_moved_on(tmp_path):
    """A retired route must not make the device's own conversation unselectable.

    ``/new`` keeps the routing key but points it at a fresh session, and a switch
    away retires the alias the same way; the conversation itself stays a legitimate
    picker target because the device already owns its row.
    """
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            earlier = sessions.get_or_create_session(
                adapter.source_for_installation(PAIRED_INSTALLATION)
            )
            sessions._db_for_key(earlier.session_key).set_session_title(
                earlier.session_id, "更早的那次对话"
            )
            seed_transcript(sessions, earlier.session_id, 2)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=earlier)
                later = sessions.reset_session(
                    earlier.session_key, display_name=f"Kissne Mobile ({PAIRED_INSTALLATION})"
                )
                assert later is not None and later.session_id != earlier.session_id
                assert sessions.lookup_by_session_id(earlier.session_id) is None
                selected = await http(
                    port, "POST", "/admin/sessions", token=token,
                    body={"session_id": earlier.session_id},
                )
                bootstrap = await http(port, "POST", "/bootstrap", token=token, body={"cursor": 0})
                listed = await http(port, "GET", "/admin/sessions", token=token)
                return earlier, later, selected, bootstrap, listed
            finally:
                await stop(adapter)

    earlier, later, selected, bootstrap, listed = run(scenario())
    assert selected[0] == 200, selected
    assert selected[1]["conversation"]["session_id"] == earlier.session_id
    assert bootstrap[0] == 200, bootstrap
    assert bootstrap[1]["conversation"]["session_id"] == earlier.session_id
    names = {row["session_id"]: row["title"] for row in listed[1]["sessions"]}
    assert names.get(earlier.session_id) == "更早的那次对话"


def test_pair_endpoint_rejects_installation_only_token_mint(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            port = await start(adapter)
            try:
                return await http(
                    port, "POST", "/pair",
                    body={"installation_id": "untrusted-installation"},
                )
            finally:
                await stop(adapter)

    result = run(scenario())
    assert result[0] == 400, result
    assert result[1]["error"] == "pairing_code_and_installation_id_required"


def test_connected_adapter_registers_mobile_read_routes(tmp_path):
    """Boot the real adapter listener and prove the deployed read routes exist, not just handlers."""
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                session_result = await http(port, "GET", "/admin/sessions", token=token)
                history_result = await http(port, "GET", "/history?limit=10", token=token)
                search_result = await http(port, "GET", "/search?q=definitely-no-match", token=token)
                return session_result, history_result, search_result
            finally:
                await stop(adapter)

    session_result, history_result, search_result = run(scenario())
    assert session_result[0] == 200, session_result
    assert history_result[0] == 200, history_result
    assert "messages" in history_result[1]
    assert search_result[0] == 200, search_result
    assert "results" in search_result[1]


def test_production_gateway_startup_chain_serves_mobile_read_routes(tmp_path, monkeypatch):
    """Full production start(): create -> wire -> connect -> publish -> real HTTP listener."""
    from gateway.config import GatewayConfig, Platform, PlatformConfig
    from gateway.run import GatewayRunner
    from _transport_harness import seed_transcript

    async def _no_async(*_args, **_kwargs):
        return None

    async def _no_secondary(self, connected_count, _skipped):
        return False, connected_count

    async def scenario():
        with isolated_runtime(tmp_path):
            platform = Platform("kissne_mobile")
            platform_config = PlatformConfig(
                enabled=True, extra={"enabled": True, "host": "127.0.0.1", "port": 0}
            )
            runner = GatewayRunner(GatewayConfig(platforms={platform: platform_config}))
            sessions = runner.session_store
            conversation = preexisting_conversation(sessions)
            seed_transcript(sessions, conversation.session_id, 2)

            # Keep GatewayRunner.start() itself real. Suppress only unrelated boot work
            # (recovery/free-tier/warmup/watchers) so this test cannot touch network or
            # leave background tasks behind; adapter creation, wiring, connect, publish,
            # route registration and HTTP remain the production implementations.
            monkeypatch.setattr(runner, "_start_recover_previous_run", _no_async)
            monkeypatch.setattr(runner, "_start_free_tier_bootstrap", lambda: None)
            monkeypatch.setattr(runner, "_start_startup_warmup", lambda: None)
            monkeypatch.setattr(runner, "_start_secondary_profiles", _no_secondary.__get__(runner))
            monkeypatch.setattr(runner, "_start_finish_wiring", _no_async)
            monkeypatch.setattr(runner, "_start_spawn_background_watchers", lambda: None)

            started = await runner.start()
            assert started is True
            assert runner._running is True
            adapter = runner.adapters[platform]
            assert adapter.gateway_runner is runner
            assert getattr(adapter, "_session_store", None) is runner.session_store
            resolver = getattr(adapter.gateway_runner, "_resolve_session_reasoning_config", None)
            assert callable(resolver), "production-started Mobile adapter must expose the real reasoning resolver"
            port = adapter.bound_port
            assert isinstance(port, int) and port > 0

            try:
                unauth = await http(port, "GET", "/admin/sessions")
                assert unauth[0] == 401, unauth

                token = await pair(port, adapter, conversation=conversation)
                sessions_result = await http(port, "GET", "/admin/sessions", token=token)
                history_result = await http(port, "GET", "/history?limit=10", token=token)
                search_result = await http(port, "GET", "/search?q=seeded", token=token)

                assert sessions_result[0] == 200, sessions_result
                assert sessions_result[1]["active_session_id"] == conversation.session_id
                assert any(
                    row["session_id"] == conversation.session_id
                    for row in sessions_result[1]["sessions"]
                )
                assert history_result[0] == 200, history_result
                history_text = " ".join(
                    str(item.get("text") or item.get("content") or "")
                    for item in history_result[1]["messages"]
                )
                assert "seeded question" in history_text
                assert "seeded answer" in history_text
                assert search_result[0] == 200, search_result
                assert search_result[1]["results"], search_result

                revoked = await http(port, "POST", "/revoke", token=token, body={})
                assert revoked[0] == 200, revoked
                expired_auth = await http(port, "GET", "/history?limit=10", token=token)
                assert expired_auth[0] == 401, expired_auth
                repaired_token = await pair(port, adapter, conversation=conversation)
                repaired = await http(port, "GET", "/admin/sessions", token=repaired_token)
                assert repaired[0] == 200, repaired
                return adapter, runner
            finally:
                # Exercise the production GatewayRunner teardown as well.  Calling only
                # adapter.disconnect() leaves runner-owned liveness guards/background
                # resources alive and can keep the pytest process from exiting.
                await runner.stop()

    adapter, runner = run(scenario())
    assert adapter.gateway_runner is runner

