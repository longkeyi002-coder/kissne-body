"""L3 contract tests for the Gateway native stream and Kissne Mobile adapter.

These tests exercise the real GatewayStreamConsumer and the real KissneMobileAdapter
at their transport boundary. They do not call a model and do not replace the mobile
adapter with a mock, so a green result is stronger than an adapter-self-consistency test.
"""

from __future__ import annotations

import asyncio

import pytest

from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.stream_consumer import GatewayStreamConsumer, StreamConsumerConfig
from plugins.platforms.kissne_mobile.device_store import EVENT_COMPLETED, EVENT_DELTA
from tests.plugins.platforms.kissne_mobile._transport_harness import (
    isolated_runtime,
    make_adapter,
)


class _LegacyNativeAdapter(BasePlatformAdapter):
    """Old shape: calling it with Gateway's keyword contract raises at invocation time."""

    SUPPORTS_NATIVE_STREAMING = True
    __abstractmethods__ = frozenset()

    async def send_stream_frame(
        self, content: str, *, stream_id: str = "", final: bool = False, metadata=None
    ):
        return SendResult(success=True)

    def supports_native_streaming(self, chat_type=None, metadata=None):
        return True

    def supports_draft_streaming(self, chat_type=None, metadata=None, chat_id=None):
        return False

    def message_len_fn_for_chat(self, chat_id):
        return len

    def max_message_length_for_chat(self, chat_id):
        return 4096


@pytest.mark.asyncio
async def test_seed_call_time_typeerror_is_contained_before_run_loop(tmp_path):
    """A legacy adapter cannot kill the consumer task during seed negotiation."""
    adapter = _LegacyNativeAdapter.__new__(_LegacyNativeAdapter)
    consumer = GatewayStreamConsumer(
        adapter,
        "inst-1",
        StreamConsumerConfig(transport="edit", cursor=""),
    )
    task = asyncio.create_task(consumer.run())
    await asyncio.sleep(0)
    consumer.finish()
    await asyncio.wait_for(task, timeout=2)
    assert consumer._use_native_streaming is False


@pytest.mark.asyncio
async def test_real_mobile_gateway_frame_contract_and_server_turn_binding(tmp_path):
    """Gateway-shaped frames reach the real Mobile adapter with correct turn identity."""
    with isolated_runtime(tmp_path):
        adapter = make_adapter()
        events = []

        async def capture_event(installation_id, event_type, **kwargs):
            events.append((installation_id, event_type, kwargs))
            return f"event-{len(events)}"

        adapter._queue_event = capture_event
        seed = await adapter.send_stream_frame(
            "", chat_id="inst-1", reply_to="kbm_turn_server", turn_id="gateway-stream")
        delta = await adapter.send_stream_frame(
            "hello", chat_id="inst-1", reply_to="kbm_turn_server", turn_id="gateway-stream")
        final = await adapter.send_stream_frame(
            "hello", chat_id="inst-1", reply_to="kbm_turn_server",
            turn_id="gateway-stream", finalize=True)

    assert seed.success and delta.success and final.success
    assert [item[1] for item in events] == [EVENT_DELTA, EVENT_COMPLETED]
    assert all(item[2].get("target_turn_id") == "kbm_turn_server" for item in events)
    assert events[-1][2]["extra"]["presentation"] == "assistant_text"


@pytest.mark.asyncio
async def test_real_mobile_consumer_to_adapter_l3_seed_delta_and_finalize(tmp_path):
    """The actual consumer and adapter exchange seed, delta and finalize without fallback."""
    with isolated_runtime(tmp_path):
        adapter = make_adapter()
        events = []

        async def capture_event(installation_id, event_type, **kwargs):
            events.append((installation_id, event_type, kwargs))
            return f"event-{len(events)}"

        adapter._queue_event = capture_event
        consumer = GatewayStreamConsumer(
            adapter,
            "inst-1",
            StreamConsumerConfig(transport="edit", edit_interval=0.001, buffer_threshold=1, cursor=""),
            initial_reply_to_id="kbm_turn_server",
        )
        task = asyncio.create_task(consumer.run())
        await asyncio.sleep(0.02)
        consumer.on_delta("hello")
        await asyncio.sleep(0.08)
        consumer.finish("hello")
        await asyncio.wait_for(task, timeout=3)

    event_types = [item[1] for item in events]
    assert EVENT_DELTA in event_types
    assert EVENT_COMPLETED in event_types
    assert all(item[2].get("target_turn_id") == "kbm_turn_server" for item in events)
    assert consumer._use_native_streaming is True
