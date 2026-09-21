"""KB1-MOBILE-CHAT-TRANSPORT / RED — the real-device entry contract (Soul §0.3.16 ① ② ⑦).

Frozen by the operator decision of 2026-09-16 (ticket §0.3.16 施工前必须冻结 access path / auth /
exposure / rollback):

* Access path: the adapter binds ``127.0.0.1`` on a FIXED port and the existing nginx vhost
  (``yeqingxu.cyou:443``) reverse-proxies it. The plugin therefore must expose exactly the four
  Android-facing endpoints and nothing else — every other path is a client error, not a feature.
* Exposure surface: ``/pair`` (short-lived single-use code, strictly rate limited), ``/bootstrap``,
  ``/messages`` and ``/cancel`` (all three require a device token).
* ``/health`` stays a loopback liveness probe (nginx must not publish it): it may report liveness only.

RED reason: only ``/pair``, ``/messages``, ``/revoke`` and ``/health`` exist today — ``/bootstrap`` and
``/cancel`` are not implemented, nothing is rate limited, and the auth gate does not cover the new
routes. Assertions fail explicitly; nothing is skipped.
"""

import asyncio

from _transport_harness import (
    http,
    isolated_runtime,
    make_adapter,
    pair,
    preexisting_conversation,
    build_session_store,
    run,
    start,
    stop,
)

FROZEN_CLIENT_PATHS = ("/pair", "/bootstrap", "/messages", "/cancel")
TOKEN_REQUIRED_PATHS = ("/bootstrap", "/messages", "/cancel")
UNKNOWN_PATHS = ("/admin", "/sessions", "/api_server", "/v1/messages", "/events", "/conversations")
KEYISH_FIELDS = ("api_key", "api_server_key", "provider_key", "openai_key", "opencode_key",
                 "runtime_key", "management_key")


