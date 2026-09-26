"""Regression coverage for Android read surfaces."""
from pathlib import Path

from _transport_harness import (
    build_session_store, http, isolated_runtime, make_adapter, pair,
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



def test_session_index_lists_cross_source_top_level_rows_with_counts(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            mobile = preexisting_conversation(sessions, chat_id="mobile", user_id="mobile-user")
            foreign = preexisting_conversation(sessions, chat_id="foreign", user_id="foreign-user")
            db = sessions._db_for_session_id(foreign.session_id)
            db._write_sql("UPDATE sessions SET source = ? WHERE id = ?", ("weixin", foreign.session_id))
            seed_transcript(sessions, mobile.session_id, 1)
            seed_transcript(sessions, foreign.session_id, 3)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=mobile)
                return foreign.session_id, await http(port, "GET", "/admin/sessions", token=token)
            finally:
                await stop(adapter)

    foreign_id, result = run(scenario())
    assert result[0] == 200, result
    row = next(item for item in result[1]["sessions"] if item["session_id"] == foreign_id)
    assert row["source"] == "weixin"
    assert row["message_count"] == 6


def test_session_index_keeps_active_archived_but_hides_other_archived(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            active = preexisting_conversation(sessions, chat_id="active-archived", user_id="active-user")
            other = preexisting_conversation(sessions, chat_id="other-archived", user_id="other-user")
            seed_transcript(sessions, active.session_id, 1)
            seed_transcript(sessions, other.session_id, 1)
            db = sessions._db_for_session_id(active.session_id)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=active)
                db.set_session_archived(active.session_id, True)
                db.set_session_archived(other.session_id, True)
                return active.session_id, other.session_id, await http(port, "GET", "/admin/sessions", token=token)
            finally:
                await stop(adapter)

    active_id, other_id, result = run(scenario())
    ids = {row["session_id"] for row in result[1]["sessions"]}
    assert active_id in ids
    assert other_id not in ids



def test_history_without_session_id_reads_only_current_bound_conversation(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            active = preexisting_conversation(
                sessions, chat_id="default-history-active", user_id="active-user"
            )
            other = preexisting_conversation(
                sessions, chat_id="default-history-other", user_id="other-user"
            )
            seed_transcript(sessions, active.session_id, 3)
            seed_transcript(sessions, other.session_id, 3)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=active)
                return active.session_id, other.session_id, await http(
                    port, "GET", "/history?limit=50", token=token
                )
            finally:
                await stop(adapter)

    active_id, other_id, result = run(scenario())
    assert result[0] == 200, result
    refs = [str(row["message_ref"]) for row in result[1]["messages"]]
    assert refs
    assert all(ref.startswith(active_id + ":") for ref in refs)
    assert not any(ref.startswith(other_id + ":") for ref in refs)


def test_web_session_history_contract_is_lazy_and_keeps_active_metadata():
    root = Path(__file__).resolve().parents[4]
    source = (root / "kissne-prototype/prototype/screens-a.js").read_text(encoding="utf-8")
    assert "T.history(50, '', sessionId)" in source
    assert "T.history(50, requestedBefore, CURRENT_SESSION_ID)" in source
    assert "还有更早的记录 · 上滑加载" in source
    assert "list.scrollTop <= 24 && sessionHistoryHasMore" in source
    assert "if (active) return '当前会话';" not in source
    assert "if (active) parts.push('当前会话');" in source


def test_session_index_matches_9120_pinned_and_active_timestamp_contract():
    root = Path(__file__).resolve().parents[4]
    source = (
        root / "plugins/platforms/kissne_mobile/adapter.py"
    ).read_text(encoding="utf-8")
    assert "include_pinned=True" in source
    assert 'active_row["last_active"] = max(numeric_stamps)' in source

def test_history_session_id_pages_only_target_session_to_oldest_message(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            active = preexisting_conversation(sessions, chat_id="active-history", user_id="active-user")
            target = preexisting_conversation(sessions, chat_id="target-history", user_id="target-user")
            seed_transcript(sessions, active.session_id, 2)
            seed_transcript(sessions, target.session_id, 61)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=active)
                before = ""
                seen = []
                while True:
                    suffix = f"&before={before}" if before else ""
                    result = await http(
                        port, "GET",
                        f"/history?session_id={target.session_id}&limit=50{suffix}",
                        token=token,
                    )
                    assert result[0] == 200, result
                    seen = result[1]["messages"] + seen
                    if not result[1]["has_more"]:
                        return target.session_id, seen
                    before = result[1]["next_before"]
            finally:
                await stop(adapter)

    target_id, seen = run(scenario())
    assert len(seen) == 122
    assert seen[0]["text"] == "seeded question 0"
    assert seen[-1]["text"] == "seeded answer 60"
    assert all(str(row["message_ref"]).startswith(target_id + ":") for row in seen)



def test_select_ended_session_is_alias_only_and_history_remains_readable(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            mobile = preexisting_conversation(sessions, chat_id="ended-mobile", user_id="mobile-user")
            ended = preexisting_conversation(sessions, chat_id="ended-target", user_id="weixin-user")
            db = sessions._db_for_session_id(ended.session_id)
            db._write_sql("UPDATE sessions SET source = ? WHERE id = ?", ("weixin", ended.session_id))
            seed_transcript(sessions, ended.session_id, 3)
            sessions._promote_session_reset(ended.session_key, ended.session_id, "session_reset")
            before = dict(db.get_session(ended.session_id))
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=mobile)
                selected = await http(
                    port, "POST", "/admin/sessions", token=token,
                    body={"session_id": ended.session_id},
                )
                history = await http(port, "GET", "/history?limit=50", token=token)
                rejected_send = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "must-not-reopen-ended", "text": "do not append"},
                )
                after = dict(db.get_session(ended.session_id))
                return ended.session_id, before, selected, history, rejected_send, after
            finally:
                await stop(adapter)

    ended_id, before, selected, history, rejected_send, after = run(scenario())
    assert selected[0] == 200, selected
    assert selected[1]["conversation"]["session_id"] == ended_id
    assert after == before
    assert after["end_reason"] == "session_reset"
    assert history[0] == 200, history
    assert rejected_send[0] == 409, rejected_send
    assert rejected_send[1]["error"] == "session_read_only"
    assert len(history[1]["messages"]) == 6
    assert all(str(row["message_ref"]).startswith(ended_id + ":") for row in history[1]["messages"])


