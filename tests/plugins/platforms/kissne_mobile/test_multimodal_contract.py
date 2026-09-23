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


def test_cancelled_attachment_turn_is_not_restored_by_bootstrap(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)

            async def accepted(event):
                event._gateway_accepted = True

            adapter.handle_message = accepted
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                sent, sent_payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "cancel-media-1", "attachments": [_attachment()]},
                )
                turn_id = sent_payload["turn_id"]
                cancelled, _, _ = await http(
                    port, "POST", "/cancel", token=token, body={"turn_id": turn_id},
                )
                boot_status, boot, _ = await http(
                    port, "POST", "/bootstrap", token=token, body={"cursor": 0},
                )
            finally:
                await stop(adapter)
        return sent, cancelled, boot_status, turn_id, boot

    sent, cancelled, boot_status, turn_id, boot = run(scenario())
    assert sent == 202
    assert cancelled == 200
    assert boot_status == 200
    assert all(row.get("_turn_id") != turn_id for row in boot["history"])


def test_attachment_retry_does_not_inject_or_materialize_twice(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            injected = []
            materialized = []
            original = adapter._materialize_attachments

            def track(items):
                materialized.append(1)
                return original(items)

            async def accepted(event):
                injected.append(event.message_id)
                event._gateway_accepted = False

            adapter._materialize_attachments = track
            adapter.handle_message = accepted
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                body = {"message_id": "retry-media-1", "attachments": [_attachment()]}
                first, first_payload, _ = await http(port, "POST", "/messages", token=token, body=body)
                retry, retry_payload, _ = await http(port, "POST", "/messages", token=token, body=body)
            finally:
                await stop(adapter)
        return first, first_payload, retry, retry_payload, injected, materialized

    first, first_payload, retry, retry_payload, injected, materialized = run(scenario())
    assert first == 202
    assert retry == 200 and retry_payload.get("duplicate") is True
    assert retry_payload["turn_id"] == first_payload["turn_id"]
    assert len(injected) == 1
    assert len(materialized) == 1


def test_admitted_attachment_is_not_persisted_until_runtime_starts(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            captured = []

            async def admitted_only(event):
                event._gateway_accepted = True
                captured.append(event)

            adapter.handle_message = admitted_only
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                status, payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "queued-media-1", "attachments": [_attachment()]},
                )
                before = adapter.device_store().attachment_messages("inst-1")
                assert captured and getattr(captured[0], "_kissne_attachment_metadata", None)
                await adapter.on_processing_start(captured[0])
                after = adapter.device_store().attachment_messages("inst-1")
            finally:
                adapter._cleanup_inbound_media(captured[0]) if captured else None
                await stop(adapter)
        return status, payload, before, after

    status, payload, before, after = run(scenario())
    assert status == 202, (status, payload)
    assert before == []
    assert len(after) == 1
    assert after[0]["turn_id"] == payload["turn_id"]


