"""KB1 Mobile bootstrap/outbound reconciliation contract.

A cold-start bootstrap may contain a completed reply that is also still present in the durable
outbound queue because the Android client died before acknowledging it.  Bootstrap must prove which
queued frames are already represented by the exact returned history snapshot, by server ``turn_id``
identity only, without consuming the queue.
"""

from _transport_harness import (
    PAIRED_INSTALLATION,
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


def _persisted_turn(store, session_id, turn_id, *, question="question", answer="same answer"):
    store.append_to_transcript(
        session_id,
        {"role": "user", "content": question, "platform_message_id": turn_id},
    )
    store.append_to_transcript(session_id, {"role": "assistant", "content": answer})


def _enqueue_turn(device_store, turn_id, *, state="completed", types=("pending", "delta", "completed")):
    device_store.open_turn(turn_id, PAIRED_INSTALLATION, state="pending")
    seqs = []
    for event_type in types:
        seqs.append(device_store.enqueue_event(
            PAIRED_INSTALLATION,
            event_type,
            {"text": f"{event_type}:{turn_id}"},
            turn_id,
        ))
    if state != "pending":
        assert device_store.close_turn(turn_id, state)
    return seqs


def test_completed_turn_represented_by_bootstrap_covers_exact_unacked_frames_without_consuming(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                turn_id = "kbm_turn_done"
                _persisted_turn(sessions, conversation.session_id, turn_id)
                device_store = adapter.device_store()
                seqs = _enqueue_turn(device_store, turn_id)
                before = device_store.events_after(PAIRED_INSTALLATION, 0)
                status, payload, _ = await http(
                    port, "POST", "/bootstrap", token=token, body={"cursor": 0})
                after = device_store.events_after(PAIRED_INSTALLATION, 0)
                return status, payload, seqs, before, after
            finally:
                await stop(adapter)

    status, payload, seqs, before, after = run(scenario())
    assert status == 200, payload
    assert payload.get("covered_event_seqs") == seqs, payload
    history = payload.get("history") or []
    assert [row.get("message_ref") for row in history] == [
        "turn:kbm_turn_done:user",
        "turn:kbm_turn_done:assistant",
    ], history
    assert before == after, "bootstrap must be non-destructive; only ACK may retire outbound rows"


def test_pending_cancelled_and_unidentified_events_are_never_covered(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                device_store = adapter.device_store()

                pending_id = "kbm_turn_pending"
                _persisted_turn(sessions, conversation.session_id, pending_id, question="pending")
                _enqueue_turn(device_store, pending_id, state="pending", types=("pending", "delta"))

                cancelled_id = "kbm_turn_cancelled"
                _persisted_turn(sessions, conversation.session_id, cancelled_id, question="cancelled")
                _enqueue_turn(device_store, cancelled_id, state="cancelled", types=("pending", "cancelled"))

                device_store.enqueue_event(
                    PAIRED_INSTALLATION, "completed", {"text": "no identity"}, None)

                status, payload, _ = await http(port, "POST", "/bootstrap", token=token)
                return status, payload
            finally:
                await stop(adapter)

    status, payload = run(scenario())
    assert status == 200, payload
    assert payload.get("covered_event_seqs") == [], payload


def test_coverage_uses_turn_identity_not_text_and_only_the_returned_bounded_snapshot(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter._history_cap = 2
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                device_store = adapter.device_store()

                old_turn = "kbm_turn_old"
                new_turn = "kbm_turn_new"
                _persisted_turn(
                    sessions, conversation.session_id, old_turn,
                    question="old question", answer="identical answer")
                old_seq = _enqueue_turn(
                    device_store, old_turn, types=("completed",))[-1]

                _persisted_turn(
                    sessions, conversation.session_id, new_turn,
                    question="new question", answer="identical answer")
                new_seq = _enqueue_turn(
                    device_store, new_turn, types=("completed",))[-1]

                status, payload, _ = await http(port, "POST", "/bootstrap", token=token)
                return status, payload, old_seq, new_seq
            finally:
                await stop(adapter)

    status, payload, old_seq, new_seq = run(scenario())
    assert status == 200, payload
    assert [item.get("text") for item in payload.get("history") or []] == [
        "new question", "identical answer"
    ], payload
    covered = payload.get("covered_event_seqs")
    assert covered == [new_seq], payload
    assert old_seq not in covered, "same reply text must never substitute for server turn identity"


def test_bounded_history_never_starts_with_an_orphan_assistant_half_turn(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter._history_cap = 3
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            _persisted_turn(sessions, conversation.session_id, "turn-a", question="q-a", answer="a-a")
            _persisted_turn(sessions, conversation.session_id, "turn-b", question="q-b", answer="a-b")
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                status, payload, _ = await http(port, "POST", "/bootstrap", token=token)
                return status, payload
            finally:
                await stop(adapter)

    status, payload = run(scenario())
    assert status == 200, payload
    history = payload.get("history") or []
    assert history and history[0].get("role") == "user", history
    assert [item.get("text") for item in history] == ["q-b", "a-b"], history
    assert payload.get("history_truncated") is True


def test_bootstrap_cursor_defaults_filters_and_fails_closed_on_invalid_values(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                turn_id = "kbm_turn_cursor"
                _persisted_turn(sessions, conversation.session_id, turn_id)
                seqs = _enqueue_turn(adapter.device_store(), turn_id)
                default = await http(port, "POST", "/bootstrap", token=token)
                filtered = await http(
                    port, "POST", "/bootstrap", token=token, body={"cursor": seqs[0]})
                string_cursor = await http(
                    port, "POST", "/bootstrap", token=token, body={"cursor": str(seqs[0])})
                bad_text = await http(
                    port, "POST", "/bootstrap", token=token, body={"cursor": "nope"})
                negative = await http(
                    port, "POST", "/bootstrap", token=token, body={"cursor": -1})
                boolean = await http(
                    port, "POST", "/bootstrap", token=token, body={"cursor": True})
                return seqs, default, filtered, string_cursor, bad_text, negative, boolean
            finally:
                await stop(adapter)

    seqs, default, filtered, string_cursor, bad_text, negative, boolean = run(scenario())
    assert default[0] == 200 and default[1].get("covered_event_seqs") == seqs, default
    expected = seqs[1:]
    assert filtered[0] == 200 and filtered[1].get("covered_event_seqs") == expected, filtered
    assert string_cursor[0] == 200 and string_cursor[1].get("covered_event_seqs") == expected, string_cursor
    assert bad_text[0] == 400 and bad_text[1].get("error") == "cursor_must_be_an_integer", bad_text
    assert negative[0] == 400 and negative[1].get("error") == "cursor_must_not_be_negative", negative
    assert boolean[0] == 400 and boolean[1].get("error") == "cursor_must_be_an_integer", boolean


def test_client_message_id_is_retry_key_but_runtime_identity_is_server_turn_id(tmp_path):
    class Recorder:
        def __init__(self):
            self.events = []

        async def __call__(self, event):
            self.events.append(event)

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            recorder = Recorder()
            adapter.set_message_handler(recorder)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                status, payload, _ = await http(
                    port,
                    "POST",
                    "/messages",
                    token=token,
                    body={"text": "identity check", "message_id": "client-retry-key"},
                )
                return status, payload, recorder.events
            finally:
                await stop(adapter)

    status, payload, events = run(scenario())
    assert status == 202, payload
    assert payload.get("message_id") == "client-retry-key", payload
    turn_id = payload.get("turn_id")
    assert turn_id and turn_id != "client-retry-key", payload
    assert len(events) == 1
    assert events[0].message_id == turn_id, (
        "Runtime-facing MessageEvent.message_id must be the server turn_id so transcript "
        "platform_message_id can reconcile against outbound turn identity"
    )


def test_bootstrap_preserves_tool_chain_and_final_turn_identity(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            turn_id = "kbm_turn_tools"
            sessions.append_to_transcript(
                conversation.session_id,
                {"role": "user", "content": "inspect", "platform_message_id": turn_id},
            )
            sessions.append_to_transcript(conversation.session_id, {
                "role": "assistant", "content": "", "reasoning": "must stay private",
                "tool_calls": [{"id": "call-1", "type": "function",
                                "function": {"name": "terminal", "arguments": "{\"cmd\":\"pwd\"}"}}],
            })
            sessions.append_to_transcript(conversation.session_id, {
                "role": "tool", "content": "x" * 5000,
                "tool_call_id": "call-1", "tool_name": "terminal",
            })
            sessions.append_to_transcript(
                conversation.session_id, {"role": "assistant", "content": "done"})
            adapter.set_session_store(sessions)
            history, truncated, represented = adapter._bootstrap_history_snapshot(
                conversation.session_id)
            return history, truncated, represented

    history, truncated, represented = run(scenario())
    assert [row["role"] for row in history] == ["user", "assistant", "tool", "assistant"]
    assert history[0]["message_ref"] == "turn:kbm_turn_tools:user"
    assert history[-1]["message_ref"] == "turn:kbm_turn_tools:assistant"
    assert all(row["turn_id"] == "kbm_turn_tools" for row in history)
    assert represented == {"kbm_turn_tools"}
    assert history[1]["tool_calls"][0]["id"] == "call-1"
    assert history[2]["tool_call_id"] == "call-1"
    assert history[2]["text"].endswith("…[truncated]")
    assert len(history[2]["text"]) < 4200
    assert all("reasoning" not in row and "reasoning_content" not in row for row in history)
    assert truncated is False


def test_bootstrap_cap_keeps_whole_tool_turns_within_message_ceiling(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter._history_cap = 5
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            _persisted_turn(sessions, conversation.session_id, "old", question="old-q", answer="old-a")
            sessions.append_to_transcript(
                conversation.session_id,
                {"role": "user", "content": "new-q", "platform_message_id": "new"},
            )
            sessions.append_to_transcript(conversation.session_id, {
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "c", "function": {"name": "terminal", "arguments": "{}"}}],
            })
            sessions.append_to_transcript(conversation.session_id, {
                "role": "tool", "content": "ok", "tool_call_id": "c", "tool_name": "terminal",
            })
            sessions.append_to_transcript(
                conversation.session_id, {"role": "assistant", "content": "new-a"})
            adapter.set_session_store(sessions)
            return adapter._bootstrap_history_snapshot(conversation.session_id)

    history, truncated, represented = run(scenario())
    assert len(history) <= 5
    assert [row["role"] for row in history] == ["user", "assistant", "tool", "assistant"]
    assert history[0]["text"] == "new-q"
    assert history[-1]["text"] == "new-a"
    assert truncated is True
    assert represented == {"new"}
    assert all(row["turn_id"] == "new" for row in history)
