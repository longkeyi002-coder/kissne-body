"""Behavioural tests for the ``/reread`` gateway slash command.

龙龙 edits ``HERMES_HOME/SOUL.md`` / ``SELF.md`` / ``memories/{MEMORY,USER}.md`` and wants the
CURRENT conversation to pick the new bytes up — without opening a new session. The session's
prompt snapshot lives in two layers:

  * ``agent._cached_system_prompt`` (frozen for the session; SELF is deliberately NOT re-read on
    normal turns, to keep the prompt-cache prefix stable), and
  * the persisted ``sessions.system_prompt`` row, which
    ``agent.conversation_loop._restore_or_build_system_prompt`` RESTORES verbatim whenever it still
    matches the runtime identity.

``/reread`` must drop BOTH, or the next turn keeps serving the OLD bytes. These tests drive the
real production pieces — ``invalidate_system_prompt``, the persisted row, the real
``_restore_or_build_system_prompt`` assembly — and only stub the prompt ASSEMBLY down to the real
``load_self_md`` / ``load_soul_md`` / MemoryStore readers pointed at a tmp HERMES_HOME. The
assertion is therefore "the next turn's system prompt now contains the newly written file bytes",
not "a mock was called".
"""

import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from agent.conversation_loop import _restore_or_build_system_prompt
from agent.prompt_builder import load_self_md, load_soul_md
from agent.system_prompt import invalidate_system_prompt
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.event import MessageEvent
from gateway.session import SessionEntry, SessionSource, build_session_key

SESSION_ID = "sess-1"
MODEL = "test-model"
PROVIDER = "openrouter"
OLD_SELF = "OLD-SELF-BODY"
NEW_SELF = "NEW-SELF-MARKER"  # never present before the edit


# ── fakes ────────────────────────────────────────────────────────────────────────────────
class _FakeSessionDB:
    """Minimal stand-in for SessionDB: just the ``system_prompt`` column both layers use."""

    def __init__(self, stored_prompt: Optional[str] = None):
        self.row: Dict[str, Any] = {"system_prompt": stored_prompt}

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return dict(self.row)

    def update_system_prompt(self, session_id: str, prompt: Optional[str]) -> None:
        self.row["system_prompt"] = prompt


class _FakeSessionStore:
    """Enough of SessionStore for ``_lookup_session_id_under_store_lock`` + no-write assertions."""

    def __init__(self, session_key: str, session_id: Optional[str]):
        self._lock = threading.Lock()
        self._entries = {session_key: SimpleNamespace(session_id=session_id)} if session_id else {}
        self.append_to_transcript = MagicMock()
        self.rewrite_transcript = MagicMock()
        self.update_session = MagicMock()

    def _ensure_loaded_locked(self) -> None:
        return None


class _FakeMemoryStore:
    """Models MemoryStore: MEMORY.md / USER.md are only re-read by ``load_from_disk``."""

    def __init__(self, home):
        self._home = home
        self.reloads = 0
        self.memory_text = ""
        self.user_text = ""
        self.load_from_disk()

    def load_from_disk(self) -> None:
        self.reloads += 1
        self.memory_text = (self._home / "memories" / "MEMORY.md").read_text(encoding="utf-8")
        self.user_text = (self._home / "memories" / "USER.md").read_text(encoding="utf-8")

    def format_for_system_prompt(self, kind: str) -> Optional[str]:
        text = self.memory_text if kind == "memory" else self.user_text
        return f"{kind.upper()} BLOCK:\n{text}" if text else None


# ── helpers ──────────────────────────────────────────────────────────────────────────────
def _write_soul_files(home, self_body: str, memory_body: str = "MEM-1") -> None:
    (home / "memories").mkdir(parents=True, exist_ok=True)
    (home / "SOUL.md").write_text("SOUL BODY v1\n", encoding="utf-8")
    (home / "SELF.md").write_text(self_body + "\n", encoding="utf-8")
    (home / "memories" / "MEMORY.md").write_text(memory_body + "\n", encoding="utf-8")
    (home / "memories" / "USER.md").write_text("USER BODY v1\n", encoding="utf-8")


