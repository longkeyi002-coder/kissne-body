"""Real HTTP/history recovery and device-owned file retrieval."""
import base64
import io
from PIL import Image
from _transport_harness import build_session_store, http, isolated_runtime, make_adapter, pair, preexisting_conversation, run, start, stop


def test_photo_survives_runtime_media_cleanup_and_returns_as_image(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            sessions = build_session_store(home)
            conversation = preexisting_conversation(sessions)
            adapter.set_session_store(sessions)
            captured = []
            async def admit(event):
                captured.append(event)
                event._gateway_accepted = True
            adapter.handle_message = admit
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                out = io.BytesIO(); Image.new('RGB', (12, 10), 'blue').save(out, format='PNG')
                original = out.getvalue()
                status, accepted, _ = await http(port, 'POST', '/messages', token=token, body={
                    'message_id':'picture', 'attachments':[{'type':'image','mime_type':'image/png','label':'相册照片.png','data':base64.b64encode(original).decode()}]})
                assert status == 202, accepted
                await adapter.on_processing_start(captured[0])
                adapter._cleanup_inbound_media(captured[0])
                turn = accepted['turn_id']
                sessions.append_to_transcript(conversation.session_id, {'role':'user','content':'[The user sent an image~ description.]\n[If you need a closer look, use vision_analyze with image_url: /private/path ~]\n[文件：相册照片.png]', 'platform_message_id':turn})
                for endpoint, method in [('/bootstrap','POST'),('/history','GET')]:
                    status, result, _ = await http(port, method, endpoint, token=token, body={} if method == 'POST' else None)
                    assert status == 200
                    rows = result.get('history', result.get('items', result.get('messages', [])))
                    image = next(row for row in rows if row.get('role') == 'user')
                    assert image['text'] == ''
                    assert image['attachments'][0]['preview'].startswith('data:image/webp;base64,')
                    assert 'stored_name' not in image['attachments'][0]
                status, result, _ = await http(port, 'GET', '/attachments?turn_id='+turn+'&index=0', token=token)
                assert status == 200
                assert base64.b64decode(result['base64']) == original
                status, _, _ = await http(port, 'GET', '/attachments?turn_id='+turn+'&index=0')
                assert status == 401
                status, _, _ = await http(port, 'GET', '/attachments?turn_id=kbm_turn_other&index=0', token=token)
                assert status == 404
            finally:
                await stop(adapter)
    run(scenario())
