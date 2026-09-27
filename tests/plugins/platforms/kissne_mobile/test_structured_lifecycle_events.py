"""Structured lifecycle events on the mobile transport (tool_call / tool_result).

Contract frozen here:

* The plugin declares ``structured_lifecycle_events_enabled()``, so the gateway hands it the
  ID-bearing tool_start/tool_complete callbacks instead of the name-correlated text progress rail.
* Each event becomes ONE typed outbound event: ``presentation: tool_call`` for starts,
  ``tool_result`` for completions, both carrying the *real* tool-call id and a semantic
  ``activity`` record the App renders as an inline tool row.
* Structured tool events never touch the draft text lane: they must not clear live draft state
  (that lane belongs to the assistant reply being streamed) and must not arrive as assistant text.
"""

from _transport_harness import (
    build_session_store,
    http,
    isolated_runtime,
    make_adapter,
    pair,
    preexisting_conversation,
    run,
    start,
    stop,
)

INSTALLATION = "inst-1"


async def _open_turn(port, token, *, text="ping", message_id="m-turn-1") -> dict:
    status, payload, _ = await http(port, "POST", "/messages", token=token,
                                    body={"text": text, "message_id": message_id})
    assert status == 202, f"opening a turn must succeed, got {status}: {payload}"
    return payload


async def _drain(port, token, cursor=0):
    status, payload, _ = await http(port, "GET", f"/messages?cursor={cursor}", token=token)
    assert status == 200, f"GET /messages must answer 200, got {status}: {payload}"
    return payload


def test_adapter_declares_the_structured_lifecycle_capability(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            assert adapter.structured_lifecycle_events_enabled() is True
            assert callable(adapter.send_structured_tool_event)

    run(scenario())


def test_tool_start_and_completion_arrive_as_correlated_typed_events(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                await _open_turn(port, token)

                await adapter.send_structured_tool_event(
                    INSTALLATION,
                    {"type": "tool.started", "tool_call_id": "call-1", "tool_name": "read_file",
                     "args": {"path": "/repo/gateway/run_turn.py"}},
                )
                await adapter.send_structured_tool_event(
                    INSTALLATION,
                    {"type": "tool.completed", "tool_call_id": "call-1", "tool_name": "read_file",
                     "is_error": False},
                )

                payload = await _drain(port, token, 0)
                tools = [
                    event for event in payload["events"]
                    if event.get("presentation") in {"tool_call", "tool_result"}
                ]
                assert len(tools) == 2, f"expected one start + one result, got {tools}"

                started, finished = tools
                assert started["presentation"] == "tool_call"
                assert started["tool_call_id"] == "call-1"
                assert started["activity"]["kind"] == "tool_call"
                assert started["activity"]["tool_call_id"] == "call-1"
                assert started["activity"]["tool_name"] == "read_file"
                assert started["activity"]["status"] == "running"
                # A semantic label is carried on the row (never raw developer chrome) and the
                # completion reuses the label its start showed.
                assert started["activity"]["label"]
                assert "run_turn.py" in started["activity"]["arguments"]

                assert finished["presentation"] == "tool_result"
                assert finished["tool_call_id"] == "call-1"
                assert finished["activity"]["kind"] == "tool_result"
                assert finished["activity"]["status"] == "completed"
                assert finished["activity"]["label"] == started["activity"]["label"]

                # Not assistant text, and not the draft lane.
                for event in tools:
                    assert event["type"] == "delta"
                    assert not event.get("text")
                    assert "draft_id" not in event
            finally:
                await stop(adapter)

    run(scenario())


def test_failed_tool_reports_failed_status(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                await _open_turn(port, token)
                await adapter.send_structured_tool_event(
                    INSTALLATION,
                    {"type": "tool.completed", "tool_call_id": "call-9", "tool_name": "terminal",
                     "args": {"command": "pytest -q"}, "is_error": True},
                )
                payload = await _drain(port, token, 0)
                results = [
                    event for event in payload["events"]
                    if event.get("presentation") == "tool_result"
                ]
                assert len(results) == 1
                assert results[0]["activity"]["status"] == "failed"
            finally:
                await stop(adapter)

    run(scenario())


def test_structured_events_do_not_clear_live_draft_state(tmp_path):
    """A tool row must not discard the in-flight draft of the reply being written."""

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                await _open_turn(port, token)
                await adapter.send_draft(INSTALLATION, 1, "working on it")
                await adapter.send_structured_tool_event(
                    INSTALLATION,
                    {"type": "tool.started", "tool_call_id": "call-2", "tool_name": "terminal",
                     "args": {"command": "ls"}},
                )
                assert adapter._draft_text_last, "structured events must not clear draft text state"
                # Only delta events were produced for the tool row (no completed/assistant_text).
                payload = await _drain(port, token, 0)
                deltas = [event for event in payload["events"] if event["type"] == "delta"]
                presentations = [event.get("presentation") for event in deltas]
                assert "tool_call" in presentations
                # The live draft lives on beside the tool row — it was not reset by the tool event.
                assert "assistant_text" in presentations
                assert "tool_result" not in presentations
            finally:
                await stop(adapter)

    run(scenario())


def test_unknown_event_types_are_ignored(tmp_path):
    """Defensive: a stray text progress entry on this lane must not become a tool row."""

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                await _open_turn(port, token)
                result = await adapter.send_structured_tool_event(
                    INSTALLATION, {"type": "progress.text", "text": "📖 读取 x.py"})
                assert result.success is True
                assert result.message_id is None
                payload = await _drain(port, token, 0)
                assert not [
                    event for event in payload["events"]
                    if event.get("presentation") in {"tool_call", "tool_result"}
                ]
            finally:
                await stop(adapter)

    run(scenario())
