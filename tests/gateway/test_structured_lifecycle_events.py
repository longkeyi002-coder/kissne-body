"""Structured lifecycle events: capability opt-in on the gateway side.

Contract frozen here:

* A platform adapter that declares ``structured_lifecycle_events_enabled()`` receives the
  ID-bearing ``agent.tool_start_callback`` / ``tool_complete_callback`` events (the rail Slack's
  native task cards use) and the name-correlated *text* tool-progress rail is suppressed for it.
* The opt-in is a capability probe, not a platform whitelist: an adapter that does not declare it
  (any other platform) keeps its existing text progress untouched — including Slack, which is
  platform-gated separately.
* ``needs_progress_queue`` becomes true for the structured rail, so the drain exists even with
  ``tool_progress`` off.
"""

import importlib
import sys
import time
import types

import pytest
import yaml

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.session import SessionSource


class CaptureAdapter(BasePlatformAdapter):
    """Minimal adapter that records sends/edits (no network)."""

    def __init__(self, platform=Platform.TELEGRAM):
        super().__init__(PlatformConfig(enabled=True, token="***"), platform)
        self.sent = []
        self.edits = []

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        return True

    async def disconnect(self) -> None:
        return None

    async def send(self, chat_id, content, reply_to=None, metadata=None) -> SendResult:
        self.sent.append({"chat_id": chat_id, "content": content, "reply_to": reply_to,
                          "metadata": metadata})
        return SendResult(success=True, message_id="progress-1")

    async def edit_message(self, chat_id, message_id, content) -> SendResult:
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "content": content})
        return SendResult(success=True, message_id=message_id)

    async def get_chat_info(self, chat_id: str):
        return {"id": chat_id}


class StructuredLifecycleAdapter(CaptureAdapter):
    """Declares the capability and records the structured lifecycle events it receives."""

    def __init__(self, platform=Platform.TELEGRAM):
        super().__init__(platform=platform)
        self.structured_events = []

    def structured_lifecycle_events_enabled(self) -> bool:
        return True

    async def send_structured_tool_event(self, chat_id, event, *, metadata=None) -> SendResult:
        self.structured_events.append({"chat_id": chat_id, "event": dict(event),
                                       "metadata": dict(metadata or {})})
        return SendResult(success=True, message_id="structured-1")


class StructuredToolsAgent:
    """Fires the ID-bearing tool lifecycle callbacks the gateway wires up."""

    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tool_start_callback = kwargs.get("tool_start_callback")
        self.tool_complete_callback = kwargs.get("tool_complete_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None, **kwargs):
        assert self.tool_start_callback is not None, "structured opt-in must wire the start callback"
        assert self.tool_complete_callback is not None, "structured opt-in must wire the completion"
        self.tool_start_callback("call-a", "terminal", {"command": "pwd"})
        time.sleep(0.4)
        self.tool_complete_callback("call-a", "terminal", {"command": "pwd"}, '{"success": true}')
        time.sleep(0.3)
        self.tool_start_callback("call-b", "web_search", {"query": "alpha"})
        time.sleep(0.4)
        # Same-name concurrency / out-of-order completion must still correlate by id, not name.
        self.tool_complete_callback("call-b", "web_search", {"query": "alpha"}, '{"error": "boom"}')
        time.sleep(0.2)
        return {"final_response": "done", "messages": [], "api_calls": 1}


class PlainToolsAgent:
    """Same lifecycle, adapter WITHOUT the capability — must keep producing text progress."""

    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tool_start_callback = kwargs.get("tool_start_callback")
        self.tool_complete_callback = kwargs.get("tool_complete_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None, **kwargs):
        # No opt-in: the ID-bearing callbacks are expected to stay unwired.
        assert self.tool_start_callback is None
        self.tool_progress_callback("tool.started", "terminal", "pwd", {})
        time.sleep(0.4)
        return {"final_response": "done", "messages": [], "api_calls": 1}


def _make_runner(adapter):
    gateway_run = importlib.import_module("gateway.run")
    GatewayRunner = gateway_run.GatewayRunner
    runner = object.__new__(GatewayRunner)
    runner.adapters = {adapter.platform: adapter}
    runner._voice_mode = {}
    runner._prefill_messages = []
    runner._ephemeral_system_prompt = ""
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._session_db = None
    runner._running_agents = {}
    runner._session_run_generation = {}
    runner.session_store = types.SimpleNamespace(_entries={}, _save=lambda: None)
    runner.hooks = types.SimpleNamespace(loaded_hooks=False)
    runner.config = types.SimpleNamespace(
        thread_sessions_per_user=False, group_sessions_per_user=False, stt_enabled=False)
    return runner


def _run_turn(adapter, agent_cls, monkeypatch, tmp_path, *, progress_mode):
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", progress_mode)
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = agent_cls
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    (tmp_path / "config.yaml").write_text(yaml.dump({"display": {}}), encoding="utf-8")

    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})
    source = SessionSource(platform=adapter.platform, chat_id="12345", chat_type="dm",
                           thread_id=None)
    return runner, source