def _make_agent(home, session_db: _FakeSessionDB, *, cached_prompt: Optional[str] = None):
    """A session agent whose prompt assembly mirrors production for the four soul files."""
    memory_store = _FakeMemoryStore(home)
    agent = MagicMock()
    agent.session_id = SESSION_ID
    agent.model = MODEL
    agent.provider = PROVIDER
    agent.platform = "telegram"
    agent.api_mode = None
    agent._session_db = session_db
    agent._memory_store = memory_store
    agent._memory_enabled = True
    agent._user_profile_enabled = True
    agent._memory_manager = None
    agent._persist_disabled = False
    agent._bot_mode_protocol = False
    agent._session_title_hint = ""
    agent._platform_hint_overrides = None
    agent._surface_switch_note = ""
    agent._gateway_turn_context_notes = ""
    agent._use_prompt_caching = False
    agent._cached_system_prompt = cached_prompt
    agent._cached_system_prompt_static = None
    agent._kissne_context_layers = "STALE-CONTEXT-LAYERS"
    agent._kissne_snapshot_refresh_reason = None

    def _build_system_prompt(_system_message) -> str:
        # Production readers, pointed at the test HERMES_HOME.
        parts = [
            "STATIC HEAD",
            load_soul_md(None, home_override=home) or "",
            load_self_md(None, home_override=home) or "",
            memory_store.format_for_system_prompt("memory") or "",
            memory_store.format_for_system_prompt("user") or "",
            f"Model: {MODEL}\nProvider: {PROVIDER}\n",
        ]
        return "\n\n".join(part for part in parts if part)

    agent._build_system_prompt = _build_system_prompt
    agent._invalidate_system_prompt = lambda reason=None: invalidate_system_prompt(agent, reason=reason)
    return agent


def _stale_prompt() -> str:
    """A persisted prompt whose runtime-identity lines still match → it WOULD be restored."""
    return (
        f"STATIC HEAD\n\nSOUL BODY v1\n\n{OLD_SELF}\n\nModel: {MODEL}\nProvider: {PROVIDER}\n"
    )


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM, user_id="u1", chat_id="c1", user_name="longlong", chat_type="dm"
    )


def _make_event(text: str = "/reread") -> MessageEvent:
    return MessageEvent(text=text, source=_make_source(), message_id="m1")


def _make_runner(monkeypatch, tmp_path, *, cached_agent=None, session_db: _FakeSessionDB,
                 store_session_id: Optional[str] = SESSION_ID):
    from gateway.run import GatewayRunner

    home = tmp_path / "hermes-home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))

    session_key = build_session_key(_make_source())
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")}
    )
    runner.adapters = {}
    runner.session_store = _FakeSessionStore(session_key, store_session_id)
    runner._session_db = session_db
    runner._running_agents = {}
    runner._pending_messages = {}
    runner._agent_cache = {}
    runner._agent_cache_lock = threading.Lock()
    # Real bindings, so the key/cache lookups match production dispatch.
    runner._session_key_for_source = GatewayRunner._session_key_for_source.__get__(
        runner, GatewayRunner
    )
    runner._resident_agent_for = GatewayRunner._resident_agent_for.__get__(runner, GatewayRunner)
    runner._cached_agent_for = GatewayRunner._cached_agent_for.__get__(runner, GatewayRunner)
    runner._lookup_session_id_under_store_lock = GatewayRunner._lookup_session_id_under_store_lock
    if cached_agent is not None:
        runner._agent_cache[session_key] = (cached_agent, "sig", 0, SESSION_ID)
    return runner, session_key, home


def _next_turn(agent) -> str:
    """Exactly what agent/turn_context.py does for a turn: restore the row or build fresh."""
    _restore_or_build_system_prompt(agent, None, [{"role": "user", "content": "next"}])
    return agent._cached_system_prompt


# ── tests ────────────────────────────────────────────────────────────────────────────────
def test_command_is_registered_and_dispatchable_when_idle():
    """The name must resolve, must not shadow /reload, and must be routable on the idle path."""
    from hermes_cli.commands import GATEWAY_KNOWN_COMMANDS, resolve_command
    from gateway.run import GatewayRunner

    cmd = resolve_command("reread")
    assert cmd is not None and cmd.name == "reread"
    assert "reread" in GATEWAY_KNOWN_COMMANDS
    # /reload stays the .env reloader (cli_only) — the new name does not collide.
    assert resolve_command("reload").name == "reload"

    runner = object.__new__(GatewayRunner)
    handlers = runner._gateway_idle_command_handlers()
    assert handlers.get("reread") is not None
    assert handlers["reread"].__name__ == "_handle_reread_command"


