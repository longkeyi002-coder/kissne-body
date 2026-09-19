"""Request-only projection for old tool calls, tool results, and image attachments.

The durable transcript remains lossless. This module only removes expensive,
replayable payloads from messages that are about to be sent again on a later
turn. The current turn is deliberately excluded by the caller because tool
calls, results, and images may still be needed by the active tool loop.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_IMAGE_PART_TYPES = frozenset({"image", "image_url", "input_image"})
_TEXT_PART_TYPES = frozenset({"text", "input_text", "output_text"})
_MAX_TOOL_ARGUMENT_CHARS = 256
_MAX_ARGUMENT_VALUE_CHARS = 64
_MAX_TOOL_RESULT_CHARS = 1536
_TOOL_RESULT_HEAD_CHARS = 896
_TOOL_RESULT_TAIL_CHARS = 384
_SENSITIVE_KEY_RE = re.compile(
    r"(?:api[_-]?key|token|secret|password|authorization|cookie)",
    re.IGNORECASE,
)


def _image_fingerprint(part: dict[str, Any]) -> str:
    """Return a stable short id without retaining the image data in the prompt."""
    image_value: Any = part.get("image_url")
    if isinstance(image_value, dict):
        image_value = image_value.get("url") or image_value.get("source") or image_value
    if image_value is None:
        image_value = part.get("source") or part.get("data") or part
    raw = str(image_value)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]


def _image_placeholder(part: dict[str, Any]) -> dict[str, str]:
    return {
        "type": "text",
        "text": f"[historical image omitted; asset={_image_fingerprint(part)}]",
    }


def _compact_tool_result_text(content: str) -> str:
    """Keep a bounded head/tail view of a large historical tool result."""
    if len(content) <= _MAX_TOOL_RESULT_CHARS:
        return content
    digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]
    omitted = max(0, len(content) - _TOOL_RESULT_HEAD_CHARS - _TOOL_RESULT_TAIL_CHARS)
    return (
        content[:_TOOL_RESULT_HEAD_CHARS]
        + "\n[historical tool result compacted; "
        + f"omitted={omitted}; chars={len(content)}; sha256={digest}]\n"
        + content[-_TOOL_RESULT_TAIL_CHARS:]
    )


def _project_content(content: Any, *, compact_text: bool = False) -> Any:
    if not isinstance(content, list):
        return content
    changed = False
    projected = []
    for part in content:
        if isinstance(part, dict) and part.get("type") in _IMAGE_PART_TYPES:
            projected.append(_image_placeholder(part))
            changed = True
            continue
        if (
            compact_text
            and isinstance(part, dict)
            and part.get("type") in _TEXT_PART_TYPES
            and isinstance(part.get("text"), str)
        ):
            new_text = _compact_tool_result_text(part["text"])
            if new_text != part["text"]:
                new_part = dict(part)
                new_part["text"] = new_text
                projected.append(new_part)
                changed = True
                continue
        projected.append(part)
    return projected if changed else content


def _short_value(value: Any) -> Any:
    if isinstance(value, str):
        return (
            value
            if len(value) <= _MAX_ARGUMENT_VALUE_CHARS
            else value[:_MAX_ARGUMENT_VALUE_CHARS] + "…"
        )
    if isinstance(value, list):
        return [_short_value(item) for item in value[:6]] + (["…"] if len(value) > 6 else [])
    if isinstance(value, dict):
        return {
            str(key): "[redacted]"
            if _SENSITIVE_KEY_RE.search(str(key))
            else _short_value(value[key])
            for key in list(value)[:12]
        }
    return value


def _minimal_tool_argument_marker(input_chars: int) -> str:
    return json.dumps(
        {"_context_compacted": True, "input_chars": input_chars},
        separators=(",", ":"),
    )


def _project_tool_arguments(arguments: Any, name: str) -> Any:
    """Keep tiny calls intact; replace larger historical inputs with bounded valid JSON."""
    if not isinstance(arguments, str) or len(arguments) <= _MAX_TOOL_ARGUMENT_CHARS:
        return arguments
    try:
        parsed = json.loads(arguments)
    except (TypeError, ValueError):
        return _minimal_tool_argument_marker(len(arguments))

    compact = {
        "_context_compacted": True,
        "tool": name,
        "input": _short_value(parsed),
        "input_chars": len(arguments),
    }
    result = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    if len(result) <= _MAX_TOOL_ARGUMENT_CHARS:
        return result
    # Never slice serialized JSON: providers expect tool-call arguments to remain
    # syntactically valid even when the call is historical.
    return _minimal_tool_argument_marker(len(arguments))


def project_historical_message(message: dict[str, Any]) -> dict[str, Any]:
    """Project one historical message for a provider request.

    Only the request copy is changed. Tool-call structure and ids remain intact
    so providers still see a valid assistant→tool pair. Large arguments become
    bounded metadata, old tool results keep only a bounded head/tail view, and
    image parts become short asset references.
    """
    projected = dict(message)
    is_tool_result = projected.get("role") == "tool"

    if "content" in projected:
        content = projected["content"]
        if is_tool_result and isinstance(content, str):
            projected["content"] = _compact_tool_result_text(content)
        else:
            projected["content"] = _project_content(content, compact_text=is_tool_result)

    tool_calls = projected.get("tool_calls")
    if isinstance(tool_calls, list):
        new_calls = []
        changed = False
        for call in tool_calls:
            if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                new_calls.append(call)
                continue
            function = dict(call["function"])
            old_arguments = function.get("arguments")
            new_arguments = _project_tool_arguments(
                old_arguments, str(function.get("name") or "")
            )
            if new_arguments != old_arguments:
                function["arguments"] = new_arguments
                changed = True
            new_call = dict(call)
            new_call["function"] = function
            new_calls.append(new_call)
        if changed:
            projected["tool_calls"] = new_calls
    return projected


__all__ = ["project_historical_message"]
