"""Regression tests for the no-progress degenerate response guard."""

from __future__ import annotations

import string
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _incident_shape() -> str:
    """Sanitized shape derived from the 2026-09-19 production transcript incident."""
    filler = []
    for ch in string.ascii_lowercase[:18]:
        # Long unique filler advances the output floor without itself looking repetitive.
        filler.append((f"{ch}context " * 28).strip())
    loops = [
        (
            "Actually, I think I should focus on the practical solution. I should check whether the dashboard works "
            "from localhost, check whether the websocket works from localhost, and then compare the public connection. "
            "If localhost works but the public path fails, that points to the network boundary; if localhost fails too, "
            "that points back to application configuration or authentication."
        ),
        (
            "Actually, I think I should focus on the practical solution. I should verify whether the dashboard works "
            "from localhost, verify whether the websocket works from localhost, and then compare the public connection. "
            "If localhost works but the public path fails, that points to the network boundary; if localhost fails too, "
            "that points back to application configuration or authentication."
        ),
        (
            "The most likely causes are authentication, websocket configuration, or a network rule. I should stop "
            "listing the same possibilities and run one concrete websocket test that separates those cases, then use "
            "the result as new evidence before proposing another diagnosis or another speculative fix."
        ),
        (
            "The most likely causes are authentication, websocket configuration, or a network rule. I should stop "
            "repeating the same possibilities and run one concrete websocket test that separates those cases, then use "
            "the result as new evidence before proposing another diagnosis or another speculative fix."
        ),
        (
            "I realize I have been spending too much time restating the plan. The next useful step is an authenticated "
            "websocket client check, because that result would show whether the server accepts the handshake and whether "
            "the abnormal close happens before or after application logic begins handling the connection."
        ),
        (
            "I realize I have been spending too much time repeating the plan. The next useful step is an authenticated "
            "websocket client check, because that result would show whether the server accepts the handshake and whether "
            "the abnormal close happens before or after application logic begins handling the connection."
        ),
    ]
    tail = ("post_guard_unique_material " * 80).strip()
    return "\n\n".join([*filler, *loops, tail])


def _unique_long_prose() -> str:
    paragraphs = []
    letters = string.ascii_lowercase
    for i in range(20):
        unique = [
            f"{letters[i]}{letters[j]}{letters[(i + j + 7) % 26]}"
            for j in range(12)
        ]
        paragraphs.append(
            "Technical analysis for this independent subsystem uses distinct vocabulary: "
            + " ".join(unique * 8)
        )
    return "\n\n".join(paragraphs)


class TestDegenerateResponseDetector:
    def test_incident_shape_hits_before_full_output(self):
        from agent.degenerate_response_guard import DegenerateResponseGuard

        text = _incident_shape()
        guard = DegenerateResponseGuard()
        for i in range(0, len(text), 137):
            if guard.feed(text[i : i + 137]):
                break
        if not guard.tripped:
            guard.finish()

        assert guard.tripped is True
        assert guard.trip_at_chars is not None
        assert guard.trip_at_chars < len(text)

    def test_long_distinct_technical_answer_is_not_killed(self):
        from agent.degenerate_response_guard import is_degenerate_response

        text = _unique_long_prose()
        assert len(text) > 6000
        assert is_degenerate_response(text) is False

    @pytest.mark.parametrize("kind", ["code", "logs", "table", "list"])
    def test_structured_repetition_is_not_killed(self, kind):
        from agent.degenerate_response_guard import is_degenerate_response

        if kind == "code":
            block = "~~~python\nfor item in values:\n    print(item)\n~~~"
        elif kind == "logs":
            block = "\n".join(f"INFO worker step {i} completed" for i in range(20))
        elif kind == "table":
            block = "\n".join(["| key | value |", "| --- | --- |", "| alpha | beta |"])
        else:
            block = (
                "1. Repeated section title with a deliberately long explanatory sentence "
                "that is valid enumerated report structure and must remain fail-open."
            )
        text = "\n\n".join(block for _ in range(160))
        assert len(text) > 6000
        assert is_degenerate_response(text) is False

    def test_chinese_near_duplicate_prose_is_supported(self, monkeypatch):
        from agent.degenerate_response_guard import DegenerateResponseGuard
        import agent.degenerate_response_guard as guard_mod

        monkeypatch.setattr(guard_mod, "MIN_TOTAL_CHARS", 180)
        monkeypatch.setattr(guard_mod, "REPEAT_HITS", 2)
        paragraphs = [
            "我应该先验证本地页面是否正常，再验证本地 websocket 是否正常，然后对比公网连接，不能继续反复猜测认证、网络或者配置问题而没有新的证据。",
            "我应该先验证本地页面是否正常，再检查本地 websocket 是否正常，然后对比公网连接，不能继续反复猜测认证、网络或者配置问题却没有新的证据。",
            "我应该先验证本地页面是否正常，再检查本地 websocket 是否正常，然后比较公网连接，不能继续反复猜测认证、网络或者配置问题却没有新的证据。",
        ]
        guard = DegenerateResponseGuard()
        for paragraph in paragraphs:
            guard.feed(paragraph + "\n\n")

        assert guard.tripped is True

    def test_short_repetition_stays_fail_open(self):
        from agent.degenerate_response_guard import is_degenerate_response

        para = (
            "This paragraph repeats a diagnosis with enough distinct words to look similar, "
            "but the entire answer is still short and should never be stopped by the guard."
        )
        text = "\n\n".join([para, para, para])
        assert len(text) < 6000
        assert is_degenerate_response(text) is False

    def test_config_can_disable_guard(self):
        from agent.degenerate_response_guard import resolve_guard_enabled

        assert resolve_guard_enabled({"enabled": False}) is False
        assert resolve_guard_enabled({"enabled": "off"}) is False
        assert resolve_guard_enabled({"enabled": True}) is True
        assert resolve_guard_enabled("bad") is True


