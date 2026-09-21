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
                await adapter.send(INSTALLATION, "the final answer", reply_to=turn["turn_id"])
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


def test_send_without_reply_anchor_does_not_close_ambiguous_pending_turn(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                first = await _open_turn(port, token, text="first", message_id="m-turn-1")
                second = await _open_turn(port, token, text="second", message_id="m-turn-2")
                await adapter.send(INSTALLATION, "unanchored status")
                payload = await _drain(port, token, 0)
                first_row = adapter.device_store().turn(first["turn_id"])
                second_row = adapter.device_store().turn(second["turn_id"])
            finally:
                await stop(adapter)
        return first, second, payload, first_row, second_row

    first, second, payload, first_row, second_row = run(scenario())
    notices = [event for event in payload.get("events") or []
               if event.get("text") == "unanchored status"]
    assert notices[0].get("type") == "notice", (
        f"ambiguous unanchored send must stay a notice: {payload.get('events')}")
    assert first_row.get("state") == "pending" and second_row.get("state") == "pending", (
        "an unanchored send with multiple pending turns must not complete either turn: "
        f"{first_row}, {second_row}")


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
                await adapter.send(
                    INSTALLATION, "answer so far and done", reply_to=turn["turn_id"])
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
