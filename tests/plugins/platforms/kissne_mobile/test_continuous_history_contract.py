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
