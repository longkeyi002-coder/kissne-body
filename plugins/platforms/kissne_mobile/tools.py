"""kissne_mobile client tools: ``kissne_sticker_search`` over the user's sticker keyword index.

The sticker library lives on the paired Android device. The app pushes its full keyword list to
``POST /sticker-index`` (authoritative replace); keywords are also learned opportunistically from
inbound ``[表情包：...]`` markers so the tool works before the app ships the push. This module owns
the index file — schema ``{"keywords": [...], "count": N, "updated_at": ts}`` under the plugin's
data dir — so adapter (writer) and tool (reader) share one contract.

Toolset gating: registered under ``toolset="kissne_mobile"`` AND pinned by ``_DEFAULT_OFF_TOOLSETS``
+ ``_TOOLSET_PLATFORM_RESTRICTIONS`` in hermes_cli (verified: only kissne_mobile sessions resolve it;
weixin/cron/api/cli pay zero tokens for it).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List

from utils import atomic_json_write

logger = logging.getLogger(__name__)

INDEX_FILENAME = "sticker_index.json"
MAX_KEYWORDS = 5000
MAX_KEYWORD_LEN = 128
#: How many matches a single search returns to the model (keeps tool output token-cheap).
MAX_RESULTS = 20

_STICKER_MARKER_RE = re.compile(r"\[表情包：([^\]]+)\]")


def _index_path():
    from plugins.plugin_storage import plugin_data_dir  # lazy: follows the active profile

    return plugin_data_dir("kissne_mobile") / INDEX_FILENAME


def load_sticker_index() -> Dict[str, Any]:
    """The stored index, or ``{}`` when missing/corrupt (never raises — a broken index must not
    break a session)."""
    try:
        data = json.loads(_index_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def write_sticker_index(keywords: List[str]) -> int:
    """Replace the index with the app-pushed library (authoritative). Returns the stored count."""
    payload = {"keywords": keywords, "count": len(keywords), "updated_at": time.time()}
    atomic_json_write(_index_path(), payload)
    return len(keywords)


def learn_sticker_keywords(text: str) -> bool:
    """Merge keywords from inbound ``[表情包：X]`` markers into the index.

    Best-effort and swallow-all by design: observation must never break message ingestion
    (the caller must not need a try/except). Returns True when the index changed.
    """
    try:
        found = []
        for match in _STICKER_MARKER_RE.finditer(text or ""):
            keyword = match.group(1).strip()
            if keyword and len(keyword) <= MAX_KEYWORD_LEN:
                found.append(keyword)
        if not found:
            return False
        data = load_sticker_index()
        keywords = [str(k) for k in data.get("keywords") or []]
        known = set(keywords)
        changed = False
        for keyword in found:
            if keyword not in known and len(keywords) < MAX_KEYWORDS:
                keywords.append(keyword)
                known.add(keyword)
                changed = True
        if not changed:
            return False
        payload = {"keywords": keywords, "count": len(keywords), "updated_at": time.time()}
        atomic_json_write(_index_path(), payload)
        return True
    except Exception:  # noqa: BLE001 — observation is a side channel, never fatal
        logger.debug("[kissne_mobile] sticker keyword observation failed", exc_info=True)
        return False


def _sticker_index_available() -> bool:
    """check_fn: hide the tool's schema until there is something to search (saves ~schema tokens
    per turn before the first sticker/push)."""
    return bool(load_sticker_index().get("keywords"))


def _search_sticker(args: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    """``task_id``/``session_id``/``user_task`` ride along as kwargs (every tool gets them) — accept
    and ignore, so dispatch never dies before reading the query."""
    query = str(args.get("query") or "").strip().lower()
    keywords = [str(k) for k in load_sticker_index().get("keywords") or []]
    if not keywords:
        return {
            "ok": False,
            "error": "sticker_index_empty",
            "hint": "The app has not synced a sticker library yet; reply with plain text only.",
        }
    if not query:
        return {"ok": True, "matches": keywords[:MAX_RESULTS], "library_size": len(keywords)}
    matches = [k for k in keywords if query in k.lower()]
    return {
        "ok": True,
        "matches": matches[:MAX_RESULTS],
        "total_matches": len(matches),
        "library_size": len(keywords),
    }


_DESCRIPTION = (
    "Search the user's Kissne sticker library for a sticker you can send. Returns exact keyword "
    "strings; send one by writing the marker [表情包：<keyword>] in your reply text — the app "
    "renders the real sticker. Use ONLY returned keywords, never invent one. No match (or the "
    "index is empty) means reply with plain text instead."
)


def register_tools(ctx) -> None:
    """Register ``kissne_sticker_search`` in the ``kissne_mobile`` toolset (kissne-only by gate)."""
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Substring to search, e.g. a mood or character name (any language).",
            },
        },
        "required": ["query"],
    }
    ctx.register_tool(
        name="kissne_sticker_search",
        toolset="kissne_mobile",
        handler=_search_sticker,
        description=_DESCRIPTION,
        schema={"name": "kissne_sticker_search", "description": _DESCRIPTION, "parameters": parameters},
        emoji="\U0001f3a8",  # artist palette
        check_fn=_sticker_index_available,
    )
