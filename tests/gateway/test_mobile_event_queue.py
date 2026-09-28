import asyncio
import queue
from types import SimpleNamespace
import pytest
from gateway.turn_context import TurnContext
from gateway.run_turn_runner import TurnRunner

@pytest.mark.asyncio
async def test_text_between_tools_does_not_stop_drain_or_overwrite_answer():
    q=queue.Queue(); received=[]
    async def tool(**kw):received.append(('tool',kw['event']['tool_call_id'],kw['metadata']))
    async def text(**kw):received.append(('text',kw['content'],kw['metadata']))
    ctx=TurnContext(source=SimpleNamespace(chat_id='device'),progress_queue=q,_run_still_current=lambda:True,event_message_id='origin')
    runner=TurnRunner(None,ctx)
    q.put({'tool_call_id':'a'});q.put('正在检查接口');q.put({'tool_call_id':'b'})
    task=asyncio.create_task(runner._send_structured_lifecycle_events(SimpleNamespace(send_structured_tool_event=tool,send=text)))
    await asyncio.sleep(.02);task.cancel();await task
    assert [(r[0],r[1]) for r in received]==[('tool','a'),('text','正在检查接口'),('tool','b')]
    assert all(r[2]['reply_to_message_id']=='origin' for r in received)
    assert received[1][2]['_interim_send'] is True

@pytest.mark.asyncio
async def test_cancel_after_commit_does_not_duplicate_or_reorder_events():
    q=queue.Queue(); committed=[]; entered=asyncio.Event(); release=asyncio.Event()
    async def send(**kw):
        call=kw['event']['tool_call_id'];committed.append(call)
        if call=='a':entered.set();await release.wait()
    ctx=TurnContext(source=SimpleNamespace(chat_id='device'),progress_queue=q,_run_still_current=lambda:True)
    runner=TurnRunner(None,ctx)
    q.put({'tool_call_id':'a'});q.put({'tool_call_id':'b'})
    task=asyncio.create_task(runner._send_structured_lifecycle_events(SimpleNamespace(send_structured_tool_event=send)))
    await entered.wait();task.cancel();await asyncio.sleep(0);release.set();await task
    assert committed==['a','b']

@pytest.mark.asyncio
async def test_superseded_turn_never_flushes_into_new_turn():
    q=queue.Queue(); current=[True]; received=[]
    async def send(**kw):received.append(kw)
    ctx=TurnContext(source=SimpleNamespace(chat_id='device'),progress_queue=q,_run_still_current=lambda:current[0])
    task=asyncio.create_task(TurnRunner(None,ctx)._send_structured_lifecycle_events(SimpleNamespace(send_structured_tool_event=send)))
    await asyncio.sleep(0);q.put({'tool_call_id':'old'});current[0]=False;task.cancel();await task
    assert received==[]
