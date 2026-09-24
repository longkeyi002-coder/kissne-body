"""Regression coverage for Android read surfaces."""
from _transport_harness import (
    build_session_store, http, isolated_runtime, make_adapter, pair,
    preexisting_conversation, run, start, stop,
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
            inactive = sessions.resolve_or_create("telegram:delete-me", display_name="delete me")
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=active)
                deleted = await http(port, "DELETE", "/admin/sessions", token=token, json={"session_id": inactive.session_id})
                listed = await http(port, "GET", "/admin/sessions", token=token)
                protected = await http(port, "DELETE", "/admin/sessions", token=token, json={"session_id": active.session_id})
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
            second = sessions.resolve_or_create("telegram:select-me", display_name="select me")
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=first)
                selected = await http(
                    port, "POST", "/admin/sessions", token=token,
                    json={"session_id": second.session_id},
                )
                bootstrap = await http(port, "POST", "/bootstrap", token=token, json={"cursor": 0})
                unauth = await http(
                    port, "POST", "/admin/sessions",
                    json={"session_id": first.session_id},
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
                    json={"installation_id": "untrusted-installation"},
                )
            finally:
                await stop(adapter)

    result = run(scenario())
    assert result[0] == 400, result
    assert result[1]["error"] == "pairing_code_and_installation_id_required"
