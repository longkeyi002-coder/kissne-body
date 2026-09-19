"""Regression guard for the high-frequency core tool schema diet.

These schemas ride in model context whenever the tools are eager.  Keep the
model-facing surface compact; rare/invalid-call guidance belongs in runtime
errors instead of every request.
"""

import json

import model_tools  # noqa: F401  # trigger core tool registration
from tools.memory_tool import MEMORY_SCHEMA
from tools.registry import registry
from tools.terminal_tool import TERMINAL_TOOL_DESCRIPTION


_TARGETS = {
    "delegate_task",
    "memory",
    "skill_manage",
    "terminal",
    "search_files",
    "patch",
    "read_file",
}


def _functions():
    definitions = registry.get_definitions(_TARGETS)
    by_name = {d["function"]["name"]: d["function"] for d in definitions}
    assert _TARGETS <= set(by_name)
    return by_name


def test_hot_schema_surface_stays_under_budget():
    functions = _functions()
    total_chars = sum(
        len(json.dumps(functions[name], separators=(",", ":"), ensure_ascii=False))
        for name in _TARGETS
    )
    # Before this diet these seven model-facing schemas were ~21.7K chars.
    # Leave headroom for dynamic limits/model-family variants while guarding
    # against the explanatory prose growing back.
    assert total_chars <= 15_500, total_chars


def test_terminal_description_stays_compact():
    assert len(TERMINAL_TOOL_DESCRIPTION) <= 300
    assert "exported environment variables persist between calls" in TERMINAL_TOOL_DESCRIPTION
    assert "once per session" in TERMINAL_TOOL_DESCRIPTION


def test_memory_advertises_one_call_shape():
    props = MEMORY_SCHEMA["parameters"]["properties"]
    assert set(props) == {"target", "operations"}
    assert MEMORY_SCHEMA["parameters"]["required"] == ["target", "operations"]
    item_props = props["operations"]["items"]["properties"]
    assert set(item_props) == {"action", "content", "old_text"}
