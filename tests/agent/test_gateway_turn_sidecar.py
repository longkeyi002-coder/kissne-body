"""Gateway must-deliver notes on the current user request.\n\nString notes join request-local runtime context and are not persisted or\nreplayed through api_content. Multimodal content keeps the existing\ndurable text-part fallback because the string projection cannot represent it.\n"""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest

from agent.turn_context import (
    append_notes_to_multimodal_content,
    build_turn_context,
    consume_gateway_turn_context_notes,
)


class _FakeTodoStore:
    def has_items(self):
        return True


class _FakeGuardrails:
    def reset_for_turn(self):
        pass


class _FakeAgent:
    """Minimal stand-in covering only what the prologue touches
    (mirrors tests/agent/test_api_content_sidecar.py)."""

    def __init__(self):
        self.session_id = "sess-1"
        self.model = "test/model"
        self.provider = "openrouter"
        self.base_url = "https://openrouter.ai/api/v1"
        self.api_key = "sk-x"
        self.api_mode = "chat_completions"
        self.platform = "discord"
        self.quiet_mode = True
        self.max_iterations = 90
        self.tools = []
        self.valid_tool_names = set()
        self._skip_mcp_refresh = True
        self.compression_enabled = False
        self.context_compressor = types.SimpleNamespace(
            protect_first_n=2, protect_last_n=2
        )
        self._cached_system_prompt = "SYSTEM"
        self._memory_store = None
        self._memory_manager = None
        self._memory_nudge_interval = 0
        self._turns_since_memory = 0
        self._user_turn_count = 0
        self._todo_store = _FakeTodoStore()
        self._tool_guardrails = _FakeGuardrails()
        self._compression_warning = None
        self._interrupt_requested = False
        self._memory_write_origin = "assistant_tool"
        self._stream_context_scrubber = None
        self._stream_think_scrubber = None

    def _ensure_db_session(self):
        pass

    def _restore_primary_runtime(self):
        pass

    def _cleanup_dead_connections(self):
        return False

    def _emit_status(self, _msg):
        pass

    def _replay_compression_warning(self):
        pass

    def _hydrate_todo_store(self, *_a, **_k):
        pass

    def _safe_print(self, *_a, **_k):
        pass

    def _persist_session(self, messages, _history=None):
        pass


def _build(agent, **overrides):
    kwargs = dict(
        agent=agent,
        user_message="hello",
        system_message=None,
        conversation_history=None,
        task_id=None,
        stream_callback=None,
        persist_user_message=None,
        restore_or_build_system_prompt=lambda *a, **k: None,
        install_safe_stdio=lambda: None,
        sanitize_surrogates=lambda s: s,
        summarize_user_message_for_log=lambda s: str(s),
        set_session_context=lambda _sid: None,
        set_current_write_origin=lambda _o: None,
        ra=lambda: types.SimpleNamespace(_set_interrupt=lambda *a, **k: None),
    )
    kwargs.update(overrides)
    return build_turn_context(**kwargs)


@pytest.fixture(autouse=True)
def _stub_runtime_main():
    with patch("agent.auxiliary_client.set_runtime_main", lambda *a, **k: None):
        yield


RESET_NOTE = (
    "[System note: The user's previous session expired due to inactivity. "
    "This is a fresh conversation with no prior context.]"
)
VC_NOTE = "[Voice channel now: dev-vc (2 members)]"


class TestConsumeIsOneShot:
    def test_consume_clears_the_attribute(self):
        agent = _FakeAgent()
        agent._gateway_turn_context_notes = RESET_NOTE
        assert consume_gateway_turn_context_notes(agent) == RESET_NOTE
        assert consume_gateway_turn_context_notes(agent) == ""

    def test_absent_attribute_is_empty(self):
        assert consume_gateway_turn_context_notes(_FakeAgent()) == ""

    def test_non_string_value_is_empty(self):
        agent = _FakeAgent()
        agent._gateway_turn_context_notes = ["not-a-string"]
        assert consume_gateway_turn_context_notes(agent) == ""



class TestStringContentRequestLocalDelivery:
    def test_notes_join_request_local_context(self):
        agent = _FakeAgent()
        agent._gateway_turn_context_notes = RESET_NOTE
        with patch("hermes_cli.plugins.invoke_hook", return_value=[]):
            ctx = _build(agent)

        msg = ctx.messages[ctx.current_turn_user_idx]
        assert msg["content"] == "hello"
        assert "api_content" not in msg
        assert ctx.plugin_user_context == RESET_NOTE
        assert agent._gateway_turn_context_notes == ""

    def test_notes_follow_plugin_context(self):
        agent = _FakeAgent()
        agent._gateway_turn_context_notes = VC_NOTE
        with patch(
            "hermes_cli.plugins.invoke_hook",
            return_value=[{"context": "PLUGIN-CTX"}],
        ):
            ctx = _build(agent)

        msg = ctx.messages[ctx.current_turn_user_idx]
        assert "api_content" not in msg
        assert ctx.plugin_user_context == "PLUGIN-CTX\n\n" + VC_NOTE

    def test_no_notes_means_no_request_local_context(self):
        agent = _FakeAgent()
        with patch("hermes_cli.plugins.invoke_hook", return_value=[]):
            ctx = _build(agent)
        assert "api_content" not in ctx.messages[ctx.current_turn_user_idx]
        assert ctx.plugin_user_context == ""


class TestMultimodalFallback:
    def test_notes_appended_as_text_part_on_list_content(self):
        """Multimodal turns cannot use the string request projection, so the
        must-deliver fact is appended as a durable text part instead."""
        agent = _FakeAgent()
        agent._gateway_turn_context_notes = RESET_NOTE
        content = [
            {"type": "text", "text": "look at this"},
            {"type": "image_url", "image_url": {"url": "https://x/img.png"}},
        ]
        with patch("hermes_cli.plugins.invoke_hook", return_value=[]):
            ctx = _build(agent, user_message=content)
        msg = ctx.messages[ctx.current_turn_user_idx]
        assert msg["content"][-1] == {"type": "text", "text": RESET_NOTE}
        # No string sidecar for list content.
        assert "api_content" not in msg

    def test_helper_appends_only_to_lists(self):
        content = [{"type": "text", "text": "hi"}]
        assert append_notes_to_multimodal_content(content, "NOTE") is True
        assert content[-1] == {"type": "text", "text": "NOTE"}
        assert append_notes_to_multimodal_content("string", "NOTE") is False
        assert append_notes_to_multimodal_content(content, "") is False
