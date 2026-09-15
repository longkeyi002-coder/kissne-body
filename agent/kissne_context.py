"""Kissne semantic context boundary on top of Hermes.

Hermes cache tiers are an implementation detail. They are deliberately kept
separate from Kissne semantics:

SOUL -> stable_core
SELF + memory -> session_snapshot
persisted transcript -> unified_history
per-turn memory lookup -> turn_recall
per-provider-call state -> live_delta

Unified History is the truth of what happened. Turn Recall and Live Delta are
request-local inputs and must never be written back as conversation history.
Hermes ContextEngine.select_context remains the single read-time filtering
extension point; this module does not create a second filtering pipeline or
memory store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional


def _join_prompt_parts(*parts: str) -> str:
    return "\n\n".join(
        part.strip() for part in parts
        if isinstance(part, str) and part.strip()
    )


def _now() -> datetime:
    from hermes_time import now as hermes_now
    return hermes_now()


def _timezone_for(moment: datetime):
    from hermes_time import get_timezone
    if moment.tzinfo is not None:
        return moment.tzinfo
    return get_timezone()


def _iso_seconds(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_timezone_for(moment))
    return moment.isoformat(timespec="seconds")


def _zone_label(moment: datetime) -> str:
    tz = _timezone_for(moment)
    name = getattr(tz, "key", None) or moment.tzname() or "local"
    offset = moment.strftime("%z")
    if offset:
        offset = f"UTC{offset[:3]}:{offset[3:]}"
        return f"{name}, {offset}" if name != offset else offset
    return name


@dataclass(frozen=True)
class SessionSnapshot:
    """SELF and memory frozen at one explicit session lifecycle boundary."""

    self_state: str = ""
    memory_state: str = ""
    captured_at: str = ""
    origin: str = "fresh_session"

    def render(self) -> str:
        return _join_prompt_parts(self.self_state, self.memory_state)


@dataclass(frozen=True)
class LiveDelta:
    """Structured state evaluated for exactly one provider request."""

    exact_earth_time: str
    timezone: str
    source: str = "hermes_time"
    earth_state: str = ""
    ai_world_state: str = ""

    def render(self) -> str:
        lines = [
            "<kissne_live_delta>",
            f"Exact Earth time: {self.exact_earth_time}",
            f"Timezone: {self.timezone}",
            f"Clock source: {self.source}",
        ]
        if self.earth_state.strip():
            lines.extend(["Earth state:", self.earth_state.strip()])
        if self.ai_world_state.strip():
            lines.extend(["AI World state:", self.ai_world_state.strip()])
        lines.append("</kissne_live_delta>")
        return "\n".join(lines)


def build_live_delta(
    *,
    moment: Optional[datetime] = None,
    source: str = "hermes_time",
    earth_state: str = "",
    ai_world_state: str = "",
) -> LiveDelta:
    """Evaluate exact time and optional world state at API-call time."""
    current = moment or _now()
    return LiveDelta(
        exact_earth_time=_iso_seconds(current),
        timezone=_zone_label(current),
        source=str(source or "hermes_time"),
        earth_state=str(earth_state or ""),
        ai_world_state=str(ai_world_state or ""),
    )


KISSNE_LIVE_CONTEXT_OPEN = "<kissne_live_context>"
KISSNE_LIVE_CONTEXT_CLOSE = "</kissne_live_context>"
KISSNE_USER_MESSAGE_OPEN = "<user_message>"
KISSNE_USER_MESSAGE_CLOSE = "</user_message>"


def compose_current_user_turn(
    content: Any,
    *,
    live_delta: Optional[LiveDelta],
    turn_recall: str = "",
    runtime_context: str = "",
) -> Optional[str]:
    """Place all request-local context before the user's exact words.

    The returned string is a provider-request projection only. Callers must
    never assign it to canonical message content or api_content.
    """
    if not isinstance(content, str):
        return None
    context_parts = []
    if live_delta is not None:
        context_parts.append(live_delta.render())
    if isinstance(turn_recall, str) and turn_recall.strip():
        context_parts.append(
            "<turn_recall>\n"
            + turn_recall.strip()
            + "\n</turn_recall>"
        )
    if isinstance(runtime_context, str) and runtime_context.strip():
        context_parts.append(
            "<runtime_context>\n"
            + runtime_context.strip()
            + "\n</runtime_context>"
        )
    if not context_parts:
        return None
    return (
        KISSNE_LIVE_CONTEXT_OPEN
        + "\n"
        + "\n\n".join(context_parts)
        + "\n"
        + KISSNE_LIVE_CONTEXT_CLOSE
        + "\n\n"
        + KISSNE_USER_MESSAGE_OPEN
        + "\n"
        + content
        + "\n"
        + KISSNE_USER_MESSAGE_CLOSE
    )


@dataclass(frozen=True)
class ContextLayers:
    """Semantic inputs for one request plus Hermes' compatibility prompt."""

    stable_core: str = ""
    session_snapshot: SessionSnapshot = field(default_factory=SessionSnapshot)
    unified_history: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    turn_recall: str = ""
    live_delta: Optional[LiveDelta] = None
    runtime_system_prompt: str = ""

    @property
    def snapshot(self) -> str:
        return self.session_snapshot.render()

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return self.unified_history

    def system_prompt(self) -> str:
        # During migration the complete Hermes prompt remains authoritative.
        # Semantic layers are observability/lifecycle boundaries, not a license
        # to drop Hermes guidance from the provider request.
        return self.runtime_system_prompt or _join_prompt_parts(
            self.stable_core, self.session_snapshot.render()
        )

    def read(
        self,
        *,
        unified_history: Optional[Iterable[Mapping[str, Any]]] = None,
        turn_recall: Optional[str] = None,
        live_delta: Optional[LiveDelta] = None,
    ) -> "ContextRead":
        """Create a request-only view without mutating canonical history."""
        source = (
            tuple(unified_history)
            if unified_history is not None
            else self.unified_history
        )
        return ContextRead(
            stable_core=self.stable_core,
            session_snapshot=self.session_snapshot,
            unified_history=tuple(source),
            turn_recall=(
                self.turn_recall
                if turn_recall is None
                else str(turn_recall or "")
            ),
            live_delta=self.live_delta if live_delta is None else live_delta,
            runtime_system_prompt=self.runtime_system_prompt,
        )


