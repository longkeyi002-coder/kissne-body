"""Kissne's first context substrate for Hermes.

The substrate separates the inputs to a model request without changing the
existing persistence format:

``stable_core``
    The byte-stable identity/instruction prefix.  It is rebuilt only at the
    same boundaries as Hermes' cached system prompt.
``snapshot``
    Session-start (or post-compaction) context that is read-only during a
    turn.  The first integration stores Hermes' existing non-stable prompt
    tier here; later layers can replace its producer without changing the
    request seam.
``history``
    The persisted conversation projected for this request.  Read-time
    filtering returns a new list and never mutates SessionDB state.
``live_delta``
    Per-request material such as memory recall and gateway/plugin context.
    It is deliberately not added to the cached system prompt.

This module is intentionally small.  It is an adapter boundary, not a second
memory store or a second transcript database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence


def _join_prompt_parts(*parts: str) -> str:
    """Join prompt parts using Hermes' existing blank-line convention."""
    return "\n\n".join(part.strip() for part in parts if isinstance(part, str) and part.strip())


def _role(message: Any) -> str:
    return message.get("role", "") if isinstance(message, Mapping) else ""


@dataclass(frozen=True)
class ContextReadPolicy:
    """Read-time policy for a request-local history projection.

    The default is deliberately identity-like.  ``history_limit`` is an
    opt-in escape hatch for a future router/retriever; it counts messages from
    the history *before* the current turn and always preserves the current
    turn.  Trimming starts on a user boundary so assistant/tool pairs are not
    split.  A request that cannot be trimmed safely is returned unchanged.
    """

    include_stable_core: bool = True
    include_snapshot: bool = True
    history_limit: Optional[int] = None

    def select_history(
        self,
        history: Sequence[Mapping[str, Any]],
        *,
        current_turn_user_index: Optional[int] = None,
    ) -> list[Mapping[str, Any]]:
        """Return a request-only history projection without mutating *history*."""
        source = list(history)
        if not source or self.history_limit is None:
            return source
        if not isinstance(self.history_limit, int) or isinstance(self.history_limit, bool):
            return source
        if self.history_limit < 0:
            return source

        current = current_turn_user_index
        if not isinstance(current, int) or current < 0 or current > len(source):
            current = len(source)

        before_current = source[:current]
        current_turn = source[current:]
        if len(before_current) <= self.history_limit:
            return source

        cut = len(before_current) - self.history_limit
        # A transcript can begin with a user row, but a provider/tool repair or
        # a custom caller may hand us an incomplete prefix.  Move the cut back
        # to a user boundary; if no safe boundary exists, fail open.
        while cut < len(before_current) and _role(before_current[cut]) != "user":
            cut += 1
        if cut >= len(before_current):
            return source

        selected = before_current[cut:] + current_turn
        if not selected or _role(selected[0]) not in {"user", "system"}:
            return source
        return selected


@dataclass(frozen=True)
class ContextLayers:
    """The five logical inputs used to construct one model request."""

    stable_core: str = ""
    snapshot: str = ""
    history: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    live_delta: str = ""

    def system_prompt(self, policy: Optional[ContextReadPolicy] = None) -> str:
        """Render only the cached system-side layers.

        ``live_delta`` is intentionally excluded.  Callers inject it through
        the existing API-time user-message sidecar path so the system prefix
        stays byte-stable.
        """
        policy = policy or ContextReadPolicy()
        return _join_prompt_parts(
            self.stable_core if policy.include_stable_core else "",
            self.snapshot if policy.include_snapshot else "",
        )

    def read(
        self,
        *,
        policy: Optional[ContextReadPolicy] = None,
        current_turn_user_index: Optional[int] = None,
        history: Optional[Iterable[Mapping[str, Any]]] = None,
        live_delta: Optional[str] = None,
    ) -> "ContextRead":
        """Create a request-local read view.

        The returned history is a new list.  Neither the supplied history nor
        the layer object is changed, which makes this safe at retry and
        provider-fallback boundaries.
        """
        policy = policy or ContextReadPolicy()
        source = tuple(history) if history is not None else self.history
        selected = policy.select_history(
            source, current_turn_user_index=current_turn_user_index
        )
        return ContextRead(
            stable_core=self.stable_core,
            snapshot=self.snapshot,
            history=tuple(selected),
            live_delta=self.live_delta if live_delta is None else str(live_delta or ""),
            policy=policy,
        )


@dataclass(frozen=True)
class ContextRead:
    """Immutable request-local view produced by :meth:`ContextLayers.read`."""

    stable_core: str
    snapshot: str
    history: tuple[Mapping[str, Any], ...]
    live_delta: str
    policy: ContextReadPolicy

    @property
    def system_prompt(self) -> str:
        return _join_prompt_parts(
            self.stable_core if self.policy.include_stable_core else "",
            self.snapshot if self.policy.include_snapshot else "",
        )


def make_context_layers(
    *,
    stable_core: str = "",
    snapshot: str = "",
    history: Iterable[Mapping[str, Any]] = (),
    live_delta: str = "",
) -> ContextLayers:
    """Normalize boundary inputs into an immutable layer object."""
    return ContextLayers(
        stable_core=str(stable_core or ""),
        snapshot=str(snapshot or ""),
        history=tuple(history or ()),
        live_delta=str(live_delta or ""),
    )


__all__ = [
    "ContextLayers",
    "ContextRead",
    "ContextReadPolicy",
    "make_context_layers",
]
