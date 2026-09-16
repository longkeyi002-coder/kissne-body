"""KB1-MOBILE-CHAT-TRANSPORT / RED — pending state and cancel acknowledgement (§0.3.16 ⑥).

Contract frozen here:

* Accepting an inbound turn publishes a ``pending`` event for it, so the device knows a turn is open
  (not just that text was accepted).
* ``POST /cancel {"turn_id": T}`` is the ONLY cancellation surface. It (a) interrupts the Runtime turn
  it belongs to, and (b) acknowledges with the resulting state, so the dumb terminal never has to
  infer "did my cancel land?" from silence.
* The turn state machine is explicit and fails closed: cancelling an unknown turn is 404, cancelling a
  turn that already completed or was already cancelled is 409. A missing ``turn_id`` is 400.
* Turns are per installation: a device can neither cancel nor probe another installation's turn.

RED reason: ``/cancel`` does not exist, the adapter never publishes a ``pending`` event, and inbound
``turn_id`` is not a first-class handle yet. Nothing is skipped.
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


def _interrupt_recorder(adapter):
    calls = []

    async def _fake(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    adapter.interrupt_session_activity = _fake
    return calls


async def _open_turn(port, token) -> dict:
    status, payload, _ = await http(port, "POST", "/messages", token=token,
                                    body={"text": "long running question", "message_id": "m-cancel-1"})
    assert status == 202, f"opening a turn must succeed, got {status}: {payload}"
    assert payload.get("turn_id"), f"the accept response must carry a turn_id: {payload}"
    return payload


async def _events(port, token, cursor=0) -> list:
    _, payload, _ = await http(port, "GET", f"/messages?cursor={cursor}", token=token)
    return list(payload.get("events") or [])


def test_an_open_turn_is_published_as_pending(tmp_path):
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
                events = await _events(port, token)
            finally:
                await stop(adapter)
        return turn, events

    turn, events = run(scenario())
    pending = [event for event in events if event.get("type") == "pending"]
    assert pending, (
        f"an accepted turn must be published as a 'pending' event so the device knows it is open: {events}")
    assert pending[-1].get("turn_id") == turn.get("turn_id"), (
        f"the pending event must carry the turn it belongs to: {pending[-1]!r}")


def test_cancel_interrupts_the_runtime_turn_and_acknowledges(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            calls = _interrupt_recorder(adapter)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token)
                status, payload, _ = await http(port, "POST", "/cancel", token=token,
                                                body={"turn_id": turn["turn_id"]})
                events = await _events(port, token)
            finally:
                await stop(adapter)
        return turn, status, payload, events, calls

    turn, status, payload, events, calls = run(scenario())
    assert status == 200, f"cancelling an open turn must answer 200, got {status}: {payload}"
    assert payload.get("acknowledged") is True, (
        f"cancel must be explicitly acknowledged, not silent: {payload}")
    assert payload.get("turn_id") == turn["turn_id"], f"cancel must echo the turn id: {payload}"
    assert payload.get("state") == "cancelled", f"cancel must report the resulting state: {payload}"
    assert calls, "cancel did not interrupt the Runtime turn at all"
    cancelled = [event for event in events if event.get("type") == "cancelled"]
    assert cancelled and cancelled[-1].get("turn_id") == turn["turn_id"], (
        f"the cancelled turn must be published as a 'cancelled' event: {events}")


def test_cancel_interrupts_the_joined_conversation(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            calls = _interrupt_recorder(adapter)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                turn = await _open_turn(port, token)
                await http(port, "POST", "/cancel", token=token, body={"turn_id": turn["turn_id"]})
            finally:
                await stop(adapter)
        return existing, calls

    existing, calls = run(scenario())
    assert calls, "cancel must interrupt the Runtime turn"
    assert existing.session_key in repr(calls), (
        "cancel must target the Conversation this installation is joined to: "
        f"{calls} does not mention {existing.session_key}")


def test_cancelling_a_finished_or_unknown_turn_fails_closed(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            _interrupt_recorder(adapter)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                unknown_status, unknown_payload, _ = await http(
                    port, "POST", "/cancel", token=token, body={"turn_id": "turn_does_not_exist"})
                missing_status, _, _ = await http(port, "POST", "/cancel", token=token, body={})

                turn = await _open_turn(port, token)
                await adapter.send(INSTALLATION, "already answered")
                late_status, late_payload, _ = await http(
                    port, "POST", "/cancel", token=token, body={"turn_id": turn["turn_id"]})
                twice = await _open_turn(port, token)
                await http(port, "POST", "/cancel", token=token, body={"turn_id": twice["turn_id"]})
                again_status, again_payload, _ = await http(
                    port, "POST", "/cancel", token=token, body={"turn_id": twice["turn_id"]})
            finally:
                await stop(adapter)
        return (unknown_status, unknown_payload, missing_status, late_status, late_payload,
                again_status, again_payload)

    (unknown_status, unknown_payload, missing_status, late_status, late_payload,
     again_status, again_payload) = run(scenario())
    assert unknown_status == 404, f"cancelling an unknown turn must be 404, got {unknown_status}"
    assert unknown_payload.get("error") == "unknown_turn", (
        f"the unknown-turn refusal must name its reason: {unknown_payload}")
    assert missing_status == 400, f"a cancel without turn_id must be 400, got {missing_status}"
    assert late_status == 409, (
        f"cancelling an already-completed turn must be 409, got {late_status}: {late_payload}")
    assert late_payload.get("error") == "turn_already_completed", (
        f"the completed-turn refusal must name its reason: {late_payload}")
    assert again_status == 409, (
        f"cancelling an already-cancelled turn must be 409, got {again_status}: {again_payload}")
    assert again_payload.get("error") == "turn_not_cancellable", (
        f"the second cancel must name its reason: {again_payload}")


def test_turns_are_isolated_per_installation(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            _interrupt_recorder(adapter)
            port = await start(adapter)
            try:
                token_a = await pair(port, adapter, installation_id="inst-a", conversation=existing)
                token_b = await pair(port, adapter, installation_id="inst-b", conversation=existing)
                turn_a = await _open_turn(port, token_a)
                status, payload, _ = await http(port, "POST", "/cancel", token=token_b,
                                                body={"turn_id": turn_a["turn_id"]})
            finally:
                await stop(adapter)
        return status, payload

    status, payload = run(scenario())
    assert status == 404, (
        "one installation cancelled (or probed) another installation's turn: "
        f"got {status}: {payload}")
