"""KB1-MOBILE-CHAT-TRANSPORT / RED — reliable outbound delivery (§0.3.16 ③ ⑤).

Contract frozen here:

* Outbound is a durable, sequence-numbered stream per installation. ``GET /messages?cursor=N`` returns
  every event with ``seq > N`` and is **non-destructive**: nothing is consumed by reading, so a
  ``GET`` whose response never reaches the device (disconnect, crash, timeout) loses nothing.
* Consumption is explicit: ``POST /messages {"ack": {"cursor": M}}`` retires events up to ``M`` and
  returns how many were retired. Unacked events redeliver; acked events never come back — including
  across a Runtime restart, which is why the queue is a row set, not process memory.
* Stream semantics are protocol level: ``delta`` events are *incremental* (`send_draft`), ``completed``
  is the final text (`send`), and every event carries the ``turn_id`` it belongs to. A client must
  never have to guess completion from a plain text payload.

RED reason: today ``GET /messages`` drains the deque (``popleft``), ``disconnect()`` clears it, no
cursor/ack exists, and no event type or turn correlation is emitted. Nothing is skipped.
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


async def _drain(port, token, cursor=None):
    cursor = 0 if cursor is None else cursor
    status, payload, _ = await http(port, "GET", f"/messages?cursor={cursor}", token=token)
    assert status == 200, f"GET /messages must answer 200, got {status}: {payload}"
    return payload


def test_queued_replies_are_typed_events_with_turn_correlation(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token)
                await adapter.send(INSTALLATION, "the final answer")
                payload = await _drain(port, token, 0)
            finally:
                await stop(adapter)
        return turn, payload

    turn, payload = run(scenario())
    events = payload.get("events")
    assert isinstance(events, list) and events, f"GET /messages must return events: {payload}"
    for event in events:
        assert isinstance(event.get("seq"), int), f"every event needs a sequence number: {event!r}"
        assert event.get("type") in {"pending", "delta", "completed", "cancelled", "notice"}, (
            f"events must be protocol-typed, not raw text: {event!r}")
    completed = [event for event in events if event.get("type") == "completed"]
    assert completed, f"the final reply must be a 'completed' event: {events}"
    assert completed[-1].get("text") == "the final answer", (
        f"the completed event must carry the final text: {completed[-1]!r}")
    assert completed[-1].get("turn_id") == turn.get("turn_id"), (
        "the completed event must be correlated with the turn that produced it: "
        f"{completed[-1].get('turn_id')} vs {turn.get('turn_id')}")
    seqs = [event["seq"] for event in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), (
        f"event sequence numbers must be strictly increasing: {seqs}")


def test_incremental_deltas_are_distinguishable_from_the_final_reply(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token)
                supports = bool(adapter.supports_draft_streaming(chat_id=INSTALLATION))
                await adapter.send_draft(INSTALLATION, 1, "answer so")
                await adapter.send_draft(INSTALLATION, 1, "answer so far")
                await adapter.send(INSTALLATION, "answer so far and done")
                payload = await _drain(port, token, 0)
            finally:
                await stop(adapter)
        return supports, turn, payload

    supports, turn, payload = run(scenario())
    assert supports is True, (
        "the adapter must declare draft streaming so the Runtime hands it incremental text")
    events = payload.get("events") or []
    deltas = [event for event in events if event.get("type") == "delta"]
    completed = [event for event in events if event.get("type") == "completed"]
    assert deltas, (
        "incremental text must arrive as 'delta' events (a client cannot infer streaming from plain "
        f"text): {events}")
    assert [event.get("text") for event in deltas] == ["answer so", "answer so far"], (
        f"deltas must carry the incremental text in order: {deltas}")
    assert len(completed) == 1 and completed[0].get("text") == "answer so far and done", (
        f"exactly one final 'completed' event must close the turn: {completed}")
    assert all(event.get("turn_id") == turn.get("turn_id") for event in events), (
        f"every event of the turn must carry its turn_id: {events}")


def test_reading_is_non_destructive_until_the_client_acks(tmp_path):
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
                await adapter.send(INSTALLATION, "first reply")
                await adapter.send(INSTALLATION, "second reply")
                read_once = await _drain(port, token, 0)
                read_twice = await _drain(port, token, 0)
            finally:
                await stop(adapter)
        return read_once, read_twice

    read_once, read_twice = run(scenario())
    assert read_once.get("events") == read_twice.get("events"), (
        "a second read at the same cursor returned a different stream: reading consumed events "
        f"({read_once.get('events')} vs {read_twice.get('events')})")
    assert read_once.get("next_cursor"), f"a read must advance a cursor: {read_once}"
    assert len(read_once["events"]) >= 2, (
        f"both queued replies must be readable: {read_once.get('events')}")


def test_ack_retires_events_and_stops_redelivery(tmp_path):
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
                await adapter.send(INSTALLATION, "ack me")
                first = await _drain(port, token, 0)
                cursor = first.get("next_cursor")
                ack_status, ack_payload, _ = await http(port, "POST", "/messages", token=token,
                                                        body={"ack": {"cursor": cursor}})
                after = await _drain(port, token, cursor)
            finally:
                await stop(adapter)
        return first, ack_status, ack_payload, after

    first, ack_status, ack_payload, after = run(scenario())
    assert ack_status == 200, f"an ack must be accepted, got {ack_status}: {ack_payload}"
    assert ack_payload.get("acked", 0) >= 1, (
        f"the ack must report how many events it retired: {ack_payload}")
    assert not after.get("events"), (
        f"acked events were redelivered: {after.get('events')}")
    assert len(first["events"]) >= 1, "the acked events were never delivered in the first place"


def test_unacked_replies_survive_a_runtime_restart_and_acked_ones_do_not(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter = make_adapter()
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                await _open_turn(port, token)
                await adapter.send(INSTALLATION, "unacked reply")
                delivered = await _drain(port, token, 0)
                cursor = delivered.get("next_cursor")
                await http(port, "POST", "/messages", token=token, body={"ack": {"cursor": cursor}})
                await adapter.send(INSTALLATION, "fresh reply")
            finally:
                await stop(adapter)

            restarted = make_adapter()
            restarted.set_session_store(build_session_store(home))
            port = await start(restarted)
            try:
                after = await _drain(port, token, cursor)
            finally:
                await stop(restarted)
        return delivered, cursor, after

    delivered, cursor, after = run(scenario())
    texts = [event.get("text") for event in after.get("events") or []]
    assert "fresh reply" in texts, (
        "replies queued before the restart must still be delivered afterwards (durable outbound): "
        f"{after}")
    assert "unacked reply" not in texts, (
        "an acked reply came back after the restart — the ack cursor is not durable: "
        f"{after.get('events')}")


def test_interim_commentary_does_not_close_the_turn(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="inspect this", message_id="m-commentary")
                await adapter.send(
                    INSTALLATION, "I will inspect the files.", metadata={"_interim_send": True})
                before_final = await _drain(port, token, 0)
                pending_before_final = adapter.device_store().pending_turn_id(INSTALLATION)
                await adapter.send(INSTALLATION, "Done.")
                after_final = await _drain(port, token, 0)
            finally:
                await stop(adapter)
        return turn, before_final, pending_before_final, after_final

    turn, before_final, pending_before_final, after_final = run(scenario())
    events = before_final.get("events") or []
    commentary = [
        event for event in events
        if event.get("presentation") == "commentary"
        and event.get("text") == "I will inspect the files."
    ]
    assert commentary, f"interim commentary must be typed separately: {events}"
    assert not [event for event in events if event.get("type") == "completed"], (
        f"commentary must not close the turn: {events}")
    assert pending_before_final == turn["turn_id"], "commentary closed the pending turn"
    completed = [
        event for event in (after_final.get("events") or [])
        if event.get("type") == "completed"
    ]
    assert completed and completed[-1].get("text") == "Done."


def test_tool_progress_is_separate_from_visible_draft_text(tmp_path):
    async def scenario():
        from gateway.stream_events import ToolCallChunk

        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(
                    port, token, text="check stickers", message_id="m-tool-activity")
                marker = adapter.format_tool_event(ToolCallChunk(
                    tool_name="terminal",
                    args={"command": 'grep -n "sticker" plugins/platforms/kissne_mobile/adapter.py'},
                    preview="grep sticker adapter.py",
                    index=3,
                ))
                frame = "I will check the implementation.\n\n---\n" + str(marker)
                await adapter.send_draft(INSTALLATION, 77, frame)
                await adapter.send_draft(INSTALLATION, 77, frame)
                payload = await _drain(port, token, 0)
            finally:
                await stop(adapter)
        return turn, payload

    turn, payload = run(scenario())
    events = payload.get("events") or []
    activity = [
        event for event in events
        if event.get("presentation") in {"tool_progress", "tool_call"}
    ]
    visible = [
        event for event in events
        if event.get("type") == "delta" and event.get("presentation") == "assistant_text"
    ]
    assert len(activity) == 1, f"repeated cumulative frames duplicated Activity: {events}"
    assert activity[-1].get("activity", {}).get("label") == "查找表情包发送逻辑"
    assert activity[-1].get("turn_id") == turn["turn_id"]
    assert len(visible) == 1 and visible[-1].get("text") == "I will check the implementation."
    assert all("grep -n" not in str(event.get("text") or "") for event in visible), (
        f"raw terminal command leaked into assistant text: {visible}")


def test_reasoning_uses_a_separate_delta_lane(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="think visibly", message_id="m-reasoning")
                await adapter.send_reasoning(
                    INSTALLATION, "first reasoning step", turn_id=turn["turn_id"])
                await adapter.send(INSTALLATION, "final answer")
                payload = await _drain(port, token, 0)
            finally:
                await stop(adapter)
        return turn, payload

    turn, payload = run(scenario())
    events = payload.get("events") or []
    reasoning = [event for event in events if event.get("presentation") == "reasoning"]
    assert len(reasoning) == 1, events
    assert reasoning[0].get("type") == "delta"
    assert reasoning[0].get("text") == "first reasoning step"
    assert reasoning[0].get("turn_id") == turn["turn_id"]
    completed = [event for event in events if event.get("type") == "completed"]
    assert completed[-1].get("text") == "final answer"
    assert completed[-1].get("presentation") == "assistant_text"


def test_native_stream_bridge_preserves_typed_tool_activity(tmp_path):
    async def scenario():
        from gateway.stream_events import ToolCallChunk

        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="inspect transport", message_id="m-native-tool")
                assert adapter.supports_native_streaming() is True
                marker = adapter.format_tool_event(ToolCallChunk(
                    tool_name="terminal", args={"command": "printf transport"},
                    preview="inspect transport", index=1,
                ))
                await adapter.send_stream_frame(
                    INSTALLATION, "Checking transport.\n\n---\n" + str(marker),
                    stream_id="native-tool-stream",
                )
                payload = await _drain(port, token, 0)
            finally:
                await stop(adapter)
        return turn, payload

    turn, payload = run(scenario())
    events = payload.get("events") or []
    activity = [event for event in events if event.get("presentation") in {"tool_progress", "tool_call"}]
    visible = [event for event in events if event.get("type") == "delta" and event.get("presentation") == "assistant_text"]
    assert activity, f"native stream must expose typed tool activity: {events}"
    assert activity[-1].get("turn_id") == turn["turn_id"]
    assert visible and visible[-1].get("text") == "Checking transport."


def test_native_stream_accepts_gateway_consumer_turn_identity(tmp_path):
    """GatewayStreamConsumer passes turn_id/reply_to to every native frame.

    Mobile must accept that contract or native streaming degrades before tool Activity can
    reach the device in real time.
    """
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="stream live", message_id="m-native-contract")
                result = await adapter.send_stream_frame(
                    INSTALLATION,
                    "",
                    turn_id="gateway-consumer-turn",
                    reply_to="reply-anchor",
                    final=False,
                )
                payload = await _drain(port, token, 0)
                return turn, result, payload
            finally:
                await stop(adapter)

    turn, result, payload = run(scenario())
    assert result.success is True
    assert any(
        event.get("type") == "pending" and event.get("turn_id") == turn["turn_id"]
        for event in (payload.get("events") or [])
    )


def test_cancelled_turn_drops_explicit_late_reasoning_and_completion(tmp_path):
    """A cancelled turn is terminal: delayed Runtime callbacks cannot reappear on device."""
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="stop me", message_id="m-late-cancel")
                turn_id = turn["turn_id"]
                status, cancel_payload, _ = await http(
                    port, "POST", "/cancel", token=token, body={"turn_id": turn_id})
                assert status == 200, cancel_payload
                before = await _drain(port, token, 0)
                reasoning = await adapter.send_reasoning(
                    INSTALLATION, "late reasoning", turn_id=turn_id)
                completed_id = await adapter._queue_event(
                    INSTALLATION, "completed", content="late answer",
                    target_turn_id=turn_id)
                after = await _drain(port, token, 0)
                return turn_id, reasoning, completed_id, before, after
            finally:
                await stop(adapter)

    turn_id, reasoning, completed_id, before, after = run(scenario())
    assert reasoning.success is False
    assert completed_id is None
    assert any(
        event.get("type") == "cancelled" and event.get("turn_id") == turn_id
        for event in (before.get("events") or [])
    )
    leaked = [
        event for event in (after.get("events") or [])
        if event.get("turn_id") == turn_id
        and (event.get("text") in {"late reasoning", "late answer"})
    ]
    assert leaked == []


def test_cancelled_native_stream_cannot_attach_draft_to_new_turn(tmp_path):
    """A stale native stream keeps the original inbound turn id after a new turn opens."""
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                old_turn = await _open_turn(
                    port, token, text="old", message_id="m-old-native")
                status, payload, _ = await http(
                    port, "POST", "/cancel", token=token,
                    body={"turn_id": old_turn["turn_id"]})
                assert status == 200, payload
                new_turn = await _open_turn(
                    port, token, text="new", message_id="m-new-native")
                stale = await adapter.send_stream_frame(
                    INSTALLATION, "late old draft",
                    turn_id="consumer-stream-old",
                    reply_to=old_turn["turn_id"],
                    final=False,
                )
                events = (await _drain(port, token, 0)).get("events") or []
                return old_turn, new_turn, stale, events
            finally:
                await stop(adapter)

    old_turn, new_turn, stale, events = run(scenario())
    assert stale.success is False
    assert not any(
        event.get("text") == "late old draft"
        and event.get("turn_id") == new_turn["turn_id"]
        for event in events
    ), events
    assert not any(
        event.get("text") == "late old draft"
        and event.get("turn_id") == old_turn["turn_id"]
        for event in events
    ), events


def test_gateway_native_fallback_cannot_attach_old_turn_to_new_turn(tmp_path):
    """A rejected native frame must not fall back into the current pending turn."""
    async def scenario():
        from gateway.stream_consumer import GatewayStreamConsumer

        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                old_turn = await _open_turn(port, token, text="old", message_id="m-old-fallback")
                status, payload, _ = await http(
                    port, "POST", "/cancel", token=token,
                    body={"turn_id": old_turn["turn_id"]})
                assert status == 200, payload
                new_turn = await _open_turn(port, token, text="new", message_id="m-new-fallback")

                consumer = GatewayStreamConsumer(
                    adapter=adapter, chat_id=INSTALLATION,
                    initial_reply_to_id=old_turn["turn_id"],
                )
                consumer._use_native_streaming = True
                consumer._native_stream_opened = True
                delivered = await consumer._send_or_edit(
                    "late old fallback", finalize=False, is_turn_final=False)
                events = (await _drain(port, token, 0)).get("events") or []
                return delivered, new_turn, events
            finally:
                await stop(adapter)

    delivered, new_turn, events = run(scenario())
    assert delivered is False
    assert not any(
        event.get("text") == "late old fallback"
        and event.get("turn_id") == new_turn["turn_id"]
        for event in events
    ), events


def test_gateway_consumer_projects_native_tool_progress_as_typed_event(tmp_path):
    """The production consumer path must not persist tool progress as assistant prose."""
    async def scenario():
        from gateway.stream_consumer import GatewayStreamConsumer

        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="inspect", message_id="m-native-progress")
                consumer = GatewayStreamConsumer(
                    adapter=adapter, chat_id=INSTALLATION,
                    initial_reply_to_id=turn["turn_id"],
                )
                consumer._tool_progress_lines = ["正在检查文件"]
                await consumer._send_frame(
                    "answer\n\n---\n正在检查文件", finalize=False)
                payload = await _drain(port, token, 0)
                return turn, payload
            finally:
                await stop(adapter)

    turn, payload = run(scenario())
    events = payload.get("events") or []
    progress = [event for event in events if event.get("presentation") == "tool_progress"]
    visible = [event for event in events if event.get("presentation") == "assistant_text"]
    assert progress and progress[-1]["turn_id"] == turn["turn_id"]
    assert progress[-1]["activity"]["detail"] == "正在检查文件"
    assert visible and visible[-1]["text"] == "answer"



def test_queue_cap_never_discards_unacked_terminal_event(tmp_path):
    """Queue pressure must not violate the explicit-ACK durability contract."""
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter._outbound_cap = 3
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="slow client", message_id="m-cap")
                for index in range(8):
                    await adapter.send_draft(INSTALLATION, 91, "draft " + str(index))
                await adapter.send(INSTALLATION, "terminal answer")
                payload = await _drain(port, token, 0)
                return turn, payload
            finally:
                await stop(adapter)

    turn, payload = run(scenario())
    events = payload.get("events") or []
    assert len(events) >= 10, events
    assert events[0].get("type") == "pending", events
    assert any(
        event.get("type") == "completed"
        and event.get("turn_id") == turn["turn_id"]
        and event.get("text") == "terminal answer"
        for event in events
    ), events
    seqs = [event["seq"] for event in events]
    assert seqs == list(range(seqs[0], seqs[-1] + 1)), seqs


def test_ack_cannot_retire_events_beyond_last_delivered_cursor(tmp_path):
    """A corrupt/buggy client cursor must not acknowledge events it was never served."""
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter._read_limit = 2
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token, text="ack fence", message_id="m-ack-fence")
                for index in range(4):
                    await adapter.send_draft(INSTALLATION, 123, "draft " + str(index))
                first = await _drain(port, token, 0)
                assert len(first.get("events") or []) == 2, first
                delivered = first["next_cursor"]

                # Deliberately acknowledge far beyond what this installation was served.
                acked = await http(
                    port, "POST", "/ack", token=token,
                    body={"ack": {"cursor": delivered + 1000}},
                )
                remaining = await _drain(port, token, delivered)
                return turn, first, acked, remaining
            finally:
                await stop(adapter)

    _turn, first, acked, remaining = run(scenario())
    assert acked[0] == 200, acked
    assert acked[1]["cursor"] == first["next_cursor"], acked
    events = remaining.get("events") or []
    assert events, (first, acked, remaining)
    assert events[0]["seq"] == first["next_cursor"] + 1


def test_delivery_watermark_survives_runtime_restart(tmp_path):
    """A served-but-unacked cursor remains the ACK ceiling after the adapter restarts."""
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            store = build_session_store(home)
            existing = preexisting_conversation(store)

            first_adapter = make_adapter()
            first_adapter._read_limit = 2
            first_adapter.set_session_store(store)
            first_port = await start(first_adapter)
            token = await pair(first_port, first_adapter, conversation=existing)
            turn = await _open_turn(
                first_port, token, text="restart fence", message_id="m-restart-fence")
            for index in range(4):
                await first_adapter.send_draft(INSTALLATION, 222, "restart draft " + str(index))
            first = await _drain(first_port, token, 0)
            delivered = first["next_cursor"]
            assert len(first.get("events") or []) == 2, first
            await stop(first_adapter)

            # A fresh adapter/store is the real persistence boundary: no in-memory watermark survives.
            restarted_store = build_session_store(home)
            restarted = make_adapter()
            restarted._read_limit = 2
            restarted.set_session_store(restarted_store)
            second_port = await start(restarted)
            try:
                acked = await http(
                    second_port, "POST", "/ack", token=token,
                    body={"ack": {"cursor": delivered + 1000}},
                )
                remaining = await _drain(second_port, token, delivered)
                return turn, delivered, acked, remaining
            finally:
                await stop(restarted)

    _turn, delivered, acked, remaining = run(scenario())
    assert acked[0] == 200, acked
    assert acked[1]["cursor"] == delivered, acked
    events = remaining.get("events") or []
    assert events, remaining
    assert events[0]["seq"] == delivered + 1, remaining


def test_repeated_poll_and_ack_are_idempotent(tmp_path):
    """Retries must neither duplicate retirement nor skip events after the acknowledged cursor."""
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter._read_limit = 2
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                await _open_turn(port, token, text="retry poll", message_id="m-retry-poll")
                for index in range(4):
                    await adapter.send_draft(INSTALLATION, 333, "retry draft " + str(index))

                first = await _drain(port, token, 0)
                repeated = await _drain(port, token, 0)
                assert first["events"] == repeated["events"]
                cursor = first["next_cursor"]

                ack1 = await http(
                    port, "POST", "/ack", token=token,
                    body={"ack": {"cursor": cursor}},
                )
                ack2 = await http(
                    port, "POST", "/ack", token=token,
                    body={"ack": {"cursor": cursor}},
                )
                remaining = await _drain(port, token, cursor)
                return first, repeated, ack1, ack2, remaining
            finally:
                await stop(adapter)

    first, repeated, ack1, ack2, remaining = run(scenario())
    assert repeated["next_cursor"] == first["next_cursor"]
    assert ack1[0] == 200 and ack1[1]["cursor"] == first["next_cursor"], ack1
    assert ack2[0] == 200 and ack2[1]["cursor"] == first["next_cursor"], ack2
    assert ack2[1]["acked"] == 0, ack2
    events = remaining.get("events") or []
    assert events, remaining
    assert events[0]["seq"] == first["next_cursor"] + 1, remaining
