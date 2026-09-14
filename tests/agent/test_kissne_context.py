"""Contract tests for the first Kissne context-substrate seam."""

from datetime import datetime, timezone

from agent.kissne_context import build_live_delta, make_context_layers
from agent.prompt_builder import load_self_md
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
    assert read.unified_history is not layers.unified_history


def test_live_delta_has_exact_request_time_and_provenance():
    moment = datetime(2026, 9, 14, 22, 3, 4, tzinfo=timezone.utc)

    delta = build_live_delta(moment=moment, earth_state="phone online")

    rendered = delta.render()
    assert "2026-09-14T22:03:04+00:00" in rendered
    assert "phone online" in rendered
    assert "Clock source: hermes_time" in rendered


def test_self_md_is_a_separate_snapshot_input(tmp_path):
    (tmp_path / "SELF.md").write_text(
        "I am learning to be more patient.", encoding="utf-8"
    )

    rendered = load_self_md(home_override=tmp_path)

    assert rendered is not None
    assert rendered.startswith("## SELF")
    assert "more patient" in rendered


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
    assert "current user" in wire[1]["content"]
    assert "<kissne_live_delta>" in wire[1]["content"]
    assert "Exact Earth time:" in wire[1]["content"]
    assert messages == [{"role": "user", "content": "current user"}]
    assert list(agent._kissne_context_last_read.unified_history) == messages
    assert "<kissne_live_delta>" not in str(
        agent._kissne_context_last_read.unified_history
    )


def test_resume_fallback_does_not_reread_or_relabel_cached_prompt():
    layers = make_context_layers(
        runtime_system_prompt="persisted prompt",
        snapshot_origin="resume_persisted_prompt",
    )

    assert layers.stable_core == ""
    assert layers.session_snapshot.render() == ""
    assert layers.session_snapshot.origin == "resume_persisted_prompt"
    assert layers.system_prompt() == "persisted prompt"
