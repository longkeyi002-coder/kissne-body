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
