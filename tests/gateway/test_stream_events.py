"""Structured stream-event protocol + dispatcher behavior.

Covers the agent→gateway delivery contract introduced to decouple *what
happened* (typed events) from *how it's delivered* (adapter decides).  The
default BasePlatformAdapter rendering must reproduce today's behavior exactly;
an adapter may override format_tool_event to eat tool chrome on platforms that
can't render it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from gateway.stream_dispatch import GatewayEventDispatcher
from gateway.stream_events import (
    Commentary,
    GatewayNotice,
    LongToolHint,
    MessageChunk,
    MessageStop,
    ToolCallChunk,
    ToolCallFinished,
)


def _base_adapter():
    """A real BasePlatformAdapter instance (abstractmethods cleared) so we
    exercise the genuine default render hooks, not a mock."""
    from gateway.platforms.base import BasePlatformAdapter

    Concrete = type("Concrete", (BasePlatformAdapter,), {})
    Concrete.__abstractmethods__ = frozenset()
    return Concrete.__new__(Concrete)


class _FakeSink:
    def __init__(self):
        self.deltas = []
        self.commentary = []
        self.segment_breaks = 0

    def on_delta(self, text):
        self.deltas.append(text)

    def on_commentary(self, text):
        self.commentary.append(text)

    def on_segment_break(self):
        self.segment_breaks += 1


# ── Message events → sink ────────────────────────────────────────────────────

def test_message_chunk_flows_to_sink_on_delta():
    sink = _FakeSink()
    d = GatewayEventDispatcher(_base_adapter(), sink)
    d.dispatch(MessageChunk("hello "))
    d.dispatch(MessageChunk("world"))
    assert sink.deltas == ["hello ", "world"]


def test_intermediate_message_stop_breaks_segment_but_final_does_not():
    sink = _FakeSink()
    d = GatewayEventDispatcher(_base_adapter(), sink)
    d.dispatch(MessageStop(final=False))
    d.dispatch(MessageStop(final=True))
    assert sink.segment_breaks == 1  # only the non-final stop breaks


def test_commentary_flows_to_sink():
    sink = _FakeSink()
    d = GatewayEventDispatcher(_base_adapter(), sink)
    d.dispatch(Commentary("I'll inspect the repo first."))
    assert sink.commentary == ["I'll inspect the repo first."]


# ── Tool events → progress queue, formatted by adapter ───────────────────────

def test_tool_call_chunk_renders_default_chrome():
    lines = []
    d = GatewayEventDispatcher(
        _base_adapter(), _FakeSink(),
        enqueue_tool_line=lines.append, tool_mode="all",
    )
    d.dispatch(ToolCallChunk(tool_name="terminal", preview="ls -la"))
    assert len(lines) == 1
    assert "terminal" in lines[0]
    assert "ls -la" in lines[0]


def test_new_mode_dedups_same_tool():
    lines = []
    d = GatewayEventDispatcher(
        _base_adapter(), _FakeSink(),
        enqueue_tool_line=lines.append, tool_mode="new",
    )
    d.dispatch(ToolCallChunk(tool_name="terminal", preview="a"))
    d.dispatch(ToolCallChunk(tool_name="terminal", preview="b"))  # deduped
    d.dispatch(ToolCallChunk(tool_name="read_file", preview="c"))
    assert len(lines) == 2  # terminal once, read_file once


def test_tool_completion_reaches_adapter_progress_queue():
    """Native adapters need the finish event to settle running Activity."""
    lines = []
    adapter = MagicMock()
    adapter.format_tool_event.side_effect = lambda event, **_: (
        f"finish:{event.tool_name}:{event.index}" if isinstance(event, ToolCallFinished)
        else f"start:{event.tool_name}:{event.index}"
    )
    d = GatewayEventDispatcher(
        adapter, _FakeSink(),
        enqueue_tool_line=lines.append, tool_mode="all",
    )
    d.dispatch(ToolCallChunk(tool_name="terminal", preview="ls", index=3))
    d.dispatch(ToolCallFinished(tool_name="terminal", duration=0.2, ok=True, index=3))
    assert lines == ["start:terminal:3", "finish:terminal:3"]


def test_new_mode_still_dispatches_tool_completion():
    lines = []
    adapter = MagicMock()
    adapter.format_tool_event.side_effect = lambda event, **_: type(event).__name__
    d = GatewayEventDispatcher(
        adapter, _FakeSink(),
        enqueue_tool_line=lines.append, tool_mode="new",
    )
    d.dispatch(ToolCallChunk(tool_name="terminal", preview="a", index=0))
    d.dispatch(ToolCallChunk(tool_name="terminal", preview="b", index=1))
    d.dispatch(ToolCallFinished(tool_name="terminal", duration=0.1, ok=True, index=0))
    assert lines == ["ToolCallChunk", "ToolCallFinished"]


# ── Control events → gateway-owned hooks ─────────────────────────────────────


