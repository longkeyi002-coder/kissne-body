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
import logging
import secrets
import sqlite3
import threading
import time
from typing import Optional

__all__ = [
    "PLUGIN_NAME",
    "DEFAULT_PAIRING_TTL_SECONDS",
    "TOKEN_PREFIX",
    "PairingError",
    "PairingCodeInvalid",
    "PairingCodeExpired",
    "PairingCodeReplayed",
    "DeviceStore",
]

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