def _make_stream_chunk(content=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(
        content=content, tool_calls=tool_calls, reasoning_content=None, reasoning=None,
    )
    choice = SimpleNamespace(index=0, delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model=None, usage=None)


def _make_tool_call_delta(index=0, tc_id=None, name=None, arguments=None):
    func = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=tc_id, type="function", function=func)


def _stream_agent():
    from run_agent import AIAgent

    agent = AIAgent(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="test/model",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
    )
    agent.api_mode = "chat_completions"
    agent._interrupt_requested = False
    agent._degenerate_guard_enabled = True
    return agent


class TestDegenerateStreamingStop:
    @patch("run_agent.AIAgent._create_request_openai_client")
    @patch("run_agent.AIAgent._close_request_openai_client")
    def test_intentional_guard_stop_is_not_a_partial_stream_drop(
        self, _mock_close, mock_create, monkeypatch
    ):
        from agent.degenerate_response_guard import FINISH_REASON
        from hermes_constants import PARTIAL_STREAM_STUB_ID
        import agent.degenerate_response_guard as guard_mod

        monkeypatch.setattr(guard_mod, "MIN_TOTAL_CHARS", 300)
        monkeypatch.setattr(guard_mod, "REPEAT_HITS", 2)
        monkeypatch.setattr(guard_mod, "RECENT_BLOCKS", 8)
        variants = [
            (
                "I should verify the local endpoint and then compare the public websocket path using concrete evidence "
                "before repeating another authentication or configuration hypothesis because speculation alone does not progress the task."
            ),
            (
                "I should verify the local endpoint, compare the public websocket route with concrete evidence, and avoid "
                "repeating another authentication or configuration hypothesis because speculation does not move the task forward."
            ),
            (
                "I should verify the local endpoint and compare the public websocket path using concrete evidence, then "
                "avoid repeating another authentication or configuration hypothesis because speculation does not move the task forward."
            ),
        ]

        def stream():
            for paragraph in variants:
                yield _make_stream_chunk(content=paragraph + "\n\n")
            yield _make_stream_chunk(content="must not be consumed", finish_reason="stop")

        client = MagicMock()
        client.chat.completions.create.side_effect = lambda *a, **kw: stream()
        mock_create.return_value = client
        agent = _stream_agent()
        response = agent._interruptible_streaming_api_call({})

        assert response.id != PARTIAL_STREAM_STUB_ID
        assert response.choices[0].finish_reason == FINISH_REASON
        assert "must not be consumed" not in (response.choices[0].message.content or "")

    @patch("run_agent.AIAgent._create_request_openai_client")
    @patch("run_agent.AIAgent._close_request_openai_client")
    def test_tool_call_start_disables_guard_before_arguments(
        self, _mock_close, mock_create, monkeypatch
    ):
        import agent.degenerate_response_guard as guard_mod

        monkeypatch.setattr(guard_mod, "MIN_TOTAL_CHARS", 250)
        monkeypatch.setattr(guard_mod, "REPEAT_HITS", 2)
        monkeypatch.setattr(guard_mod, "RECENT_BLOCKS", 8)
        preamble = (
            "I will inspect the endpoint with a concrete command and use the returned evidence rather than repeat "
            "another theory about authentication, networking, configuration, or heartbeat behavior without testing it first."
        )

        def stream():
            yield _make_stream_chunk(content=preamble + "\n\n")
            yield _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, tc_id="call_1", name="terminal", arguments="{")
            ])
            yield _make_stream_chunk(tool_calls=[
                _make_tool_call_delta(index=0, arguments='"command":"echo ok"}')
            ])
            yield _make_stream_chunk(finish_reason="tool_calls")

        client = MagicMock()
        client.chat.completions.create.side_effect = lambda *a, **kw: stream()
        mock_create.return_value = client
        agent = _stream_agent()
        response = agent._interruptible_streaming_api_call({})

        assert response.choices[0].finish_reason == "tool_calls"
        calls = response.choices[0].message.tool_calls
        assert calls and len(calls) == 1
        assert calls[0].function.name == "terminal"
        assert calls[0].function.arguments == '{"command":"echo ok"}'


