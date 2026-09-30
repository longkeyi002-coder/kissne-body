"""Device-authenticated Lifemem candidate review, using the one provider store."""
from __future__ import annotations
import asyncio
from pathlib import Path
from aiohttp import web

async def handle_memory_review(adapter, request):
    if not await adapter._authenticated_installation(request):
        return web.json_response({'error':'unauthorized'},status=401)
    from hermes_cli.config import cfg_get, load_config_readonly
    if cfg_get(load_config_readonly(),'memory','provider',default='') != 'lifemem':
        return web.json_response({'error':'lifemem_not_active'},status=503)
    try:
        if request.method == 'GET':
            payload={'action':'list','limit':int(request.query.get('limit','100'))}
        else:
            payload=await request.json()
            if not isinstance(payload,dict) or payload.get('action') not in {'approve','reject'}:
                raise ValueError('invalid_review_action')
        from hermes_constants import get_hermes_home
        path=Path(get_hermes_home())/'kissne-lifemem'/'memory.db'
        result=await asyncio.to_thread(review_at_path,path,payload)
        return web.json_response({'ok':True,**result})
    except (ValueError,TypeError,KeyError) as exc:
        return web.json_response({'error':str(exc)},status=400)

def review_at_path(path, payload):
    from plugins.memory.lifemem.store import MemoryStore
    from plugins.memory.lifemem.review import MemoryReview
    if not path.exists():
        if payload['action'] == 'list': return {'items':[]}
        raise ValueError('memory_not_found')
    store=MemoryStore(str(path))
    try:
        review=MemoryReview(store)
        if payload['action'] == 'list':
            fields=('id','summary','quote','category','subject','scope','memory_space','admission_reason','session_id','turn_id','status')
            return {'items':[{k:row.get(k) for k in fields} for row in review.list(payload.get('limit',100))]}
        return review.review(payload['id'],payload['action'],payload.get('updates'))
    finally:
        store.close()
