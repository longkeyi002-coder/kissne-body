"""KB1-MOBILE-MULTIMODAL / RED — image + sticker inbound contract.

The existing text-only POST /messages contract remains valid.  Multimodal messages add a bounded
`attachments` array; image bytes must reach Hermes through MessageEvent.media_urls/media_types rather
than being replaced by a generated caption.  Sticker labels are metadata only, never a substitute for
the image itself.
"""

import base64
from pathlib import Path

from gateway.platforms.event import MessageType
from _transport_harness import (
    build_session_store, http, isolated_runtime, make_adapter, pair,
    preexisting_conversation, run, start, stop,
)

# 1x1 transparent PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _attachment(kind="image", data=PNG, label=None):
    item = {
        "type": kind,
        "mime_type": "image/png",
        "data": base64.b64encode(data).decode("ascii"),
    }
    if label is not None:
        item["label"] = label
    return item


def test_image_only_message_reaches_runtime_as_real_media(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            captured = []

            async def capture(event):
                captured.append({
                    "text": event.text,
                    "message_type": event.message_type,
                    "media_types": list(event.media_types),
                    "bytes": [Path(p).read_bytes() for p in event.media_urls],
                    "raw": event.raw_message,
                })

            adapter.handle_message = capture
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                status, payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "img-1", "attachments": [_attachment()]},
                )
            finally:
                await stop(adapter)
        return status, payload, captured

    status, payload, captured = run(scenario())
    assert status == 202, (status, payload)
    assert len(captured) == 1
    event = captured[0]
    assert event["message_type"] == MessageType.PHOTO
    assert event["media_types"] == ["image/png"]
    assert event["bytes"] == [PNG]
    assert event["text"] == ""


def test_sticker_reaches_runtime_as_sticker_media_not_caption(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            captured = []

            async def capture(event):
                captured.append((event.text, event.message_type, list(event.media_types),
                                 [Path(p).read_bytes() for p in event.media_urls]))

            adapter.handle_message = capture
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                status, payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "stk-1",
                          "attachments": [_attachment("sticker", label="开心")]},
                )
            finally:
                await stop(adapter)
        return status, payload, captured

    status, payload, captured = run(scenario())
    assert status == 202, (status, payload)
    assert captured == [("", MessageType.STICKER, ["image/png"], [PNG])]


def test_text_contract_remains_backward_compatible(tmp_path):
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
                status, payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "txt-1", "text": "原来的纯文本仍然能发"},
                )
            finally:
                await stop(adapter)
        return status, payload, captured

    status, payload, captured = run(scenario())
    assert status == 202, (status, payload)
    assert len(captured) == 1
    assert captured[0].text == "原来的纯文本仍然能发"
    assert captured[0].message_type == MessageType.TEXT
    assert captured[0].media_urls == []


def test_attachment_is_part_of_idempotency_payload(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)

            async def capture(_event):
                return None

            adapter.handle_message = capture
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                first, _, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "same-id", "attachments": [_attachment(data=PNG)]},
                )
                retry, retry_payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "same-id", "attachments": [_attachment(data=PNG)]},
                )
                changed, _, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "same-id", "attachments": [_attachment(data=PNG + b"x")]},
                )
            finally:
                await stop(adapter)
        return first, retry, retry_payload, changed

    first, retry, retry_payload, changed = run(scenario())
    assert first == 202
    assert retry == 200 and retry_payload.get("duplicate") is True
    assert changed == 409


def test_bad_attachment_shapes_are_refused(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                cases = [
                    {"attachments": "not-a-list"},
                    {"attachments": [{"type": "video", "mime_type": "image/png", "data": "AA=="}]},
                    {"attachments": [{"type": "image", "mime_type": "text/html", "data": "AA=="}]},
                    {"attachments": [{"type": "image", "mime_type": "image/png", "data": "***"}]},
                ]
                statuses = []
                for i, body in enumerate(cases):
                    body["message_id"] = "bad-%d" % i
                    status, _, _ = await http(port, "POST", "/messages", token=token, body=body)
                    statuses.append(status)
            finally:
                await stop(adapter)
        return statuses

    assert run(scenario()) == [400, 400, 400, 400]


def test_document_reaches_runtime_as_document_media(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            captured = []

            async def capture(event):
                captured.append((event.message_type, list(event.media_types),
                                 [Path(p).read_bytes() for p in event.media_urls]))

            adapter.handle_message = capture
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                data = base64.b64encode(b"hello from kissne").decode("ascii")
                status, payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "doc-1", "attachments": [{
                        "type": "file", "mime_type": "text/plain",
                        "data": data, "label": "note.txt",
                    }]},
                )
            finally:
                await stop(adapter)
        return status, payload, captured

    status, payload, captured = run(scenario())
    assert status == 202, (status, payload)
    assert captured == [(MessageType.DOCUMENT, ["text/plain"], [b"hello from kissne"])]


def test_bootstrap_restores_attachment_presentation_metadata(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                device_store = adapter.device_store()
                device_store.record_attachment_message(
                    "inst-1", "turn-attachment-1", "给你看",
                    [{"type": "image", "mime_type": "image/png", "label": ""}],
                )
                status, payload, _ = await http(
                    port, "POST", "/bootstrap", token=token, body={"cursor": 0},
                )
            finally:
                await stop(adapter)
        return status, payload

    status, payload = run(scenario())
    assert status == 200, (status, payload)
    restored = [row for row in payload["history"]
                if row.get("_turn_id") == "turn-attachment-1"]
    assert len(restored) == 1
    assert restored[0]["text"] == "给你看"
    assert restored[0]["attachments"] == [
        {"type": "image", "mime_type": "image/png", "label": ""}
    ]
    # Presentation persistence must never put the original base64/binary payload into bootstrap.
    assert "data" not in restored[0]["attachments"][0]
