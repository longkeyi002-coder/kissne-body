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
import hashlib
import importlib.util
import json
import re
import logging
import secrets
import shlex
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
DEFAULT_MAX_BODY_BYTES = 64 * 1024
DEFAULT_MEDIA_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_OUTBOUND_QUEUE_CAP = 200

# This platform has NO external credential, so enablement needs an explicit per-profile opt-in:
# either ``platforms.kissne_mobile.enabled: true`` in that profile's config.yaml or this flag in
# that profile's own ``.env``. See ``_is_connected`` for why the opt-in must never be read from
# ``PlatformConfig.enabled``.
OPT_IN_ENV = "KISSNE_MOBILE_ENABLED"

PAIRING_PATH = "/pair"
BOOTSTRAP_PATH = "/bootstrap"
MESSAGES_PATH = "/messages"
HISTORY_PATH = "/history"
SEARCH_PATH = "/search"
CANCEL_PATH = "/cancel"
REVOKE_PATH = "/revoke"
HEALTH_PATH = "/health"
MODEL_OPTIONS_PATH = "/model-options"
SET_MODEL_PATH = "/set-model"
ADMIN_SESSIONS_PATH = "/admin/sessions"
ADMIN_STATUS_PATH = "/admin/status"

#: How many history messages a fresh app launch may ask for (§0.3.16: bootstrap returns a BOUNDED tail).
DEFAULT_HISTORY_CAP = 50
#: How many events one poll may return; the device acks and polls again for the rest.
DEFAULT_READ_LIMIT = 200
_ACTIVITY_MARKER_PREFIX = "[[KISSNE_ACTIVITY:"
_ACTIVITY_MARKER_SUFFIX = "]]"
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

    # Mobile's durable draft/event transport is a native stream consumer: this is
    # what makes Gateway tool progress reach send_draft as typed Activity instead
    # of falling back to the legacy progress path.
    SUPPORTS_NATIVE_STREAMING = True

    def supports_native_streaming(self, chat_type=None, metadata=None) -> bool:
        return True

    async def send_stream_frame(self, chat_id: str, content: str, *,
                                stream_id: str = "", turn_id: str = "",
                                reply_to: Optional[str] = None, final: bool = False,
                                metadata: Optional[Dict[str, Any]] = None) -> SendResult:
        # GatewayStreamConsumer identifies one native stream with its own turn_id.
        # Accept that standard argument explicitly; otherwise the consumer's first seed
        # raises TypeError and silently degrades Mobile to buffered send(), which is why
        # live tool Activity only appeared after reopening the app.
        stream_key = str(stream_id or turn_id or "mobile")
        draft_id = abs(hash(stream_key)) % 2147483647 or 1
        return await self.send_draft(chat_id, draft_id, content, metadata=metadata)

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
        self._draft_text_last: Dict[Tuple[str, int], str] = {}
        self._draft_activity_seen: Dict[Tuple[str, int], set[str]] = {}
        self._draft_tool_labels: Dict[Tuple[str, int], Dict[str, str]] = {}
        self._session_reset_pending: set[str] = set()
        self._session_reset_turns: Dict[str, str] = {}
        # Turns admitted through the HTTP inbound path; direct store turns remain auxiliary notices.
        self._inbound_turns: set[str] = set()
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

        Uses only public ``SessionStore`` API — ``bind_source_to_existing_session`` writes the
        routing alias and nothing else: no session row is created, ended or reopened and the joined
        row's identity is left untouched — so the resolution itself is the store's truth and
        survives a restart. Returns ``False`` when the target conversation does not exist
        or the store cannot do it; the plugin never invents a conversation of its own.
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
        try:
            entry = store.bind_source_to_existing_session(
                self.source_for_installation(installation), target.session_id,
            )
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
        app = web.Application(
            client_max_size=max(self._max_body_bytes, DEFAULT_MEDIA_MAX_BYTES + 1024 * 1024))
        app.router.add_post(PAIRING_PATH, self._handle_pair)
        app.router.add_post(BOOTSTRAP_PATH, self._handle_bootstrap)
        app.router.add_post(MESSAGES_PATH, self._handle_inbound)
        app.router.add_get(MESSAGES_PATH, self._handle_outbound)
        app.router.add_get(HISTORY_PATH, self._handle_history)
        app.router.add_get(SEARCH_PATH, self._handle_history_search)
        app.router.add_post(CANCEL_PATH, self._handle_cancel)
        app.router.add_post(REVOKE_PATH, self._handle_revoke)
        app.router.add_get(HEALTH_PATH, self._handle_health)
        app.router.add_get(MODEL_OPTIONS_PATH, self._handle_model_options)
        app.router.add_post(SET_MODEL_PATH, self._handle_set_model)
        app.router.add_get(ADMIN_SESSIONS_PATH, self._handle_admin_sessions)
        app.router.add_post(ADMIN_SESSIONS_PATH, self._handle_select_admin_session)
        app.router.add_delete(ADMIN_SESSIONS_PATH, self._handle_delete_admin_session)
        app.router.add_get(ADMIN_STATUS_PATH, self._handle_admin_status)
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
        self._draft_text_last.clear()
        self._draft_activity_seen.clear()
        self._mark_disconnected()
        logger.info("[kissne_mobile] disconnected")

    # -- outbound ----------------------------------------------------------------------------------

    @staticmethod
    def _activity_detail(text: str, limit: int = 900) -> str:
        """Compact detail for the optional tap-to-expand view; redact obvious secrets."""
        value = str(text or "").strip()
        value = re.sub(
            r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s'\"]+",
            r"\1[hidden]", value)
        value = re.sub(
            r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s'\"]+",
            r"\1[hidden]", value)
        return value if len(value) <= limit else value[: max(0, limit - 1)] + "…"

    @staticmethod
    def _tool_command(args: Optional[Dict[str, Any]]) -> str:
        if not isinstance(args, dict):
            return ""
        for key in ("command", "cmd", "script", "query", "path", "file_path"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @classmethod
    def _semantic_activity_label(
        cls, tool_name: str, args: Optional[Dict[str, Any]], preview: Optional[str],
    ) -> str:
        """Describe the user-facing action rather than exposing developer tool chrome."""
        tool = str(tool_name or "").strip()
        low_tool = tool.lower()
        raw = cls._tool_command(args) or str(preview or "")
        low = raw.lower()
        if ("sticker" in low or "表情" in raw) and re.search(r"\b(grep|rg|find)\b", low):
            return "查找表情包发送逻辑"
        if ("adapter.py" in low or "kissne_mobile" in low) and re.search(
                r"\b(grep|rg|sed|cat|read|reading)\b", low):
            return "检查 Mobile Adapter"
        if re.search(r"\bgit\s+log\b", low):
            return "检查 Git 历史"
        if re.search(r"\bgit\s+(status|diff|show)\b", low):
            return "检查 Git 状态"
        if re.search(r"\b(pytest|gradle|lint|test)\b", low):
            return "运行相关检查"
        file_matches = re.findall(r"([\\w./-]+\\.(?:py|js|ts|kt|css|html|md))", raw, re.I)
        file_name = file_matches[-1] if file_matches else ""
        if re.search(r"\\b(sed|cat|head|tail|read|reading|open)\\b", low) and file_name:
            return f"读取 {file_name.rsplit('/', 1)[-1]}"
        if re.search(r"\b(grep|rg)\b", low):
            pattern = re.search(
                r"(?:grep|rg)\s+(?:-[^\s]+\s+)*(?:\"([^\"]+)\"|'([^']+)'|([^\s|]+))",
                raw, re.I)
            term = next((part for part in (pattern.groups() if pattern else ()) if part), "")
            term = re.sub(r"[_*\\]+", "", term).strip()
            if term and len(term) <= 18:
                return f"查找「{term}」相关代码"
            return "查找相关代码"
        if re.search(r"\bfind\b", low):
            return "查找相关文件"
        if low_tool in {"read", "read_file", "fetch_file"} or "read" in low_tool:
            return f"读取 {file_name.rsplit('/', 1)[-1]}" if file_name else "读取文件"
        if any(word in low_tool for word in ("edit", "write", "patch", "update")):
            return "修改文件"
        if any(word in low_tool for word in ("search", "grep", "find")):
            return "查找相关内容"
        if any(word in low_tool for word in ("github", "git")):
            return "检查 Git"
        if low_tool in {"terminal", "shell", "bash"}:
            return "运行命令"
        return f"使用 {tool}" if tool else "使用工具"

    @classmethod
    def _encode_activity_marker(cls, payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return f"{_ACTIVITY_MARKER_PREFIX}{encoded}{_ACTIVITY_MARKER_SUFFIX}"

    @staticmethod
    def _decode_activity_marker(line: str) -> Optional[Dict[str, Any]]:
        text = str(line or "").strip()
        if not (text.startswith(_ACTIVITY_MARKER_PREFIX) and text.endswith(_ACTIVITY_MARKER_SUFFIX)):
            return None
        token = text[len(_ACTIVITY_MARKER_PREFIX):-len(_ACTIVITY_MARKER_SUFFIX)]
        try:
            token += "=" * (-len(token) % 4)
            value = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
        except Exception:
            return None
        return value if isinstance(value, dict) else None

    def format_tool_event(
        self, event: Any, *, mode: str = "all", preview_max_len: int = 40,
    ) -> Optional[str]:
        """Encode a semantic Activity record; send_draft separates it from assistant text."""
        from gateway.stream_events import ToolCallChunk, ToolCallFinished
        if isinstance(event, ToolCallFinished):
            index = int(event.index or 0)
            return self._encode_activity_marker({
                "kind": "tool_result",
                "tool_call_id": f"draft-tool:{index}",
                "tool_name": str(event.tool_name or ""),
                "index": index,
                "status": "completed" if bool(event.ok) else "failed",
                "duration": round(float(event.duration or 0.0), 3),
            })
        if not isinstance(event, ToolCallChunk):
            return None
        command = self._tool_command(event.args)
        if command:
            detail = command
        elif event.preview:
            detail = str(event.preview)
        elif event.args:
            detail = json.dumps(event.args, ensure_ascii=False, default=str)
        else:
            detail = str(event.tool_name or "")
        index = int(event.index or 0)
        payload = {
            "kind": "tool_call",
            "tool_call_id": f"draft-tool:{index}",
            "label": self._semantic_activity_label(event.tool_name, event.args, event.preview),
            "tool_name": str(event.tool_name or ""),
            "arguments": self._activity_detail(detail),
            "index": index,
            "status": "running",
        }
        return self._encode_activity_marker(payload)

    def _split_draft_frame(self, content: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Separate internal Activity marker lines from the visible cumulative draft."""
        activities: List[Dict[str, Any]] = []
        visible: List[str] = []
        for line in str(content or "").splitlines():
            activity = self._decode_activity_marker(line)
            if activity is not None:
                activities.append(activity)
            else:
                visible.append(line)
        text = "\n".join(visible)
        if activities:
            text = re.sub(r"\n*---\s*$", "", text).rstrip()
        return text, activities

    def _clear_draft_state(self, installation_id: str) -> None:
        installation = str(installation_id or "")
        keys = set(self._draft_text_last) | set(self._draft_activity_seen) | set(self._draft_tool_labels)
        for key in [key for key in keys if key[0] == installation]:
            self._draft_text_last.pop(key, None)
            self._draft_activity_seen.pop(key, None)
            self._draft_tool_labels.pop(key, None)

    async def _queue_event(self, installation_id: str, event_type: str, *,
                           content: Optional[str] = None, reply_to: Optional[str] = None,
                           extra: Optional[Dict[str, Any]] = None,
                           target_turn_id: Optional[str] = None) -> Optional[str]:
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
        pending_turn_id = await asyncio.to_thread(store.pending_turn_id, installation)
        explicit_turn_id = str(target_turn_id or "").strip()
        turn_id = explicit_turn_id or str(pending_turn_id or "")
        # Explicitly-bound live frames are admitted atomically with the durable turn
        # state. This closes the check/enqueue race with cancel; completed also changes
        # pending->completed in the same transaction as its final event.
        try:
            if explicit_turn_id and event_type in {EVENT_DELTA, EVENT_COMPLETED}:
                seq = await asyncio.to_thread(
                    store.enqueue_pending_turn_event,
                    installation, explicit_turn_id, event_type, payload,
                    cap=max(1, self._outbound_cap),
                    close=event_type == EVENT_COMPLETED,
                )
                if seq is None:
                    logger.debug(
                        "[kissne_mobile] dropping late %s for closed turn %s",
                        event_type, _fingerprint(explicit_turn_id))
                    return None
            else:
                seq = await asyncio.to_thread(
                    store.enqueue_event, installation, event_type, payload, turn_id or None,
                    cap=max(1, self._outbound_cap),
                )
                if event_type == EVENT_COMPLETED and turn_id:
                    await asyncio.to_thread(store.close_turn, turn_id, TURN_COMPLETED)
            if event_type == EVENT_COMPLETED and turn_id:
                self._inbound_turns.discard(turn_id)
        except Exception:
            logger.exception("[kissne_mobile] failed to queue %s event for installation %s",
                             event_type, _fingerprint(installation))
            return None
        logger.debug("[kissne_mobile] queued %s event seq=%d (%s) for installation %s",
                     event_type, seq, message_id, _fingerprint(installation))
        return message_id

    async def send(self, chat_id: str, content: str, reply_to: Optional[str] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> SendResult:
        """Queue final text, reset notices, or auxiliary notices without closing unrelated turns."""
        installation = str(chat_id or "").strip()
        reset_turn = self._session_reset_turns.get(installation)
        if installation in self._session_reset_pending and reset_turn and (
            reply_to == reset_turn or reply_to is None
        ):
            notice_id = f"kbn_{secrets.token_hex(8)}"
            message_id = await self._queue_event(
                installation, EVENT_COMPLETED, content=content, reply_to=reply_to,
                target_turn_id=reset_turn,
                extra={"presentation": "session_reset", "notice_id": notice_id,
                       "message_ref": "notice:" + notice_id})
            await asyncio.to_thread(
                self.device_store().record_timeline_notice,
                installation, notice_id, "session_reset", content,
            )
            self._session_reset_pending.discard(installation)
            self._session_reset_turns.pop(installation, None)
        elif bool((metadata or {}).get("_interim_send")):
            message_id = await self._queue_event(
                installation, EVENT_DELTA, content=content, reply_to=reply_to,
                extra={"presentation": "commentary", "interim": True})
        else:
            pending_turn = await asyncio.to_thread(
                self.device_store().pending_turn_id, installation)
            # A normal Runtime reply closes an HTTP-admitted turn. A turn opened directly in the
            # device store has no Runtime admission marker and remains an auxiliary notice.
            if reply_to is None and pending_turn and pending_turn not in self._inbound_turns:
                message_id = await self._queue_event(
                    installation, "notice", content=content, reply_to=None,
                    extra={"presentation": "notice"})
            else:
                self._clear_draft_state(installation)
                final_extra = {"presentation": "assistant_text"} if reply_to is None else None
                message_id = await self._queue_event(
                    installation, EVENT_COMPLETED, content=content, reply_to=reply_to,
                    extra=final_extra)
        if message_id is None:
            return SendResult(success=False, error="missing target installation")
        return SendResult(success=True, message_id=message_id)

    async def send_reasoning(self, chat_id: str, content: str, *,
                             draft_id: int = 0, turn_id: str = "") -> SendResult:
        """Queue provider-visible reasoning on its own transport lane.

        This never enters assistant_text: final answer scrubbing remains unchanged while
        models/providers that expose reasoning can stream it to capable clients.
        """
        text = str(content or "")
        if not text:
            return SendResult(success=True, message_id=None)
        message_id = await self._queue_event(
            chat_id, EVENT_DELTA, content=text,
            target_turn_id=str(turn_id or "").strip() or None,
            extra={
                "draft_id": int(draft_id or 0),
                "presentation": "reasoning",
                "interim": True,
            },
        )
        if message_id is None:
            return SendResult(success=False, error="missing target installation")
        return SendResult(success=True, message_id=message_id)

    async def send_draft(self, chat_id: str, draft_id: int, content: str,
                         metadata: Optional[Dict[str, Any]] = None) -> SendResult:
        """Separate cumulative assistant text from semantic tool Activity before delivery."""
        installation = str(chat_id or "").strip()
        key = (installation, int(draft_id))
        visible, activities = self._split_draft_frame(content)
        seen = self._draft_activity_seen.setdefault(key, set())
        labels = self._draft_tool_labels.setdefault(key, {})
        last_message_id: Optional[str] = None

        for activity in activities:
            identity = str(
                activity.get("tool_call_id")
                or f"draft-tool:{activity.get('index', '')}"
            )
            kind = str(activity.get("kind") or "tool_call")
            phase_key = f"{kind}:{identity}"
            if phase_key in seen:
                continue
            seen.add(phase_key)
            if kind == "tool_call":
                labels[identity] = str(activity.get("label") or "")
            elif kind == "tool_result" and not activity.get("label"):
                activity["label"] = labels.get(identity, "") or self._semantic_activity_label(
                    str(activity.get("tool_name") or ""), None, None)
            presentation = "tool_result" if kind == "tool_result" else "tool_call"
            last_message_id = await self._queue_event(
                installation, EVENT_DELTA, content="",
                extra={
                    "draft_id": int(draft_id),
                    "presentation": presentation,
                    "tool_call_id": identity,
                    "activity": activity,
                })

        if visible.strip() and self._draft_text_last.get(key) != visible:
            self._draft_text_last[key] = visible
            last_message_id = await self._queue_event(
                installation, EVENT_DELTA, content=visible,
                extra={"draft_id": int(draft_id), "presentation": "assistant_text"})

        if last_message_id is None:
            return SendResult(success=True, message_id=None)
        return SendResult(success=True, message_id=last_message_id)

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
        bound = False
        if conversation_key:
            bound = await asyncio.to_thread(self.bind_conversation, installation, conversation_key)
        return _json_response({
            "ok": True,
            "installation_id": installation,
            "device_token": token,
            "token_type": "Bearer",
            "conversation_bound": bound,
        }, status=201)

    @staticmethod
    def _payload_fingerprint(text: str) -> str:
        """Digest of an inbound payload — the thing that separates a retry from a rewrite."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_upload_name(name: str) -> str:
        base = _Path(str(name or "upload.bin")).name
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
        return stem[:120] or "upload.bin"

    async def _handle_media_inbound(self, request: web.Request, installation: str) -> web.Response:
        """Multipart photo/document -> normal Hermes MessageEvent with a local media path."""
        from aiohttp import web
        from plugins.plugin_storage import plugin_data_dir

        if self.bound_conversation(installation) is None:
            return _error_response("installation_not_bound_to_a_runtime_conversation", 409)
        if (request.content_length or 0) > DEFAULT_MEDIA_MAX_BYTES + 1024 * 1024:
            return _error_response("attachment_too_large", 413)

        message_id = ""
        kind = "file"
        file_name = ""
        mime_type = ""
        file_bytes = bytearray()
        try:
            reader = await request.multipart()
            while True:
                part = await reader.next()
                if part is None:
                    break
                field = str(part.name or "")
                if field == "file":
                    if not file_name:
                        file_name = str(part.filename or "")
                    if not mime_type:
                        mime_type = str(part.headers.get("Content-Type") or "")
                    while True:
                        chunk = await part.read_chunk(size=64 * 1024)
                        if not chunk:
                            break
                        file_bytes.extend(chunk)
                        if len(file_bytes) > DEFAULT_MEDIA_MAX_BYTES:
                            return _error_response("attachment_too_large", 413)
                elif field in {"message_id", "kind", "file_name", "mime_type"}:
                    value = (await part.text()).strip()
                    if field == "message_id":
                        message_id = value
                    elif field == "kind":
                        kind = value if value in {"photo", "sticker"} else "file"
                    elif field == "file_name":
                        file_name = value
                    elif field == "mime_type":
                        mime_type = value
        except web.HTTPRequestEntityTooLarge:
            return _error_response("attachment_too_large", 413)
        except Exception:
            logger.warning("[kissne_mobile] invalid multipart upload", exc_info=True)
            return _error_response("invalid_attachment", 400)

        if not file_bytes:
            return _error_response("attachment_required", 400)
        file_name = _Path(file_name or ("photo" if kind == "photo" else "file")).name
        mime_type = (mime_type or "application/octet-stream").strip()
        if mime_type.startswith("image/") and kind != "sticker":
            kind = "photo"

        store = self.device_store()
        client_message_id = message_id.strip()
        digest = hashlib.sha256()
        for piece in (
            kind.encode("utf-8"),
            file_name.encode("utf-8", errors="replace"),
            mime_type.encode("utf-8", errors="replace"),
            bytes(file_bytes),
        ):
            digest.update(piece)
            digest.update(b"\0")
        fingerprint = digest.hexdigest()

        if client_message_id:
            existing = await asyncio.to_thread(
                store.inbound_record, installation, client_message_id)
            if existing is not None:
                if str(existing.get("payload_hash") or "") == fingerprint:
                    return self._duplicate_response(
                        client_message_id, str(existing.get("turn_id") or ""))
                return _error_response("message_id_conflict", 409)

        message_id = client_message_id or f"kbm_in_{secrets.token_hex(8)}"
        turn_id = f"kbm_turn_{secrets.token_hex(8)}"
        if client_message_id:
            outcome = await asyncio.to_thread(
                store.record_inbound, installation, client_message_id, fingerprint, turn_id)
            if outcome == INBOUND_DUPLICATE:
                record = await asyncio.to_thread(
                    store.inbound_record, installation, client_message_id) or {}
                return self._duplicate_response(
                    client_message_id, str(record.get("turn_id") or ""))
            if outcome == INBOUND_CONFLICT:
                return _error_response("message_id_conflict", 409)

        upload_dir = plugin_data_dir(PLATFORM_NAME) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        disk_path = upload_dir / f"{turn_id}_{self._safe_upload_name(file_name)}"
        try:
            await asyncio.to_thread(disk_path.write_bytes, bytes(file_bytes))
        except Exception:
            logger.exception("[kissne_mobile] failed to persist inbound attachment")
            return _error_response("attachment_store_failed", 503)

        await asyncio.to_thread(store.open_turn, turn_id, installation, state=TURN_PENDING)
        self._inbound_turns.add(turn_id)
        await asyncio.to_thread(
            store.enqueue_event, installation, EVENT_PENDING,
            {"message_id": message_id}, turn_id, cap=max(1, self._outbound_cap))

        is_photo = kind == "photo"
        marker = f"[照片：{file_name}]" if is_photo else f"[文件：{file_name}]"
        event = MessageEvent(
            text=marker,
            message_type=MessageType.PHOTO if is_photo else MessageType.DOCUMENT,
            source=self.source_for_installation(installation),
            raw_message={
                "kind": kind,
                "file_name": file_name,
                "mime_type": mime_type,
                "size": len(file_bytes),
            },
            message_id=turn_id,
            user_id=installation,
            media_urls=[str(disk_path)],
            media_types=[mime_type],
            media_text_inlined=[False],
        )
        try:
            await self.handle_message(event)
            await asyncio.to_thread(
                store.record_attachment_message,
                installation, turn_id, marker,
                [{"type": "image" if is_photo else "file", "mime_type": mime_type, "label": file_name}],
            )
        except Exception:
            logger.exception("[kissne_mobile] failed to inject inbound attachment %s", message_id)
            return _error_response("inbound_injection_failed", 503)

        return _json_response({
            "ok": True,
            "message_id": message_id,
            "turn_id": turn_id,
            "kind": kind,
            "file_name": file_name,
            "mime_type": mime_type,
            "size": len(file_bytes),
        }, status=202)

    def _mobile_history_sessions(self, installation: str) -> List[Dict[str, Any]]:
        """Return the bound Runtime conversation plus its Mobile-owned continuations.

        Pairing is an alias: it deliberately does not rewrite the canonical Runtime
        session row session_key. Querying only by the Mobile alias therefore hides
        the conversation the device just joined.
        """
        store = getattr(self, "_session_store", None)
        if store is None:
            return []
        mobile_key = self.mobile_session_key(installation)
        bound = self.bound_conversation(installation)
        db = store._db_for_key(mobile_key)
        if db is None or not hasattr(db, "list_sessions_rich"):
            return []
        rows = db.list_sessions_rich(
            session_key=mobile_key,
            include_archived=True, include_children=True,
            project_compression_tips=False, order_by_last_active=True,
            limit=500, offset=0, compact_rows=True,
        )
        by_id = {str(row.get("id") or ""): row for row in rows if str(row.get("id") or "")}
        bound_id = str(getattr(bound, "session_id", "") or "")
        if bound_id and bound_id not in by_id:
            get_session = getattr(db, "get_session", None)
            canonical = get_session(bound_id) if callable(get_session) else None
            by_id[bound_id] = canonical if isinstance(canonical, dict) else {"id": bound_id}
        return list(by_id.values())

    def _mobile_history_rows(self, installation: str) -> List[Dict[str, Any]]:
        """Flatten /new-separated transcripts into one Mobile-visible timeline."""
        store = getattr(self, "_session_store", None)
        if store is None:
            return []
        try:
            saved_attachments = self.device_store().attachment_messages(installation, 500)
        except Exception:
            logger.warning("[kissne_mobile] attachment history read failed", exc_info=True)
            saved_attachments = []
        attachments_by_turn = {
            str(item.get("turn_id") or ""): list(item.get("attachments") or [])
            for item in saved_attachments if str(item.get("turn_id") or "")
        }
        try:
            saved_replies = self.device_store().reply_links(installation)
        except Exception:
            logger.warning("[kissne_mobile] reply-link history read failed", exc_info=True)
            saved_replies = []
        replies_by_turn = {
            str(item.get("turn_id") or ""): item
            for item in saved_replies if str(item.get("turn_id") or "")
        }
        rows: List[Dict[str, Any]] = []
        for session in self._mobile_history_sessions(installation):
            session_id = str(session.get("id") or "")
            if not session_id:
                continue
            try:
                transcript = store.load_transcript(session_id) or []
            except Exception:
                logger.warning("[kissne_mobile] history read failed for %s", session_id, exc_info=True)
                continue
            active_mobile_turn = ""
            for index, row in enumerate(transcript):
                if not isinstance(row, dict):
                    continue
                role = str(row.get("role") or "").strip().lower()
                if role not in {"user", "assistant"}:
                    continue
                mobile_turn = ""
                if role == "user":
                    candidate = str(row.get("message_id") or "").strip()
                    active_mobile_turn = candidate if candidate.startswith("kbm_turn_") else ""
                    mobile_turn = active_mobile_turn
                else:
                    mobile_turn = active_mobile_turn
                    active_mobile_turn = ""
                text = row.get("content", row.get("text"))
                if not isinstance(text, str):
                    text = ""
                attachments = attachments_by_turn.get(mobile_turn, []) if role == "user" else []
                if not text.strip() and not attachments:
                    continue
                stamp = row.get("created_at", row.get("timestamp", row.get("ts")))
                stamp = float(stamp) if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) else 0.0
                message_ref = f"turn:{mobile_turn}:{role}" if mobile_turn else f"{session_id}:{index}"
                item: Dict[str, Any] = {"message_ref": message_ref, "role": role, "text": text, "created_at": stamp}
                if mobile_turn:
                    item["_turn_id"] = mobile_turn
                if attachments:
                    item["attachments"] = attachments
                if role == "user" and mobile_turn:
                    link = replies_by_turn.get(mobile_turn)
                    if link:
                        item["reply_to"] = str(link.get("reply_to") or "")
                        item["reply_preview"] = {
                            "role": str(link.get("quoted_role") or ""),
                            "text": str(link.get("quoted_text") or ""),
                        }
                rows.append(item)
        seen_attachment_turns = {
            str(row.get("_turn_id") or "") for row in rows if row.get("_turn_id")
        }
        for turn_id, attachment_list in attachments_by_turn.items():
            if turn_id and turn_id not in seen_attachment_turns:
                record = next((item for item in saved_attachments
                               if str(item.get("turn_id") or "") == turn_id), {})
                rows.append({
                    "message_ref": f"turn:{turn_id}:user",
                    "_turn_id": turn_id,
                    "role": "user",
                    "text": str(record.get("text") or ""),
                    "created_at": float(record.get("created_at") or 0),
                    "attachments": attachment_list,
                })
        try:
            notices = self.device_store().timeline_notices(installation)
        except Exception:
            notices = []
        for notice in notices:
            notice_id, text = str(notice.get("notice_id") or ""), str(notice.get("text") or "")
            if notice_id and text:
                rows.append({
                    "message_ref": "notice:" + notice_id, "role": "system", "text": text,
                    "created_at": float(notice.get("created_at") or 0),
                    "presentation": str(notice.get("presentation") or ""),
                })
        rows.sort(key=lambda item: (float(item.get("created_at") or 0), str(item["message_ref"])))
        return rows

    async def _handle_history(self, request: web.Request) -> web.Response:
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        try:
            limit = int(request.query.get("limit", "50"))
        except (TypeError, ValueError):
            return _error_response("limit_must_be_an_integer", 400)
        limit = max(1, min(limit, 100))
        before = str(request.query.get("before") or "").strip()
        rows = await asyncio.to_thread(self._mobile_history_rows, installation)
        end = len(rows)
        if before:
            positions = [i for i, item in enumerate(rows) if item["message_ref"] == before]
            if not positions:
                return _error_response("history_cursor_not_found", 400)
            end = positions[0]
        start = max(0, end - limit)
        page = rows[start:end]
        return _json_response({"ok": True, "messages": page, "has_more": start > 0,
                               "next_before": page[0]["message_ref"] if start > 0 and page else None})

    async def _handle_history_search(self, request: web.Request) -> web.Response:
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        query = str(request.query.get("q") or "").strip()
        if not query:
            return _error_response("query_required", 400)
        try:
            limit = int(request.query.get("limit", "20"))
        except (TypeError, ValueError):
            return _error_response("limit_must_be_an_integer", 400)
        limit = max(1, min(limit, 50))
        needle = query.casefold()
        rows = await asyncio.to_thread(self._mobile_history_rows, installation)
        matches = [item for item in reversed(rows) if needle in str(item.get("text") or "").casefold()]
        return _json_response({"ok": True, "results": matches[:limit]})

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

    def _materialize_attachments(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Decode bounded JSON attachments once and return temporary media paths."""
        from plugins.plugin_storage import plugin_data_dir

        upload_dir = plugin_data_dir(PLATFORM_NAME) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        materialized: List[Dict[str, Any]] = []
        try:
            for item in items:
                kind = str(item.get("type") or "").strip().lower()
                mime_type = str(item.get("mime_type") or "").strip().lower()
                encoded = item.get("data")
                if kind not in {"image", "sticker", "file"} or not mime_type:
                    raise ValueError("invalid_attachment")
                if kind in {"image", "sticker"} and not mime_type.startswith("image/"):
                    raise ValueError("invalid_attachment")
                if not isinstance(encoded, str) or not encoded:
                    raise ValueError("attachment_required")
                file_bytes = base64.b64decode(encoded, validate=True)
                if not file_bytes or len(file_bytes) > DEFAULT_MEDIA_MAX_BYTES:
                    raise ValueError("attachment_too_large")
                label = self._safe_upload_name(str(item.get("label") or "upload.bin"))
                path = upload_dir / f"kissne_in_{secrets.token_hex(8)}_{label}"
                path.write_bytes(file_bytes)
                materialized.append({
                    "path": str(path), "bytes": len(file_bytes), "kind": kind,
                    "mime_type": mime_type, "label": str(item.get("label") or ""),
                })
        except Exception:
            for row in materialized:
                try:
                    _Path(row["path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            raise
        return materialized

    def _set_inbound_attachment_metadata(
        self, event: MessageEvent, installation: str, turn_id: str,
        marker: str, attachments: List[Dict[str, Any]], paths: List[str],
    ) -> None:
        setattr(event, "_kissne_attachment_metadata", {
            "installation": installation, "turn_id": turn_id, "marker": marker,
            "attachments": attachments, "paths": paths, "persisted": False,
        })

    async def on_processing_start(self, event: MessageEvent) -> None:
        """Persist attachment presentation metadata when the Runtime admits a turn."""
        metadata = getattr(event, "_kissne_attachment_metadata", None)
        if not isinstance(metadata, dict) or metadata.get("persisted"):
            return
        await asyncio.to_thread(
            self.device_store().record_attachment_message,
            str(metadata.get("installation") or ""),
            str(metadata.get("turn_id") or ""),
            str(metadata.get("marker") or ""),
            list(metadata.get("attachments") or []),
        )
        metadata["persisted"] = True

    def _cleanup_inbound_media(self, event: MessageEvent) -> None:
        metadata = getattr(event, "_kissne_attachment_metadata", None)
        if not isinstance(metadata, dict):
            return
        for raw_path in metadata.get("paths") or []:
            try:
                _Path(str(raw_path)).unlink(missing_ok=True)
            except Exception:
                logger.debug("[kissne_mobile] could not remove temporary inbound media", exc_info=True)

    async def _handle_json_attachment_inbound(
        self, body: Dict[str, Any], installation: str
    ) -> web.Response:
        """JSON attachment -> a real media MessageEvent; text is optional."""
        attachments = body.get("attachments")
        if not isinstance(attachments, list) or len(attachments) != 1:
            return _error_response("attachments_must_be_a_single_item_list", 400)
        item = attachments[0]
        if not isinstance(item, dict):
            return _error_response("invalid_attachment", 400)
        kind = str(item.get("type") or "").strip().lower()
        mime_type = str(item.get("mime_type") or "").strip().lower()
        encoded = item.get("data")
        if kind not in {"image", "sticker", "file"} or not mime_type:
            return _error_response("invalid_attachment", 400)
        if kind in {"image", "sticker"} and not mime_type.startswith("image/"):
            return _error_response("invalid_attachment", 400)
        if not isinstance(encoded, str) or not encoded:
            return _error_response("attachment_required", 400)
        try:
            file_bytes = base64.b64decode(encoded, validate=True)
        except Exception:
            return _error_response("invalid_attachment", 400)
        if not file_bytes or len(file_bytes) > DEFAULT_MEDIA_MAX_BYTES:
            return _error_response("attachment_too_large", 413)
        if self.bound_conversation(installation) is None:
            return _error_response("installation_not_bound_to_a_runtime_conversation", 409)

        client_message_id = str(body.get("message_id") or "").strip()
        fingerprint = hashlib.sha256(
            json.dumps({"type": kind, "mime_type": mime_type, "data": encoded},
                       sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        store = self.device_store()
        if client_message_id:
            existing = await asyncio.to_thread(store.inbound_record, installation, client_message_id)
            if existing is not None:
                if str(existing.get("payload_hash") or "") == fingerprint:
                    return self._duplicate_response(client_message_id, str(existing.get("turn_id") or ""))
                return _error_response("message_id_conflict", 409)

        message_id = client_message_id or f"kbm_in_{secrets.token_hex(8)}"
        turn_id = f"kbm_turn_{secrets.token_hex(8)}"
        if client_message_id:
            outcome = await asyncio.to_thread(
                store.record_inbound, installation, client_message_id, fingerprint, turn_id
            )
            if outcome == INBOUND_DUPLICATE:
                record = await asyncio.to_thread(store.inbound_record, installation, client_message_id) or {}
                return self._duplicate_response(client_message_id, str(record.get("turn_id") or ""))
            if outcome == INBOUND_CONFLICT:
                return _error_response("message_id_conflict", 409)

        try:
            materialized = self._materialize_attachments([item])
        except ValueError as exc:
            return _error_response(str(exc) or "invalid_attachment", 400)
        except Exception:
            logger.exception("[kissne_mobile] failed to materialize inbound attachment")
            return _error_response("attachment_store_failed", 503)
        row = materialized[0]
        await asyncio.to_thread(store.open_turn, turn_id, installation, state=TURN_PENDING)
        self._inbound_turns.add(turn_id)
        await asyncio.to_thread(
            store.enqueue_event, installation, EVENT_PENDING,
            {"message_id": message_id}, turn_id, cap=max(1, self._outbound_cap)
        )
        message_type = (
            MessageType.STICKER if kind == "sticker"
            else MessageType.PHOTO if kind == "image"
            else MessageType.DOCUMENT
        )
        safe_attachment = {
            "type": kind, "mime_type": mime_type,
            "label": str(item.get("label") or ""),
        }
        marker = str(body.get("text") or "")
        event = MessageEvent(
            text=marker, message_type=message_type, source=self.source_for_installation(installation),
            raw_message=body, message_id=turn_id, user_id=installation,
            media_urls=[row["path"]], media_types=[mime_type], media_text_inlined=[False],
        )
        self._set_inbound_attachment_metadata(
            event, installation, turn_id, marker, [safe_attachment], [row["path"]],
        )
        try:
            await self.handle_message(event)
        except Exception:
            self._cleanup_inbound_media(event)
            logger.exception("[kissne_mobile] failed to inject JSON attachment %s", message_id)
            return _error_response("inbound_injection_failed", 503)
        return _json_response({
            "ok": True, "message_id": message_id, "turn_id": turn_id,
            "kind": kind, "mime_type": mime_type, "size": len(file_bytes),
        }, status=202)

    async def _handle_inbound(self, request: web.Request) -> web.Response:
        """Authenticated text in -> the Runtime's normal inbound path.

        Idempotent per client ``message_id``: a retry repeats the original ``turn_id`` without injecting
        a second turn, and a retry that carries a different payload is refused instead of rewriting a
        turn the Runtime already started.
        """
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        if str(getattr(request, "content_type", "") or "").lower().startswith("multipart/"):
            return await self._handle_media_inbound(request, installation)
        payload, error = await self._payload(request)
        if error is not None:
            return error
        body = payload or {}
        if "ack" in body:
            if str(body.get("text") or "").strip():
                return _error_response("text_and_ack_are_mutually_exclusive", 400)
            return await self._handle_ack(installation, body)
        text = str(body.get("text") or "")
        if "attachments" in body:
            if isinstance(body.get("attachments"), list):
                return await self._handle_json_attachment_inbound(body, installation)
            return _error_response("invalid_attachment", 400)
        if not text.strip():
            return _error_response("text_required", 400)

        conversation_key = str(body.get("session_key") or "").strip()
        if conversation_key:
            if not await asyncio.to_thread(self.bind_conversation, installation, conversation_key):
                return _error_response("conversation_not_bound", 409)
        elif self.bound_conversation(installation) is None:
            # Never let an unbound installation open a second, mobile-only conversation.
            logger.warning("[kissne_mobile] inbound refused for unbound installation %s",
                           _fingerprint(installation))
            return _error_response("installation_not_bound_to_a_runtime_conversation", 409)

        store = self.device_store()
        client_message_id = str(body.get("message_id") or "").strip()
        reply_ref = str(body.get("reply_to") or "").strip()
        quoted = None
        if reply_ref:
            history_rows = await asyncio.to_thread(self._mobile_history_rows, installation)
            quoted = next((item for item in history_rows if item["message_ref"] == reply_ref), None)
            if quoted is None:
                return _error_response("reply_target_not_found", 400)
            if str(quoted.get("role") or "") == "system":
                return _error_response("reply_target_not_quotable", 400)
        fingerprint = hashlib.sha256((text + "\0" + reply_ref).encode("utf-8")).hexdigest()
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
        self._inbound_turns.add(turn_id)
        await asyncio.to_thread(
            store.enqueue_event, installation, EVENT_PENDING,
            {"message_id": message_id}, turn_id, cap=max(1, self._outbound_cap))

        source = self.source_for_installation(installation)
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=body,
            # The client message_id is only an HTTP retry/idempotency key.  The server turn_id is
            # Runtime identity, so the persisted user row can be reconciled with outbound frames.
            message_id=turn_id,
            user_id=installation,
            reply_to_message_id=reply_ref or None,
            reply_to_text=str(quoted.get("text") or "") if quoted else None,
            reply_to_author_name=(
                "叶青栩" if quoted and quoted.get("role") == "assistant" else
                "用户" if quoted else None
            ),
            reply_to_is_own_message=bool(quoted and quoted.get("role") == "assistant"),
            allow_gateway_control=text.strip().lower() in {"/new", "/reset"},
        )
        if quoted:
            await asyncio.to_thread(
                store.record_reply_link, installation, turn_id, reply_ref,
                str(quoted.get("role") or ""), str(quoted.get("text") or ""),
            )
        try:
            await self.handle_message(event)
        except Exception:
            logger.exception("[kissne_mobile] failed to inject inbound message %s", message_id)
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

    # -- model controls ---------------------------------------------------------------------------

    def _live_model_selection(self, installation: str) -> Tuple[str, str]:
        """Best-effort current (model, provider) for this joined Runtime Conversation."""
        entry = self.bound_conversation(installation)
        model = str(getattr(entry, "model", "") or "") if entry is not None else ""
        provider = str(getattr(entry, "provider", "") or "") if entry is not None else ""

        runner = getattr(self, "gateway_runner", None)
        overrides = getattr(runner, "_session_model_overrides", {}) or {}
        keys = [self.mobile_session_key(installation)]
        identity = self._conversation_identity(installation)
        canonical = str((identity or {}).get("session_key") or "")
        if canonical and canonical not in keys:
            keys.append(canonical)
        for key in keys:
            override = overrides.get(key)
            if not isinstance(override, dict):
                continue
            model = str(override.get("model") or model or "")
            provider = str(override.get("provider") or provider or "")
            if model or provider:
                break
        return model, provider

    def _live_reasoning_effort(self, installation: str, model: str = "") -> str:
        """Read the effective reasoning effort from the same Gateway resolver used for the next turn."""
        runner = getattr(self, "gateway_runner", None)
        resolver = getattr(runner, "_resolve_session_reasoning_config", None)
        if not callable(resolver):
            return ""
        source = self.source_for_installation(installation)
        # Reasoning overrides live on the canonical Runtime conversation. The mobile
        # installation key is only a routing alias; resolving against that alias made
        # the picker report "none" even while the selected conversation had an effort.
        identity = self._conversation_identity(installation) or {}
        canonical_key = str(identity.get("session_key") or "").strip()
        session_key = canonical_key or self.mobile_session_key(installation)
        try:
            config = resolver(
                source=source,
                session_key=session_key,
                model=str(model or ""),
            )
        except Exception:
            logger.debug("[kissne_mobile] could not resolve live reasoning effort", exc_info=True)
            return ""
        if config is None:
            return "medium"
        if isinstance(config, dict) and config.get("enabled") is False:
            return "none"
        if isinstance(config, dict):
            return str(config.get("effort") or "medium")
        return ""

    async def _handle_model_options(self, request: web.Request) -> web.Response:
        """Same provider/model inventory as the Hermes Dashboard picker, under the device's profile."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        if self.bound_conversation(installation) is None:
            return _error_response("installation_not_bound_to_a_runtime_conversation", 409)

        source = self.source_for_installation(installation)
        profile = str(getattr(source, "profile", "") or getattr(self, "_owner_profile", "") or "")
        current_model, current_provider = self._live_model_selection(installation)
        current_effort = self._live_reasoning_effort(installation, current_model)

        def _build() -> Dict[str, Any]:
            from contextlib import nullcontext
            from hermes_cli.inventory import build_model_options_payload, load_picker_context

            scope = nullcontext()
            if profile:
                try:
                    from hermes_cli.web_server_profiles import _config_profile_scope
                    scope = _config_profile_scope(profile)
                except Exception:
                    logger.debug("[kissne_mobile] profile scope unavailable for model options", exc_info=True)
            with scope:
                # Keep the mobile picker identical to Hermes 9120 Dashboard:
                # same profile, same inventory builder, same filtering.
                # include_unconfigured mirrors the Dashboard's opt-in so the
                # full provider universe is visible (same as #56974 on web).
                payload = build_model_options_payload(
                    load_picker_context(), include_unconfigured=True
                )
            # Mirror Hermes' canonical reasoning vocabulary without importing Agent truth
            # across the mobile-plugin boundary.
            payload["efforts"] = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
            if current_model:
                payload["model"] = current_model
            if current_provider:
                payload["provider"] = current_provider
            if current_effort:
                payload["effort"] = current_effort
                payload["current_effort"] = current_effort
            return payload

        try:
            payload = await asyncio.to_thread(_build)
        except Exception:
            logger.exception("[kissne_mobile] failed to build Dashboard model options")
            return _error_response("model_options_failed", 503)
        return _json_response(payload)

    async def _handle_set_model(self, request: web.Request) -> web.Response:
        """Apply the picker choice through the Gateway's canonical /model and /reasoning handlers."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        if self.bound_conversation(installation) is None:
            return _error_response("installation_not_bound_to_a_runtime_conversation", 409)
        payload, error = await self._payload(request)
        if error is not None:
            return error
        body = payload or {}
        model = str(body.get("model") or "").strip()
        provider = str(body.get("provider") or "").strip()
        effort = str(body.get("effort") or "").strip()
        if not model and not effort:
            return _error_response("model_or_effort_required", 400)
        if model and not provider:
            return _error_response("provider_required_with_model", 400)

        runner = getattr(self, "gateway_runner", None)
        if runner is None:
            return _error_response("runtime_control_unavailable", 503)
        source = self.source_for_installation(installation)

        try:
            model_reply = ""
            if model:
                event = MessageEvent(
                    text=f"/model {shlex.quote(model)} --provider {shlex.quote(provider)} --session",
                    message_type=MessageType.TEXT,
                    source=source,
                    raw_message={"internal": "kissne_mobile_model_control"},
                    message_id=f"kbm_control_{secrets.token_hex(8)}",
                    user_id=installation,
                )
                model_reply = str(await runner._handle_model_command(event) or "")
                if model_reply.startswith("❌"):
                    return _json_response({"ok": False, "error": "model_switch_failed", "detail": model_reply}, 409)
                if model_reply.startswith("⚠"):
                    return _json_response({"ok": False, "error": "model_confirmation_required", "detail": model_reply}, 409)

            reasoning_reply = ""
            if effort:
                event = MessageEvent(
                    text=f"/reasoning {shlex.quote(effort)}",
                    message_type=MessageType.TEXT,
                    source=source,
                    raw_message={"internal": "kissne_mobile_reasoning_control"},
                    message_id=f"kbm_control_{secrets.token_hex(8)}",
                    user_id=installation,
                )
                reasoning_reply = str(await runner._handle_reasoning_command(event) or "")
                if reasoning_reply.startswith("❌"):
                    return _json_response({"ok": False, "error": "reasoning_switch_failed", "detail": reasoning_reply}, 409)
        except Exception:
            logger.exception("[kissne_mobile] model control failed")
            return _error_response("model_control_failed", 503)

        current_model, current_provider = self._live_model_selection(installation)
        current_effort = self._live_reasoning_effort(installation, current_model or model)
        return _json_response({
            "ok": True,
            "model": current_model or model,
            "provider": current_provider or provider,
            "effort": current_effort or effort,
            "model_reply": model_reply,
            "reasoning_reply": reasoning_reply,
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
        """Return bounded complete turns, including safe tool activity metadata.

        Mobile receives enough structure to rebuild Hermes tool activity, but never raw reasoning.
        The cap remains a physical message-row ceiling. Selection happens only at complete user-led
        turn boundaries, so tool chatter cannot leave an orphaned half-turn in the returned tail.
        """
        store = getattr(self, "_session_store", None)
        if store is None or not session_id:
            return [], False, set()
        try:
            rows = store.load_transcript(session_id) or []
        except Exception:
            logger.warning("[kissne_mobile] could not read history for a bootstrap", exc_info=True)
            return [], False, set()

        def clipped(value: Any, limit: int = 4096) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                text = value
            else:
                try:
                    text = json.dumps(value, ensure_ascii=False, default=str)
                except Exception:
                    text = str(value)
            if len(text) <= limit:
                return text
            return text[:limit] + "…[truncated]"

        def safe_tool_calls(value: Any) -> List[Dict[str, Any]]:
            if not isinstance(value, list):
                return []
            result: List[Dict[str, Any]] = []
            for index, call in enumerate(value[:24]):
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                function = function if isinstance(function, dict) else {}
                call_id = str(call.get("id") or call.get("tool_call_id") or f"history-tool:{index}")
                name = str(function.get("name") or call.get("name") or call.get("tool_name") or "")
                arguments = function.get("arguments", call.get("arguments", ""))
                result.append({
                    "id": call_id,
                    "name": name,
                    "arguments": clipped(arguments, 4096),
                })
            return result

        groups: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "").strip().lower()
            if role not in {"user", "assistant", "tool"}:
                continue
            # Deliberately do not read/copy row["reasoning"].
            text_value = row.get("content", row.get("text"))
            text = text_value if isinstance(text_value, str) else ""
            stamp = row.get("created_at", row.get("timestamp", row.get("ts")))

            if role == "user":
                if current is not None:
                    groups.append(current)
                turn_id = str(row.get("message_id") or "").strip()
                item: Dict[str, Any] = {"role": "user", "text": text}
                if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
                    item["created_at"] = float(stamp)
                if turn_id:
                    item["message_ref"] = f"turn:{turn_id}:user"
                current = {"turn_id": turn_id, "items": [item]}
                continue

            # Never expose orphan assistant/tool rows from before the bounded user-led turn.
            if current is None:
                continue

            if role == "assistant":
                calls = safe_tool_calls(row.get("tool_calls"))
                if not text.strip() and not calls:
                    continue
                item = {"role": "assistant", "text": text}
                if calls:
                    item["tool_calls"] = calls
                    item["activity_only"] = not bool(text.strip())
                if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
                    item["created_at"] = float(stamp)
                current["items"].append(item)
                continue

            # Tool output is intentionally a bounded preview; binary/base64-sized payloads never
            # travel wholesale through bootstrap.
            tool_call_id = str(row.get("tool_call_id") or row.get("call_id") or "").strip()
            tool_name = str(row.get("tool_name") or row.get("name") or "").strip()
            if not tool_call_id and not tool_name and not text.strip():
                continue
            item = {
                "role": "tool",
                "text": clipped(text, 4096),
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
            }
            if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
                item["created_at"] = float(stamp)
            current["items"].append(item)

        if current is not None:
            groups.append(current)

        # Keep the long-standing contract: history_cap is a physical message-row ceiling.
        # Select only whole user-led groups from the tail, so the response is <= cap rows and never
        # starts in the middle of a turn. A single pathological turn larger than the cap is omitted
        # rather than split into an orphaned tool/final fragment.
        cap = max(0, self._history_cap)
        all_groups = groups
        if cap:
            selected: List[Dict[str, Any]] = []
            used = 0
            for group in reversed(all_groups):
                size = len(group.get("items") or [])
                if size > cap:
                    if not selected:
                        continue
                    break
                if used + size > cap:
                    break
                selected.append(group)
                used += size
            groups = list(reversed(selected))
            truncated = len(groups) < len(all_groups)
        else:
            truncated = False

        items: List[Dict[str, Any]] = []
        represented_turn_ids: set[str] = set()
        for group in groups:
            turn_id = str(group.get("turn_id") or "").strip()
            group_items = list(group.get("items") or [])
            # The final visible assistant belongs to the originating user turn even when any number
            # of assistant(tool_calls)/tool rows sit between them. Preserve reconciliation semantics.
            final_assistant: Optional[Dict[str, Any]] = None
            for item in group_items:
                if item.get("role") == "assistant" and str(item.get("text") or "").strip():
                    final_assistant = item
            if turn_id:
                for item in group_items:
                    item["turn_id"] = turn_id
            if turn_id and final_assistant is not None:
                final_assistant["message_ref"] = f"turn:{turn_id}:assistant"
                represented_turn_ids.add(turn_id)
            items.extend(group_items)

        return items, truncated, represented_turn_ids

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
            logger.info("[kissne_mobile] bootstrap: installation %s has joined no conversation yet",
                        _fingerprint(installation))
            return _json_response({
                "ok": True, "bound": False, "conversation": None,
                "history": [], "history_truncated": False, "pending_turn_id": None,
                "covered_event_seqs": [],
            })
        history, truncated, represented_turn_ids = self._bootstrap_history_snapshot(
            identity["session_id"])
        # Attachment-only turns may not yet exist in the Hermes transcript during a cold start;
        # restore their durable presentation metadata so the device can render them.
        try:
            saved_attachments = await asyncio.to_thread(
                self.device_store().attachment_messages, installation, 500)
        except Exception:
            saved_attachments = []
        for record in saved_attachments:
            turn_id = str(record.get("turn_id") or "").strip()
            if not turn_id or turn_id in represented_turn_ids:
                continue
            history.append({
                "role": "user",
                "text": str(record.get("text") or ""),
                "_turn_id": turn_id,
                "message_ref": f"turn:{turn_id}:user",
                "attachments": list(record.get("attachments") or []),
                "created_at": float(record.get("created_at") or 0),
            })
            represented_turn_ids.add(turn_id)
        history.sort(key=lambda item: (float(item.get("created_at") or 0), str(item.get("message_ref") or "")))
        pending = await asyncio.to_thread(self.device_store().pending_turn_id, installation)
        covered = await self._bootstrap_covered_event_seqs(
            installation, cursor, represented_turn_ids)
        return _json_response({
            "ok": True,
            "bound": True,
            "conversation": identity,
            "history": history,
            "history_truncated": truncated,
            "pending_turn_id": pending,
            "covered_event_seqs": covered,
        })

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
        self._inbound_turns.discard(turn_id)
        self._clear_draft_state(installation)
        await asyncio.to_thread(
            store.enqueue_event, installation, EVENT_CANCELLED,
            {"turn_id": turn_id}, turn_id, cap=max(1, self._outbound_cap))
        # Stop the Runtime work this turn started, exactly like a "stop" on any other channel does.
        # The Runtime registers an in-flight turn under the key of the channel that STARTED it, so cancel
        # must speak this installation's own routing key (an alias, not the Conversation's canonical key —
        # using the canonical key would stop another entry point's turn on the same Conversation).
        session_key = self.mobile_session_key(installation)
        try:
            await self.interrupt_session_activity(session_key, installation, None)
        except Exception:
            logger.warning("[kissne_mobile] cancel could not interrupt turn %s",
                           _fingerprint(turn_id), exc_info=True)
        logger.info("[kissne_mobile] cancelled turn %s for installation %s",
                    _fingerprint(turn_id), _fingerprint(installation))
        return _json_response({
            "ok": True, "acknowledged": True, "turn_id": turn_id, "state": TURN_CANCELLED,
        })

    async def _handle_admin_sessions(self, request: web.Request) -> web.Response:
        """Device-scoped read-only session index for the Android conversation picker."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        store = getattr(self, "_session_store", None)
        if store is None:
            return _error_response("session_store_unavailable", 503)
        try:
            entries = await asyncio.to_thread(store.list_sessions)
        except Exception:
            logger.warning("[kissne_mobile] could not list sessions", exc_info=True)
            return _error_response("session_list_unavailable", 503)

        current = self._conversation_identity(installation)
        current_id = str((current or {}).get("session_id") or "")
        # Routing aliases can point at the same Conversation. Return one row per
        # canonical session id, preferring a non-mobile key/title when available.
        by_id: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            sid = str(getattr(entry, "session_id", "") or "")
            if not sid:
                continue
            key = str(getattr(entry, "session_key", "") or "")
            display = str(getattr(entry, "display_name", "") or "")
            updated = getattr(entry, "updated_at", None)
            created = getattr(entry, "created_at", None)
            row = {
                "session_id": sid,
                "session_key": key,
                "title": display,
                "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else str(updated or ""),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                "active": sid == current_id,
            }
            previous = by_id.get(sid)
            mobile_key = key.startswith("kissne_mobile:")
            previous_mobile = bool(previous and str(previous.get("session_key") or "").startswith("kissne_mobile:"))
            if previous is None or (previous_mobile and not mobile_key):
                by_id[sid] = row
            elif sid == current_id:
                previous["active"] = True
        rows = list(by_id.values())
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return _json_response({"ok": True, "sessions": rows, "active_session_id": current_id})

    async def _handle_select_admin_session(self, request: web.Request) -> web.Response:
        """Rebind this paired installation to an existing Runtime conversation."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        store = getattr(self, "_session_store", None)
        if store is None:
            return _error_response("session_store_unavailable", 503)
        payload, error = await self._payload(request)
        if error is not None:
            return error
        body = payload or {}
        session_id = str(body.get("session_id") or "").strip()
        session_key = str(body.get("session_key") or "").strip()
        if not session_id and not session_key:
            return _error_response("session_identity_required", 400)
        try:
            target = (await asyncio.to_thread(store.lookup_by_session_id, session_id)
                      if session_id else await asyncio.to_thread(store.lookup_by_session_key, session_key))
        except Exception:
            logger.warning("[kissne_mobile] could not resolve selected session", exc_info=True)
            return _error_response("session_select_unavailable", 503)
        if target is None:
            return _error_response("session_not_found", 404)
        mobile_key = self.mobile_session_key(installation)
        try:
            current = await asyncio.to_thread(store.lookup_by_session_key, mobile_key)
            if current is None:
                bound = await asyncio.to_thread(
                    self.bind_conversation, installation, str(target.session_key or "")
                )
            else:
                switched = await asyncio.to_thread(store.switch_session, mobile_key, target.session_id)
                bound = switched is not None and switched.session_id == target.session_id
        except Exception:
            logger.warning("[kissne_mobile] failed to switch installation %s to %s",
                           _fingerprint(installation), target.session_id, exc_info=True)
            bound = False
        if not bound:
            return _error_response("session_select_failed", 409)
        identity = self._conversation_identity(installation) or {}
        return _json_response({"ok": True, "conversation": identity})

    async def _handle_delete_admin_session(self, request: web.Request) -> web.Response:
        """Delete one inactive canonical Hermes conversation selected by the paired device."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        store = getattr(self, "_session_store", None)
        if store is None:
            return _error_response("session_store_unavailable", 503)
        try:
            body = await request.json()
        except Exception:
            body = {}
        session_id = str((body or {}).get("session_id") or "").strip()
        if not session_id:
            return _error_response("session_id_required", 400)
        current = self._conversation_identity(installation)
        current_id = str((current or {}).get("session_id") or "")
        if session_id == current_id:
            return _error_response("active_session_delete_forbidden", 409)
        try:
            target = await asyncio.to_thread(store.lookup_by_session_id, session_id)
            if target is None:
                return _error_response("session_not_found", 404)
            # SessionStore intentionally has no destructive delete API. Remove the
            # inactive conversation from the active routing index and end its durable
            # session row through the same lifecycle primitive used by resets/switches.
            target_key = str(target.session_key or "")
            db = store._db_for_key(target_key)
            if db is not None:
                promote = getattr(db, "promote_to_session_reset", None)
                if callable(promote):
                    promote(session_id, "session_deleted")
                else:
                    db.end_session(session_id, "session_deleted")
            with store._lock:
                store._ensure_loaded_locked()
                routed = store._entries.get(target_key)
                if routed is None or routed.session_id != session_id:
                    return _error_response("session_not_found", 404)
                store._entries.pop(target_key, None)
                store._save()
        except Exception:
            logger.warning("[kissne_mobile] could not delete session %s", _fingerprint(session_id), exc_info=True)
            return _error_response("session_delete_unavailable", 503)
        return _json_response({"ok": True, "deleted": True, "session_id": session_id})

    async def _handle_admin_status(self, request: web.Request) -> web.Response:
        """Small read-only operational snapshot safe for a paired device token."""
        installation = await self._authenticated_installation(request)
        if not installation:
            return _error_response("unauthorized", 401)
        started = getattr(self, "_connected_at", None)
        uptime = 0.0
        if isinstance(started, (int, float)):
            uptime = max(0.0, time.time() - float(started))
        return _json_response({
            "ok": True,
            "uptime_seconds": uptime,
            "git": {"head": "", "describe": "", "branch": "", "dirty_files": 0},
            "deploy": {"running": False, "success": None, "type": None},
            "mobile": {"connected": bool(self.is_connected), "bound_port": self.bound_port},
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


def register(ctx) -> None:
    """Plugin entry point — called by the Hermes plugin system."""
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
            "for one or send one over this channel. When a sticker fits naturally, you may send one "
            "with [表情包：关键词]; useful keywords include 开心、哈哈、疑惑、好的、没问题、收到、"
            "无语、惊讶、挥手、晚安、救命. You may place normal text before or after the marker. "
            "The app resolves it to the user's real Kissne sticker; do not invent a sticker if no match is likely."
        ),
    )
