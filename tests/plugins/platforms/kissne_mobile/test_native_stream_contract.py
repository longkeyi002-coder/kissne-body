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
        "inst-1", 7, marker + "
",
        metadata={"_mobile_turn_id": "kbm_turn_1"},
    )

    assert queued and queued[0][0] == "delta"
    assert queued[0][1] == "kbm_turn_1"
