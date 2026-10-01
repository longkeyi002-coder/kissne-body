"""Transport provenance only; conversation ownership remains in the Runtime session store."""
from __future__ import annotations


def remember_turn(adapter, installation: str, turn_id: str) -> dict:
    identity = adapter._conversation_identity(installation) or {}
    session_id = str(identity.get("session_id") or "")
    if session_id:
        cache = getattr(adapter, "_turn_delivery_sessions", None)
        if cache is None:
            cache = adapter._turn_delivery_sessions = {}
        cache[(installation, turn_id)] = session_id
        while len(cache) > 1024:
            cache.pop(next(iter(cache)))
    return {"session_id": session_id} if session_id else {}


def turn_session(adapter, installation: str, turn_id: str) -> str:
    if not turn_id:
        return ""
    key = (installation, turn_id)
    cache = getattr(adapter, "_turn_delivery_sessions", {})
    if key in cache:
        return cache[key]
    # A resumed turn is resolved from the authoritative owning store, never the
    # installation's currently selected room. No new conversation table is kept.
    store = getattr(adapter, "_session_store", None)
    if store is None:
        return ""
    db = store._db_for_key(adapter.mobile_session_key(installation))
    if db is None:
        return ""
    row = db._read_one(
        "SELECT session_id FROM messages WHERE platform_message_id = ? ORDER BY id DESC LIMIT 1",
        (turn_id,),
    )
    session_id = str(row["session_id"]) if row else ""
    if session_id:
        cache = getattr(adapter, "_turn_delivery_sessions", None)
        if cache is None:
            cache = adapter._turn_delivery_sessions = {}
        cache[key] = session_id
        while len(cache) > 1024:
            cache.pop(next(iter(cache)))
    return session_id
