"""Native GatewayStreamConsumer -> Kissne Mobile contract regressions."""

import pytest

from gateway.platforms.base import SendResult
from gateway.stream_consumer import GatewayStreamConsumer
from plugins.platforms.kissne_mobile.adapter import KissneMobileAdapter


@pytest.mark.asyncio
async def test_seed_call_time_error_is_contained_and_send_result_is_normalized():
    class Broken:
        def send_stream_frame(self, *args, **kwargs):
            raise TypeError("old native-stream signature")

    consumer = object.__new__(GatewayStreamConsumer)
    consumer.adapter = Broken()
    consumer.chat_id = "mobile-1"
    consumer._initial_reply_to_id = "kbm_turn_1"
    consumer._turn_id = "gateway-turn-1"

    assert await consumer._try_seed_frame("seed failed") is False

    async def failed():
        return SendResult(success=False, error="rejected")

    assert await consumer._try_frame(failed(), "frame failed") is False


@pytest.mark.asyncio
async def test_mobile_native_frame_maps_delta_and_finalize_to_one_turn():
    adapter = object.__new__(KissneMobileAdapter)
    queued = []
    adapter._stream_draft_ids = {}
    adapter._draft_text_last = {}
    adapter._draft_activity_seen = {}
    adapter._draft_tool_labels = {}

    async def queue_event(installation, event_type, *, content=None, reply_to=None,
                          extra=None, target_turn_id=None):
        queued.append({
            "installation": installation, "type": event_type, "content": content,
            "reply_to": reply_to, "extra": extra or {}, "target_turn_id": target_turn_id,
        })
        return "out-1"

    adapter._queue_event = queue_event
    adapter._clear_draft_state = lambda installation: None

    delta = await adapter.send_stream_frame(
        "inst-1", "hello", turn_id="gateway-turn-1", reply_to="kbm_turn_1")
    final = await adapter.send_stream_frame(
        "inst-1", "hello", turn_id="gateway-turn-1", reply_to="kbm_turn_1", finalize=True)

    assert delta.success and final.success
    assert [row["type"] for row in queued] == ["delta", "completed"]
    assert queued[0]["target_turn_id"] == "kbm_turn_1"
    assert queued[1]["target_turn_id"] == "kbm_turn_1"
    assert queued[1]["content"] == "hello"
    assert queued[1]["extra"]["presentation"] == "assistant_text"
    assert adapter._stream_draft_ids == {}


@pytest.mark.asyncio
async def test_mobile_native_tool_activity_uses_the_same_turn():
    adapter = object.__new__(KissneMobileAdapter)
    adapter._stream_draft_ids = {}
    adapter._draft_text_last = {}
    adapter._draft_activity_seen = {}
    adapter._draft_tool_labels = {}

    queued = []

    async def queue_event(installation, event_type, *, content=None, reply_to=None,
                          extra=None, target_turn_id=None):
        queued.append((event_type, target_turn_id, extra or {}))
        return "out-1"

    adapter._queue_event = queue_event
    marker = KissneMobileAdapter._encode_activity_marker({
        "kind": "tool_call", "tool_call_id": "draft-tool:0",
        "tool_name": "read", "label": "读取文件", "index": 0,
    })
    await adapter.send_draft(
        "inst-1", 7, marker + "\n",
        metadata={"_mobile_turn_id": "kbm_turn_1"},
    )

    assert queued and queued[0][0] == "delta"
    assert queued[0][1] == "kbm_turn_1"


@pytest.mark.asyncio
async def test_gateway_native_tool_progress_is_typed_and_removed_from_assistant_text():
    adapter = object.__new__(KissneMobileAdapter)
    adapter._stream_draft_ids = {}
    adapter._draft_text_last = {}
    adapter._draft_activity_seen = {}
    adapter._draft_tool_labels = {}
    queued = []

    async def queue_event(installation, event_type, *, content=None, reply_to=None,
                          extra=None, target_turn_id=None):
        queued.append({
            "installation": installation, "type": event_type, "content": content,
            "extra": extra or {}, "target_turn_id": target_turn_id,
        })
        return "out-1"

    adapter._queue_event = queue_event
    adapter._clear_draft_state = lambda installation: None
    result = await adapter.send_stream_frame(
        "answer\n\n---\n正在检查文件",
        chat_id="inst-1", turn_id="gateway-turn-1", reply_to="kbm_turn_1",
        metadata={"_stream_tool_progress": ["正在检查文件"]},
    )

    assert result.success is True
    assert [row["extra"].get("presentation") for row in queued] == [
        "tool_progress", "assistant_text",
    ]
    assert queued[0]["target_turn_id"] == "kbm_turn_1"
    assert queued[0]["extra"]["activity"]["detail"] == "正在检查文件"
    assert queued[1]["content"] == "answer"


@pytest.mark.asyncio
async def test_gateway_native_frame_carries_progress_metadata_only_for_opt_in_adapter():
    class Capture:
        SUPPORTS_STRUCTURED_TOOL_PROGRESS = True

        async def send_stream_frame(self, content, **kwargs):
            self.content = content
            self.kwargs = kwargs
            return SendResult(success=True)

    consumer = object.__new__(GatewayStreamConsumer)
    consumer.adapter = Capture()
    consumer.chat_id = "mobile-1"
    consumer._initial_reply_to_id = "kbm_turn_1"
    consumer._turn_id = "gateway-turn-1"
    consumer.metadata = {"source": "test"}
    consumer._tool_progress_lines = ["正在检查文件"]

    result = await consumer._send_frame("answer\n\n---\n正在检查文件", finalize=False)

    assert result.success is True
    assert consumer.adapter.kwargs["metadata"] == {
        "source": "test", "_stream_tool_progress": ["正在检查文件"],
    }



def test_gateway_real_tool_events_are_semantic_not_private_markers(tmp_path):
    """Exercise formatter -> consumer progress -> native frame -> device event end to end."""
    async def scenario():
        from gateway.stream_consumer import GatewayStreamConsumer
        from gateway.stream_events import ToolCallChunk, ToolCallFinished

        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="inspect", message_id="m-real-tool")
                consumer = GatewayStreamConsumer(
                    adapter=adapter, chat_id=INSTALLATION,
                    initial_reply_to_id=turn["turn_id"],
                )
                started = adapter.format_tool_event(
                    ToolCallChunk("read_file", args={"path": "gateway/session.py"}, index=7)
                )
                finished = adapter.format_tool_event(
                    ToolCallFinished("read_file", duration=0.25, ok=True, index=7)
                )
                consumer._tool_progress_lines = [started, finished]
                await consumer._send_frame(
                    consumer._compose_frame_content(), finalize=False
                )
                payload = await _drain(port, token, 0)
                return turn, payload, started, finished
            finally:
                await stop(adapter)

    turn, payload, started, finished = run(scenario())
    events = payload.get("events") or []
    activities = [
        event for event in events
        if event.get("presentation") in {"tool_call", "tool_result"}
    ]
    assert [event["presentation"] for event in activities[-2:]] == ["tool_call", "tool_result"]
    assert all(event.get("turn_id") == turn["turn_id"] for event in activities[-2:])
    assert activities[-2]["activity"]["status"] == "running"
    assert activities[-1]["activity"]["status"] == "completed"
    assert activities[-1]["activity"]["label"] == activities[-2]["activity"]["label"]
    serialized = str(activities[-2:]) 
    assert started not in serialized and finished not in serialized
    assert "KISSNE_ACTIVITY" not in serialized
