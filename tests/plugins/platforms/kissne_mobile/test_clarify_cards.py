"""Choice cards exercise real authenticated HTTP and the production pending primitive."""
from _transport_harness import build_session_store, http, isolated_runtime, make_adapter, pair, run, start, stop
from tools import clarify_gateway


def test_choice_cards_bind_to_device_restore_and_reject_expired_or_repeated_clicks(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            adapter.set_session_store(store)
            store.get_or_create_session(adapter.source_for_installation("device-a"))
            store.get_or_create_session(adapter.source_for_installation("device-b"))
            port = await start(adapter)
            key = adapter.mobile_session_key("device-a")
            try:
                token = await pair(port, adapter, installation_id="device-a")
                foreign = await pair(port, adapter, installation_id="device-b")
                for credential in (token, foreign):
                    status, _, _ = await http(port, "POST", "/bootstrap", token=credential, body={})
                    assert status == 200
                entry = clarify_gateway.register("real-choice", key, "现在重启还是稍后？", ["现在重启", "稍后"])
                result = await adapter.send_clarify("device-a", entry.question, entry.choices, entry.clarify_id, key)
                assert result.success
                _, boot, _ = await http(port, "POST", "/bootstrap", token=token, body={})
                assert boot["pending_clarifies"][0]["clarify_id"] == entry.clarify_id
                _, events, _ = await http(port, "GET", "/messages?cursor=0", token=token)
                assert any(row["type"] == "clarify_required" and row["choices"] == entry.choices for row in events["events"])
                for credential, value, expected in [(foreign, "1", 404), (token, "9", 400), (token, "2", 200), (token, "1", 404)]:
                    status, _, _ = await http(port, "POST", "/clarify", token=credential, body={"clarify_id": entry.clarify_id, "response": value})
                    assert status == expected
                assert entry.response == "稍后"
                clarify_gateway.clear_session(key)
                entry = clarify_gateway.register("multi", key, "选哪些？", ["A", "B"], multi_select=True)
                await adapter.send_clarify("device-a", entry.question, entry.choices, entry.clarify_id, key)
                status, _, _ = await http(port, "POST", "/clarify", token=token, body={"clarify_id": entry.clarify_id, "response": "1,2"})
                assert status == 200 and entry.response == '["A", "B"]'
                clarify_gateway.clear_session(key)
                entry = clarify_gateway.register("other", key, "选哪个？", ["A", "B"])
                await adapter.send_clarify("device-a", entry.question, entry.choices, entry.clarify_id, key)
                status, result, _ = await http(port, "POST", "/clarify", token=token, body={"clarify_id": entry.clarify_id, "other": True})
                assert status == 200 and result["status"] == "awaiting_text" and not entry.event.is_set()
                status, _, _ = await http(port, "POST", "/clarify", token=token, body={"clarify_id": entry.clarify_id, "response": "自定义回答"})
                assert status == 200 and entry.response == "自定义回答"
                clarify_gateway.clear_session(key)
                entry = clarify_gateway.register("expired", key, "继续？", ["是", "否"])
                await adapter.send_clarify("device-a", entry.question, entry.choices, entry.clarify_id, key)
                clarify_gateway.clear_session(key)
                await adapter.retire_clarify_card(entry.clarify_id, "请求超时")
                status, _, _ = await http(port, "POST", "/clarify", token=token, body={"clarify_id": entry.clarify_id, "response": "1"})
                assert status == 404
                assert adapter.device_store().pending_turn_id("device-a") is None
            finally:
                clarify_gateway.clear_session(key)
                await stop(adapter)
    run(scenario())
