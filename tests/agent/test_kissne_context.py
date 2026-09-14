"""Contract tests for the first Kissne context-substrate seam."""

from datetime import datetime, timezone

from agent.kissne_context import (
    KISSNE_LIVE_CONTEXT_CLOSE,
    KISSNE_LIVE_CONTEXT_OPEN,
    KISSNE_USER_MESSAGE_CLOSE,
    KISSNE_USER_MESSAGE_OPEN,
    build_live_delta,
    make_context_layers,
)
from agent.prompt_builder import load_self_md
from agent.system_prompt import _kissne_volatile_head
from agent.turn_context import build_api_messages


def test_semantic_layers_keep_runtime_cache_tiers_separate():
    history = [{"role": "user", "content": "hello"}]
    layers = make_context_layers(
        stable_core="SOUL only",
        self_state="growing SELF",
        memory_state="frozen MEMORY",
        unified_history=history,
        runtime_system_prompt="complete Hermes runtime prompt",
    )

    read = layers.read(turn_recall="recalled fact")

    assert read.stable_core == "SOUL only"
    assert read.session_snapshot.render() == "growing SELF\n\nfrozen MEMORY"
    assert read.system_prompt == "complete Hermes runtime prompt"
    assert read.turn_recall == "recalled fact"
    assert list(read.unified_history) == history
    # The contract is immutability + independence, not object identity: for a
    # tuple input, ``tuple(t) is t`` is implementation-defined. Mutating the
    # source list after the snapshot must not reach the read.
    history.append({"role": "user", "content": "later"})
    assert list(read.unified_history) == [{"role": "user", "content": "hello"}]


def test_live_delta_has_exact_request_time_and_provenance():
    moment = datetime(2026, 9, 14, 22, 3, 4, tzinfo=timezone.utc)

    delta = build_live_delta(moment=moment, earth_state="phone online")

    rendered = delta.render()
    assert "2026-09-14T22:03:04+00:00" in rendered
    assert "phone online" in rendered
    assert "Clock source: hermes_time" in rendered


def test_self_md_uses_the_canonical_home_root(tmp_path):
    (tmp_path / "SELF.md").write_text(
        "I am learning to be more patient.", encoding="utf-8"
    )

    rendered = load_self_md(home_override=tmp_path)

    assert rendered is not None
    assert rendered.startswith("## SELF")
    assert "more patient" in rendered


def test_self_md_rejects_the_old_memories_location(tmp_path):
    memories = tmp_path / "memories"
    memories.mkdir()
    (memories / "SELF.md").write_text(
        "wrong duplicate identity source", encoding="utf-8"
    )

    # Reverse-direction guard: MemoryStore's directory must not become a
    # second identity truth source.
    assert load_self_md(home_override=tmp_path) is None


def test_volatile_snapshot_order_and_reverse_order_guard():
    ordered = _kissne_volatile_head(
        "SELF SNAPSHOT", ["MEMORY SNAPSHOT"], "SKILLS INDEX"
    )

    assert ordered == ["SELF SNAPSHOT", "MEMORY SNAPSHOT", "SKILLS INDEX"]
    assert ordered != ["SKILLS INDEX", "SELF SNAPSHOT", "MEMORY SNAPSHOT"]


class _WireAgent:
    provider = "test"
    api_mode = "chat_completions"
    model = "test-model"
    ephemeral_system_prompt = None
    prefill_messages = []
    _use_prompt_caching = False
    _current_turn_timestamp = datetime(2026, 9, 14, tzinfo=timezone.utc)
    _kissne_context_layers = make_context_layers(
        stable_core="SOUL",
        self_state="SELF",
        memory_state="MEMORY",
        runtime_system_prompt="legacy full prompt",
    )
    _kissne_earth_state = ""
    _kissne_ai_world_state = ""

    def _copy_reasoning_content_for_api(self, _source, _target):
        return None

    def _should_sanitize_tool_calls(self):
        return False


