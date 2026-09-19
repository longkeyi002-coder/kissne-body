"""Deterministic guard for degenerate, no-progress assistant output.

This is deliberately local and conservative: no embeddings, no LLM judge, no external
calls. It catches a response that keeps producing near-duplicate prose paragraphs while
making no tool call. Streaming callers can stop consuming the provider stream early;
non-streaming callers use the same classifier after the response arrives.

The older agent.repetition_guard detects long verbatim repetition inside one truncated
fragment. This module targets a different shape: multiple paragraphs that say substantially
the same thing with small wording changes.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Deque

FINISH_REASON = "degenerate_repetition"
SYNTHETIC_FLAG = "_degenerate_guard_nudge"
RECOVERY_NUDGE = (
    "Internal recovery: your previous response was stopped because it repeated the same "
    "analysis without new evidence. Do not restate hypotheses or announce another check. "
    "Either make one concrete tool call now, or answer briefly with only verified facts "
    "and what remains unknown."
)
RECOVERY_PLACEHOLDER = "[repetitive no-progress output stopped by runtime guard]"

DEFAULT_ENABLED = True
MIN_TOTAL_CHARS = 6000
MIN_BLOCK_CHARS = 80
MAX_COMPARE_CHARS = 900
HISTORY_BLOCKS = 48
RECENT_BLOCKS = 16
REPEAT_HITS = 3
SEQUENCE_RATIO = 0.80
TOKEN_JACCARD = 0.50

_SPLIT_RE = re.compile(r"\n\s*\n")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_NON_WORD_RE = re.compile(r"[^0-9a-z_<>一-鿿]+")
_TOKEN_RE = re.compile(r"[0-9a-z_<>]+|[一-鿿]+")
_LISTISH_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|\|)")
_LOGISH_RE = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}[T\s]|\d{2}:\d{2}:\d{2}\b|"
    r"(?:DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL)\b|Traceback\b)",
    re.IGNORECASE,
)


def resolve_guard_enabled(section: Any) -> bool:
    """Resolve agent.degenerate_response_guard.enabled; malformed input uses the default."""
    if not isinstance(section, dict):
        return DEFAULT_ENABLED
    raw = section.get("enabled", DEFAULT_ENABLED)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in {"0", "false", "no", "off"}:
            return False
        if value in {"1", "true", "yes", "on"}:
            return True
    return DEFAULT_ENABLED


def _normalize_block(text: str) -> str:
    text = _NUMBER_RE.sub("<n>", text.lower())
    text = _NON_WORD_RE.sub(" ", text)
    return " ".join(text.split())[:MAX_COMPARE_CHARS]


def _tokenize(normalized: str) -> frozenset[str]:
    """Word tokens for Latin text plus CJK bigrams so Chinese prose is not one token."""
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(normalized):
        value = match.group(0)
        if value and all("一" <= ch <= "鿿" for ch in value):
            if len(value) == 1:
                tokens.append(value)
            else:
                tokens.extend(value[i : i + 2] for i in range(len(value) - 1))
        else:
            tokens.append(value)
    return frozenset(tokens)


def _looks_structured(text: str) -> bool:
    """Skip code, tables, enumerations and log dumps; repeated structure can be legitimate."""
    stripped = text.strip()
    if not stripped:
        return True
    if "```" in stripped or "~~~" in stripped:
        return True
    lines = [line for line in stripped.splitlines() if line.strip()]
    # A single numbered/bulleted/log paragraph may be separated by blank lines in a
    # perfectly legitimate report. Treat its leading marker as structured too.
    if lines and (_LISTISH_RE.search(lines[0]) or _LOGISH_RE.search(lines[0])):
        return True
    if len(lines) >= 3:
        structured = sum(
            bool(_LISTISH_RE.search(line) or _LOGISH_RE.search(line)) for line in lines
        )
        if structured / len(lines) >= 0.60:
            return True
    if len(lines) >= 2 and sum("|" in line for line in lines) / len(lines) >= 0.60:
        return True
    return False


@dataclass(frozen=True)
class _Block:
    normalized: str
    tokens: frozenset[str]


class DegenerateResponseGuard:
    """Incremental near-duplicate paragraph detector with conservative fail-open gates."""

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self.total_chars = 0
        self._buffer = ""
        self._history: Deque[_Block] = deque(maxlen=HISTORY_BLOCKS)
        self._recent_hits: Deque[bool] = deque(maxlen=RECENT_BLOCKS)
        self.tripped = False
        self.trip_at_chars: int | None = None

    def feed(self, text: str) -> bool:
        if self.tripped:
            return True
        if not self.enabled or not isinstance(text, str) or not text:
            return False
        self.total_chars += len(text)
        self._buffer += text.replace("\r\n", "\n")
        parts = _SPLIT_RE.split(self._buffer)
        self._buffer = parts.pop() if parts else ""
        for part in parts:
            if self._observe_block(part):
                return True
        return False

    def finish(self) -> bool:
        if self.tripped or not self.enabled:
            return self.tripped
        tail, self._buffer = self._buffer, ""
        if tail:
            self._observe_block(tail)
        return self.tripped

    def _observe_block(self, raw: str) -> bool:
        raw = raw.strip()
        if len(raw) < MIN_BLOCK_CHARS or _looks_structured(raw):
            return False
        normalized = _normalize_block(raw)
        if len(normalized) < MIN_BLOCK_CHARS:
            return False
        tokens = _tokenize(normalized)
        if len(tokens) < 10:
            return False

        repeat = any(_near_duplicate(normalized, tokens, prior) for prior in self._history)
        self._history.append(_Block(normalized=normalized, tokens=tokens))
        self._recent_hits.append(repeat)
        if self.total_chars >= MIN_TOTAL_CHARS and sum(self._recent_hits) >= REPEAT_HITS:
            self.tripped = True
            self.trip_at_chars = self.total_chars
            return True
        return False


def _near_duplicate(normalized: str, tokens: frozenset[str], prior: _Block) -> bool:
    union = tokens | prior.tokens
    if not union:
        return False
    jaccard = len(tokens & prior.tokens) / len(union)
    if jaccard < TOKEN_JACCARD:
        return False
    return SequenceMatcher(None, normalized, prior.normalized, autojunk=False).ratio() >= SEQUENCE_RATIO


def is_degenerate_response(text: str, *, enabled: bool = True) -> bool:
    guard = DegenerateResponseGuard(enabled=enabled)
    guard.feed(text or "")
    return guard.finish()
