"""The read-only native observer can reconcile status after the UI acknowledges events."""
from _transport_harness import (
    build_session_store, http, isolated_runtime, make_adapter, pair,
    preexisting_conversation, run, start, stop,
)


def test_poll_reports_live_pending_state_without_consuming_chat_events(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            adapter.set_session_store(store)
            existing = preexisting_conversation(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                status, turn, _ = await http(port, 'POST', '/messages', token=token,
                    body={'message_id': 'notification-turn', 'text': 'hello'})
                assert status == 202
                _, first, _ = await http(port, 'GET', '/messages?cursor=0', token=token)
                _, second, _ = await http(port, 'GET', '/messages?cursor=0', token=token)
                assert first['pending_turn_id'] == turn['turn_id']
                assert first['events'] == second['events']
                await adapter.send('inst-1', 'finished')
                _, final, _ = await http(port, 'GET', '/messages?cursor=0', token=token)
                cursor = final['next_cursor']
                await http(port, 'POST', '/messages', token=token, body={'ack': {'cursor': cursor}})
                _, empty, _ = await http(port, 'GET', f'/messages?cursor={cursor}', token=token)
                assert empty['events'] == []
                assert empty['pending_turn_id'] is None
            finally:
                await stop(adapter)
    run(scenario())
