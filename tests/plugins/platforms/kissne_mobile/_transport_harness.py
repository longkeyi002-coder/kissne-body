"""Shared HTTP harness for the ``KB1-MOBILE-CHAT-TRANSPORT`` tests (Soul §0.3.16).

Every transport assertion runs against the adapter's REAL loopback listener, so what is pinned here is
what the Android client will actually see: the route table, the auth gate, status codes and event
shapes. The HTTP layer is never mocked, and no Android/UI code is involved (the ticket forbids it).

Isolation: ``HERMES_HOME`` is redirected per test, so the device registry (plugin data dir) and the
Runtime session store both live inside the test's tmp dir and nothing touches the live Runtime.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ADAPTER_MODULE = "plugins.platforms.kissne_mobile.adapter"
PLATFORM = "kissne_mobile"
OPT_IN_ENV = "KISSNE_MOBILE_ENABLED"
#: The installation id every test pairs by default (per-device identity, not a Conversation).
PAIRED_INSTALLATION = "inst-1"

Status = int
Payload = Dict[str, Any]


@contextmanager
def isolated_runtime(tmp_path, *, opt_in: bool = True):
    """Point ``HERMES_HOME`` (and the platform opt-in) at this test's tmp dir."""
    home = Path(tmp_path) / "hermes-home"
    home.mkdir(parents=True, exist_ok=True)
    saved = {key: os.environ.get(key) for key in ("HERMES_HOME", OPT_IN_ENV)}
    os.environ["HERMES_HOME"] = str(home)
    if opt_in:
        os.environ[OPT_IN_ENV] = "1"
    else:
        os.environ.pop(OPT_IN_ENV, None)
    try:
        yield home
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# ── Runtime side (SessionStore is the Conversation truth; the plugin must not copy it) ──────────────

def build_session_store(home):
    from gateway.config import GatewayConfig
    from gateway.session import SessionStore

    return SessionStore(Path(home) / "runtime-sessions", GatewayConfig())


def preexisting_conversation(store, *, chat_id: str = "existing-chat", user_id: str = "user-existing"):
    """A Conversation that already exists in the Runtime, created through the normal public path."""
    from gateway.config import Platform
    from gateway.session import SessionSource

    source = SessionSource(platform=Platform.TELEGRAM, chat_id=chat_id, chat_type="dm", user_id=user_id)
    return store.get_or_create_session(source)


def seed_transcript(store, session_id: str, turns: int) -> None:
    """Write ``turns`` user/assistant pairs through the public transcript API."""
    for index in range(turns):
        store.append_to_transcript(session_id, {"role": "user", "content": f"seeded question {index}"})
        store.append_to_transcript(session_id, {"role": "assistant", "content": f"seeded answer {index}"})


# ── Adapter side ────────────────────────────────────────────────────────────────────────────────────

def adapter_module():
    return importlib.import_module(ADAPTER_MODULE)


def make_adapter(*, host: str = "127.0.0.1", port: int = 0, **extra):
    """A fresh adapter over the isolated home — a second call is the "Runtime restarted" case."""
    module = adapter_module()
    from gateway.config import Platform, PlatformConfig

    config = PlatformConfig(enabled=True, extra={"host": host, "port": port, **extra})
    return module.KissneMobileAdapter(config, Platform(PLATFORM))


async def start(adapter) -> int:
    """Bind the real listener and return the port the OS gave us."""
    started = await adapter.connect()
    assert started, "the mobile adapter refused to bind its loopback listener"
    port = getattr(adapter, "bound_port", None)
    assert isinstance(port, int) and port > 0, f"adapter.bound_port must be a real port, got {port!r}"
    return port


async def stop(adapter) -> None:
    try:
        await adapter.disconnect()
    finally:
        close = getattr(getattr(adapter, "_store", None), "close", None)
        if callable(close):  # already closed by disconnect(); keep the harness forgiving
            close()


async def http(port: int, method: str, path: str, *, token: Optional[str] = None,
               body: Any = None, timeout: float = 10.0) -> Tuple[Status, Payload, Dict[str, str]]:
    """One request against the adapter's listener; returns ``(status, json_payload, headers)``."""
    import aiohttp

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    kwargs: Dict[str, Any] = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.request(method, f"http://127.0.0.1:{port}{path}", **kwargs) as response:
            raw = await response.text()
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"_raw": raw}
            return response.status, payload, {k.lower(): v for k, v in response.headers.items()}


async def pair(port: int, adapter, *, installation_id: str = PAIRED_INSTALLATION, conversation=None,
               ttl: Optional[float] = None) -> str:
    """Operator mints a code, device redeems it over HTTP; returns the device token."""
    code = adapter.issue_pairing_code() if ttl is None else adapter.issue_pairing_code(ttl)
    body: Dict[str, Any] = {"pairing_code": code, "installation_id": installation_id}
    if conversation is not None:
        body["session_key"] = conversation.session_key
    status, payload, _ = await http(port, "POST", "/pair", body=body)
    assert status == 201, f"pairing must succeed, got {status}: {payload}"
    assert payload.get("device_token"), f"pairing must return a device token: {payload}"
    return str(payload["device_token"])


def event_types(events) -> list:
    return [str(item.get("type")) for item in events or []]


def run(coro, *, timeout: float = 90.0):
    """Drive one async scenario; a hung scenario fails the test instead of the whole session."""
    return asyncio.run(asyncio.wait_for(coro, timeout=timeout))