def test_request_assembly_injects_live_delta_without_changing_history():
    messages = [{"role": "user", "content": "current user"}]

    agent = _WireAgent()
    wire, system = build_api_messages(
        agent,
        messages,
        current_turn_user_idx=0,
        ext_prefetch_cache="recalled memory",
        plugin_user_context="plugin context",
        moa_config=None,
        active_system_prompt="legacy full prompt",
    )

    assert system == "legacy full prompt"
    assert wire[0] == {"role": "system", "content": "legacy full prompt"}
    request_content = wire[1]["content"]
    assert "<kissne_live_delta>" in request_content
    assert "Exact Earth time:" in request_content
    assert "recalled memory" in request_content
    assert "plugin context" in request_content
    assert request_content.startswith(KISSNE_LIVE_CONTEXT_OPEN)
    assert request_content.endswith(KISSNE_USER_MESSAGE_CLOSE)
    assert (
        request_content.index(KISSNE_LIVE_CONTEXT_OPEN)
        < request_content.index(KISSNE_LIVE_CONTEXT_CLOSE)
        < request_content.index(KISSNE_USER_MESSAGE_OPEN)
        < request_content.index("current user")
        < request_content.index(KISSNE_USER_MESSAGE_CLOSE)
    )
    # Reverse-direction guards: neither the user's words nor Live Delta may
    # appear in the old suffix order.
    assert not request_content.startswith("current user")
    assert request_content.rfind("<kissne_live_delta>") < request_content.index(
        KISSNE_USER_MESSAGE_OPEN
    )
    assert messages == [{"role": "user", "content": "current user"}]
    assert "api_content" not in messages[0]
    assert list(agent._kissne_context_last_read.unified_history) == messages
    assert "<kissne_live_delta>" not in str(
        agent._kissne_context_last_read.unified_history
    )


def test_request_local_context_is_not_replayed_on_the_next_turn():
    agent = _WireAgent()
    messages = [{"role": "user", "content": "first user"}]

    first_wire, _ = build_api_messages(
        agent,
        messages,
        current_turn_user_idx=0,
        ext_prefetch_cache="first recall",
        plugin_user_context="first runtime context",
        moa_config=None,
        active_system_prompt="legacy full prompt",
    )
    assert KISSNE_LIVE_CONTEXT_OPEN in first_wire[1]["content"]
    assert "api_content" not in messages[0]

    messages.extend([
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second user"},
    ])
    second_wire, _ = build_api_messages(
        agent,
        messages,
        current_turn_user_idx=2,
        ext_prefetch_cache="second recall",
        plugin_user_context="second runtime context",
        moa_config=None,
        active_system_prompt="legacy full prompt",
    )

    # Reverse-direction guard: the historical first user row is clean and its
    # previous request-local context does not reappear.
    assert second_wire[1]["content"] == "first user"
    assert KISSNE_LIVE_CONTEXT_OPEN not in second_wire[1]["content"]
    assert "first recall" not in str(second_wire)
    assert "second recall" in second_wire[3]["content"]


def test_fixed_live_context_delimiters_do_not_drift():
    assert KISSNE_LIVE_CONTEXT_OPEN == "<kissne_live_context>"
    assert KISSNE_LIVE_CONTEXT_CLOSE == "</kissne_live_context>"
    assert KISSNE_USER_MESSAGE_OPEN == "<user_message>"
    assert KISSNE_USER_MESSAGE_CLOSE == "</user_message>"


def test_resume_fallback_does_not_reread_or_relabel_cached_prompt():
    layers = make_context_layers(
        runtime_system_prompt="persisted prompt",
        snapshot_origin="resume_persisted_prompt",
    )

    assert layers.stable_core == ""
    assert layers.session_snapshot.render() == ""
    assert layers.session_snapshot.origin == "resume_persisted_prompt"
    assert layers.system_prompt() == "persisted prompt"
