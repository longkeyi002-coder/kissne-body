import json

from agent.historical_context_projection import project_historical_message


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
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + ("A" * 10000)}},
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
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + ("B" * 10000)}},
        ],
    }

    projected = project_historical_message(original)

    assert len(projected["content"][0]["text"]) <= 1536
    assert "historical tool result compacted" in projected["content"][0]["text"]
    assert projected["content"][1]["type"] == "text"
    assert "historical image omitted" in projected["content"][1]["text"]
    assert original["content"][1]["type"] == "image_url"
