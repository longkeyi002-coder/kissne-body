"""KB1-MOBILE-CHAT-TRANSPORT / RED — retry idempotency on the client ``message_id`` (§0.3.16 ④).

Contract frozen here:

* ``POST /messages`` accepts a client-supplied ``message_id``. The same ``message_id`` with the same
  payload is a RETRY: it must not produce a second turn — the Runtime sees exactly one inbound event,
  and the answer repeats the original ``turn_id`` with ``duplicate=true``.
* The same ``message_id`` with a DIFFERENT payload fails closed (409 ``message_id_conflict``): a client
  must never be able to rewrite an already-accepted turn by retrying.
* The idempotency record is durable, so a retry after the Runtime restarted is still a retry.
* The response carries a ``turn_id`` — the correlation handle used by stream/cancel events.

RED reason: today ``message_id`` is only copied into the inbound event and never checked, so every
retry injects a second turn. Nothing is skipped.
"""

import asyncio

from _transport_harness import (
    build_session_store,
    http,
    isolated_runtime,
    make_adapter,
    pair,
    preexisting_conversation,
    run,
    start,
    stop,
)


class Recorder:
    """Stands in for ``BasePlatformAdapter.handle_message`` — counts the turns the Runtime sees."""

    def __init__(self):
        self.events = []

    async def __call__(self, event):
        self.events.append(event)

    @property
    def count(self):
        return len(self.events)


async def _post_inbound(port, token, text, message_id):
    return await http(port, "POST", "/messages", token=token,
                      body={"text": text, "message_id": message_id})


def test_a_retry_of_the_same_message_id_injects_exactly_one_turn(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            recorder = Recorder()
            adapter.set_message_handler(recorder)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                first = await _post_inbound(port, token, "hello runtime", "m-1")
                retry = await _post_inbound(port, token, "hello runtime", "m-1")
                other = await _post_inbound(port, token, "hello runtime", "m-2")
            finally:
                await stop(adapter)
        return first, retry, other, recorder

    first, retry, other, recorder = run(scenario())
    status, payload, _ = first
    assert status == 202, f"a first inbound must be accepted with 202, got {status}: {payload}"
    turn_id = payload.get("turn_id")
    assert turn_id, f"the accept response must carry the turn correlation handle: {payload}"

    status, retry_payload, _ = retry
    assert status == 200, (
        f"a retry of the same message_id must be recognised (200 + duplicate), got {status}: {retry_payload}")
    assert retry_payload.get("duplicate") is True, (
        f"a retry must be flagged as a duplicate: {retry_payload}")
    assert retry_payload.get("turn_id") == turn_id, (
        "a retry must repeat the ORIGINAL turn id, not mint a new one: "
        f"{retry_payload.get('turn_id')} vs {turn_id}")

    assert other[0] == 202, f"a new message_id must open a new turn, got {other[0]}: {other[1]}"
    assert other[1].get("turn_id") != turn_id, "a new message_id reused the previous turn id"

    assert recorder.count == 2, (
        "the Runtime saw %d inbound turns for 3 requests (1 retry + 2 distinct messages); "
        "a retried message_id must not inject a second turn" % recorder.count)


def test_the_same_message_id_with_a_different_payload_fails_closed(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            recorder = Recorder()
            adapter.set_message_handler(recorder)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                await _post_inbound(port, token, "original text", "m-9")
                status, payload, _ = await _post_inbound(port, token, "REWRITTEN text", "m-9")
            finally:
                await stop(adapter)
        return status, payload, recorder

    status, payload, recorder = run(scenario())
    assert status == 409, (
        f"reusing a message_id with a different payload must fail closed (409), got {status}: {payload}")
    assert payload.get("error") == "message_id_conflict", (
        f"the conflict must be named explicitly: {payload}")
    assert recorder.count == 1, (
        "a conflicting retry rewrote/injected a turn: the Runtime saw %d turns" % recorder.count)


def test_idempotency_survives_a_runtime_restart(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            store = build_session_store(home)
            existing = preexisting_conversation(store)

            adapter = make_adapter()
            adapter.set_session_store(store)
            first_recorder = Recorder()
            adapter.set_message_handler(first_recorder)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                await _post_inbound(port, token, "survives a restart", "m-restart")
            finally:
                await stop(adapter)

            restarted = make_adapter()
            restarted.set_session_store(build_session_store(home))
            second_recorder = Recorder()
            restarted.set_message_handler(second_recorder)
            port = await start(restarted)
            try:
                status, payload, _ = await _post_inbound(port, token, "survives a restart", "m-restart")
            finally:
                await stop(restarted)
        return status, payload, second_recorder

    status, payload, recorder = run(scenario())
    assert status == 200 and payload.get("duplicate") is True, (
        f"after a Runtime restart the retry must still be a duplicate, got {status}: {payload}")
    assert recorder.count == 0, (
        "the retried message was injected as a fresh turn after the restart: the idempotency record "
        "is not durable")


def test_an_unknown_installation_cannot_reuse_anothers_message_id(tmp_path):
    """Idempotency is per installation: one device must not collide with (or probe) another's ids."""

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            recorder = Recorder()
            adapter.set_message_handler(recorder)
            port = await start(adapter)
            try:
                token_a = await pair(port, adapter, installation_id="inst-a", conversation=existing)
                token_b = await pair(port, adapter, installation_id="inst-b", conversation=existing)
                await _post_inbound(port, token_a, "from A", "shared-id")
                status, payload, _ = await _post_inbound(port, token_b, "from B", "shared-id")
            finally:
                await stop(adapter)
        return status, payload, recorder

    status, payload, recorder = run(scenario())
    assert status == 202, (
        "another installation's message_id must not be treated as this device's retry: "
        f"got {status}: {payload}")
    assert recorder.count == 2, (
        "the second installation's message was swallowed as a duplicate of the first "
        f"(%d turns for 2 devices)" % recorder.count)


def test_real_photo_upload_reaches_runtime_as_media(tmp_path):
    async def post_media(port, token, *, message_id, content=b"image-bytes"):
        import aiohttp

        form = aiohttp.FormData()
        form.add_field("message_id", message_id)
        form.add_field("kind", "photo")
        form.add_field("file_name", "羊羊照片.png")
        form.add_field("mime_type", "image/png")
        form.add_field(
            "file",
            content,
            filename="upload.bin",
            content_type="image/png",
        )
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://127.0.0.1:{port}/messages",
                data=form,
                headers=headers,
            ) as response:
                return response.status, await response.json()

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            recorder = Recorder()
            adapter.set_message_handler(recorder)
            port = await start(adapter)
            try:
                token = await pair(port, adapter, conversation=existing)
                first = await post_media(port, token, message_id="media-1")
                retry = await post_media(port, token, message_id="media-1")
            finally:
                await stop(adapter)
        return first, retry, recorder

    first, retry, recorder = run(scenario())
    assert first[0] == 202, first
    assert retry[0] == 200 and retry[1].get("duplicate") is True, retry
    assert recorder.count == 1
    event = recorder.events[0]
    assert event.message_type.value == "photo"
    assert event.media_types == ["image/png"]
    assert len(event.media_urls) == 1
    from pathlib import Path
    path = Path(event.media_urls[0])
    assert path.exists() and path.read_bytes() == b"image-bytes"
    assert event.text == "[照片：羊羊照片.png]"
