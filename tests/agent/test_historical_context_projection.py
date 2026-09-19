import json
from types import SimpleNamespace
from unittest.mock import patch

from agent.historical_context_projection import project_historical_message
from agent.message_sanitization import _strip_images_from_messages
from agent.turn_context import build_api_messages
from tools.tool_result_storage import maybe_persist_tool_result


def _fake_agent():
    class _Layers:
        def read(self, **_kwargs):
            return SimpleNamespace(system_prompt="")

    return SimpleNamespace(
        api_mode="chat_completions",
        provider="openai",
        _current_turn_timestamp=1.0,
        _kissne_context_layers=_Layers(),
        ephemeral_system_prompt="",
        _copy_reasoning_content_for_api=lambda _msg, _api_msg: None,
        _should_sanitize_tool_calls=lambda: False,
    )


def _image_part(marker: str = "A"):
    return {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64," + (marker * 10000)},
    }


def test_large_historical_tool_arguments_are_bounded_without_mutating_input():
    original = {
        "role": "assistant",
        "tool_calls": [{
            "id": "call-1",
            "type": "function",
            "function": {"name": "terminal", "arguments": '{"command":"' + ("x" * 2000) + '"}'},
        }],
    }

    projected = project_historical_message(original)
    arguments = projected["tool_calls"][0]["function"]["arguments"]

    assert len(arguments) <= 256
    assert json.loads(arguments)["_context_compacted"] is True
    assert len(original["tool_calls"][0]["function"]["arguments"]) > 2000


def test_historical_images_become_short_references():
    original = {
        "role": "user",
        "content": [
            {"type": "text", "text": "请看看"},
            _image_part(),
        ],
    }

    projected = project_historical_message(original)

    assert projected["content"][1]["type"] == "text"
    assert "historical image omitted" in projected["content"][1]["text"]
    assert len(projected["content"][1]["text"]) < 100
    assert original["content"][1]["type"] == "image_url"


def test_small_tool_arguments_and_plain_text_are_preserved():
    message = {
        "role": "assistant",
        "content": "已完成",
        "tool_calls": [{"function": {"name": "read_file", "arguments": '{"path":"a.txt"}'}}],
    }

    assert project_historical_message(message) == message


def test_large_historical_tool_result_keeps_bounded_head_and_tail_without_mutation():
    original_text = "HEAD-" + ("x" * 5000) + "-TAIL"
    original = {"role": "tool", "tool_call_id": "call-1", "content": original_text}

    projected = project_historical_message(original)

    assert len(projected["content"]) <= 1536
    assert projected["content"].startswith("HEAD-")
    assert projected["content"].endswith("-TAIL")
    assert "historical tool result compacted" in projected["content"]
    assert original["content"] == original_text


def test_historical_tool_result_projects_images_and_long_text_blocks():
    original = {
        "role": "tool",
        "tool_call_id": "call-2",
        "content": [
            {"type": "text", "text": "start-" + ("y" * 5000) + "-end"},
            _image_part("B"),
        ],
    }

    projected = project_historical_message(original)

    assert len(projected["content"][0]["text"]) <= 1536
    assert "historical tool result compacted" in projected["content"][0]["text"]
    assert projected["content"][1]["type"] == "text"
    assert "historical image omitted" in projected["content"][1]["text"]
    assert original["content"][1]["type"] == "image_url"


def test_previous_turn_image_keeps_one_turn_recovery_grace():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "look"}, _image_part()]},
        {"role": "assistant", "content": "seen"},
        {"role": "user", "content": "next"},
    ]

    api_messages, _ = build_api_messages(
        _fake_agent(),
        messages,
        current_turn_user_idx=2,
        ext_prefetch_cache=None,
        plugin_user_context="",
        moa_config=None,
        active_system_prompt="",
    )

    # The immediately previous completed turn stays byte-exact for one turn so
    # 413 / invalid-image recovery can still remove the payload and retry.
    assert api_messages[0]["content"][1]["type"] == "image_url"
    assert _strip_images_from_messages(api_messages) is True
    # Recovery acts on the request copy only; durable history remains lossless.
    assert messages[0]["content"][1]["type"] == "image_url"


def test_image_is_projected_after_recovery_grace_expires():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "old image"}, _image_part()]},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "previous turn"},
        {"role": "assistant", "content": "previous answer"},
        {"role": "user", "content": "current"},
    ]

    api_messages, _ = build_api_messages(
        _fake_agent(),
        messages,
        current_turn_user_idx=4,
        ext_prefetch_cache=None,
        plugin_user_context="",
        moa_config=None,
        active_system_prompt="",
    )

    assert api_messages[0]["content"][1]["type"] == "text"
    assert "historical image omitted" in api_messages[0]["content"][1]["text"]
    assert messages[0]["content"][1]["type"] == "image_url"


def test_current_turn_image_survives_when_canonicalization_drops_prefix_rows():
    current_image = _image_part("C")
    messages = [
        {"role": "user", "content": "previous"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "dangling-read",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'},
            }],
        },
        {"role": "user", "content": [{"type": "text", "text": "current"}, current_image]},
    ]

    api_messages, _ = build_api_messages(
        _fake_agent(),
        messages,
        current_turn_user_idx=2,
        ext_prefetch_cache=None,
        plugin_user_context="",
        moa_config=None,
        active_system_prompt="",
    )

    current = api_messages[-1]["content"]
    assert any(part.get("type") == "image_url" for part in current)
    assert messages[-1]["content"][1]["type"] == "image_url"


def test_persisted_terminal_pointer_survives_historical_result_bound():
    path = "/tmp/hermes-results/call-pointer.txt"
    with (
        patch("tools.tool_result_storage._write_to_spillover", return_value=path),
        patch("tools.tool_result_storage._is_host_side_env", return_value=True),
    ):
        persisted = maybe_persist_tool_result(
            content="terminal output\n" + ("z" * 10000),
            tool_name="terminal",
            tool_use_id="call-pointer",
            threshold=1,
        )

    assert f"Full output saved to: {path}" in persisted
    projected = project_historical_message(
        {"role": "tool", "tool_call_id": "call-pointer", "content": persisted}
    )

    assert len(projected["content"]) <= 1536
    assert f"Full output saved to: {path}" in projected["content"]
    assert "historical tool result compacted" in projected["content"]
    assert "sha256=" in projected["content"]