def test_approval_endpoint_rejects_forged_id(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                return await http(port, "POST", "/approval", token=token,
                                  body={"approval_id": "forged", "decision": "allow", "scope": "once"})
            finally:
                await stop(adapter)
    status, payload, _ = run(scenario())
    assert status == 404
    assert payload["error"] == "unknown_approval"


def test_approval_endpoint_resolves_exact_live_request_and_duplicate_fails(tmp_path):
    async def scenario():
        from tools import approval
        from tools.approval_gateway_wait import _ApprovalEntry
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                key = adapter.mobile_session_key("inst-1")
                entry = _ApprovalEntry({"request_id": "approval-1", "command": "echo ok",
                                        "description": "test", "allow_session": True,
                                        "allow_permanent": False})
                with approval._lock:
                    approval._gateway_queues[key] = [entry]
                first = await http(port, "POST", "/approval", token=token,
                                   body={"approval_id": "approval-1", "decision": "allow",
                                         "scope": "session"})
                second = await http(port, "POST", "/approval", token=token,
                                    body={"approval_id": "approval-1", "decision": "allow",
                                          "scope": "session"})
                return first, second, entry.result
            finally:
                with approval._lock:
                    approval._gateway_queues.pop(adapter.mobile_session_key("inst-1"), None)
                await stop(adapter)
    first, second, result = run(scenario())
    assert first[0] == 200
    assert first[1]["status"] == "approved"
    assert result == "session"
    assert second[0] == 404


def test_approval_endpoint_enforces_scope_capability(tmp_path):
    async def scenario():
        from tools import approval
        from tools.approval_gateway_wait import _ApprovalEntry
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                key = adapter.mobile_session_key("inst-1")
                entry = _ApprovalEntry({"request_id": "approval-scope", "command": "echo ok",
                                        "description": "test", "allow_session": True,
                                        "allow_permanent": False})
                with approval._lock:
                    approval._gateway_queues[key] = [entry]
                response = await http(port, "POST", "/approval", token=token,
                                      body={"approval_id": "approval-scope", "decision": "allow",
                                            "scope": "always"})
                return response, entry.result
            finally:
                with approval._lock:
                    approval._gateway_queues.pop(adapter.mobile_session_key("inst-1"), None)
                await stop(adapter)
    response, result = run(scenario())
    assert response[0] == 409
    assert response[1]["error"] == "approval_scope_not_allowed"
    assert result is None


def test_multiple_approvals_resolve_by_exact_id(tmp_path):
    async def scenario():
        from tools import approval
        from tools.approval_gateway_wait import _ApprovalEntry
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            conversation = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=conversation)
                key = adapter.mobile_session_key("inst-1")
                first = _ApprovalEntry({"request_id": "approval-a", "command": "a",
                                        "description": "a", "allow_session": True})
                second = _ApprovalEntry({"request_id": "approval-b", "command": "b",
                                         "description": "b", "allow_session": True})
                with approval._lock:
                    approval._gateway_queues[key] = [first, second]
                response = await http(port, "POST", "/approval", token=token,
                                      body={"approval_id": "approval-b", "decision": "deny",
                                            "reason": "not now"})
                remaining = approval.list_gateway_approvals(key)
                return response, first.result, second.result, second.reason, remaining
            finally:
                with approval._lock:
                    approval._gateway_queues.pop(adapter.mobile_session_key("inst-1"), None)
                await stop(adapter)
    response, first_result, second_result, reason, remaining = run(scenario())
    assert response[0] == 200
    assert first_result is None
    assert second_result == "deny"
    assert reason == "not now"
    assert [item["request_id"] for item in remaining] == ["approval-a"]


def test_post_approval_timeout_carries_exact_request_id(monkeypatch):
    import tools.approval_gateway_wait as waitmod
    observed = []

    monkeypatch.setattr(waitmod, "_poll_event", lambda *args, **kwargs: "timeout")
    monkeypatch.setattr(waitmod._ctx, "_fire_approval_hook",
                        lambda hook, **kwargs: observed.append((hook, kwargs)))
    result = waitmod._await_gateway_decision(
        "kissne_mobile:dm:inst-timeout", {"request_id": "approval-timeout-a",
        "command": "danger", "description": "test"}, timeout=0.01)
    posts = [payload for hook, payload in observed if hook == "post_approval_response"]
    assert posts
    assert posts[-1]["choice"] == "timeout"
    assert posts[-1]["request_id"] == "approval-timeout-a"


def test_timeout_identity_does_not_alias_concurrent_approval(monkeypatch):
    import tools.approval_gateway_wait as waitmod
    observed = []

    monkeypatch.setattr(waitmod, "_poll_event", lambda *args, **kwargs: "timeout")
    monkeypatch.setattr(waitmod, "_fire_approval_hook",
                        lambda hook, **kwargs: observed.append((hook, kwargs)))
    for request_id in ("approval-a", "approval-b"):
        waitmod._await_gateway_decision(
            "kissne_mobile:dm:inst-concurrent",
            {"request_id": request_id, "command": request_id, "description": "test"},
            timeout=0.01)
    posts = [payload for hook, payload in observed if hook == "post_approval_response"]
    assert [item["request_id"] for item in posts] == ["approval-a", "approval-b"]
    assert all(item["choice"] == "timeout" for item in posts)
