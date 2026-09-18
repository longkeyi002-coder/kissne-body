"""SELF.md rides the memory-store injection chain (``target="self"``).

Contract pinned here:

* ``MemoryStore.format_for_system_prompt("self")`` is the SELF block, rendered
  with SELF's OWN header (never MEMORY's) from ``<HERMES_HOME>/SELF.md`` —
  ``memories/SELF.md`` is the legacy migration source, never a data source;
* the frozen-snapshot rule holds for SELF exactly as for MEMORY/USER: a
  mid-session write does not touch this session's system prompt;
* SELF.md is an entry list like MEMORY.md (§-delimited): ``add``/``replace``/
  ``remove``/``operations`` all apply, and its bytes still never count against
  MEMORY's 2,200-char budget (SELF is uncapped);
* ``replace_whole_file`` stays as the one-call whole-file rewrite escape hatch;
* KB1-IDENTITY-DEGRADED still fires: a missing or untouched-placeholder SELF.md
  keeps producing the explicit degraded notice in ``kissne_self``.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.system_prompt import _assemble_prompt_parts, _self_block
from hermes_cli.default_self import DEFAULT_SELF_MD
from tools.memory_tool import ENTRY_DELIMITER, MEMORY_BLOCK_HEADERS, MemoryStore, memory_tool

CUSTOM_SELF = "# Self\n\nI answer more briefly now, and I like tea."


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated HERMES_HOME; SELF.md lives at its root (canonical location)."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(h))
    return h


def _agent(**overrides):
    """Minimal agent stub for ``_assemble_prompt_parts`` (shape of the identity suite)."""
    base = dict(
        load_soul_identity=True,
        skip_context_files=True,
        valid_tool_names=[],
        _task_completion_guidance=False,
        _tool_use_enforcement=False,
        _execution_guidance=False,
        _environment_probe=False,
        _kanban_worker_guidance="",
        _memory_store=None,
        _memory_enabled=True,
        _user_profile_enabled=True,
        _memory_manager=None,
        context_compressor=None,
        model="",
        provider="",
        platform="",
        pass_session_id=False,
        session_id="",
        _emit_status=lambda *_a, **_k: None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _parts(store):
    agent = _agent(_memory_store=store)
    with (
        patch("agent.system_prompt._skills_prompt", return_value=""),
        patch("agent.system_prompt._frozen_plugin_prompt_sections", return_value={}),
        patch("agent.system_prompt._plugin_section_blocks", return_value=[]),
        patch("agent.system_prompt._timestamp_line", return_value=""),
        patch("agent.prompt_builder.build_environment_hints", return_value=""),
    ):
        return agent, _assemble_prompt_parts(agent)


# ── 1. the store serves the SELF block, with SELF's header ──────────────────


def test_self_block_comes_from_the_store_with_its_own_header(home):
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    block = store.format_for_system_prompt("self")
    assert block is not None
    assert CUSTOM_SELF in block
    assert MEMORY_BLOCK_HEADERS["self"] in block
    # The two-way-fallback bug: SELF must never render as the notes store.
    assert MEMORY_BLOCK_HEADERS["memory"] not in block
    assert MEMORY_BLOCK_HEADERS["user"] not in block


def test_self_block_is_injected_first_in_the_volatile_band(home):
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    (home / "memories").mkdir()
    (home / "memories" / "MEMORY.md").write_text("Deploy target is Ubuntu 24.04.", encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()  # snapshot freezes BOTH blocks here

    _agent_obj, parts = _parts(store)

    volatile = parts["volatile"]
    assert volatile.startswith(store.format_for_system_prompt("self"))
    assert volatile.index(MEMORY_BLOCK_HEADERS["self"]) < volatile.index(MEMORY_BLOCK_HEADERS["memory"])
    assert CUSTOM_SELF in parts["kissne_self"]


def test_self_reads_the_canonical_root_and_ignores_the_legacy_memories_copy(home):
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    (home / "memories").mkdir()
    (home / "memories" / "SELF.md").write_text("LEGACY SELF FROM memories/", encoding="utf-8")

    store = MemoryStore()
    store.load_from_disk()

    assert MemoryStore._path_for("self") == home / "SELF.md"
    assert "LEGACY SELF FROM memories/" not in (store.format_for_system_prompt("self") or "")


def test_render_block_refuses_an_unknown_target_instead_of_defaulting_to_memory(home):
    store = MemoryStore()
    with pytest.raises(ValueError):
        store._render_block("soul", ["anything"])


# ── 2. frozen snapshot semantics (prefix cache) ─────────────────────────────


def test_self_write_does_not_change_this_session_snapshot(home):
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()
    frozen = store.format_for_system_prompt("self")

    assert store.replace("self", "I like tea", "REWRITTEN SELF")["success"] is True

    # Live state moved on, the frozen snapshot did not (same rule as MEMORY/USER).
    assert store.self_text == "REWRITTEN SELF"
    assert store.format_for_system_prompt("self") == frozen
    assert "REWRITTEN SELF" not in (store.format_for_system_prompt("self") or "")

    fresh = MemoryStore()
    fresh.load_from_disk()
    assert "REWRITTEN SELF" in (fresh.format_for_system_prompt("self") or "")


# ── 3. whole-file write semantics ───────────────────────────────────────────


def test_replace_target_self_edits_only_the_matching_entry(home):
    keep = "# Self\n\nKeeps replies short."
    (home / "SELF.md").write_text(f"{keep}{ENTRY_DELIMITER}Likes tea.\n", encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    result = json.loads(memory_tool(action="replace", target="self", old_text="tea",
                                    content="Drinks coffee instead.", store=store))

    assert result["success"] is True
    assert result["target"] == "self"
    assert store._entries_for("self") == [keep, "Drinks coffee instead."]
    written = (home / "SELF.md").read_text(encoding="utf-8")
    assert keep in written and "Drinks coffee instead." in written and "Likes tea." not in written


def test_add_appends_a_new_entry_to_self(home):
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    result = json.loads(memory_tool(action="add", target="self", content="Keeps replies short.", store=store))

    assert result["success"] is True
    assert store._entries_for("self") == [CUSTOM_SELF, "Keeps replies short."]
    assert "Keeps replies short." in (home / "SELF.md").read_text(encoding="utf-8")


def test_remove_drops_only_the_matching_entry(home):
    keep = "# Self\n\nKeeps replies short."
    (home / "SELF.md").write_text(f"{keep}{ENTRY_DELIMITER}Likes tea.\n", encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    result = json.loads(memory_tool(action="remove", target="self", old_text="tea", store=store))

    assert result["success"] is True
    assert store._entries_for("self") == [keep]
    assert "Likes tea." not in (home / "SELF.md").read_text(encoding="utf-8")


def test_batch_operations_apply_to_self_in_one_call(home):
    keep = "# Self\n\nKeeps replies short."
    (home / "SELF.md").write_text(keep, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    result = json.loads(memory_tool(target="self", operations=[
        {"action": "add", "content": "Likes tea."},
        {"action": "replace", "old_text": "Keeps replies short", "content": "Keeps replies very short."},
    ], store=store))

    assert result["success"] is True
    assert store._entries_for("self") == ["Keeps replies very short.", "Likes tea."]


def test_a_batch_may_not_empty_self(home):
    """#103419 still holds: an all-or-nothing batch cannot wipe the last entry."""
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    result = json.loads(memory_tool(
        target="self", operations=[{"action": "remove", "old_text": "tea"}], store=store))

    assert result["success"] is False
    assert "empty" in result["error"]
    assert (home / "SELF.md").read_text(encoding="utf-8").strip() == CUSTOM_SELF