def test_every_token_path_refuses_an_unauthenticated_request(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter.set_session_store(build_session_store(home))
            port = await start(adapter)
            try:
                results = {}
                for path in TOKEN_REQUIRED_PATHS:
                    status, payload, _ = await http(port, "POST", path, body={})
                    results[f"POST {path}"] = (status, payload)
                status, payload, _ = await http(port, "GET", "/messages")
                results["GET /messages"] = (status, payload)
            finally:
                await stop(adapter)
        return results

    results = run(scenario())
    offenders = {name: value for name, value in results.items() if value[0] != 401}
    assert not offenders, (
        "every device-token endpoint must answer 401 without a token (no endpoint may be reachable "
        f"unauthenticated): {offenders}")


def test_unknown_paths_are_refused(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter.set_session_store(build_session_store(home))
            port = await start(adapter)
            try:
                found = {}
                for path in UNKNOWN_PATHS:
                    status, _, _ = await http(port, "GET", path)
                    found[path] = status
                    status_post, _, _ = await http(port, "POST", path, body={})
                    found[f"POST {path}"] = status_post
            finally:
                await stop(adapter)
        return found

    found = run(scenario())
    leaked = {path: status for path, status in found.items() if status not in (404, 405)}
    assert not leaked, (
        "the adapter must expose the four client endpoints only; these paths answered something "
        f"else: {leaked}")


def test_health_is_liveness_only(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter.set_session_store(build_session_store(home))
            port = await start(adapter)
            try:
                _, payload, _ = await http(port, "GET", "/health")
            finally:
                await stop(adapter)
        return payload

    payload = run(scenario())
    forbidden = sorted(set(payload) & set(KEYISH_FIELDS))
    assert not forbidden, f"/health leaked a credential-shaped field: {forbidden}"
    leaked_identity = sorted(set(payload) & {"conversation", "conversation_id", "session_id",
                                             "session_key", "history", "devices"})
    assert not leaked_identity, (
        f"/health must stay a liveness probe and not describe a Conversation: {leaked_identity}")


def test_auto_pair_accepts_installation_id_without_pairing_code(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter.set_session_store(build_session_store(home))
            port = await start(adapter)
            try:
                status, payload, _ = await http(
                    port,
                    "POST",
                    "/pair",
                    body={"installation_id": "android-auto-pair"},
                )
            finally:
                await stop(adapter)
        return status, payload

    status, payload = run(scenario())
    assert status == 201, (
        "default mobile pairing must accept installation_id without pairing_code; "
        f"got {status}: {payload}"
    )
    assert payload.get("installation_id") == "android-auto-pair"
    assert str(payload.get("device_token") or "").startswith("kbm1_")
    assert payload.get("conversation_bound") is True


def test_fresh_auto_pair_bootstrap_and_first_message_share_one_conversation(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            adapter.set_session_store(store)
            seen = []

            async def capture(event):
                seen.append(event)

            adapter.set_message_handler(capture)
            port = await start(adapter)
            try:
                pair_status, pair_payload, _ = await http(
                    port, "POST", "/pair",
                    body={"installation_id": "android-fresh-flow"},
                )
                token = str(pair_payload.get("device_token") or "")
                bootstrap_status, bootstrap_payload, _ = await http(
                    port, "POST", "/bootstrap", token=token,
                )
                message_status, message_payload, _ = await http(
                    port, "POST", "/messages", token=token,
                    body={"message_id": "fresh-1", "text": "hello fresh conversation"},
                )
                bound = adapter.bound_conversation("android-fresh-flow")
                session_count = len(store.list_sessions())
            finally:
                await stop(adapter)
        return pair_status, pair_payload, bootstrap_status, bootstrap_payload, message_status, message_payload, bound, session_count, seen

    pair_status, pair_payload, bootstrap_status, bootstrap_payload, message_status, message_payload, bound, session_count, seen = run(scenario())
    assert pair_status == 201, pair_payload
    assert pair_payload.get("conversation_bound") is True, pair_payload
    assert bootstrap_status == 200, bootstrap_payload
    assert bootstrap_payload.get("bound") is True, bootstrap_payload
    conversation = bootstrap_payload.get("conversation") or {}
    assert bound is not None
    assert conversation.get("session_id") == bound.session_id
    assert session_count == 1, "fresh pairing must create exactly one Runtime Conversation"
    assert message_status == 202, message_payload
    assert message_payload.get("turn_id"), message_payload
    assert len(seen) == 1
    assert seen[0].text == "hello fresh conversation"


def test_pairing_never_hands_out_anything_but_a_device_token(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            store = build_session_store(home)
            existing = preexisting_conversation(store)
            adapter.set_session_store(store)
            port = await start(adapter)
            try:
                code = adapter.issue_pairing_code()
                status, payload, _ = await http(port, "POST", "/pair", body={
                    "pairing_code": code, "installation_id": "inst-1",
                    "session_key": existing.session_key,
                })
            finally:
                await stop(adapter)
        return status, payload

    status, payload = run(scenario())
    assert status == 201, f"a valid pairing code must pair, got {status}: {payload}"
    offenders = sorted(set(payload) & set(KEYISH_FIELDS))
    assert not offenders, f"pairing handed out a Runtime/provider credential: {offenders}"
    token = str(payload.get("device_token") or "")
    assert token.startswith("kbm1_"), (
        f"the device credential must be a device-scoped token (kbm1_*), got {token[:12]!r}")


def test_pairing_is_refused_for_every_bad_code_shape(tmp_path):
    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter.set_session_store(build_session_store(home))
            port = await start(adapter)
            try:
                outcomes = {}
                status, _, _ = await http(port, "POST", "/pair",
                                          body={"pairing_code": "not-a-code", "installation_id": "i"})
                outcomes["forged"] = status
                expired = adapter.issue_pairing_code(ttl_seconds=0.05)
                await asyncio.sleep(0.2)
                status, _, _ = await http(port, "POST", "/pair",
                                          body={"pairing_code": expired, "installation_id": "i"})
                outcomes["expired"] = status
                reused = adapter.issue_pairing_code()
                await http(port, "POST", "/pair",
                           body={"pairing_code": reused, "installation_id": "i"})
                status, _, _ = await http(port, "POST", "/pair",
                                          body={"pairing_code": reused, "installation_id": "i"})
                outcomes["replayed"] = status
            finally:
                await stop(adapter)
        return outcomes

    outcomes = run(scenario())
    assert outcomes["forged"] == 400, f"a forged code must be refused with 400, got {outcomes}"
    assert outcomes["expired"] == 410, f"an expired code must be refused with 410, got {outcomes}"
    assert outcomes["replayed"] == 409, f"a replayed code must be refused with 409, got {outcomes}"


def test_pairing_attempts_are_rate_limited(tmp_path):
    """Operator decision: no IP allowlist (mobile networks move), so ``/pair`` must be throttled."""

    async def scenario():
        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter.set_session_store(build_session_store(home))
            port = await start(adapter)
            try:
                statuses = []
                retry_after = None
                for attempt in range(40):
                    status, _, headers = await http(port, "POST", "/pair", body={
                        "pairing_code": f"kbm1_p_bruteforce_{attempt}", "installation_id": "i",
                    })
                    statuses.append(status)
                    if status == 429:
                        retry_after = headers.get("retry-after")
                        break
            finally:
                await stop(adapter)
        return statuses, retry_after

    statuses, retry_after = run(scenario())
    assert 429 in statuses, (
        "40 rapid wrong pairing codes were all accepted: /pair is not rate limited "
        f"(statuses={statuses})")
    assert retry_after, "a 429 from /pair must carry a Retry-After header"
    first_throttle = statuses.index(429)
    assert first_throttle >= 1, (
        "the very first pairing attempt was throttled: the limit must allow normal use")


def test_deployment_routes_require_operator_scoped_token(tmp_path, monkeypatch):
    async def scenario():
        from plugins.platforms.kissne_mobile import admin_api

        with isolated_runtime(tmp_path) as home:
            adapter = make_adapter()
            adapter.set_session_store(build_session_store(home))
            port = await start(adapter)
            try:
                device_status, device_pair, _ = await http(
                    port, "POST", "/pair",
                    body={"installation_id": "ordinary-device"},
                )
                device_token = str(device_pair.get("device_token") or "")
                merge_device = await http(port, "POST", "/admin/merge", token=device_token)
                rollback_device = await http(port, "POST", "/admin/rollback", token=device_token)

                code = adapter.issue_pairing_code()
                admin_status, admin_pair, _ = await http(
                    port, "POST", "/pair",
                    body={"installation_id": "operator-device", "pairing_code": code},
                )
                admin_token = str(admin_pair.get("device_token") or "")
                monkeypatch.setattr(admin_api, "DEPLOY_SCRIPT", tmp_path / "missing-deploy.sh")
                merge_admin = await http(port, "POST", "/admin/merge", token=admin_token)
            finally:
                await stop(adapter)
        return device_status, device_pair, merge_device, rollback_device, admin_status, admin_pair, merge_admin

    device_status, device_pair, merge_device, rollback_device, admin_status, admin_pair, merge_admin = run(scenario())
    assert device_status == 201, device_pair
    assert merge_device[0] == 403 and merge_device[1].get("error") == "admin_scope_required", merge_device
    assert rollback_device[0] == 403 and rollback_device[1].get("error") == "admin_scope_required", rollback_device
    assert admin_status == 201, admin_pair
    assert merge_admin[0] == 404 and merge_admin[1].get("error") == "deploy script not found", merge_admin