def test_reselect_current_ended_session_is_noop(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            current = preexisting_conversation(sessions, chat_id="ended-current", user_id="mobile-user")
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=current)
                db = sessions._db_for_session_id(current.session_id)
                sessions._promote_session_reset(current.session_key, current.session_id, "session_reset")
                before = dict(db.get_session(current.session_id))
                selected = await http(
                    port, "POST", "/admin/sessions", token=token,
                    body={"session_id": current.session_id},
                )
                after = dict(db.get_session(current.session_id))
                return current.session_id, before, selected, after
            finally:
                await stop(adapter)

    current_id, before, selected, after = run(scenario())
    assert selected[0] == 200, selected
    assert selected[1]["conversation"]["session_id"] == current_id
    assert after == before

def test_cross_lane_select_changes_only_mobile_alias(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            mobile = preexisting_conversation(sessions, chat_id="mobile-origin", user_id="mobile-user")
            foreign = preexisting_conversation(sessions, chat_id="weixin-origin", user_id="weixin-user")
            foreign_key = foreign.session_key
            db = sessions._db_for_session_id(foreign.session_id)
            db._write_sql("UPDATE sessions SET source = ? WHERE id = ?", ("weixin", foreign.session_id))
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=mobile)
                before = sessions.lookup_by_session_key(foreign_key)
                mobile_before = dict(db.get_session(mobile.session_id))
                foreign_before = dict(db.get_session(foreign.session_id))
                selected = await http(
                    port, "POST", "/admin/sessions", token=token,
                    body={"session_id": foreign.session_id},
                )
                after = sessions.lookup_by_session_key(foreign_key)
                durable_after = dict(db.get_session(foreign.session_id))
                mobile_after = dict(db.get_session(mobile.session_id))
                return (
                    foreign, before, selected, after, adapter.bound_conversation("inst-1"),
                    foreign_before, durable_after, mobile_before, mobile_after,
                )
            finally:
                await stop(adapter)

    (
        foreign, before, selected, after, mobile_bound,
        foreign_before, durable_after, mobile_before, mobile_after,
    ) = run(scenario())
    assert selected[0] == 200, selected
    assert before.session_id == foreign.session_id
    assert after.session_id == foreign.session_id
    assert after.session_key == before.session_key
    assert mobile_bound.session_id == foreign.session_id
    assert durable_after == foreign_before
    assert durable_after["source"] == "weixin"
    assert mobile_after == mobile_before


def test_history_rejects_unknown_target_session(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            active = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=active)
                return await http(port, "GET", "/history?session_id=does-not-exist&limit=50", token=token)
            finally:
                await stop(adapter)

    result = run(scenario())
    assert result[0] == 404
    assert result[1]["error"] == "session_not_found"


def test_history_cursor_cannot_cross_selected_session(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            active = preexisting_conversation(sessions, chat_id="cursor-active", user_id="active")
            target = preexisting_conversation(sessions, chat_id="cursor-target", user_id="target")
            seed_transcript(sessions, active.session_id, 2)
            seed_transcript(sessions, target.session_id, 2)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=active)
                active_page = await http(
                    port, "GET", f"/history?session_id={active.session_id}&limit=1", token=token,
                )
                foreign_cursor = active_page[1]["messages"][0]["message_ref"]
                return await http(
                    port, "GET",
                    f"/history?session_id={target.session_id}&limit=1&before={foreign_cursor}",
                    token=token,
                )
            finally:
                await stop(adapter)

    result = run(scenario())
    assert result[0] == 400
    assert result[1]["error"] == "history_cursor_not_found"
