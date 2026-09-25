"""Real loopback multipart attachment lifecycle regressions."""

from pathlib import Path

import aiohttp
import pytest

from gateway.platforms.event import MessageType, ProcessingOutcome
from _transport_harness import (
    build_session_store, isolated_runtime, make_adapter, pair,
    preexisting_conversation, run, start, stop,
)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02"
    b"\x00\x00\x00\x0bIDAT\x08\xd7c\x64\xf8\x0f\x00\x05\x01\x01\x01\xa3\x18\x9d\x8b"
    b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
)


async def post_multipart(port, token, *, kind, mime_type):
    form = aiohttp.FormData()
    form.add_field("kind", kind)
    form.add_field("message_id", "multipart-1")
    form.add_field("file_name", "sticker.png")
    form.add_field("mime_type", mime_type)
    form.add_field("file", PNG, filename="sticker.png", content_type=mime_type)
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"http://127.0.0.1:{port}/messages",
            data=form,
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            return response.status, await response.json()


@pytest.mark.asyncio
async def test_multipart_sticker_matches_json_semantics_and_admission_persistence(tmp_path):
    with isolated_runtime(tmp_path) as home:
        adapter = make_adapter()
        store = build_session_store(home)
        conversation = preexisting_conversation(store)
        adapter.set_session_store(store)
        captured = []

        async def capture(event):
            captured.append(event)

        adapter.handle_message = capture
        port = await start(adapter)
        try:
            token = await pair(port, adapter, conversation=conversation)
            status, payload = await post_multipart(
                port, token, kind="sticker", mime_type="image/png"
            )
            assert status == 202, payload
            assert len(captured) == 1
            event = captured[0]
            assert event.text == ""
            assert event.message_type == MessageType.STICKER
            assert event.media_types == ["image/png"]
            assert [Path(path).read_bytes() for path in event.media_urls] == [PNG]
            assert adapter.device_store().attachment_messages("inst-1") == []

            await adapter.on_processing_start(event)
            saved = adapter.device_store().attachment_messages("inst-1")
            assert saved[0]["turn_id"] == payload["turn_id"]
            assert saved[0]["attachments"] == [
                {"type": "sticker", "mime_type": "image/png", "label": "sticker.png"}
            ]

            await adapter.on_processing_complete(event, ProcessingOutcome.FAILURE)
            assert adapter.device_store().attachment_messages("inst-1") == []
            assert not Path(event.media_urls[0]).exists()
        finally:
            await stop(adapter)


def test_multipart_sticker_mime_mismatch_is_rejected_before_runtime(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            captured = []

            async def capture(event):
                captured.append(event)

            adapter.handle_message = capture
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                status, payload = await post_multipart(
                    port, token, kind="sticker", mime_type="text/plain"
                )
                saved = adapter.device_store().attachment_messages("inst-1")
            finally:
                await stop(adapter)
        return status, payload, captured, saved

    status, payload, captured, saved = run(scenario())
    assert status == 400
    assert payload["error"] == "invalid_attachment"
    assert captured == []
    assert saved == []