class TestGuardScaffoldCleanup:
    def test_tool_round_drops_guard_scaffold_before_persistence(self):
        from agent.degenerate_response_guard import SYNTHETIC_FLAG
        from agent.turn_tool_round import stage_tool_call_message
        from tests.agent.test_run_agent import _mock_assistant_msg, _mock_tool_call

        agent = MagicMock()
        agent._build_assistant_message.return_value = {
            "role": "assistant", "content": "", "tool_calls": [{"id": "call_1"}]
        }
        agent._has_content_after_think_block.return_value = False
        agent._should_emit_quiet_tool_messages.return_value = False
        messages = [
            {"role": "user", "content": "diagnose it"},
            {"role": "assistant", "content": "stopped", SYNTHETIC_FLAG: True},
            {"role": "user", "content": "act now", SYNTHETIC_FLAG: True},
        ]
        assistant = _mock_assistant_msg(content="", tool_calls=[_mock_tool_call()])

        stage_tool_call_message(
            agent, assistant_message=assistant, finish_reason="tool_calls", messages=messages
        )

        assert all(not m.get(SYNTHETIC_FLAG) for m in messages)
        assert messages == [{"role": "user", "content": "diagnose it"}]


@pytest.fixture()
def loop_agent():
    from run_agent import AIAgent

    with (
        patch("model_tools.get_tool_definitions", return_value=[]),
        patch("model_tools.check_toolset_requirements", return_value={}),
        patch("agent.process_bootstrap.OpenAI"),
    ):
        agent = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
    agent.client = MagicMock()
    agent._cached_system_prompt = "You are helpful."
    agent._use_prompt_caching = False
    agent.compression_enabled = False
    agent.save_trajectories = False
    return agent


class TestDegenerateRecoveryBound:
    def test_two_degenerate_responses_use_exactly_one_recovery(self, loop_agent):
        from tests.agent.test_run_agent import _mock_response

        bad = _incident_shape()
        loop_agent.client.chat.completions.create.side_effect = [
            _mock_response(content=bad, finish_reason="stop"),
            _mock_response(content=bad, finish_reason="stop"),
        ]

        with (
            patch.object(loop_agent, "_persist_session"),
            patch.object(loop_agent, "_save_trajectory"),
            patch.object(loop_agent, "_cleanup_task_resources"),
        ):
            result = loop_agent.run_conversation("diagnose the websocket problem")

        assert loop_agent.client.chat.completions.create.call_count == 2
        assert "repeated the same analysis twice" in (result["final_response"] or "")

        second_call = loop_agent.client.chat.completions.create.call_args_list[1]
        sent = second_call.kwargs.get("messages") or second_call.args[0].get("messages")
        from agent.degenerate_response_guard import RECOVERY_PLACEHOLDER
        assert any(
            message.get("role") == "assistant" and message.get("content") == RECOVERY_PLACEHOLDER
            for message in sent
        )
        assert bad[:160] not in str(sent)

        assert not any(
            isinstance(message, dict) and message.get("_degenerate_guard_nudge")
            for message in result["messages"]
        )
