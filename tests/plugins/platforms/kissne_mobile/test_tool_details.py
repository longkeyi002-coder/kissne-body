"""Real HTTP checks: retained output, pagination and device isolation."""
import asyncio
from types import SimpleNamespace
import queue
from _transport_harness import isolated_runtime, make_adapter, build_session_store, preexisting_conversation, start, stop, pair, http, run
from gateway.turn_context import TurnContext
from gateway.run_turn_runner import TurnRunner


def test_complete_tool_output_roundtrips_through_gateway_and_http(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter(); sessions = build_session_store(home)
            existing = preexisting_conversation(sessions); adapter.set_session_store(sessions)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                _, inbound, _ = await http(port, 'POST', '/messages', token=token,
                                           body={'text':'check', 'message_id':'full-output'})
                turn = inbound['turn_id']
                q = queue.Queue()
                ctx = TurnContext(source=SimpleNamespace(chat_id='inst-1'), progress_queue=q,
                                  _run_still_current=lambda: True, event_message_id=turn)
                runner = TurnRunner(None, ctx)
                args = {'command':'pytest -q', 'note':'参数🦊'*800}
                output = '完整开头\n' + ('中文🦊\n' * 1900) + '\n完整结尾'
                runner.structured_tool_start_callback('same/id', 'terminal', args)
                runner.structured_tool_complete_callback('same/id', 'terminal', args, output)
                task = asyncio.create_task(runner._send_structured_lifecycle_events(adapter))
                await asyncio.sleep(.1); task.cancel(); await task
                _, events, _ = await http(port, 'GET', '/messages?cursor=0', token=token)
                result = next(e['activity'] for e in events['events'] if e.get('presentation')=='tool_result')
                assert result['output']==output[:2000]
                assert result['result_truncated'] is True
                assert result['detail_ref']['turn_id']==turn
                path = '/tool-details?turn_id='+turn+'&tool_call_id=same%2Fid&field=result'
                status, _, _ = await http(port, 'GET', path)
                assert status==401
                gathered = ''; offset = 0
                while True:
                    status, page, _ = await http(port, 'GET', path+'&offset='+str(offset), token=token)
                    assert status==200
                    gathered += page['text']
                    if page['next_offset'] is None: break
                    offset=page['next_offset']
                assert gathered==output
                status, _, _=await http(port, 'GET', path+'&offset=-1', token=token)
                assert status==400
                other_token = await pair(port, adapter, installation_id='another-device')
                status, _, _ = await http(port, 'GET', path, token=other_token)
                assert status == 404
                # Reopen the real SQLite store, not only the adapter's label cache.
                store_class = type(adapter.device_store())
                adapter._store.close()
                adapter._store = store_class()
                status, page, _ = await http(port, 'GET', path, token=token)
                assert status == 200
                assert page['text'] == output[:2000]
            finally:
                await stop(adapter)
    run(scenario())