@pytest.mark.asyncio
async def test_capability_adapter_receives_structured_lifecycle_and_no_text_progress(
    monkeypatch, tmp_path
):
    adapter = StructuredLifecycleAdapter()
    runner, source = _run_turn(adapter, StructuredToolsAgent, monkeypatch, tmp_path,
                               progress_mode="all")
    result = await runner._run_agent(
        message="hello", context_prompt="", history=[], source=source,
        session_id="sess-structured", session_key="agent:main:telegram:dm:12345")

    assert result["final_response"] == "done"

    events = [entry["event"] for entry in adapter.structured_events]
    assert [event["type"] for event in events] == [
        "tool.started", "tool.completed", "tool.started", "tool.completed",
    ]
    assert [event["tool_call_id"] for event in events] == ["call-a", "call-a", "call-b", "call-b"]
    assert [event["tool_name"] for event in events] == ["terminal", "terminal", "web_search",
                                                        "web_search"]
    # Start carries the args and the preview; completion carries the outcome.
    assert events[0]["args"] == {"command": "pwd"}
    assert events[0]["preview"]
    assert events[1]["is_error"] is False
    assert events[3]["is_error"] is True
    assert adapter.structured_events[0]["chat_id"] == "12345"

    # The name-correlated text tool-progress rail is suppressed for this adapter.
    rendered = "\n".join(
        [entry["content"] for entry in adapter.sent]
        + [entry["content"] for entry in adapter.edits]
    )
    assert "pwd" not in rendered, f"text tool progress leaked: {rendered!r}"


@pytest.mark.asyncio
async def test_without_capability_text_progress_is_unchanged(monkeypatch, tmp_path):
    adapter = CaptureAdapter()
    runner, source = _run_turn(adapter, PlainToolsAgent, monkeypatch, tmp_path,
                              progress_mode="all")
    result = await runner._run_agent(
        message="hello", context_prompt="", history=[], source=source,
        session_id="sess-plain", session_key="agent:main:telegram:dm:12345")

    assert result["final_response"] == "done"
    # Non-declaring adapters keep the exact previous behaviour: a text tool-progress line.
    rendered = "\n".join(
        [entry["content"] for entry in adapter.sent]
        + [entry["content"] for entry in adapter.edits]
    )
    assert "pwd" in rendered, f"expected the legacy text progress line, got: {rendered!r}"
    assert not hasattr(adapter, "send_structured_tool_event")


@pytest.mark.asyncio
async def test_structured_rail_works_with_tool_progress_off(monkeypatch, tmp_path):
    """The structured rail must not depend on the text rail being enabled."""
    adapter = StructuredLifecycleAdapter()
    runner, source = _run_turn(adapter, StructuredToolsAgent, monkeypatch, tmp_path,
                               progress_mode="off")
    result = await runner._run_agent(
        message="hello", context_prompt="", history=[], source=source,
        session_id="sess-structured-off", session_key="agent:main:telegram:dm:12345")

    assert result["final_response"] == "done"
    assert [entry["event"]["type"] for entry in adapter.structured_events] == [
        "tool.started", "tool.completed", "tool.started", "tool.completed",
    ]
