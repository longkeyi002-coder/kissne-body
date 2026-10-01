"""Real HTTP review handler with device-auth boundary and durable provider writes."""
import asyncio
import sys
import types
from aiohttp import web, ClientSession
from plugins.platforms.kissne_mobile.memory_review import handle_memory_review
from plugins.memory.lifemem.store import MemoryStore


def test_review_http_auth_and_evidence_checked_write(tmp_path,monkeypatch):
    monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    config=types.ModuleType('hermes_cli.config')
    config.load_config_readonly=lambda: {}
    config.cfg_get=lambda *a,**kw: 'lifemem'
    monkeypatch.setitem(sys.modules,'hermes_cli.config',config)
    path=tmp_path/'kissne-lifemem'/'memory.db';path.parent.mkdir()
    db=MemoryStore(str(path))
    tid=db.add_turn('s','记住，我喜欢绿色','收到')
    mid=db.add_memory('记住，我喜欢绿色','记住，我喜欢绿色',status='candidate',category='preference',subject='user',scope='reality',session_id='s',turn_id=tid)
    db.close()
    class DeviceBoundary:
        async def _authenticated_installation(self,request):
            return {'installation_id':'device'} if request.headers.get('Authorization')=='Bearer paired' else None
    async def scenario():
        adapter=DeviceBoundary();app=web.Application()
        async def handler(request):return await handle_memory_review(adapter,request)
        app.router.add_get('/memory/review',handler);app.router.add_post('/memory/review',handler)
        runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])+'/memory/review'
        try:
            async with ClientSession() as client:
                async with client.post(url,json={'action':'approve','id':mid}) as response:assert response.status==401
                headers={'Authorization':'Bearer paired'}
                async with client.get(url,headers=headers) as response:
                    assert response.status==200;assert (await response.json())['items'][0]['id']==mid
                async with client.post(url,headers=headers,json={'action':'audit'}) as response:assert response.status==400
                async with client.post(url,headers=headers,json={'action':'approve','id':mid}) as response:
                    assert response.status==200;assert (await response.json())['status']=='active'
                async with client.get(url,headers=headers) as response:assert (await response.json())['items']==[]
        finally:await runner.cleanup()
    asyncio.run(scenario())
    db=MemoryStore(str(path));assert db.list_memories()[0]['id']==mid;db.close()