@dataclass(frozen=True)
class ContextRead:
    """Immutable request-local context view."""

    stable_core: str
    session_snapshot: SessionSnapshot
    unified_history: tuple[Mapping[str, Any], ...]
    turn_recall: str
    live_delta: Optional[LiveDelta]
    runtime_system_prompt: str

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return self.unified_history

    @property
    def system_prompt(self) -> str:
        return self.runtime_system_prompt or _join_prompt_parts(
            self.stable_core, self.session_snapshot.render()
        )


def make_context_layers(
    *,
    stable_core: str = "",
    self_state: str = "",
    memory_state: str = "",
    unified_history: Iterable[Mapping[str, Any]] = (),
    runtime_system_prompt: str = "",
    snapshot_origin: str = "fresh_session",
    snapshot_captured_at: Optional[str] = None,
) -> ContextLayers:
    """Create immutable semantic layers at a snapshot boundary."""
    captured_at = snapshot_captured_at
    if captured_at is None:
        captured_at = _iso_seconds(_now())
    return ContextLayers(
        stable_core=str(stable_core or ""),
        session_snapshot=SessionSnapshot(
            self_state=str(self_state or ""),
            memory_state=str(memory_state or ""),
            captured_at=str(captured_at or ""),
            origin=str(snapshot_origin or "fresh_session"),
        ),
        unified_history=tuple(unified_history or ()),
        runtime_system_prompt=str(runtime_system_prompt or ""),
    )


__all__ = [
    "ContextLayers",
    "ContextRead",
    "LiveDelta",
    "SessionSnapshot",
    "KISSNE_LIVE_CONTEXT_CLOSE",
    "KISSNE_LIVE_CONTEXT_OPEN",
    "KISSNE_USER_MESSAGE_CLOSE",
    "KISSNE_USER_MESSAGE_OPEN",
    "build_live_delta",
    "compose_current_user_turn",
    "make_context_layers",
]
