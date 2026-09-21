"""Device credential layer for the ``kissne_mobile`` platform plugin.

Registry of Android installations paired to THIS Runtime, persisted on the plugin's own storage
layer (``<hermes home>/plugin-data/kissne_mobile/``):

* :meth:`DeviceStore.issue_pairing_code` mints a **short-lived, single-use** registration secret.
* :meth:`DeviceStore.redeem_pairing_code` consumes it exactly once and hands back a device token.
* :meth:`DeviceStore.authenticate` / :meth:`DeviceStore.revoke` gate and kill that token, and both
  decisions survive a Runtime restart because they are rows, not process memory.

At rest this store keeps **only SHA-256 digests** — of pairing codes and of device tokens alike. The
plaintext token exists solely inside the one HTTP response that delivers it to the device, so if the
store leaks, no usable credential leaks with it.

Scope note: nothing here knows about conversations. Conversation truth stays in the Runtime session
store, and this module deliberately has no session/conversation column at all — the plugin must not
build a second installation→conversation mapping next to the Runtime's own.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

__all__ = [
    "PLUGIN_NAME",
    "DEFAULT_PAIRING_TTL_SECONDS",
    "TOKEN_PREFIX",
    "PairingError",
    "PairingCodeInvalid",
    "PairingCodeExpired",
    "PairingCodeReplayed",
    "DeviceStore",
    "TURN_PENDING",
    "TURN_COMPLETED",
    "TURN_CANCELLED",
    "INBOUND_NEW",
    "INBOUND_DUPLICATE",
    "INBOUND_CONFLICT",
    "EVENT_NOTICE",
    "EVENT_APPROVAL_REQUIRED",
    "EVENT_APPROVAL_RESOLVED",
]

#: Turn states published to a device. A turn is opened by an accepted inbound message and closed by the
#: reply (``completed``) or by an acknowledged cancel (``cancelled``).
TURN_PENDING = "pending"
TURN_COMPLETED = "completed"
TURN_CANCELLED = "cancelled"

#: The same states as they appear on the wire: every outbound event a device reads is typed, so a client
#: switches on ``type`` instead of inferring meaning from plain text.
EVENT_PENDING = TURN_PENDING
EVENT_DELTA = "delta"
EVENT_COMPLETED = TURN_COMPLETED
EVENT_CANCELLED = TURN_CANCELLED
EVENT_NOTICE = "notice"
EVENT_APPROVAL_REQUIRED = "approval_required"
EVENT_APPROVAL_RESOLVED = "approval_resolved"

#: Outcomes of recording a client ``message_id``: a fresh message, a retry of the same one, or a retry
#: that tries to rewrite an already accepted payload (which must fail closed).
INBOUND_NEW = "new"
INBOUND_DUPLICATE = "duplicate"
INBOUND_CONFLICT = "conflict"

PLUGIN_NAME = "kissne_mobile"
#: Default validity window of a pairing code: 5 minutes (the ticket's "short-lived").
DEFAULT_PAIRING_TTL_SECONDS = 300.0
#: Leading marker of both pairing codes and device tokens, so a leaked string is recognisable.
TOKEN_PREFIX = "kbm1_"
_FINGERPRINT_CHARS = 12
_PAIRING_MARK = "p"
_DEVICE_MARK = "d"

logger = logging.getLogger(__name__)


class PairingError(Exception):
    """Base class for refused registrations."""


class PairingCodeInvalid(PairingError):
    """No pairing code matches the presented value (typo, forged, or already pruned)."""


class PairingCodeExpired(PairingError):
    """The pairing code was issued but its short validity window has passed."""


class PairingCodeReplayed(PairingError):
    """The pairing code was already consumed — pairing codes are single-use."""


def _digest(secret: str) -> str:
    """SHA-256 hex digest of a secret; the only representation ever written to disk or logged."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _fingerprint(digest: str) -> str:
    """Short, non-reversible label for log lines — never the secret, never the whole digest."""
    return digest[:_FINGERPRINT_CHARS]


