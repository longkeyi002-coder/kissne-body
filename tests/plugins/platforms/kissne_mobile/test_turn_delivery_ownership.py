"""Late replies and native stream frames retain the HTTP-admitted originating turn."""
from _transport_harness import build_session_store, http, isolated_runtime, make_adapter, pair, preexisting_conversation, run, start, stop


def test_older_reply_and_stream_do_not_close_or_write_into_newer_turn(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                turns = []
                for client_id in ("first", "second"):
                    status, accepted, _ = await http(port, "POST", "/messages", token=token, body={"message_id": client_id, "text": client_id})
                    assert status == 202
                    turns.append(accepted["turn_id"])
                other = preexisting_conversation(sessions, chat_id="other-room", user_id="other-user")
                assert adapter.bind_conversation("inst-1", other.session_key)
                await adapter.send_stream_frame("旧轮工具调用前的回复", chat_id="inst-1", turn_id="consumer-stream-id", reply_to=turns[0])
                await adapter.send_stream_frame("新轮保持原帧", chat_id="inst-1", turn_id="new-consumer", reply_to=turns[1])
                await adapter.send("inst-1", "旧轮结束", reply_to=turns[0])
                await adapter.send_stream_frame("新轮保持原帧", chat_id="inst-1", turn_id="new-consumer", reply_to=turns[1])
                _, payload, _ = await http(port, "GET", "/messages?cursor=0", token=token)
                text_events = [event for event in payload["events"] if str(event.get("text") or "").startswith("旧轮")]
                assert text_events and all(event["turn_id"] == turns[0] for event in text_events)
                assert all(event.get("session_id") == conversation.session_id for event in text_events)
                assert len([event for event in payload["events"] if event.get("text") == "新轮保持原帧"]) == 1
                assert adapter.device_store().turn(turns[0])["state"] == "completed"
                assert adapter.device_store().turn(turns[1])["state"] == "pending"
            finally:
                await stop(adapter)
    run(scenario())


def test_bootstrap_preserves_process_channels_and_search_keeps_message_ownership(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            for row in [
                {"role": "user", "content": "问候", "platform_message_id": "kbm_turn_history"},
                {"role": "assistant", "content": "准备查询", "display_kind": "commentary"},
                {"role": "assistant", "content": "公开的过程说明", "display_kind": "reasoning"},
                {"role": "assistant", "content": "另一种过程通道", "display_kind": "analysis"},
                {"role": "assistant", "content": "内部噪音", "display_kind": "hidden"},
                {"role": "assistant", "content": "正式回答", "reasoning": "provider-private"},
            ]:
                sessions.append_to_transcript(conversation.session_id, row)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                _, boot, _ = await http(port, "POST", "/bootstrap", token=token, body={})
                history = boot["history"]
                assert not any(row.get("text") == "内部噪音" for row in history)
                assert next(row for row in history if row.get("text") == "准备查询")["presentation"] == "commentary"
                assert next(row for row in history if row.get("text") == "公开的过程说明")["presentation"] == "reasoning"
                assert next(row for row in history if row.get("text") == "另一种过程通道")["presentation"] == "reasoning"
                assert all("reasoning" not in row for row in history)
                _, result, _ = await http(port, "GET", "/search?q=正式回答", token=token)
                assert result["results"][0]["session_id"] == conversation.session_id
                assert result["results"][0]["message_ref"] == "turn:kbm_turn_history:assistant"
                _, result, _ = await http(port, "GET", "/search?q=准备查询", token=token)
                assert result["results"] == []
            finally:
                await stop(adapter)
    run(scenario())