def test_without_the_command_the_next_turn_reuses_the_stale_snapshot(monkeypatch, tmp_path):
    """Control: documents the behaviour 龙龙 is stuck with today (the reason /reread exists)."""
    home = tmp_path / "hermes-home"
    _write_soul_files(home, OLD_SELF)
    db = _FakeSessionDB()
    agent = _make_agent(home, db)
    _make_runner(monkeypatch, tmp_path, cached_agent=None, session_db=db)

    # First turn of the session: the prompt is built from disk and persisted.
    _restore_or_build_system_prompt(agent, None, [{"role": "user", "content": "first"}])
    assert OLD_SELF in agent._cached_system_prompt
    assert db.row["system_prompt"] == agent._cached_system_prompt

    # 龙龙 edits SELF.md, then keeps chatting in the same session.
    _write_soul_files(home, NEW_SELF, memory_body="MEM-2")
    reused = _next_turn(agent)
    assert OLD_SELF in reused and NEW_SELF not in reused
    assert "MEM-2" not in reused

    # A fresh agent (the gateway builds one per turn for a cold cache) also restores the row.
    fresh = _make_agent(home, db)
    restored = _next_turn(fresh)
    assert OLD_SELF in restored and NEW_SELF not in restored


@pytest.mark.asyncio
async def test_reread_makes_the_next_turn_read_the_new_soul_files(monkeypatch, tmp_path):
    """The acceptance test: /reread → next turn's prompt carries the newly written bytes."""
    home = tmp_path / "hermes-home"
    _write_soul_files(home, OLD_SELF)
    db = _FakeSessionDB()
    agent = _make_agent(home, db)
    runner, _session_key, _home = _make_runner(
        monkeypatch, tmp_path, cached_agent=agent, session_db=db
    )

    _restore_or_build_system_prompt(agent, None, [{"role": "user", "content": "first"}])
    assert OLD_SELF in agent._cached_system_prompt
    assert db.row["system_prompt"] == agent._cached_system_prompt
    reloads_before = agent._memory_store.reloads

    # 龙龙 rewrites the soul files on disk.
    _write_soul_files(home, NEW_SELF, memory_body="MEM-2")

    out = await runner._handle_reread_command(_make_event())

    assert out and "SELF.md" in out
    # Layer 1 — the frozen in-memory snapshot is gone, and with it the Kissne context layers.
    assert agent._cached_system_prompt is None
    assert agent._cached_system_prompt_static is None
    assert agent._kissne_context_layers is None
    assert agent._kissne_snapshot_refresh_reason == "reread"
    # MEMORY.md / USER.md were re-read from disk by the same call.
    assert agent._memory_store.reloads == reloads_before + 1
    # Layer 2 — the persisted row can no longer be restored verbatim.
    assert db.row["system_prompt"] is None

    rebuilt = _next_turn(agent)
    assert NEW_SELF in rebuilt
    assert OLD_SELF not in rebuilt
    assert "MEM-2" in rebuilt
    # The rebuilt prompt is re-persisted, so following turns are cache-stable again.
    assert db.row["system_prompt"] == rebuilt


@pytest.mark.asyncio
async def test_reread_drops_the_stale_row_when_no_agent_is_cached(monkeypatch, tmp_path):
    """Cold cache (gateway builds a fresh agent per turn): the persisted row is the only layer."""
    home = tmp_path / "hermes-home"
    _write_soul_files(home, OLD_SELF)
    db = _FakeSessionDB(_stale_prompt())
    runner, _session_key, _home = _make_runner(
        monkeypatch, tmp_path, cached_agent=None, session_db=db
    )

    # Paired control: before the command, a fresh agent restores the stale bytes from the row.
    stale = _next_turn(_make_agent(home, db))
    assert OLD_SELF in stale and NEW_SELF not in stale

    _write_soul_files(home, NEW_SELF, memory_body="MEM-2")
    out = await runner._handle_reread_command(_make_event())

    assert out and "SELF.md" in out
    assert db.row["system_prompt"] is None
    fresh = _next_turn(_make_agent(home, db))
    assert NEW_SELF in fresh and OLD_SELF not in fresh


@pytest.mark.asyncio
async def test_reread_never_touches_the_transcript(monkeypatch, tmp_path):
    """No new conversation, no history rewrite, no compression side effects."""
    home = tmp_path / "hermes-home"
    _write_soul_files(home, OLD_SELF)
    db = _FakeSessionDB()
    agent = _make_agent(home, db)
    runner, _session_key, _home = _make_runner(
        monkeypatch, tmp_path, cached_agent=agent, session_db=db
    )
    _restore_or_build_system_prompt(agent, None, [{"role": "user", "content": "first"}])

    await runner._handle_reread_command(_make_event())

    runner.session_store.append_to_transcript.assert_not_called()
    runner.session_store.rewrite_transcript.assert_not_called()
    runner.session_store.update_session.assert_not_called()
    assert agent.session_id == SESSION_ID  # same session, not a new one