class DeviceStore:
    """Persistent device registry. ``DeviceStore()`` over the same home is a restart."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        logger.debug("[kissne_mobile] device store opened")

    # -- lifecycle ---------------------------------------------------------------------------------

    def _connect(self) -> None:
        from plugins.plugin_storage import plugin_db

        conn = plugin_db(PLUGIN_NAME)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                token_hash      TEXT PRIMARY KEY,
                installation_id TEXT NOT NULL,
                scope           TEXT NOT NULL DEFAULT 'device',
                created_at      REAL NOT NULL,
                last_seen_at    REAL,
                revoked_at      REAL
            );
            CREATE TABLE IF NOT EXISTS pairing_codes (
                code_hash                 TEXT PRIMARY KEY,
                created_at                REAL NOT NULL,
                expires_at                REAL NOT NULL,
                redeemed_at               REAL,
                redeemed_installation_id  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_devices_installation ON devices (installation_id);
            CREATE TABLE IF NOT EXISTS outbound_events (
                installation_id TEXT NOT NULL,
                seq             INTEGER NOT NULL,
                turn_id         TEXT,
                event_type      TEXT NOT NULL,
                payload         TEXT NOT NULL,
                created_at      REAL NOT NULL,
                PRIMARY KEY (installation_id, seq)
            );
            CREATE TABLE IF NOT EXISTS turns (
                turn_id         TEXT PRIMARY KEY,
                installation_id TEXT NOT NULL,
                state           TEXT NOT NULL,
                created_at      REAL NOT NULL,
                updated_at      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inbound_seen (
                installation_id   TEXT NOT NULL,
                client_message_id TEXT NOT NULL,
                payload_hash      TEXT NOT NULL,
                turn_id           TEXT NOT NULL,
                created_at        REAL NOT NULL,
                PRIMARY KEY (installation_id, client_message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_outbound_installation ON outbound_events (installation_id, seq);
            CREATE INDEX IF NOT EXISTS idx_turns_installation ON turns (installation_id, state);
            -- Sequence numbers must never be reused: acked events are DELETED, so deriving the next
            -- sequence from MAX(seq) would restart at 1 and hand a device a cursor it has already passed.
            CREATE TABLE IF NOT EXISTS attachment_messages (
                installation_id TEXT NOT NULL,
                turn_id         TEXT NOT NULL,
                text            TEXT NOT NULL DEFAULT '',
                attachments     TEXT NOT NULL,
                created_at      REAL NOT NULL,
                PRIMARY KEY (installation_id, turn_id)
            );
            CREATE INDEX IF NOT EXISTS idx_attachment_messages_installation
                ON attachment_messages (installation_id, created_at);
            CREATE TABLE IF NOT EXISTS timeline_notices (
                installation_id TEXT NOT NULL,
                notice_id       TEXT NOT NULL,
                presentation    TEXT NOT NULL,
                text            TEXT NOT NULL,
                created_at      REAL NOT NULL,
                PRIMARY KEY (installation_id, notice_id)
            );
            CREATE INDEX IF NOT EXISTS idx_timeline_notices_installation
                ON timeline_notices (installation_id, created_at);
            CREATE TABLE IF NOT EXISTS reply_links (
                installation_id TEXT NOT NULL,
                turn_id         TEXT NOT NULL,
                reply_to        TEXT NOT NULL,
                quoted_role     TEXT NOT NULL,
                quoted_text     TEXT NOT NULL,
                created_at      REAL NOT NULL,
                PRIMARY KEY (installation_id, turn_id)
            );
            CREATE INDEX IF NOT EXISTS idx_reply_links_installation
                ON reply_links (installation_id, created_at);
            CREATE TABLE IF NOT EXISTS seq_counters (
                installation_id TEXT PRIMARY KEY,
                next_seq        INTEGER NOT NULL
            );
            """
        )
        conn.commit()
        self._conn = conn

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("device store is closed")
        return self._conn

    def close(self) -> None:
        """Release the database handle. Idempotent; a later call is a no-op."""
        with self._lock:
            conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # pragma: no cover - closing must never mask the caller's work
                logger.warning("[kissne_mobile] failed to close the device store", exc_info=True)
        logger.debug("[kissne_mobile] device store closed")

    # -- pairing -----------------------------------------------------------------------------------

    def issue_pairing_code(self, ttl_seconds: float = DEFAULT_PAIRING_TTL_SECONDS) -> str:
        """Mint a one-time registration secret valid for ``ttl_seconds``. Never logged in the clear."""
        ttl = float(ttl_seconds)
        if ttl <= 0:
            raise ValueError(f"pairing code ttl must be > 0 seconds, got {ttl_seconds!r}")
        code = f"{TOKEN_PREFIX}{_PAIRING_MARK}_{secrets.token_urlsafe(24)}"
        digest = _digest(code)
        now = time.time()
        with self._lock:
            conn = self._db()
            try:
                # Unredeemed expired codes are dead weight: pruned here so the table tracks live
                # registrations, while a *redeemed* row is kept as the replay evidence.
                conn.execute(
                    "DELETE FROM pairing_codes WHERE expires_at <= ? AND redeemed_at IS NULL", (now,)
                )
                conn.execute(
                    "INSERT INTO pairing_codes (code_hash, created_at, expires_at) VALUES (?, ?, ?)",
                    (digest, now, now + ttl),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        logger.info("[kissne_mobile] issued pairing code %s (ttl=%.1fs)", _fingerprint(digest), ttl)
        return code

    def redeem_pairing_code(self, code: str, installation_id: str) -> str:
        """Consume ``code`` once and return the PLAINTEXT device token for ``installation_id``.

        Raises :class:`PairingCodeInvalid` / :class:`PairingCodeExpired` / :class:`PairingCodeReplayed`
        — a code is accepted exactly once, and only inside its validity window.
        """
        if not isinstance(code, str) or not code.strip():
            raise PairingCodeInvalid("empty pairing code")
        installation = str(installation_id or "").strip()
        if not installation:
            raise ValueError("installation_id is required to redeem a pairing code")
        digest = _digest(code.strip())
        now = time.time()
        with self._lock:
            conn = self._db()
            row = conn.execute(
                "SELECT expires_at, redeemed_at FROM pairing_codes WHERE code_hash = ?", (digest,)
            ).fetchone()
            if row is None:
                logger.warning("[kissne_mobile] pairing code %s refused: unknown", _fingerprint(digest))
                raise PairingCodeInvalid("unknown pairing code")
            if row["redeemed_at"] is not None:
                logger.warning("[kissne_mobile] pairing code %s refused: already redeemed", _fingerprint(digest))
                raise PairingCodeReplayed("pairing code was already redeemed")
            if now >= float(row["expires_at"]):
                logger.warning("[kissne_mobile] pairing code %s refused: expired", _fingerprint(digest))
                raise PairingCodeExpired("pairing code expired")

            token = f"{TOKEN_PREFIX}{_DEVICE_MARK}_{secrets.token_urlsafe(32)}"
            token_hash = _digest(token)
            try:
                # The conditional UPDATE is the single-use gate: two concurrent redemptions both see
                # an unredeemed row, but only one can flip it.
                claimed = conn.execute(
                    "UPDATE pairing_codes SET redeemed_at = ?, redeemed_installation_id = ? "
                    "WHERE code_hash = ? AND redeemed_at IS NULL",
                    (now, installation, digest),
                )
                if claimed.rowcount != 1:
                    conn.rollback()
                    logger.warning("[kissne_mobile] pairing code %s refused: redemption race lost",
                                   _fingerprint(digest))
                    raise PairingCodeReplayed("pairing code was already redeemed")
                conn.execute(
                    "INSERT INTO devices (token_hash, installation_id, scope, created_at) "
                    "VALUES (?, ?, 'device', ?)",
                    (token_hash, installation, now),
                )
                conn.commit()
            except PairingError:
                raise
            except Exception:
                conn.rollback()
                raise
        logger.info("[kissne_mobile] paired installation %s with device token %s",
                    installation, _fingerprint(token_hash))
        return token

    # -- device tokens -----------------------------------------------------------------------------

    def authenticate(self, token: str) -> Optional[str]:
        """Installation id for a live token, or ``None`` when it is unknown or revoked."""
        if not isinstance(token, str) or not token.strip():
            return None
        digest = _digest(token.strip())
        with self._lock:
            conn = self._db()
            row = conn.execute(
                "SELECT installation_id, revoked_at FROM devices WHERE token_hash = ?", (digest,)
            ).fetchone()
            if row is None:
                logger.warning("[kissne_mobile] device token %s refused: unknown", _fingerprint(digest))
                return None
            if row["revoked_at"] is not None:
                logger.warning("[kissne_mobile] device token %s refused: revoked", _fingerprint(digest))
                return None
            installation = str(row["installation_id"])
            try:
                conn.execute("UPDATE devices SET last_seen_at = ? WHERE token_hash = ?", (time.time(), digest))
                conn.commit()
            except Exception:  # pragma: no cover - last-seen bookkeeping is best-effort
                conn.rollback()
                logger.debug("[kissne_mobile] last-seen update failed for token %s", _fingerprint(digest))
        logger.debug("[kissne_mobile] device token %s accepted for installation %s",
                     _fingerprint(digest), installation)
        return installation

    def revoke(self, token: str) -> bool:
        """Kill one device token. ``True`` when a live token was revoked, ``False`` otherwise.

        The revocation is a committed row, so it still holds after a Runtime restart.
        """
        if not isinstance(token, str) or not token.strip():
            return False
        digest = _digest(token.strip())
        with self._lock:
            conn = self._db()
            try:
                cursor = conn.execute(
                    "UPDATE devices SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                    (time.time(), digest),
                )
                conn.commit()
                revoked = cursor.rowcount == 1
            except Exception:
                conn.rollback()
                raise
        if revoked:
            logger.info("[kissne_mobile] revoked device token %s", _fingerprint(digest))
        else:
            logger.warning("[kissne_mobile] revoke ignored for device token %s (unknown or already revoked)",
                           _fingerprint(digest))
        return revoked

    def revoke_installation(self, installation_id: str) -> int:
        """Revoke every live token of one installation (lost/forfeited device). Returns the count."""
        installation = str(installation_id or "").strip()
        if not installation:
            return 0
        with self._lock:
            conn = self._db()
            try:
                cursor = conn.execute(
                    "UPDATE devices SET revoked_at = ? WHERE installation_id = ? AND revoked_at IS NULL",
                    (time.time(), installation),
                )
                conn.commit()
                count = int(cursor.rowcount)
            except Exception:
                conn.rollback()
                raise
        logger.info("[kissne_mobile] revoked %d device token(s) for installation %s", count, installation)
        return count

    def live_device_count(self) -> int:
        """Number of tokens that would currently authenticate (dashboard/health surface)."""
        with self._lock:
            row = self._db().execute(
                "SELECT COUNT(*) AS n FROM devices WHERE revoked_at IS NULL"
            ).fetchone()
        return int(row["n"]) if row is not None else 0

    # -- transport reliability ---------------------------------------------------------------------
    # Durable transport state for the Android client: the sequence-numbered outbound event stream with
    # explicit acknowledgement, the turn state machine, and inbound retry idempotency. All of it is
    # rows, not process memory, so a Runtime restart loses no reply and re-delivers no acked one. Still
    # deliberately free of conversation truth: a "turn" is a transport concept and no
    # installation→conversation mapping is kept here (see the module docstring).

    @staticmethod
    def _installation(value: str) -> str:
        installation = str(value or "").strip()
        if not installation:
            raise ValueError("installation_id is required")
        return installation

    def enqueue_event(self, installation_id: str, event_type: str, payload: Dict[str, Any],
                      turn_id: Optional[str] = None, *, cap: int = 200) -> int:
        """Append one outbound event; returns its sequence number (the cursor the device acks with)."""
        installation = self._installation(installation_id)
        body = payload if isinstance(payload, dict) else {"text": str(payload)}
        now = time.time()
        with self._lock:
            conn = self._db()
            try:
                # Allocate from the durable counter, never from MAX(seq): acked rows are DELETED, so MAX
                # would restart the numbering and strand a device at a cursor it has already passed.
                conn.execute(
                    "INSERT OR IGNORE INTO seq_counters (installation_id, next_seq) "
                    "SELECT ?, COALESCE(MAX(seq), 0) + 1 FROM outbound_events WHERE installation_id = ?",
                    (installation, installation),
                )
                conn.execute(
                    "UPDATE seq_counters SET next_seq = next_seq + 1 WHERE installation_id = ?",
                    (installation,),
                )
                row = conn.execute(
                    "SELECT next_seq FROM seq_counters WHERE installation_id = ?", (installation,)
                ).fetchone()
                seq = int(row["next_seq"]) - 1
                conn.execute(
                    "INSERT INTO outbound_events "
                    "(installation_id, seq, turn_id, event_type, payload, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (installation, seq, turn_id, str(event_type),
                     json.dumps(body, ensure_ascii=False), now),
                )
                if int(cap) > 0:
                    # A device that never acks must not grow the file without bound: the oldest events
                    # fall off once the window is exceeded (acknowledgement is the normal way they go).
                    conn.execute(
                        "DELETE FROM outbound_events WHERE installation_id = ? AND seq <= ?",
                        (installation, seq - int(cap)),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return seq

    def events_after(self, installation_id: str, cursor: int = 0, *,
                     limit: int = 200) -> List[Dict[str, Any]]:
        """Unacknowledged events after ``cursor``, oldest first. Reading never consumes anything."""
        installation = self._installation(installation_id)
        start = max(0, int(cursor or 0))
        with self._lock:
            rows = self._db().execute(
                "SELECT seq, turn_id, event_type, payload, created_at FROM outbound_events "
                "WHERE installation_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
                (installation, start, max(1, int(limit))),
            ).fetchall()
        events: List[Dict[str, Any]] = []
        for row in rows:
            try:
                decoded = json.loads(row["payload"])
            except (TypeError, ValueError):  # pragma: no cover - a corrupt row must not kill a poll
                decoded = {}
            event: Dict[str, Any] = dict(decoded) if isinstance(decoded, dict) else {"text": str(decoded)}
            event["type"] = str(row["event_type"])
            event["seq"] = int(row["seq"])
            event["turn_id"] = row["turn_id"]
            event.setdefault("created_at", float(row["created_at"]))
            events.append(event)
        return events

    def ack_events(self, installation_id: str, cursor: int) -> int:
        """Retire every event up to and including ``cursor``; returns how many were retired."""
        installation = self._installation(installation_id)
        upto = max(0, int(cursor or 0))
        with self._lock:
            conn = self._db()
            try:
                removed = conn.execute(
                    "DELETE FROM outbound_events WHERE installation_id = ? AND seq <= ?",
                    (installation, upto),
                )
                conn.commit()
                count = int(removed.rowcount or 0)
            except Exception:
                conn.rollback()
                raise
        logger.debug("[kissne_mobile] device acked up to %d for installation %s (%d retired)",
                     upto, _fingerprint(installation), count)
        return count

    def open_turn(self, turn_id: str, installation_id: str, *, state: str = TURN_PENDING) -> None:
        """Record a newly accepted inbound turn (the handle the device correlates events with)."""
        handle = str(turn_id or "").strip()
        if not handle:
            raise ValueError("turn_id is required")
        installation = self._installation(installation_id)
        now = time.time()
        with self._lock:
            conn = self._db()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO turns (turn_id, installation_id, state, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (handle, installation, str(state), now, now),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def turn(self, turn_id: str) -> Optional[Dict[str, Any]]:
        """One turn row (``installation_id`` / ``state``), or ``None`` when it never existed."""
        handle = str(turn_id or "").strip()
        if not handle:
            return None
        with self._lock:
            row = self._db().execute(
                "SELECT turn_id, installation_id, state, created_at, updated_at FROM turns "
                "WHERE turn_id = ?",
                (handle,),
            ).fetchone()
        return dict(row) if row is not None else None

    def set_turn_state(self, turn_id: str, state: str) -> bool:
        """Move a turn to ``state``; ``False`` when the turn does not exist."""
        handle = str(turn_id or "").strip()
        if not handle:
            return False
        with self._lock:
            conn = self._db()
            try:
                cursor = conn.execute(
                    "UPDATE turns SET state = ?, updated_at = ? WHERE turn_id = ?",
                    (str(state), time.time(), handle),
                )
                conn.commit()
                return int(cursor.rowcount or 0) == 1
            except Exception:
                conn.rollback()
                raise

    def close_turn(self, turn_id: str, state: str, *, from_state: str = TURN_PENDING) -> bool:
        """Close a turn only if it is still in ``from_state``.

        The conditional UPDATE is what keeps a race honest: a reply that arrives after the user
        cancelled the turn must not report the turn as completed, and a double cancel must not look
        like a success. Returns ``True`` when this call is the one that moved it.
        """
        handle = str(turn_id or "").strip()
        if not handle:
            return False
        with self._lock:
            conn = self._db()
            try:
                cursor = conn.execute(
                    "UPDATE turns SET state = ?, updated_at = ? WHERE turn_id = ? AND state = ?",
                    (str(state), time.time(), handle, str(from_state)),
                )
                conn.commit()
                return int(cursor.rowcount or 0) == 1
            except Exception:
                conn.rollback()
                raise

    def pending_turn_id(self, installation_id: str) -> Optional[str]:
        """The newest still-pending turn of one installation."""
        installation = self._installation(installation_id)
        with self._lock:
            row = self._db().execute(
                "SELECT turn_id FROM turns WHERE installation_id = ? AND state = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (installation, TURN_PENDING),
            ).fetchone()
        return str(row["turn_id"]) if row is not None else None

    def record_attachment_message(self, installation_id: str, turn_id: str, text: str,
                                  attachments: List[Dict[str, Any]]) -> None:
        """Persist presentation metadata only; never duplicate attachment binary bytes."""
        installation = self._installation(installation_id)
        handle = str(turn_id or "").strip()
        if not handle:
            raise ValueError("turn_id is required")
        safe = [{"type": str(x.get("type") or ""), "mime_type": str(x.get("mime_type") or ""),
                 "label": str(x.get("label") or "")}
                for x in (attachments or []) if isinstance(x, dict)]
        with self._lock:
            conn = self._db()
            conn.execute(
                "INSERT OR REPLACE INTO attachment_messages "
                "(installation_id, turn_id, text, attachments, created_at) VALUES (?, ?, ?, ?, ?)",
                (installation, handle, str(text or ""), json.dumps(safe, ensure_ascii=False), time.time()))
            conn.commit()

    def delete_attachment_message(self, installation_id: str, turn_id: str) -> None:
        """Remove presentation metadata for a turn that will never be part of history."""
        installation = self._installation(installation_id)
        handle = str(turn_id or "").strip()
        if not handle:
            return
        with self._lock:
            conn = self._db()
            conn.execute(
                "DELETE FROM attachment_messages WHERE installation_id = ? AND turn_id = ?",
                (installation, handle),
            )
            conn.commit()

    def attachment_messages(self, installation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        installation = self._installation(installation_id)
        with self._lock:
            rows = self._db().execute(
                "SELECT turn_id, text, attachments, created_at FROM attachment_messages "
                "WHERE installation_id = ? ORDER BY created_at DESC LIMIT ?",
                (installation, max(1, int(limit)))).fetchall()
        out = []
        for row in reversed(rows):
            try:
                attachments = json.loads(row["attachments"])
            except (TypeError, ValueError):
                attachments = []
            out.append({"turn_id": str(row["turn_id"]), "text": str(row["text"] or ""),
                        "attachments": attachments if isinstance(attachments, list) else [],
                        "created_at": float(row["created_at"])})
        return out

    def record_timeline_notice(self, installation_id: str, notice_id: str,
                               presentation: str, text: str) -> None:
        """Persist backend-authored timeline notices verbatim for later cross-session history."""
        installation = self._installation(installation_id)
        handle = str(notice_id or "").strip()
        if not handle:
            raise ValueError("notice_id is required")
        with self._lock:
            conn = self._db()
            conn.execute(
                "INSERT OR REPLACE INTO timeline_notices "
                "(installation_id, notice_id, presentation, text, created_at) VALUES (?, ?, ?, ?, ?)",
                (installation, handle, str(presentation or ""), str(text or ""), time.time()),
            )
            conn.commit()

    def timeline_notices(self, installation_id: str) -> List[Dict[str, Any]]:
        installation = self._installation(installation_id)
        with self._lock:
            rows = self._db().execute(
                "SELECT notice_id, presentation, text, created_at FROM timeline_notices "
                "WHERE installation_id = ? ORDER BY created_at ASC",
                (installation,),
            ).fetchall()
        return [
            {"notice_id": str(row["notice_id"]), "presentation": str(row["presentation"] or ""),
             "text": str(row["text"] or ""), "created_at": float(row["created_at"])}
            for row in rows
        ]

    def record_reply_link(self, installation_id: str, turn_id: str, reply_to: str,
                          quoted_role: str, quoted_text: str) -> None:
        """Persist one Mobile reply relation without copying Runtime conversation ownership."""
        installation = self._installation(installation_id)
        handle = str(turn_id or "").strip()
        target = str(reply_to or "").strip()
        if not handle or not target:
            raise ValueError("turn_id and reply_to are required")
        with self._lock:
            conn = self._db()
            conn.execute(
                "INSERT OR REPLACE INTO reply_links "
                "(installation_id, turn_id, reply_to, quoted_role, quoted_text, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (installation, handle, target, str(quoted_role or ""),
                 str(quoted_text or ""), time.time()),
            )
            conn.commit()

    def delete_reply_link(self, installation_id: str, turn_id: str) -> None:
        installation = self._installation(installation_id)
        handle = str(turn_id or "").strip()
        if not handle:
            return
        with self._lock:
            conn = self._db()
            conn.execute(
                "DELETE FROM reply_links WHERE installation_id = ? AND turn_id = ?",
                (installation, handle),
            )
            conn.commit()

    def reply_links(self, installation_id: str) -> List[Dict[str, Any]]:
        installation = self._installation(installation_id)
        with self._lock:
            rows = self._db().execute(
                "SELECT turn_id, reply_to, quoted_role, quoted_text, created_at FROM reply_links "
                "WHERE installation_id = ? ORDER BY created_at ASC",
                (installation,),
            ).fetchall()
        return [
            {"turn_id": str(row["turn_id"]), "reply_to": str(row["reply_to"]),
             "quoted_role": str(row["quoted_role"] or ""), "quoted_text": str(row["quoted_text"] or ""),
             "created_at": float(row["created_at"])}
            for row in rows
        ]

    def inbound_record(self, installation_id: str, client_message_id: str) -> Optional[Dict[str, Any]]:
        """The stored record of a client ``message_id``, or ``None`` when it is new."""
        installation = self._installation(installation_id)
        handle = str(client_message_id or "").strip()
        if not handle:
            return None
        with self._lock:
            row = self._db().execute(
                "SELECT turn_id, payload_hash, created_at FROM inbound_seen "
                "WHERE installation_id = ? AND client_message_id = ?",
                (installation, handle),
            ).fetchone()
        return dict(row) if row is not None else None

    def record_inbound(self, installation_id: str, client_message_id: str, payload_hash: str,
                       turn_id: str) -> str:
        """Claim a client ``message_id`` for ``turn_id``.

        Returns :data:`INBOUND_NEW` when the claim succeeded, :data:`INBOUND_DUPLICATE` when the same
        id arrived with the same payload before (a retry: the caller must not inject a second turn) or
        :data:`INBOUND_CONFLICT` when the same id arrived with a DIFFERENT payload (a client must never
        be able to rewrite an accepted turn, so the caller must fail closed).
        """
        installation = self._installation(installation_id)
        handle = str(client_message_id or "").strip()
        if not handle:
            raise ValueError("client_message_id is required")
        digest = str(payload_hash or "")
        now = time.time()
        with self._lock:
            conn = self._db()
            try:
                conn.execute(
                    "INSERT INTO inbound_seen "
                    "(installation_id, client_message_id, payload_hash, turn_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (installation, handle, digest, str(turn_id), now),
                )
                conn.commit()
                return INBOUND_NEW
            except sqlite3.IntegrityError:
                conn.rollback()
            except Exception:
                conn.rollback()
                raise
        existing = self.inbound_record(installation, handle) or {}
        if str(existing.get("payload_hash") or "") == digest:
            logger.info("[kissne_mobile] inbound %s for installation %s is a retry of turn %s",
                        _fingerprint(handle), _fingerprint(installation), existing.get("turn_id"))
            return INBOUND_DUPLICATE
        logger.warning("[kissne_mobile] inbound %s for installation %s reused with a different payload",
                       _fingerprint(handle), _fingerprint(installation))
        return INBOUND_CONFLICT