def test_self_entry_calls_write_self_and_never_reroute_into_memory(home):
    """The store's own entry API targets SELF.md, not the notes store."""
    store = MemoryStore()
    store.load_from_disk()

    assert store.add("self", "entry")["success"] is True
    assert store.replace("self", "entry", "changed")["success"] is True
    assert store.remove("self", "changed")["success"] is True
    assert store.apply_batch("self", [{"action": "add", "content": "batched"}])["success"] is True

    assert (home / "SELF.md").read_text(encoding="utf-8").strip() == "batched"
    assert store.memory_entries == []
    assert not (MemoryStore._path_for("memory")).exists()


def test_self_entry_writes_require_their_fields(home):
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    # replace without old_text has no entry to select.
    missing_old = json.loads(memory_tool(action="replace", target="self", content="NEW", store=store))
    assert missing_old["success"] is False
    assert "old_text" in missing_old["error"]

    # replace with old_text but blank content is refused too.
    blank = json.loads(memory_tool(action="replace", target="self", old_text="tea", content="   ", store=store))
    assert blank["success"] is False
    assert "content" in blank["error"]

    assert (home / "SELF.md").read_text(encoding="utf-8").strip() == CUSTOM_SELF


def test_invalid_target_error_names_self(home):
    store = MemoryStore()
    store.load_from_disk()

    result = json.loads(memory_tool(action="replace", target="soul", content="x", store=store))

    assert result["success"] is False
    assert "'self'" in result["error"]


# ── 4. SELF is outside MEMORY's budget ──────────────────────────────────────


def test_self_bytes_do_not_touch_memory_budget_or_usage_pct(home):
    (home / "SELF.md").write_text("x" * 5000, encoding="utf-8")
    store = MemoryStore(memory_char_limit=100)
    store.load_from_disk()
    store.add("memory", "Deploy target is Ubuntu 24.04.")

    assert store._char_count("self") == 5000
    assert store._char_count("memory") == len("Deploy target is Ubuntu 24.04.")
    assert store._char_limit("self") == 0
    assert "2,200" not in store._usage_pct("self", 5000)
    assert store._usage_pct("self", 5000) == "5,000 chars (unbudgeted)"
    # A huge SELF.md must not block memory writes.
    assert store.add("memory", "second note")["success"] is True


# ── 5. KB1-IDENTITY-DEGRADED still fires on the store path ──────────────────


@pytest.mark.parametrize("body,reason", [
    (None, "SELF.md:missing"),
    (DEFAULT_SELF_MD, "SELF.md:placeholder"),
])
def test_degraded_notice_survives_the_store_path(home, body, reason):
    if body is not None:
        (home / "SELF.md").write_text(body, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    agent, parts = _parts(store)

    assert reason in parts["kissne_self"]
    assert "KISSNE-IDENTITY-DEGRADED" in parts["kissne_self"]
    assert parts["kissne_self"] == parts["volatile"].split("\n\n")[0]
    assert reason in agent._identity_state.reasons


def test_healthy_self_produces_no_notice_on_the_store_path(home):
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()

    agent, parts = _parts(store)

    assert not [r for r in agent._identity_state.reasons if r.startswith("SELF.md")]
    assert "KISSNE-IDENTITY-DEGRADED" not in parts["volatile"]
    assert CUSTOM_SELF in parts["kissne_self"]


def test_self_block_reader_is_the_store_not_a_private_file_read(home):
    """``_self_block`` must go through the store when one is attached."""
    (home / "SELF.md").write_text(CUSTOM_SELF, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()
    agent = _agent(_memory_store=store)

    with patch("agent.prompt_builder.load_self_md") as legacy_reader:
        block = _self_block(agent, None)

    legacy_reader.assert_not_called()
    assert block == store.format_for_system_prompt("self")
