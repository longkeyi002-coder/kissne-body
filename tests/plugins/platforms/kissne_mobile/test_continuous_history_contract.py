"""Continuous Mobile timeline: /new boundaries stay internal; search and quotes cross them."""

from ._transport_harness import http, isolated_runtime, make_adapter, pair, run, start, stop


def _rows():
    return [
        {"message_ref": "old-session:0", "role": "user", "text": "以前讨论微信修复", "created_at": 1.0},
        {"message_ref": "old-session:1", "role": "assistant", "text": "先检查 gateway 日志", "created_at": 2.0},
        {"message_ref": "new-session:0", "role": "user", "text": "现在继续 Kissne", "created_at": 3.0},
    ]


def test_history_pages_across_hidden_session_boundaries(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            adapter._mobile_history_rows = lambda _installation: _rows()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                return await http(port, "GET", "/history?limit=2", token=token)
            finally:
                await stop(adapter)
    status, payload, _ = run(scenario())
    assert status == 200
    assert [m["message_ref"] for m in payload["messages"]] == ["old-session:1", "new-session:0"]
    assert payload["has_more"] is True
    assert payload["next_before"] == "old-session:1"
    assert all("session_id" not in m for m in payload["messages"])


def test_search_crosses_hidden_session_boundaries(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            adapter._mobile_history_rows = lambda _installation: _rows()
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                return await http(port, "GET", "/search?q=微信", token=token)
            finally:
                await stop(adapter)
    status, payload, _ = run(scenario())
    assert status == 200
    assert [m["message_ref"] for m in payload["results"]] == ["old-session:0"]


def test_quote_old_session_message_reaches_runtime_reply_fields(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            adapter._mobile_history_rows = lambda _installation: _rows()
            captured = []

            async def capture(event):
                captured.append(event)

            adapter.handle_message = capture
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                status, payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "quote-1", "text": "这个继续处理",
                          "reply_to": "old-session:1"},
                )
                return status, payload, captured
            finally:
                await stop(adapter)
    status, payload, captured = run(scenario())
    assert status == 202, payload
    assert len(captured) == 1
    event = captured[0]
    assert event.text == "这个继续处理"
    assert event.reply_to_message_id == "old-session:1"
    assert event.reply_to_text == "先检查 gateway 日志"
    assert event.reply_to_author_name == "叶青栩"
    assert event.reply_to_is_own_message is True


def test_new_remains_a_real_hermes_command_but_chat_yes_is_not_approval(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            captured = []

            async def capture(event):
                captured.append((event.text, event.allow_gateway_control))

            adapter.handle_message = capture
            port = await start(adapter)
            try:
                token = await pair(port, adapter)
                await http(port, "POST", "/messages", token=token,
                           body={"message_id": "cmd-new", "text": "/new"})
                await http(port, "POST", "/messages", token=token,
                           body={"message_id": "plain-yes", "text": "yes"})
                await http(port, "POST", "/messages", token=token,
                           body={"message_id": "no-chat-approve", "text": "/approve"})
                return captured
            finally:
                await stop(adapter)
    assert run(scenario()) == [("/new", True), ("yes", False), ("/approve", False)]


def test_session_reset_notice_uses_backend_reply_verbatim(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            sent = []
            original_queue = adapter._queue_event

            async def capture(installation_id, event_type, **kwargs):
                sent.append((event_type, kwargs))
                return "out-reset"

            adapter._queue_event = capture
            adapter.device_store().open_turn("kbm_turn_reset", "phone-a")
            adapter._session_reset_pending.add("phone-a")
            adapter._session_reset_turns["phone-a"] = "kbm_turn_reset"
            backend_text = (
                "✨ Session reset! Starting fresh.\n\n"
                "◆ Model: `future-model-from-hermes`\n"
                "◆ Provider: future-provider\n"
                "◆ Context: 2.0M tokens (detected)\n"
                "✦ Tip: backend-owned text"
            )
            result = await adapter.send("phone-a", backend_text)
            adapter._queue_event = original_queue
            notices = adapter.device_store().timeline_notices("phone-a")
            return result, sent, notices

    result, sent, notices = run(scenario())
    assert result.success is True
    assert len(sent) == 1
    event_type, kwargs = sent[0]
    assert kwargs["content"].endswith("✦ Tip: backend-owned text")
    assert "future-model-from-hermes" in kwargs["content"]
    assert kwargs["extra"]["presentation"] == "session_reset"
    assert kwargs["extra"]["notice_id"].startswith("kbn_")
    assert len(notices) == 1
    assert notices[0]["presentation"] == "session_reset"
    assert notices[0]["text"] == kwargs["content"]
    assert notices[0]["notice_id"] == kwargs["extra"]["notice_id"]

def test_session_reset_marker_is_not_consumed_by_an_unrelated_newer_turn(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path):
            adapter = make_adapter()
            sent = []

            async def capture(installation_id, event_type, **kwargs):
                sent.append((event_type, kwargs))
                return "out"

            adapter._queue_event = capture
            store = adapter.device_store()
            store.open_turn("kbm_turn_reset", "phone-a")
            adapter._session_reset_pending.add("phone-a")
            adapter._session_reset_turns["phone-a"] = "kbm_turn_reset"

            # A newer ordinary turn is now the pending turn. Its reply must not consume /new's marker.
            store.open_turn("kbm_turn_plain", "phone-a")
            await adapter.send("phone-a", "ordinary reply")
            marker_after_plain = (
                "phone-a" in adapter._session_reset_pending,
                adapter._session_reset_turns.get("phone-a"),
            )

            store.close_turn("kbm_turn_plain", "completed")
            await adapter.send("phone-a", "canonical reset reply")
            return sent, marker_after_plain, adapter._session_reset_turns.get("phone-a")

    sent, marker_after_plain, remaining = run(scenario())
    assert marker_after_plain == (True, "kbm_turn_reset")
    assert sent[0][1].get("extra") in (None, {})
    assert sent[1][1]["extra"]["presentation"] == "session_reset"
    assert sent[1][1]["extra"]["notice_id"].startswith("kbn_")
    assert remaining is None


def test_mobile_history_uses_stable_turn_refs_and_persists_quote_preview(tmp_path):
    with isolated_runtime(tmp_path):
        adapter = make_adapter()
        turn_id = "kbm_turn_quote"
        target_ref = "legacy-session:0"

        class TranscriptStore:
            @staticmethod
            def load_transcript(_session_id):
                return [
                    {"role": "assistant", "content": "被引用的旧回复", "created_at": 1.0},
                    {"role": "user", "content": "这个继续处理", "message_id": turn_id, "created_at": 2.0},
                    {"role": "assistant", "content": "继续处理完成", "created_at": 3.0},
                ]

        adapter._session_store = TranscriptStore()
        adapter._mobile_history_sessions = lambda _installation: [{"id": "legacy-session"}]
        adapter.device_store().record_reply_link(
            "phone-a", turn_id, target_ref, "assistant", "被引用的旧回复"
        )
        adapter.device_store().record_attachment_message(
            "phone-a", turn_id, "这个继续处理",
            [{"type": "file", "mime_type": "text/plain", "label": "notes.txt"}],
        )

        rows = adapter._mobile_history_rows("phone-a")

    assert rows[0]["message_ref"] == target_ref
    assert rows[1]["message_ref"] == "turn:kbm_turn_quote:user"
    assert rows[1]["reply_to"] == target_ref
    assert rows[1]["reply_preview"] == {"role": "assistant", "text": "被引用的旧回复"}
    assert rows[1]["attachments"][0]["label"] == "notes.txt"
    assert rows[2]["message_ref"] == "turn:kbm_turn_quote:assistant"

