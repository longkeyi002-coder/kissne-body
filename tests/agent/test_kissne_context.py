"""Contract tests for the first Kissne context-substrate seam."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.conversation_compression import _rebuild_system_prompt_at_boundary
from agent.kissne_context import (
    KISSNE_LIVE_CONTEXT_CLOSE,
    KISSNE_LIVE_CONTEXT_OPEN,
    KISSNE_USER_MESSAGE_CLOSE,
    KISSNE_USER_MESSAGE_OPEN,
    build_live_delta,
    make_context_layers,
)
from agent.prompt_builder import load_self_md
from agent.system_prompt import (
    _assemble_prompt_parts,
    _kissne_volatile_head,
    build_system_prompt,
    invalidate_system_prompt,
)
from agent.turn_context import build_api_messages
from hermes_cli.config import _ensure_default_self_md
from hermes_cli.default_self import (
    DEFAULT_SELF_MD,
    LEGACY_DEFAULT_SELF_MD,
)


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


def test_missing_self_md_is_created_at_the_canonical_home_root(tmp_path):
    _ensure_default_self_md(tmp_path)

    self_path = tmp_path / "SELF.md"
    assert self_path.is_file()
    assert self_path.read_text(encoding="utf-8") == DEFAULT_SELF_MD
    assert not (tmp_path / "memories" / "SELF.md").exists()


def test_existing_self_md_is_never_overwritten(tmp_path):
    self_path = tmp_path / "SELF.md"
    self_path.write_text("my established current self", encoding="utf-8")

    _ensure_default_self_md(tmp_path)

    assert self_path.read_text(encoding="utf-8") == "my established current self"


def test_self_md_falls_back_to_the_legacy_location_before_migration(tmp_path):
    memories = tmp_path / "memories"
    memories.mkdir()
    (memories / "SELF.md").write_text("REAL LEGACY SELF", encoding="utf-8")

    rendered = load_self_md(home_override=tmp_path)

    assert rendered is not None
    assert rendered.startswith("## SELF")
    assert "REAL LEGACY SELF" in rendered


def test_home_initialization_migrates_legacy_self_without_deleting_it(tmp_path):
    memories = tmp_path / "memories"
    memories.mkdir()
    legacy_path = memories / "SELF.md"
    legacy_path.write_text("REAL LEGACY SELF", encoding="utf-8")

    _ensure_default_self_md(tmp_path)

    assert (tmp_path / "SELF.md").read_text(encoding="utf-8") == "REAL LEGACY SELF"
    assert legacy_path.read_text(encoding="utf-8") == "REAL LEGACY SELF"
    assert "REAL LEGACY SELF" in load_self_md(home_override=tmp_path)


def test_old_generated_template_cannot_shadow_real_legacy_self(tmp_path):
    (tmp_path / "SELF.md").write_text(
        LEGACY_DEFAULT_SELF_MD, encoding="utf-8"
    )
    memories = tmp_path / "memories"
    memories.mkdir()
    (memories / "SELF.md").write_text("REAL LEGACY SELF", encoding="utf-8")

    _ensure_default_self_md(tmp_path)

    assert (tmp_path / "SELF.md").read_text(encoding="utf-8") == "REAL LEGACY SELF"


def test_seeded_default_self_passes_its_own_context_scanner(tmp_path):
    _ensure_default_self_md(tmp_path)

    rendered = load_self_md(home_override=tmp_path)

    assert rendered is not None
    assert "[BLOCKED:" not in rendered
    assert "No evolving self-description" in rendered


def test_volatile_snapshot_order_and_reverse_order_guard():
    ordered = _kissne_volatile_head(
        "SELF SNAPSHOT", ["MEMORY SNAPSHOT"], "SKILLS INDEX"
    )

    assert ordered == ["SELF SNAPSHOT", "MEMORY SNAPSHOT", "SKILLS INDEX"]
    assert ordered != ["SKILLS INDEX", "SELF SNAPSHOT", "MEMORY SNAPSHOT"]


def test_assembled_volatile_prompt_uses_ctx_14_physical_order():
    agent = SimpleNamespace(
        context_compressor=None,
        valid_tool_names=set(),
        load_soul_identity=True,
        skip_context_files=False,
    )
    with (
        patch("agent.system_prompt._identity_parts", return_value=(["SOUL"], True)),
        patch("agent.system_prompt._guidance_parts", return_value=[]),
        patch("agent.system_prompt._skills_prompt", return_value="SKILLS INDEX"),
        patch("agent.system_prompt._alibaba_identity_part", return_value=[]),
        patch("agent.system_prompt._coding_parts", return_value=([], [], [])),
        patch("agent.system_prompt._post_workspace_parts", return_value=[]),
        patch("agent.system_prompt._context_files_part", return_value=[]),
        patch("agent.system_prompt._agent_home", return_value=None),
        patch("agent.prompt_builder.build_environment_hints", return_value=""),
        patch("agent.prompt_builder.load_self_md", return_value="SELF SNAPSHOT"),
        patch("agent.system_prompt._memory_parts", return_value=["MEMORY SNAPSHOT"]),
        patch("agent.system_prompt._frozen_plugin_prompt_sections", return_value={}),
        patch("agent.system_prompt._plugin_section_blocks", return_value=[]),
        patch("agent.system_prompt._timestamp_line", return_value="SESSION INFO"),
    ):
        volatile = _assemble_prompt_parts(agent)["volatile"]

    expected = ["SELF SNAPSHOT", "MEMORY SNAPSHOT", "SKILLS INDEX", "SESSION INFO"]
    assert [volatile.index(item) for item in expected] == sorted(
        volatile.index(item) for item in expected
    )
    # Reverse-direction guard against the previous Skills-first assembly.
    assert volatile.index("SKILLS INDEX") > volatile.index("MEMORY SNAPSHOT")


class _WireAgent:
    session_id = "test-session"
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


class _ReloadableMemory:
    def __init__(self, content):
        self.content = content
        self.disk_content = content
        self.reloads = 0

    def load_from_disk(self):
        self.content = self.disk_content
        self.reloads += 1


def _snapshot_parts(home, memory):
    self_state = load_self_md(home_override=home) or ""
    memory_state = memory.content
    return {
        "stable": "SOUL SNAPSHOT",
        "context": "",
        "volatile": "\n\n".join((self_state, memory_state)),
        "kissne_stable_core": "SOUL SNAPSHOT",
        "kissne_self": self_state,
        "kissne_memory": memory_state,
    }


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


def test_request_local_context_is_not_replayed_and_cache_scope_is_explicit():
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

    # The system plus older canonical history is byte-stable. The immediately
    # previous current-user projection is intentionally not part of that
    # reusable prefix because its Live Delta must not be replayed.
    assert second_wire[0] == first_wire[0]
    assert second_wire[1]["content"] != first_wire[1]["content"]

    messages.extend([
        {"role": "assistant", "content": "second answer"},
        {"role": "user", "content": "third user"},
    ])
    third_wire, _ = build_api_messages(
        agent,
        messages,
        current_turn_user_idx=4,
        ext_prefetch_cache="third recall",
        plugin_user_context="third runtime context",
        moa_config=None,
        active_system_prompt="legacy full prompt",
    )
    assert third_wire[:3] == second_wire[:3]
    assert third_wire[3]["content"] == "second user"
    assert second_wire[3]["content"] != third_wire[3]["content"]


@pytest.mark.parametrize(
    ("api_mode", "provider", "moa_config"),
    [
        ("codex_app_server", "test", None),
        ("chat_completions", "moa", None),
        ("chat_completions", "test", {}),
    ],
)
def test_protocol_owned_modes_skip_kissne_user_projection(
    api_mode, provider, moa_config
):
    agent = _WireAgent()
    agent.api_mode = api_mode
    agent.provider = provider
    messages = [{"role": "user", "content": "protocol-owned user"}]

    wire, _ = build_api_messages(
        agent,
        messages,
        current_turn_user_idx=0,
        ext_prefetch_cache="must not be wrapped",
        plugin_user_context="must not be wrapped",
        moa_config=moa_config,
        active_system_prompt="legacy full prompt",
    )

    assert wire[1]["content"] == "protocol-owned user"
    assert KISSNE_LIVE_CONTEXT_OPEN not in wire[1]["content"]
    assert messages == [{"role": "user", "content": "protocol-owned user"}]


def test_normal_turn_does_not_hot_reload_self_snapshot(tmp_path):
    self_path = tmp_path / "SELF.md"
    self_path.write_text("SELF V1", encoding="utf-8")
    memory = _ReloadableMemory("MEMORY V1")
    agent = _WireAgent()
    agent._memory_store = memory
    agent._emit_status = lambda _message: None

    with patch(
        "agent.system_prompt._assemble_prompt_parts",
        side_effect=lambda *_a, **_k: _snapshot_parts(tmp_path, memory),
    ):
        agent._cached_system_prompt = build_system_prompt(agent)
        self_path.write_text("SELF V2", encoding="utf-8")
        memory.disk_content = "MEMORY V2"

        wire, effective_system = build_api_messages(
            agent,
            [{"role": "user", "content": "next turn"}],
            current_turn_user_idx=0,
            ext_prefetch_cache="",
            plugin_user_context="",
            moa_config=None,
            active_system_prompt=agent._cached_system_prompt,
        )

    assert "SELF V1" in effective_system
    assert "MEMORY V1" in effective_system
    assert "SELF V2" not in effective_system
    assert "MEMORY V2" not in effective_system
    assert wire[0]["content"] == effective_system
    assert memory.reloads == 0


def test_compression_boundary_reloads_self_and_memory_snapshot(tmp_path):
    self_path = tmp_path / "SELF.md"
    self_path.write_text("SELF V1", encoding="utf-8")
    memory = _ReloadableMemory("MEMORY V1")
    agent = _WireAgent()
    agent._memory_store = memory
    agent._emit_status = lambda _message: None
    agent._invalidate_system_prompt = (
        lambda reason=None: invalidate_system_prompt(agent, reason)
    )
    agent._build_system_prompt = (
        lambda system_message=None: build_system_prompt(agent, system_message)
    )

    with (
        patch(
            "agent.system_prompt._assemble_prompt_parts",
            side_effect=lambda *_a, **_k: _snapshot_parts(tmp_path, memory),
        ),
        patch(
            "agent.conversation_compression._refresh_agent_tool_definitions",
            return_value=None,
        ),
    ):
        agent._cached_system_prompt = build_system_prompt(agent)
        self_path.write_text("SELF V2", encoding="utf-8")
        memory.disk_content = "MEMORY V2"

        refreshed = _rebuild_system_prompt_at_boundary(agent, "")

    assert "SELF V2" in refreshed
    assert "MEMORY V2" in refreshed
    assert "SELF V1" not in refreshed
    assert "MEMORY V1" not in refreshed
    assert memory.reloads == 1
    assert agent._kissne_context_layers.session_snapshot.origin == "compression"


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
