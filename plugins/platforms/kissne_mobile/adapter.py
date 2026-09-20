"""Kissne Mobile (Android) platform adapter — Runtime side of the KB1-MOBILE-ADAPTER ticket.

One Android installation talks to the SAME Hermes Runtime and the SAME Runtime Conversation as every
other channel. The adapter owns a loopback HTTP listener so the plugin needs no core change:

``POST /pair``
    An installation exchanges a **short-lived, single-use pairing code** for a device-scoped token.
    Reachability alone never registers anything, and the only thing handed to the device is that
    token — never a Runtime management key, never a provider key.

``POST /bootstrap``
    Device token in, "which Runtime Conversation am I on" out: the joined Conversation's identity plus a
    **bounded tail** of its history, so a fresh app launch shows the current chat instead of an empty
    new one. Read straight from the Runtime session store on every call; it never creates anything, and
    an installation that has joined nothing gets ``bound=false``.

``POST /messages``
    A paired device posts text, authenticated with its device token. The adapter turns it into a
    :class:`~gateway.platforms.event.MessageEvent` through ``build_source`` and hands it to
    ``await self.handle_message(event)`` — the same inbound path every other adapter uses. A client
    ``message_id`` makes the call idempotent (a retry never injects a second turn; a retry that rewrites
    the payload is refused with 409), and the reply carries the ``turn_id`` the device correlates
    stream/cancel events with. The same endpoint also takes ``{"ack": {"cursor": N}}`` to retire
    delivered replies.

``GET /messages?cursor=N``
    The device reads the replies this Runtime queued for it: typed, sequence-numbered events
    (``pending`` / ``delta`` / ``completed`` / ``cancelled``) newer than ``N``. Reading is
    **non-destructive** — a poll whose response never arrives loses nothing — and every event carries
    the ``turn_id`` it belongs to.

``POST /cancel``
    ``{"turn_id": T}`` interrupts that turn's Runtime activity and answers with the resulting state, so
    the device never has to infer "did my cancel land?" from silence.

``POST /revoke``
    The device kills its own token immediately; the row is committed, so it stays dead across restarts.

``GET /health``
    Liveness only (the reverse proxy must not publish it).

Conversation truth is NOT owned here. The Mobile routing source is derived from ``installation_id``
and pointed at an **already existing** Runtime Conversation through the public ``SessionStore`` API
(``bind_source_to_existing_session`` — an alias-only routing write that creates no session row, ends
nothing and reopens nothing, both persisted by the store itself); this module
keeps no installation→conversation table of its own, and the adapter holds no Agent / Memory /
Provider truth. Mobile inbound that is not bound to an existing conversation is refused instead of
silently opening a second, mobile-only Conversation.

Out of scope for this ticket: the Android client itself (``KB1-ANDROID-CHAT``).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import os
import tempfile
import importlib.util
import json
import logging
import secrets
import sys
import time
from collections import deque
from pathlib import Path as _Path
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # typing only — the module is imported lazily where it is actually needed
    from aiohttp import web

sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))

from gateway.config import Platform, PlatformConfig
from gateway.platforms._shared import coerce_port, get_scoped_secret
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.platforms.event import MessageEvent, MessageType
from gateway.session import build_session_key

from .device_store import (
    DEFAULT_PAIRING_TTL_SECONDS,
    EVENT_CANCELLED,
    EVENT_APPROVAL_REQUIRED,
    EVENT_APPROVAL_RESOLVED,
    EVENT_COMPLETED,
    EVENT_DELTA,
    EVENT_PENDING,
    INBOUND_CONFLICT,
    INBOUND_DUPLICATE,
    DeviceStore,
    PairingCodeExpired,
    PairingCodeInvalid,
    PairingCodeReplayed,
    PairingError,
    TURN_CANCELLED,
    TURN_COMPLETED,
    TURN_PENDING,
)

logger = logging.getLogger(__name__)

PLATFORM_NAME = "kissne_mobile"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0  # ephemeral by default: the Android side is told the port it must reach
DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENTS = 4
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/zip",
}
ALLOWED_ATTACHMENT_MIME_TYPES = ALLOWED_IMAGE_MIME_TYPES | ALLOWED_DOCUMENT_MIME_TYPES
DEFAULT_OUTBOUND_QUEUE_CAP = 200

# This platform has NO external credential, so enablement needs an explicit per-profile opt-in:
# either ``platforms.kissne_mobile.enabled: true`` in that profile's config.yaml or this flag in
# that profile's own ``.env``. See ``_is_connected`` for why the opt-in must never be read from
# ``PlatformConfig.enabled``.
OPT_IN_ENV = "KISSNE_MOBILE_ENABLED"

PAIRING_PATH = "/pair"
BOOTSTRAP_PATH = "/bootstrap"
MESSAGES_PATH = "/messages"
CANCEL_PATH = "/cancel"
REVOKE_PATH = "/revoke"
HEALTH_PATH = "/health"

#: How many history messages a fresh app launch may ask for (§0.3.16: bootstrap returns a BOUNDED tail).
DEFAULT_HISTORY_CAP = 50
#: How many events one poll may return; the device acks and polls again for the rest.
DEFAULT_READ_LIMIT = 200
#: Pairing throttle. The exposure decision dropped IP allowlisting (mobile networks move), so ``/pair``
#: is rate limited instead: this many attempts per client address per window, then 429 + Retry-After.
PAIR_ATTEMPT_LIMIT = 10
PAIR_ATTEMPT_WINDOW_SECONDS = 60.0


def _fingerprint(value: str) -> str:
    """Short non-secret label for log lines (installation ids are identities, not credentials)."""
    text = str(value or "")
    return text if len(text) <= 24 else f"{text[:12]}…"


def _json_response(payload: Dict[str, Any], status: int = 200) -> web.Response:
    from aiohttp import web

    return web.json_response(payload, status=status)


def _error_response(error: str, status: int) -> web.Response:
    return _json_response({"ok": False, "error": error}, status=status)


class KissneMobileAdapter(BasePlatformAdapter):
    """Loopback HTTP adapter for paired Android installations."""

    supports_code_blocks = True
    typed_command_prefix = "/"

    def __init__(self, config: PlatformConfig, platform: Optional[Platform] = None) -> None:
        super().__init__(config, platform or Platform(PLATFORM_NAME))
        extra = config.extra or {}
        self._host: str = str(extra.get("host", DEFAULT_HOST) or DEFAULT_HOST)
        self._port: int = coerce_port(extra.get("port", DEFAULT_PORT), DEFAULT_PORT)
        self._max_body_bytes: int = coerce_port(
            extra.get("max_body_bytes", DEFAULT_MAX_BODY_BYTES), DEFAULT_MAX_BODY_BYTES)
        self._outbound_cap: int = coerce_port(
            extra.get("outbound_queue_cap", DEFAULT_OUTBOUND_QUEUE_CAP), DEFAULT_OUTBOUND_QUEUE_CAP)
        self._history_cap: int = coerce_port(
            extra.get("history_cap", DEFAULT_HISTORY_CAP), DEFAULT_HISTORY_CAP)
        self._read_limit: int = coerce_port(
            extra.get("read_limit", DEFAULT_READ_LIMIT), DEFAULT_READ_LIMIT)
        self._pair_attempt_limit: int = coerce_port(
            extra.get("pair_attempt_limit", PAIR_ATTEMPT_LIMIT), PAIR_ATTEMPT_LIMIT)
        self._runner: Any = None
        self._store: Optional[DeviceStore] = None
        # Transport only, and only for the throttle: recent pairing attempts per client address. Queued
        # replies are NOT kept in memory — they are rows (see ``device_store``), so a restart loses none.
        self._pair_attempts: Dict[str, Deque[float]] = {}
        self.bound_port: Optional[int] = None

    # -- device credentials (delegated to the plugin's own persistent layer) -----------------------

    def device_store(self) -> DeviceStore:
        """The plugin's persistent device registry, opened on first use."""
        if self._store is None:
            self._store = DeviceStore()
        return self._store

    def issue_pairing_code(self, ttl_seconds: float = DEFAULT_PAIRING_TTL_SECONDS) -> str:
        """Mint a one-time registration secret for an operator to hand to a device out of band.

        The code is single-use and short-lived, and is deliberately NOT logged: whoever holds it can
        pair one installation.
        """
        return self.device_store().issue_pairing_code(ttl_seconds=ttl_seconds)

    # -- Runtime Conversation (routing through the existing SessionStore only) ---------------------

    def source_for_installation(self, installation_id: str) -> Any:
        """The Mobile routing source for one installation.

        ``installation_id`` is a stable SOURCE identity (no IMEI / advertising id / phone number /
        hardware serial) and is the only input: the same installation always derives the same
        routing key.
        """
        installation = str(installation_id or "").strip()
        if not installation:
            raise ValueError("installation_id is required")
        return self.build_source(
            chat_id=installation,
            chat_name=f"Kissne Mobile ({_fingerprint(installation)})",
            chat_type="dm",
            user_id=installation,
        )

    @staticmethod
    def _profile_for_key(store: Any, source: Any) -> Optional[str]:
        """Mirror of the store's profile namespace resolution for key derivation."""
        if not getattr(getattr(store, "config", None), "multiplex_profiles", False):
            return None
        if getattr(source, "profile", None):
            return str(source.profile)
        return None

    def mobile_session_key(self, installation_id: str) -> str:
        """The routing key this installation maps to (derived — never stored by the plugin)."""
        store = getattr(self, "_session_store", None)
        source = self.source_for_installation(installation_id)
        config = getattr(store, "config", None)
        return build_session_key(
            source,
            group_sessions_per_user=bool(getattr(config, "group_sessions_per_user", True)),
            thread_sessions_per_user=bool(getattr(config, "thread_sessions_per_user", False)),
            profile=self._profile_for_key(store, source),
        )

    def bound_conversation(self, installation_id: str) -> Optional[Any]:
        """This installation's routing entry when it already points at a conversation, else None.

        Read-only: a miss means the installation has never been bound, and the caller must refuse
        rather than let the store open a mobile-only conversation.
        """
        store = getattr(self, "_session_store", None)
        if store is None:
            return None
        try:
            return store.lookup_by_session_key(self.mobile_session_key(installation_id))
        except Exception:
            logger.warning("[kissne_mobile] could not read the routing entry for installation %s",
                           _fingerprint(installation_id), exc_info=True)
            return None

    def bind_conversation(self, installation_id: str, session_key: str) -> bool:
        """Point this installation's routing key at an ALREADY EXISTING Runtime Conversation.

        Uses only public ``SessionStore`` API.  When the routing key is already bound to
        the *same* session, this is a no-op that returns ``True``.  When it points at a
        *different* session, ``switch_session`` re-targets the alias so that a stale
        client-sent ``session_key`` does not hard-fail the message.
        """
        store = getattr(self, "_session_store", None)
        installation = str(installation_id or "").strip()
        target_key = str(session_key or "").strip()
        if store is None:
            logger.warning("[kissne_mobile] cannot bind installation %s: no session store attached",
                           _fingerprint(installation))
            return False
        if not installation or not target_key:
            return False
        target = store.lookup_by_session_key(target_key)
        if target is None:
            logger.warning("[kissne_mobile] refusing to bind installation %s: conversation %s does not exist",
                           _fingerprint(installation), target_key)
            return False

        source = self.source_for_installation(installation)

        # Already bound to the same session → nothing to do.
        current = store.peek_session_id(self.mobile_session_key(installation))
        if current == target.session_id:
            return True

        # Currently unbound → fresh bind.
        if current is None:
            try:
                entry = store.bind_source_to_existing_session(source, target.session_id)
            except Exception:
                logger.warning("[kissne_mobile] failed to bind installation %s to %s",
                               _fingerprint(installation), target_key, exc_info=True)
                return False
            if entry is None or entry.session_id != target.session_id:
                logger.warning("[kissne_mobile] installation %s did not resolve to the target conversation",
                               _fingerprint(installation))
                return False
            logger.info("[kissne_mobile] installation %s joined the existing conversation on key %s",
                        _fingerprint(installation), target_key)
            return True

        # Already bound elsewhere → re-point via switch_session.
        try:
            entry = store.switch_session(self.mobile_session_key(installation), target.session_id)
        except Exception:
            logger.warning("[kissne_mobile] failed to switch installation %s to %s",
                           _fingerprint(installation), target_key, exc_info=True)
            return False
        if entry is None or entry.session_id != target.session_id:
            logger.warning("[kissne_mobile] installation %s switch did not resolve to target",
                           _fingerprint(installation))
            return False
        logger.info("[kissne_mobile] installation %s re-pointed to conversation on key %s",
                    _fingerprint(installation), target_key)
        return True

    # -- listener lifecycle ------------------------------------------------------------------------

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Bind the loopback listener and start accepting paired devices."""
        if not check_kissne_mobile_requirements():
            logger.error("[kissne_mobile] aiohttp is unavailable; cannot serve paired devices")
            return False
        from aiohttp import web

        if self._runner is not None:
            logger.debug("[kissne_mobile] connect() while already listening; keeping the current listener")
            return True
        # client_max_size makes aiohttp enforce the cap on every read path, including chunked
        # bodies with no Content-Length.
        app = web.Application(client_max_size=self._max_body_bytes)
        app.router.add_post(PAIRING_PATH, self._handle_pair)
        app.router.add_post(BOOTSTRAP_PATH, self._handle_bootstrap)
        app.router.add_post(MESSAGES_PATH, self._handle_inbound)
        app.router.add_get(MESSAGES_PATH, self._handle_outbound)
        app.router.add_post(CANCEL_PATH, self._handle_cancel)
        app.router.add_post("/approval", self._handle_approval)
        app.router.add_post(REVOKE_PATH, self._handle_revoke)
        app.router.add_get(HEALTH_PATH, self._handle_health)
        # Plugin-registered routes must be wired before ``AppRunner.setup()`` freezes the router
        # (same lifecycle point as ``plugins/platforms/line/adapter.py``). The aiohttp application
        # is this platform's native client, so that is what handler factories receive.
        self._wire_plugin_handlers(app)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        try:
            await site.start()
        except Exception:
            await runner.cleanup()
            logger.exception("[kissne_mobile] failed to bind %s:%s", self._host, self._port)
            return False
        self._runner = runner
        self.bound_port = self._bound_port(site)
        self._mark_connected(listener_base=f"http://{self._host}:{self.bound_port}")
        logger.info("[kissne_mobile] device listener on http://%s:%d (%s, %s)",
                    self._host, self.bound_port, PAIRING_PATH, MESSAGES_PATH)
        return True

    def _bound_port(self, site: Any) -> int:
        """The port the OS actually gave us (``port: 0`` asks for an ephemeral one)."""
        server = getattr(site, "_server", None)
        for sock in (getattr(server, "sockets", None) or ()):
            try:
                return int(sock.getsockname()[1])
            except Exception:  # pragma: no cover - defensive
                continue
        return self._port

    async def disconnect(self) -> None:
        """Stop accepting devices and release the credential handle.

        Queued replies are rows, not process memory, so they are deliberately NOT dropped here: a
        restart re-delivers whatever the device has not acknowledged yet.
        """
        runner, self._runner = self._runner, None
        self.bound_port = None
        if runner is not None:
            try:
                await runner.cleanup()
            except Exception:
                logger.warning("[kissne_mobile] error while stopping the device listener", exc_info=True)
        store, self._store = self._store, None
        if store is not None:
            await asyncio.to_thread(store.close)
        self._pair_attempts.clear()
        self._mark_disconnected()
        logger.info("[kissne_mobile] disconnected")

    # -- outbound ----------------------------------------------------------------------------------

    async def _queue_event(self, installation_id: str, event_type: str, *,
                           content: Optional[str] = None, reply_to: Optional[str] = None,
                           extra: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Append one typed event to the installation's durable stream; returns its transport message id.

        The row is committed *before* the device is told anything, so nothing between "reply produced"
        and "reply delivered" can lose it — not a dropped poll, not a Runtime restart. ``None`` means
        there was no target installation at all (a caller mistake the Runtime must see as a failed send).
        ``metadata`` is deliberately never echoed to the device: it carries Runtime-side routing.
        """
        installation = str(installation_id or "").strip()
        if not installation:
            return None
        message_id = f"kbm_out_{secrets.token_hex(8)}"
        payload: Dict[str, Any] = {"message_id": message_id}
        if content is not None:
            payload["text"] = self.format_message(content)
        if reply_to:
            payload["reply_to"] = reply_to
        if extra:
            payload.update(extra)
        try:
            store = self.device_store()
        except Exception:
            logger.error("[kissne_mobile] device store unavailable; cannot queue outbound", exc_info=True)
            return None
        turn_id = await asyncio.to_thread(store.pending_turn_id, installation)
        try:
            seq = await asyncio.to_thread(
                store.enqueue_event, installation, event_type, payload, turn_id,
                cap=max(1, self._outbound_cap),
            )
            if event_type == EVENT_COMPLETED and turn_id:
                # The reply closes the turn it answers — but only from ``pending``: a late reply must not
                # resurrect a turn the user already cancelled.
                await asyncio.to_thread(store.close_turn, turn_id, TURN_COMPLETED)
        except Exception:
            logger.exception("[kissne_mobile] failed to queue %s event for installation %s",
                             event_type, _fingerprint(installation))
            return None
        logger.debug("[kissne_mobile] queued %s event seq=%d (%s) for installation %s",
                     event_type, seq, message_id, _fingerprint(installation))
        return message_id

    async def send(self, chat_id: str, content: str, reply_to: Optional[str] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> SendResult:
        """Queue the FINAL reply for the installation as a ``completed`` event."""
        message_id = await self._queue_event(chat_id, EVENT_COMPLETED, content=content, reply_to=reply_to)
        if message_id is None:
            return SendResult(success=False, error="missing target installation")
        return SendResult(success=True, message_id=message_id)

    async def send_draft(self, chat_id: str, draft_id: int, content: str,
                         metadata: Optional[Dict[str, Any]] = None) -> SendResult:
        """Queue one INCREMENTAL slice of a streaming answer as a ``delta`` event.

        Deltas are their own event type, so the device renders them as they arrive and closes the turn
        on the final ``send`` — it never has to guess whether a given text was the last one.
        """
        message_id = await self._queue_event(
            chat_id, EVENT_DELTA, content=content, extra={"draft_id": int(draft_id)})
        if message_id is None:
            return SendResult(success=False, error="missing target installation")
        return SendResult(success=True, message_id=message_id)

    async def edit_message(
        self, chat_id: str, message_id: str, content: str, *, finalize: bool = False,
    ) -> SendResult:
        """Polling adapter: no native message-edit, so "edit" = queue a fresh delta.

        The gateway's progress system calls ``edit_message`` to update the tool-progress bubble
        in-place.  Since the Android client re-fetches by cursor, a new delta with the same
        ``draft_id`` replaces the previous text in the client's view.
        """
        extra: Dict[str, Any] = {"draft_id": 0, "edited_message_id": message_id}
        new_id = await self._queue_event(chat_id, EVENT_DELTA, content=content, extra=extra)
        if new_id is None:
            return SendResult(success=False, error="missing target installation")
        return SendResult(success=True, message_id=new_id)

    def supports_draft_streaming(self, chat_type: Optional[str] = None,
                                 metadata: Optional[Dict[str, Any]] = None,
                                 chat_id: Optional[str] = None) -> bool:
        """Yes — streaming reaches this device as typed delta events (see :meth:`send_draft`)."""
        return True

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """A Mobile "chat" is one installation."""
        installation = str(chat_id or "").strip()
        return {
            "id": installation,
            "name": f"Kissne Mobile ({_fingerprint(installation)})",
            "type": "dm",
            "installation_id": installation,
        }

    @staticmethod
    def _cleanup_inbound_media(event: MessageEvent) -> None:
        """Remove plugin-owned inbound temp files after Runtime has finished with the event."""
        for path in list(getattr(event, "media_urls", None) or []):
            if not os.path.basename(path).startswith("kissne-mobile-"):
                continue
            try:
                os.unlink(path)
            except OSError:
                pass

    def _install_mobile_approval_notify(self, installation: str) -> None:
        """Bridge Hermes' synchronous approval notifier into this device's durable event stream."""
        session_key = self.mobile_session_key(installation)
        loop = asyncio.get_running_loop()
        from tools.approval import register_gateway_notify

        def notify(data: Dict[str, Any]) -> None:
            payload = {
                "approval_id": str(data.get("request_id") or ""),
                "tool_input": {"command": str(data.get("command") or "")},
                "summary": str(data.get("description") or "Approval required"),
                "allow_session": bool(data.get("allow_session", False)),
                "allow_permanent": bool(data.get("allow_permanent", False)),
                "status": "pending",
            }
            asyncio.run_coroutine_threadsafe(
                self._queue_event(installation, EVENT_APPROVAL_REQUIRED, extra=payload), loop)

        register_gateway_notify(session_key, notify)

    async def on_processing_start(self, event: MessageEvent) -> None:
        """Persist attachment metadata only when Runtime actually starts this event."""
        pending = getattr(event, "_kissne_attachment_metadata", None)
        if not pending:
            return
        installation, turn_id, text, attachments = pending
        await asyncio.to_thread(
            self.device_store().record_attachment_message,
            installation, turn_id, text, attachments,
        )
        event._kissne_attachment_metadata = None

    async def on_processing_complete(self, event: MessageEvent, outcome: Any) -> None:
        """BasePlatformAdapter calls this only when background processing is actually finished."""
        self._cleanup_inbound_media(event)

    # -- HTTP handlers -----------------------------------------------------------------------------

    async def _payload(self, request: web.Request) -> Any:
        """Size-capped JSON body -> ``(payload, None)`` or ``(None, error_response)``."""
        from aiohttp import web

        if (request.content_length or 0) > self._max_body_bytes:
            return None, _error_response("payload_too_large", 413)
        try:
            raw = await request.read()
        except web.HTTPRequestEntityTooLarge:
            return None, _error_response("payload_too_large", 413)
        except Exception:
            return None, _error_response("bad_request", 400)
        if len(raw) > self._max_body_bytes:
            return None, _error_response("payload_too_large", 413)
        if not raw.strip():
            return {}, None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None, _error_response("invalid_json", 400)
        if not isinstance(payload, dict):
            return None, _error_response("invalid_payload", 400)
        return payload, None

    def _presented_token(self, request: web.Request) -> str:
        """The bearer token on the request, or ``""`` (never logged)."""
        header = str(request.headers.get("Authorization", "") or "")
        scheme, _, value = header.partition(" ")
        return value.strip() if scheme.lower() == "bearer" else ""

    async def _authenticated_installation(self, request: web.Request) -> Optional[str]:
        token = self._presented_token(request)
        if not token:
            return None
        try:
            store = self.device_store()
        except Exception:
            logger.warning("[kissne_mobile] device store unavailable while authenticating", exc_info=True)
            return None
        return await asyncio.to_thread(store.authenticate, token)

    async def _handle_health(self, request: web.Request) -> web.Response:
        devices = 0
        try:
            devices = await asyncio.to_thread(self.device_store().live_device_count)
        except Exception:
            logger.warning("[kissne_mobile] health probe could not read the device store", exc_info=True)
        return _json_response({
            "status": "ok",
            "platform": PLATFORM_NAME,
            "listening": self._runner is not None,
            "live_devices": devices,
        })

    def _client_address(self, request: web.Request) -> str:
        """The address the pairing throttle counts against.

        Deliberately the socket peer, never a client-supplied ``X-Forwarded-For``: a header a caller can
        invent would let one attacker spread brute-force attempts across unlimited buckets. Behind the
        reverse proxy this is the proxy's own address, which still makes guessing codes expensive.
        """
        return str(getattr(request, "remote", None) or "unknown")

    def _pair_throttle(self, request: web.Request) -> Optional[float]:
        """``None`` when this attempt may proceed, else the seconds the caller must wait.

        Operator decision (2026-09-16): no IP allowlist — mobile addresses move, so the exposure knob is
        a strict rate limit on ``/pair`` instead. The window is per client address and covers every
        attempt, successful or not.
        """
        now = time.time()
        window_start = now - PAIR_ATTEMPT_WINDOW_SECONDS
        client = self._client_address(request)
        attempts = self._pair_attempts.setdefault(client, deque())
        while attempts and attempts[0] <= window_start:
            attempts.popleft()
        if len(attempts) >= max(1, self._pair_attempt_limit):
            return max(0.0, (attempts[0] + PAIR_ATTEMPT_WINDOW_SECONDS) - now)
        attempts.append(now)
        return None

    async def _handle_pair(self, request: web.Request) -> web.Response:
        """One-time pairing code -> device token. Nothing else registers an installation."""
        retry_after = self._pair_throttle(request)
        if retry_after is not None:
            logger.warning("[kissne_mobile] pairing attempts from %s throttled for %.1fs",
                           _fingerprint(self._client_address(request)), retry_after)
            response = _error_response("too_many_pairing_attempts", 429)
            response.headers["Retry-After"] = str(max(1, int(retry_after) + 1))
            return response
        payload, error = await self._payload(request)
        if error is not None:
            return error
        body = payload or {}
        code = str(body.get("pairing_code") or "").strip()
        installation = str(body.get("installation_id") or "").strip()
        if not code or not installation:
            return _error_response("pairing_code_and_installation_id_required", 400)
        try:
            store = self.device_store()
        except Exception:
            logger.error("[kissne_mobile] device store unavailable; refusing to pair", exc_info=True)
            return _error_response("device_store_unavailable", 503)
        try:
            token = await asyncio.to_thread(store.redeem_pairing_code, code, installation)
        except PairingCodeInvalid:
            return _error_response("invalid_pairing_code", 400)
        except PairingCodeExpired:
            return _error_response("pairing_code_expired", 410)
        except PairingCodeReplayed:
            return _error_response("pairing_code_replayed", 409)
        except PairingError:
            return _error_response("pairing_refused", 400)
        except ValueError as exc:
            return _error_response(f"bad_request: {exc}", 400)

        conversation_key = str(body.get("session_key") or "").strip()
        if conversation_key:
            bound = await asyncio.to_thread(self.bind_conversation, installation, conversation_key)
        else:
            # No explicit session_key: auto-bind to the installation's own mobile_session_key
            # so a fresh mobile-native conversation is ready on first message.
            own_key = self.mobile_session_key(installation)
            bound = await asyncio.to_thread(self.bind_conversation, installation, own_key)
        return _json_response({
            "ok": True,
            "installation_id": installation,
            "device_token": token,
            "token_type": "Bearer",
            "conversation_bound": bound,
        }, status=201)

    @staticmethod
    def _payload_fingerprint(text: str, attachments: Optional[List[Dict[str, Any]]] = None) -> str:
        """Digest text plus attachment identity so idempotency also covers media changes."""
        items = [{
            "type": item["type"], "mime_type": item["mime_type"],
            "label": item.get("label", ""),
            "sha256": hashlib.sha256(item["bytes"]).hexdigest(),
        } for item in (attachments or [])]
        canonical = json.dumps({"text": text, "attachments": items}, ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _decode_attachments(body: Dict[str, Any]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        raw = body.get("attachments", [])
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            return None, "attachments_must_be_an_array"
        if len(raw) > MAX_ATTACHMENTS:
            return None, "too_many_attachments"
        decoded: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                return None, "attachment_must_be_an_object"
            kind = str(item.get("type") or "").strip().lower()
            mime = str(item.get("mime_type") or "").strip().lower()
            data = item.get("data")
            if kind not in {"image", "sticker", "file"}:
                return None, "unsupported_attachment_type"
            if mime not in ALLOWED_ATTACHMENT_MIME_TYPES:
                return None, "unsupported_attachment_mime_type"
            if kind in {"image", "sticker"} and mime not in ALLOWED_IMAGE_MIME_TYPES:
                return None, "unsupported_attachment_mime_type"
            if kind == "file" and mime not in ALLOWED_DOCUMENT_MIME_TYPES:
                return None, "unsupported_attachment_mime_type"
            if not isinstance(data, str) or not data:
                return None, "attachment_data_required"
            try:
                blob = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                return None, "invalid_attachment_data"
            if not blob:
                return None, "attachment_data_required"
            if len(blob) > MAX_ATTACHMENT_BYTES:
                return None, "attachment_too_large"
            decoded.append({"type": kind, "mime_type": mime,
                            "label": str(item.get("label") or "").strip(), "bytes": blob})
        return decoded, None

    @staticmethod
    def _materialize_attachments(attachments: List[Dict[str, Any]]) -> List[str]:
        suffixes = {
            "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
            "application/pdf": ".pdf", "text/plain": ".txt", "text/markdown": ".md",
            "text/csv": ".csv", "application/json": ".json", "application/zip": ".zip",
        }
        paths: List[str] = []
        try:
            for item in attachments:
                fd, path = tempfile.mkstemp(prefix="kissne-mobile-", suffix=suffixes[item["mime_type"]])
                with os.fdopen(fd, "wb") as handle:
                    handle.write(item["bytes"])
                paths.append(path)
            return paths
        except Exception:
            for path in paths:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            raise

    async def _handle_ack(self, installation: str, body: Dict[str, Any]) -> web.Response:
        """``{"ack": {"cursor": N}}`` — retire what the device has durably received."""
        ack = body.get("ack")
        if not isinstance(ack, dict):
            return _error_response("ack_must_be_an_object", 400)
        raw_cursor = ack.get("cursor")
        if isinstance(raw_cursor, bool) or not isinstance(raw_cursor, (int, str)):
            return _error_response("ack_cursor_required", 400)
        try:
            cursor = int(raw_cursor)
        except ValueError:
            return _error_response("ack_cursor_required", 400)
        if cursor < 0:
            return _error_response("ack_cursor_must_not_be_negative", 400)
        retired = await asyncio.to_thread(self.device_store().ack_events, installation, cursor)
        return _json_response({"ok": True, "acked": retired, "cursor": cursor})

    async def _handle_inbound(self, request: web.Request) -> web.Response:
        """Authenticated text in -> the Runtime's normal inbound path.

        Idempotent per client ``message_id``: a retry repeats the original ``turn_id`` without injecting
        a second turn, and a retry that carries a different payload is refused instead of rewriting a
        turn the Runtime already started.
        """
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        payload, error = await self._payload(request)
        if error is not None:
            return error
        body = payload or {}
        if "ack" in body:
            if str(body.get("text") or "").strip() or body.get("attachments"):
                return _error_response("message_and_ack_are_mutually_exclusive", 400)
            return await self._handle_ack(installation, body)
        text = str(body.get("text") or "")
        attachments, attachment_error = self._decode_attachments(body)
        if attachment_error:
            return _error_response(attachment_error, 400)
        attachments = attachments or []
        if not text.strip() and not attachments:
            return _error_response("text_or_attachment_required", 400)

        conversation_key = str(body.get("session_key") or "").strip()
        if conversation_key:
            if not await asyncio.to_thread(self.bind_conversation, installation, conversation_key):
                return _error_response("conversation_not_bound", 409)
        elif self.bound_conversation(installation) is None:
            # Unbound installation without explicit session_key: auto-bind to its own
            # mobile_session_key so the gateway creates a fresh, mobile-native conversation.
            own_key = self.mobile_session_key(installation)
            if not await asyncio.to_thread(self.bind_conversation, installation, own_key):
                logger.warning("[kissne_mobile] auto-bind failed for unbound installation %s",
                               _fingerprint(installation))
                return _error_response("auto_bind_failed", 500)

        store = self.device_store()
        client_message_id = str(body.get("message_id") or "").strip()
        fingerprint = self._payload_fingerprint(text, attachments)
        if client_message_id:
            existing = await asyncio.to_thread(
                store.inbound_record, installation, client_message_id)
            if existing is not None:
                if str(existing.get("payload_hash") or "") == fingerprint:
                    return self._duplicate_response(client_message_id, str(existing.get("turn_id") or ""))
                return _error_response("message_id_conflict", 409)

        message_id = client_message_id or f"kbm_in_{secrets.token_hex(8)}"
        turn_id = f"kbm_turn_{secrets.token_hex(8)}"
        if client_message_id:
            # The claim is the gate: whichever concurrent retry wins it is the one that injects the turn.
            outcome = await asyncio.to_thread(
                store.record_inbound, installation, client_message_id, fingerprint, turn_id)
            if outcome == INBOUND_DUPLICATE:
                record = await asyncio.to_thread(
                    store.inbound_record, installation, client_message_id) or {}
                return self._duplicate_response(client_message_id, str(record.get("turn_id") or ""))
            if outcome == INBOUND_CONFLICT:
                return _error_response("message_id_conflict", 409)

        await asyncio.to_thread(store.open_turn, turn_id, installation, state=TURN_PENDING)
        await asyncio.to_thread(
            store.enqueue_event, installation, EVENT_PENDING,
            {"message_id": message_id}, turn_id, cap=max(1, self._outbound_cap))

        source = self.source_for_installation(installation)
        # Approval callbacks are session-scoped and synchronous on the agent thread. Register the
        # mobile bridge immediately before this installation injects work into that session.
        self._install_mobile_approval_notify(installation)
        media_paths: List[str] = []
        try:
            if attachments:
                media_paths = self._materialize_attachments(attachments)
            message_type = MessageType.TEXT
            if attachments:
                if all(item["type"] == "sticker" for item in attachments):
                    message_type = MessageType.STICKER
                elif all(item["type"] == "file" for item in attachments):
                    message_type = MessageType.DOCUMENT
                else:
                    message_type = MessageType.PHOTO
            event = MessageEvent(
                text=text,
                message_type=message_type,
                source=source,
                raw_message=body,
                media_urls=media_paths,
                media_types=[item["mime_type"] for item in attachments],
                # The client message_id is only an HTTP retry/idempotency key.  The server turn_id is
                # Runtime identity, so the persisted user row can be reconciled with outbound frames.
                message_id=turn_id,
                user_id=installation,
            )
            if attachments:
                # Attach before admission: an immediately spawned background task may reach
                # on_processing_start before handle_message() returns.
                event._kissne_attachment_metadata = (
                    installation, turn_id, text,
                    [{"type": item["type"], "mime_type": item["mime_type"],
                      "label": str(item.get("label") or "")} for item in attachments],
                )
            await self.handle_message(event)
            accepted = bool(getattr(event, "_gateway_accepted", False))
            # Accepted events are owned by BasePlatformAdapter's background task; its
            # on_processing_complete hook removes media only after the Runtime is done reading it.
            # Test doubles / refused events have no background owner, so clean them here.
            if not accepted:
                self._cleanup_inbound_media(event)
        except Exception:
            logger.exception("[kissne_mobile] failed to inject inbound message %s", message_id)
            for path in media_paths:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            return _error_response("inbound_injection_failed", 503)
        return _json_response(
            {"ok": True, "message_id": message_id, "turn_id": turn_id}, status=202)

    @staticmethod
    def _duplicate_response(client_message_id: str, turn_id: str) -> web.Response:
        """The answer to a retry: the original turn, and an explicit ``duplicate`` flag."""
        return _json_response({
            "ok": True,
            "duplicate": True,
            "message_id": client_message_id,
            "turn_id": turn_id,
        }, status=200)

    async def _handle_outbound(self, request: web.Request) -> web.Response:
        """Typed events after the device's cursor. Reading them does NOT consume them: only an ack does."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        raw_cursor = request.query.get("cursor")
        try:
            cursor = int(raw_cursor) if raw_cursor not in (None, "") else 0
        except (TypeError, ValueError):
            return _error_response("cursor_must_be_an_integer", 400)
        if cursor < 0:
            return _error_response("cursor_must_not_be_negative", 400)
        limit = max(1, self._read_limit)
        events = await asyncio.to_thread(
            self.device_store().events_after, installation, cursor, limit=limit)
        next_cursor = int(events[-1]["seq"]) if events else cursor
        return _json_response({
            "ok": True,
            "events": events,
            "next_cursor": next_cursor,
            "has_more": len(events) >= limit,
        })

    # -- bootstrap / cancel (the app's cold start, and its stop button) -----------------------------

    def _conversation_identity(self, installation: str) -> Optional[Dict[str, Any]]:
        """The Runtime Conversation this installation is joined to, or ``None`` when it joined none.

        Read live through the alias the bind already wrote, so the plugin keeps no mapping of its own and
        a re-pointed installation is reported correctly on the very next call.
        """
        entry = self.bound_conversation(installation)
        if entry is None:
            return None
        session_id = str(getattr(entry, "session_id", "") or "")
        if not session_id:
            return None
        # This installation's key is an *alias*; the Conversation's canonical key is how every other entry
        # point addresses it. Identity = canonical, and the alias is reported separately so the app can
        # still see which routing key its own traffic travels under.
        installation_key = self.mobile_session_key(installation)
        canonical = self._canonical_key_for(session_id)
        return {
            "session_id": session_id,
            "session_key": canonical or installation_key,
            "installation_key": installation_key,
        }

    def _canonical_key_for(self, session_id: str) -> str:
        """The canonical routing key of a Conversation, or ``""`` when it cannot be resolved.

        An alias row carries the Conversation's ``session_id`` too, so this asks the store (first key that
        points at the id — the one the Conversation was created under) instead of guessing from the key's
        shape.
        """
        store = getattr(self, "_session_store", None)
        if store is None or not session_id:
            return ""
        try:
            entry = store.lookup_by_session_id(session_id)
        except Exception:
            logger.warning("[kissne_mobile] could not resolve a Conversation's canonical key", exc_info=True)
            return ""
        return str(getattr(entry, "session_key", "") or "")

    def _bootstrap_history_snapshot(
        self, session_id: str
    ) -> Tuple[List[Dict[str, Any]], bool, set[str]]:
        """Returned history plus turn identities proven by that exact snapshot.

        ``SessionStore.load_transcript()`` exposes the persisted ``platform_message_id`` as
        ``message_id`` for JSONL compatibility.  New Mobile inbound writes the server ``turn_id``
        there; legacy rows carry a client retry id and therefore cannot match a DeviceStore turn.
        """
        store = getattr(self, "_session_store", None)
        if store is None or not session_id:
            return [], False, set()
        try:
            rows = store.load_transcript(session_id) or []
        except Exception:
            logger.warning("[kissne_mobile] could not read history for a bootstrap", exc_info=True)
            return [], False, set()
        items: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            text = row.get("content", row.get("text"))
            if not isinstance(text, str) or not text.strip():
                continue
            item: Dict[str, Any] = {"role": role, "text": text}
            if role == "user":
                turn_id = str(row.get("message_id") or "").strip()
                if turn_id:
                    item["_turn_id"] = turn_id
            stamp = row.get("created_at", row.get("timestamp", row.get("ts")))
            if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
                item["created_at"] = float(stamp)
            items.append(item)

        cap = max(0, self._history_cap)
        truncated = bool(cap and len(items) > cap)
        if truncated:
            items = items[-cap:]
        # A bounded tail may cut between user and assistant.  That assistant half-turn cannot prove
        # reconciliation, so never expose it as the first visible history row.
        if items and items[0].get("role") == "assistant":
            items = items[1:]

        represented_turn_ids: set[str] = set()
        for current, following in zip(items, items[1:]):
            if current.get("role") != "user" or following.get("role") != "assistant":
                continue
            turn_id = str(current.get("_turn_id") or "").strip()
            if turn_id:
                represented_turn_ids.add(turn_id)

        history = [
            {key: value for key, value in item.items() if key != "_turn_id"}
            for item in items
        ]
        return history, truncated, represented_turn_ids

    def _history_tail(self, session_id: str) -> Tuple[List[Dict[str, Any]], bool]:
        """The bounded user/assistant tail retained for existing callers/tests."""
        history, truncated, _represented = self._bootstrap_history_snapshot(session_id)
        return history, truncated

    async def _bootstrap_covered_event_seqs(
        self, installation: str, cursor: int, represented_turn_ids: set[str],
    ) -> List[int]:
        """Non-destructively identify queued frames already materialized in bootstrap history."""
        if not represented_turn_ids:
            return []
        store = self.device_store()
        events = await asyncio.to_thread(
            store.events_after, installation, cursor,
            limit=max(1, self._outbound_cap, self._read_limit),
        )
        covered: List[int] = []
        turn_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        coverable_types = {EVENT_PENDING, EVENT_DELTA, EVENT_COMPLETED}
        for event in events:
            if str(event.get("type") or "") not in coverable_types:
                continue
            turn_id = str(event.get("turn_id") or "").strip()
            if not turn_id or turn_id not in represented_turn_ids:
                continue
            if turn_id not in turn_cache:
                turn_cache[turn_id] = await asyncio.to_thread(store.turn, turn_id)
            turn = turn_cache[turn_id]
            if not isinstance(turn, dict):
                continue
            if str(turn.get("installation_id") or "") != installation:
                continue
            if str(turn.get("state") or "") != TURN_COMPLETED:
                continue
            covered.append(int(event["seq"]))
        return covered

    async def _handle_bootstrap(self, request: web.Request) -> web.Response:
        """Which Conversation this device is on, plus a bounded tail of it. Creates nothing, ever."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        payload, error = await self._payload(request)
        if error is not None:
            return error
        body = payload or {}
        raw_cursor = body.get("cursor", 0)
        if isinstance(raw_cursor, bool) or not isinstance(raw_cursor, (int, str)):
            return _error_response("cursor_must_be_an_integer", 400)
        try:
            cursor = int(raw_cursor) if raw_cursor != "" else 0
        except (TypeError, ValueError):
            return _error_response("cursor_must_be_an_integer", 400)
        if cursor < 0:
            return _error_response("cursor_must_not_be_negative", 400)

        identity = self._conversation_identity(installation)
        if identity is None:
            # Auto-bind to the installation's own mobile_session_key so a fresh
            # mobile-native conversation is created on first cold start.
            own_key = self.mobile_session_key(installation)
            await asyncio.to_thread(self.bind_conversation, installation, own_key)
            identity = self._conversation_identity(installation)
        if identity is None:
            logger.info("[kissne_mobile] bootstrap: installation %s has joined no conversation yet",
                        _fingerprint(installation))
            return _json_response({
                "ok": True, "bound": False, "conversation": None,
                "history": [], "history_truncated": False, "pending_turn_id": None,
                "covered_event_seqs": [],
            })
        history, truncated, represented_turn_ids = self._bootstrap_history_snapshot(
            identity["session_id"])
        attachment_messages = await asyncio.to_thread(
            self.device_store().attachment_messages, installation, self._history_cap)
        if attachment_messages:
            by_turn = {str(item.get("_turn_id") or ""): item for item in history if item.get("_turn_id")}
            for saved in attachment_messages:
                turn = str(saved.get("turn_id") or "")
                if turn and turn in by_turn:
                    by_turn[turn]["attachments"] = list(saved.get("attachments") or [])
                elif turn:
                    history.append({"role": "user", "text": str(saved.get("text") or ""),
                                    "attachments": list(saved.get("attachments") or []),
                                    "_turn_id": turn,
                                    "created_at": float(saved.get("created_at") or 0)})
            history.sort(key=lambda item: float(item.get("created_at") or 0))
        pending = await asyncio.to_thread(self.device_store().pending_turn_id, installation)
        # In-process reconnects can restore every still-live approval. After a Runtime restart the
        # in-memory Hermes queue is empty, so stale persisted markers are deliberately not revived.
        from tools.approval import list_gateway_approvals
        live_approvals = await asyncio.to_thread(
            list_gateway_approvals, self.mobile_session_key(installation))
        approvals = [{
            "approval_id": str(item.get("request_id") or ""),
            "tool_input": {"command": str(item.get("command") or "")},
            "summary": str(item.get("description") or "Approval required"),
            "allow_session": bool(item.get("allow_session", False)),
            "allow_permanent": bool(item.get("allow_permanent", False)),
            "status": "pending",
        } for item in live_approvals]
        covered = await self._bootstrap_covered_event_seqs(
            installation, cursor, represented_turn_ids)
        return _json_response({
            "ok": True,
            "bound": True,
            "conversation": identity,
            "history": history,
            "history_truncated": truncated,
            "pending_turn_id": pending,
            "pending_approvals": approvals,
            "covered_event_seqs": covered,
        })

    async def _handle_approval(self, request: web.Request) -> web.Response:
        """Resolve one real, currently-pending Hermes approval by its opaque request id."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        payload, error = await self._payload(request)
        if error is not None:
            return error
        body = payload or {}
        approval_id = str(body.get("approval_id") or "").strip()
        decision = str(body.get("decision") or "").strip().lower()
        scope = str(body.get("scope") or "once").strip().lower()
        reason = str(body.get("reason") or "").strip() or None
        if not approval_id:
            return _error_response("approval_id_required", 400)
        if decision not in {"allow", "deny"}:
            return _error_response("invalid_approval_decision", 400)
        if scope not in {"once", "session", "always"}:
            return _error_response("invalid_approval_scope", 400)
        session_key = self.mobile_session_key(installation)
        from tools.approval import list_gateway_approvals, resolve_gateway_approval
        pending = await asyncio.to_thread(list_gateway_approvals, session_key)
        current = next((item for item in pending
                        if str(item.get("request_id") or "") == approval_id), None)
        if current is None:
            # Do not distinguish forged, expired, already-resolved, or another device's id.
            return _error_response("unknown_approval", 404)
        if decision == "allow":
            if scope == "always" and not bool(current.get("allow_permanent", False)):
                return _error_response("approval_scope_not_allowed", 409)
            if scope == "session" and not bool(current.get("allow_session", False)):
                return _error_response("approval_scope_not_allowed", 409)
            choice = scope
        else:
            choice = "deny"
        resolved = await asyncio.to_thread(
            resolve_gateway_approval, session_key, choice,
            False, reason, approval_id)
        if resolved != 1:
            return _error_response("approval_no_longer_pending", 409)
        await asyncio.to_thread(
            self.device_store().enqueue_event, installation, EVENT_APPROVAL_RESOLVED,
            {"approval_id": approval_id, "decision": "approved" if decision == "allow" else "denied",
             "scope": scope if decision == "allow" else None, "reason": reason},
            None, cap=max(1, self._outbound_cap))
        return _json_response({"ok": True, "approval_id": approval_id,
                               "status": "approved" if decision == "allow" else "denied"})

    async def _handle_cancel(self, request: web.Request) -> web.Response:
        """``{"turn_id": T}`` -> interrupt that turn's Runtime activity and acknowledge the state."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        payload, error = await self._payload(request)
        if error is not None:
            return error
        body = payload or {}
        turn_id = str(body.get("turn_id") or "").strip()
        if not turn_id:
            return _error_response("turn_id_required", 400)
        store = self.device_store()
        turn = await asyncio.to_thread(store.turn, turn_id)
        if turn is None or str(turn.get("installation_id") or "") != installation:
            # One answer for "never existed" and "belongs to another device": a device must not be able
            # to probe which turns exist.
            return _error_response("unknown_turn", 404)
        state = str(turn.get("state") or "")
        if state == TURN_COMPLETED:
            return _error_response("turn_already_completed", 409)
        if state == TURN_CANCELLED:
            return _error_response("turn_not_cancellable", 409)
        moved = await asyncio.to_thread(
            store.close_turn, turn_id, TURN_CANCELLED, from_state=TURN_PENDING)
        if not moved:
            return _error_response("turn_not_cancellable", 409)
        # A cancelled pending turn must not reappear as a synthetic attachment-only
        # history row on the next bootstrap.
        await asyncio.to_thread(store.delete_attachment_message, installation, turn_id)
        await asyncio.to_thread(
            store.enqueue_event, installation, EVENT_CANCELLED,
            {"turn_id": turn_id}, turn_id, cap=max(1, self._outbound_cap))
        # Stop the Runtime work this turn started, exactly like a "stop" on any other channel does.
        # The Runtime registers an in-flight turn under the key of the channel that STARTED it, so cancel
        # must speak this installation's own routing key (an alias, not the Conversation's canonical key —
        # using the canonical key would stop another entry point's turn on the same Conversation).
        session_key = self.mobile_session_key(installation)
        # Snapshot before interrupt: unregister/cancellation wakes and removes the live queue.
        from tools.approval import list_gateway_approvals
        cancelled_approvals = await asyncio.to_thread(list_gateway_approvals, session_key)
        try:
            await self.interrupt_session_activity(session_key, installation, None)
        except Exception:
            logger.warning("[kissne_mobile] cancel could not interrupt turn %s",
                           _fingerprint(turn_id), exc_info=True)
        for approval in cancelled_approvals:
            approval_id = str(approval.get("request_id") or "")
            if approval_id:
                await asyncio.to_thread(
                    store.enqueue_event, installation, EVENT_APPROVAL_RESOLVED,
                    {"approval_id": approval_id, "decision": "denied",
                     "scope": None, "reason": "turn_cancelled"},
                    turn_id, cap=max(1, self._outbound_cap))
        logger.info("[kissne_mobile] cancelled turn %s for installation %s",
                    _fingerprint(turn_id), _fingerprint(installation))
        return _json_response({
            "ok": True, "acknowledged": True, "turn_id": turn_id, "state": TURN_CANCELLED,
        })

    async def _handle_revoke(self, request: web.Request) -> web.Response:
        """Self-revoke: the device kills its own token (immediate, and durable)."""
        token = self._presented_token(request)
        if not token:
            return _error_response("unauthorized", 401)
        try:
            store = self.device_store()
        except Exception:
            logger.error("[kissne_mobile] device store unavailable; cannot revoke", exc_info=True)
            return _error_response("device_store_unavailable", 503)
        revoked = await asyncio.to_thread(store.revoke, token)
        if not revoked:
            return _error_response("unauthorized", 401)
        return _json_response({"ok": True, "revoked": True})


def create_adapter(config: PlatformConfig) -> KissneMobileAdapter:
    """``PlatformEntry.adapter_factory`` entry point (``PlatformConfig -> adapter``)."""
    return KissneMobileAdapter(config, Platform(PLATFORM_NAME))


def check_kissne_mobile_requirements() -> bool:
    """PASSIVE dependency probe: the listener needs aiohttp, nothing else."""
    try:
        return importlib.util.find_spec("aiohttp") is not None
    except Exception:  # pragma: no cover - an unimportable parent package is simply "not ready"
        return False


def _env_flag(name: str) -> str:
    """Scope-aware flag read. ``get_scoped_secret`` makes an installed profile's own secret scope
    authoritative: a scoped miss returns the default instead of borrowing ``os.environ``, so flagging
    Mobile in one profile can never enable it in another. The unscoped default profile falls back to
    its own ``os.environ`` value. (``agent.secret_scope`` is off-limits here — the ticket's boundary
    guard forbids this plugin from importing anything under ``agent``.)"""
    return str(get_scoped_secret(name, "") or "").strip()


def _opted_in_via_env() -> bool:
    return _env_flag(OPT_IN_ENV).strip().lower() in {"1", "true", "yes", "on"}


def _env_enablement() -> Optional[Dict[str, Any]]:
    """``env_enablement_fn``: enable ONLY the profile whose own env carries the opt-in flag — ``None``
    everywhere else, so no profile inherits the listener from another one."""
    return {"enabled": True} if _opted_in_via_env() else None


def _apply_yaml_config(_yaml_cfg: Any, platform_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """YAML bridge: an explicit ``platforms.kissne_mobile.enabled: true`` in THIS profile's block is a
    real opt-in, so surface it in ``extra`` — where ``_is_connected`` looks. (``enabled`` is a typed
    key, so ``PlatformConfig.from_dict`` deliberately keeps it out of ``extra``.)"""
    return {"enabled": True} if (platform_cfg or {}).get("enabled") is True else {}


def _is_connected(config: Optional[PlatformConfig] = None) -> bool:
    """Configured = THIS profile explicitly opted in (its own env flag or ``enabled: true`` in its YAML).

    MUST NOT read ``config.enabled``. ``gateway/config_env.py::_plugin_is_configured`` probes every
    plugin platform with a transient ``PlatformConfig(enabled=True, extra=...)`` view — the question is
    "if the user enabled it, is it configured?" — so echoing that field reports "configured" for every
    profile on the box and silently auto-enables the listener gateway-wide (a Discord-only profile then
    grows a Mobile adapter). Same contract as ``plugins/platforms/raft/adapter.py``, another platform
    that has no external credential to test for.
    """
    extra = getattr(config, "extra", None) or {}
    return bool(extra.get("enabled"))


def _mobile_post_approval_response(**payload: Any) -> None:
    """Mirror Hermes' real approval outcome into Mobile without becoming an approval authority."""
    session_key = str(payload.get("session_key") or "")
    if not session_key.startswith(f"{PLATFORM_NAME}:"):
        return
    choice = str(payload.get("choice") or "")
    if choice not in {"timeout", "deny"}:
        return
    # request_id is intentionally supplied by the approval wait lifecycle when available.
    approval_id = str(payload.get("request_id") or "")
    if not approval_id:
        return
    # The adapter instance owns delivery; lifecycle hooks have no adapter handle by design.
    # Resolution for explicit mobile allow/deny is emitted by POST /approval. This hook is
    # reserved for Runtime-owned terminal outcomes once the lifecycle exposes request_id.
    logger.debug("[kissne_mobile] Hermes approval %s ended with %s", _fingerprint(approval_id), choice)


def register(ctx) -> None:
    """Plugin entry point — called by the Hermes plugin system."""
    ctx.register_hook("post_approval_response", _mobile_post_approval_response)
    ctx.register_platform(
        name=PLATFORM_NAME,
        label="Kissne Mobile",
        adapter_factory=create_adapter,
        check_fn=check_kissne_mobile_requirements,
        is_connected=_is_connected,
        # No external credential exists, so the opt-in IS the platform's config signal: the flag in this
        # profile's own env (``env_enablement_fn``) or ``enabled: true`` in its YAML (bridge below).
        required_env=[OPT_IN_ENV],
        env_enablement_fn=_env_enablement,
        apply_yaml_config_fn=_apply_yaml_config,
        install_hint="Kissne Mobile needs the gateway's aiohttp dependency (present in a standard install).",
        emoji="📱",
        platform_hint=(
            "You are also reachable from the Kissne Mobile Android app. Reply normally: the app "
            "polls this Runtime for your text. The app holds a device-scoped token only — it never "
            "sees an API key, a provider key or any Runtime management credential, so never ask it "
            "for one or send one over this channel."
        ),
    )
