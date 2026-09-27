"""Native-stream contract: gateway/stream_consumer_transport.py calls send_stream_frame with the
frame TEXT positionally and routing keyword-only. A parameter-order mismatch raises
``TypeError: got multiple values for argument 'chat_id'`` and aborts the whole turn, so the call
shape is pinned here with the gateway's exact arguments."""

from _transport_harness import isolated_runtime, make_adapter, run


def test_stream_frame_accepts_the_gateway_call_shape(tmp_path):
    delivered = []

    async def fake_send_draft(chat_id, draft_id, content, metadata=None):
        delivered.append((chat_id, draft_id, content))
        return "sent"

    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            adapter.send_draft = fake_send_draft
            # seed frame, content frame, finalize frame — literally the gateway's calls
            await adapter.send_stream_frame(
                "", chat_id="phone-a", reply_to="m-1", turn_id="turn-1")
            await adapter.send_stream_frame(
                "hello", chat_id="phone-a", reply_to="m-1", turn_id="turn-1")
            await adapter.send_stream_frame(
                "", finalize=True, chat_id="phone-a", reply_to=None, turn_id="turn-1")

    run(scenario())
    assert [item[0] for item in delivered] == ["phone-a"] * 3
    assert [item[2] for item in delivered] == ["", "hello", ""]
    assert len({item[1] for item in delivered}) == 1, "every frame of one turn updates one draft"


def test_stream_frame_fails_closed_without_a_target(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            return await adapter.send_stream_frame("hi", chat_id=None, turn_id="turn-1")

    result = run(scenario())
    assert result.success is False
