"""Contract tests for the first Kissne context-substrate seam."""

from agent.kissne_context import ContextReadPolicy, make_context_layers
from agent.turn_context import build_api_messages


def test_default_read_keeps_all_layers_separate():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    layers = make_context_layers(
        stable_core="core",
        snapshot="snapshot",
        history=history,
        live_delta="recall",
    )

    read = layers.read()

    assert read.system_prompt == "core\n\nsnapshot"
    assert read.live_delta == "recall"
    assert list(read.history) == history
    assert read.history is not layers.history
    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_read_time_history_limit_starts_at_user_boundary_and_keeps_current_turn():
    history = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent answer"},
        {"role": "user", "content": "current user"},
    ]
    layers = make_context_layers(history=history)

    read = layers.read(
        policy=ContextReadPolicy(history_limit=2),
        current_turn_user_index=4,
    )

    assert [message["content"] for message in read.history] == [
        "recent user",
        "recent answer",
        "current user",
    ]
    assert history[0]["content"] == "old user"


def test_unsafe_history_cut_fails_open():
    history = [
        {"role": "assistant", "content": "orphaned assistant"},
        {"role": "tool", "content": "orphaned tool"},
    ]

    read = make_context_layers(history=history).read(
        policy=ContextReadPolicy(history_limit=1),
    )

    assert list(read.history) == history


def test_live_delta_is_never_rendered_into_system_prompt():
    read = make_context_layers(
        stable_core="stable",
        snapshot="snapshot",
        live_delta="per-request memory",
    ).read()

    assert "per-request memory" not in read.system_prompt


class _WireAgent:
    provider = "test"
    api_mode = "chat_completions"
    model = "test-model"
    ephemeral_system_prompt = None
    prefill_messages = []
    _use_prompt_caching = False
    _kissne_context_read_policy = ContextReadPolicy(history_limit=2)
    _kissne_context_layers = make_context_layers(
        stable_core="core",
        snapshot="snapshot",
    )

    def _copy_reasoning_content_for_api(self, _source, _target):
        return None

    def _should_sanitize_tool_calls(self):
        return False


def test_request_assembly_uses_read_time_projection():
    messages = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent answer"},
        {"role": "user", "content": "current user"},
    ]

    wire, system = build_api_messages(
        _WireAgent(),
        messages,
        current_turn_user_idx=4,
        ext_prefetch_cache="",
        plugin_user_context="",
        moa_config=None,
        active_system_prompt="legacy full prompt",
    )

    # A stored legacy prompt remains authoritative when only history is
    # filtered; the layer object still controls the request-local projection.
    assert system == "legacy full prompt"
    assert [message["content"] for message in wire] == [
        "legacy full prompt",
        "recent user",
        "recent answer",
        "current user",
    ]
    assert [message["content"] for message in messages] == [
        "old user",
        "old answer",
        "recent user",
        "recent answer",
        "current user",
    ]
