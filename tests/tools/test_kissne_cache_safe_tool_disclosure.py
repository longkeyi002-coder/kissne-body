"""Static contract tests for cache-safe progressive tool disclosure.

These tests deliberately avoid changing the production defer set. They define the
properties Kissne requires before any additional core tool can move behind Tool Search:
1. deterministic, byte-stable model-visible schemas for the same capability set;
2. catalog growth must not perturb the stable visible prefix;
3. adding deferred tools must cost materially less than exposing their full schemas;
4. unknown tools fail open (remain visible) instead of disappearing.

Live model success/latency/cache-read behavior remains covered by evals/tool_search.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def _td(name: str, description: str = "", payload_chars: int = 0) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "string",
                        "description": "x" * payload_chars,
                    },
                },
            },
        },
    }


def _wire_bytes(defs) -> bytes:
    return json.dumps(defs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def test_same_capability_set_is_byte_stable():
    from tools.tool_search import ToolSearchConfig, assemble_tool_defs

    cfg = ToolSearchConfig.from_raw({
        "enabled": "on",
        "listing": "auto",
        "listing_max_tokens": 1800,
        "defer": ["computer_use", "text_to_speech"],
    })
    defs = [
        _td("memory", "Persistent memory", 200),
        _td("text_to_speech", "Speak text aloud", 700),
        _td("computer_use", "Drive the OS", 900),
    ]

    first = assemble_tool_defs(defs, context_length=200_000, config=cfg)
    second = assemble_tool_defs(list(reversed(defs)), context_length=200_000, config=cfg)

    # Stable-prefix/cache contract: registry discovery order must not change the
    # bytes sent to the provider for an equivalent capability set.
    assert _wire_bytes(first.tool_defs) == _wire_bytes(second.tool_defs)


def test_deferred_catalog_growth_preserves_visible_prefix():
    from tools.tool_search import ToolSearchConfig, assemble_tool_defs

    cfg = ToolSearchConfig.from_raw({
        "enabled": "on",
        "listing": "auto",
        "listing_max_tokens": 1800,
        "defer": ["computer_use", "text_to_speech", "session_search"],
    })
    base = [
        _td("memory", "Persistent memory", 300),
        _td("computer_use", "Drive the OS", 900),
    ]
    grown = base + [
        _td("text_to_speech", "Speak text aloud", 900),
        _td("session_search", "Search previous sessions", 900),
    ]

    before = assemble_tool_defs(base, context_length=200_000, config=cfg)
    after = assemble_tool_defs(grown, context_length=200_000, config=cfg)

    # The directly-visible working set is the provider-cache prefix. Future
    # deferred/plugin growth may change the bridge suffix, never this prefix.
    assert _wire_bytes(before.tool_defs[:1]) == _wire_bytes(after.tool_defs[:1])


def test_deferred_growth_has_sublinear_wire_cost():
    from tools.tool_search import ToolSearchConfig, assemble_tool_defs

    deferred = [f"future_tool_{i}" for i in range(40)]
    cfg = ToolSearchConfig.from_raw({
        "enabled": "on",
        "listing": "auto",
        "listing_max_tokens": 1800,
        "defer": deferred,
    })
    defs = [_td("memory", "Persistent memory", 300)]
    defs += [_td(name, f"Future capability {i}", 1200) for i, name in enumerate(deferred)]

    eager_bytes = len(_wire_bytes(defs))
    assembled = assemble_tool_defs(defs, context_length=200_000, config=cfg)
    lazy_bytes = len(_wire_bytes(assembled.tool_defs))

    assert assembled.activated
    assert assembled.deferred_count == len(deferred)
    # Architectural growth gate: adding many future capabilities must not make
    # the ordinary request carry anything close to their complete schemas.
    assert lazy_bytes < eager_bytes * 0.35


def test_unknown_capability_fails_open_visible():
    from tools.tool_search import ToolSearchConfig, assemble_tool_defs

    cfg = ToolSearchConfig.from_raw({"enabled": "on"})
    unknown = _td("kissne_future_unregistered_tool", "Future capability", 800)
    assembled = assemble_tool_defs([unknown], context_length=200_000, config=cfg)

    assert not assembled.activated
    assert assembled.tool_defs == [unknown]
