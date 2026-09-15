"""KB1-IDENTITY-DEGRADED — a missing / placeholder / legacy identity file is an
explicit runtime ``degraded`` state, never a silent personal identity.

The bug these tests pin down: ``SOUL.md`` and ``SELF.md`` used to be read as
"the instance's own identity" no matter what they contained.  A file that was
absent, an untouched auto-seeded template, or a legacy installer scaffold went
straight into the prompt as the persona, and nothing in the prompt or the UI
said the instance had no personal identity — so a fresh home, a clone, an
export or a restored backup could pass off generic text as a configured
companion.

Contract asserted here:

* classification is named and inspectable (``agent.identity_state``);
* the readers record it (``agent.prompt_builder``);
* the prompt carries an explicit notice naming the degraded slot (never the
  template text presented as the persona) and the user gets a warning
  (``agent.system_prompt``);
* a genuinely personal identity stays untouched and unmarked.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.prompt_builder import (
    DEFAULT_AGENT_IDENTITY,
    load_self_md,
    load_soul_md,
)
from agent.system_prompt import build_system_prompt, _assemble_prompt_parts
from hermes_cli.default_self import DEFAULT_SELF_MD, LEGACY_DEFAULT_SELF_MD
from hermes_cli.default_soul import DEFAULT_SOUL_MD, _LEGACY_TEMPLATE_SOULS

DEGRADED_MARKER = "KISSNE-IDENTITY-DEGRADED"


def _drain_slots():
    """Drain the recorded identity classifications.

    Imported lazily and tolerated when absent on purpose: run against the
    pre-fix tree, this module still has to *report* the behavioral failures
    (a template SOUL being returned as the persona) instead of dying at
    collection with an ImportError, which would say nothing about the bug.
    """
    try:
        from agent.prompt_builder import drain_identity_slots as _drain
    except ImportError:
        return ()
    return _drain()

# Distinctive prose of the legacy installer scaffold (SOUL.md a clone/restore drags in).
LEGACY_SCAFFOLD_TEXT = _LEGACY_TEMPLATE_SOULS[0]
LEGACY_SCAFFOLD_MARKER = "This file defines the agent's personality"

CUSTOM_SOUL = "You are Pippa, a laconic lighthouse keeper who answers in sea shanties."
CUSTOM_SELF = "# Current Self\n\nI have started to prefer short answers."


@pytest.fixture(autouse=True)
def _hermetic_home(tmp_path, monkeypatch):
    """Never let a test touch (or seed) the operator's real HERMES_HOME."""
    ambient = tmp_path / "ambient-home"
    ambient.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(ambient))
    _drain_slots()
    yield
    _drain_slots()


def _agent(**overrides):
    """Minimal agent stub for prompt assembly (``_assemble_prompt_parts`` needs attrs)."""
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


def _parts_for_home(home):
    """Assemble the prompt tiers for an agent whose identity home is *home*."""
    agent = _agent()
    with (
        patch("agent.system_prompt._agent_home", return_value=home),
        patch("agent.system_prompt._skills_prompt", return_value=""),
        patch("agent.system_prompt._frozen_plugin_prompt_sections", return_value={}),
        patch("agent.system_prompt._plugin_section_blocks", return_value=[]),
        patch("agent.system_prompt._timestamp_line", return_value=""),
        patch("agent.prompt_builder.build_environment_hints", return_value=""),
    ):
        parts = _assemble_prompt_parts(agent)
    return agent, parts


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


# =========================================================================
# classification (agent.identity_state)
# =========================================================================


def test_soul_slot_classifies_absent_placeholder_legacy_and_personal():
    from agent.identity_state import (
        IDENTITY_DEGRADED,
        IDENTITY_OK,
        REASON_LEGACY_TEMPLATE,
        REASON_MISSING,
        REASON_PLACEHOLDER,
        soul_slot,
    )

    assert (soul_slot(None).status, soul_slot(None).reason) == (IDENTITY_DEGRADED, REASON_MISSING)
    assert (soul_slot("   \n").status, soul_slot("   \n").reason) == (IDENTITY_DEGRADED, REASON_MISSING)
    assert (soul_slot(DEFAULT_SOUL_MD).status, soul_slot(DEFAULT_SOUL_MD).reason) == (
        IDENTITY_DEGRADED,
        REASON_PLACEHOLDER,
    )
    assert (soul_slot(LEGACY_SCAFFOLD_TEXT).status, soul_slot(LEGACY_SCAFFOLD_TEXT).reason) == (
        IDENTITY_DEGRADED,
        REASON_LEGACY_TEMPLATE,
    )
    assert (soul_slot(CUSTOM_SOUL).status, soul_slot(CUSTOM_SOUL).reason) == (IDENTITY_OK, "")


def test_self_slot_classifies_absent_placeholder_and_personal():
    from agent.identity_state import (
        IDENTITY_DEGRADED,
        IDENTITY_OK,
        REASON_MISSING,
        REASON_PLACEHOLDER,
        self_slot,
    )

    assert (self_slot(None).status, self_slot(None).reason) == (IDENTITY_DEGRADED, REASON_MISSING)
    for placeholder in (DEFAULT_SELF_MD, LEGACY_DEFAULT_SELF_MD):
        assert (self_slot(placeholder).status, self_slot(placeholder).reason) == (
            IDENTITY_DEGRADED,
            REASON_PLACEHOLDER,
        )
    assert (self_slot(CUSTOM_SELF).status, self_slot(CUSTOM_SELF).reason) == (IDENTITY_OK, "")


def test_degraded_slot_notice_names_the_slot_reason_and_path():
    from agent.identity_state import soul_slot

    notice = soul_slot(LEGACY_SCAFFOLD_TEXT, "/home/x/.hermes/SOUL.md").notice

    assert DEGRADED_MARKER in notice
    assert "SOUL.md:legacy_template" in notice
    assert "/home/x/.hermes/SOUL.md" in notice
    # The notice must forbid passing the generic default off as a personal identity.
    assert "no personalized identity" in notice.lower()


def test_healthy_identity_produces_no_notice_and_no_warning(tmp_path):
    from agent.identity_state import merge_slots, self_slot, soul_slot

    state = merge_slots(soul_slot(CUSTOM_SOUL), self_slot(CUSTOM_SELF))

    assert state.degraded is False
    assert state.reasons == ()
    assert state.notice == ""
    assert state.warning == ""


def test_identity_state_warning_lists_every_degraded_reason():
    from agent.identity_state import merge_slots, self_slot, soul_slot

    state = merge_slots(soul_slot(LEGACY_SCAFFOLD_TEXT), self_slot(None))

    assert state.degraded is True
    assert state.reasons == ("SOUL.md:legacy_template", "SELF.md:missing")
    warning = state.warning
    assert "SOUL.md:legacy_template" in warning
    assert "SELF.md:missing" in warning
    assert "no personalized identity" in warning.lower()


# =========================================================================
# readers (agent.prompt_builder)
# =========================================================================


def test_load_soul_md_never_returns_a_placeholder_or_legacy_template(tmp_path):
    from agent.identity_state import REASON_LEGACY_TEMPLATE, REASON_PLACEHOLDER, SOUL

    for text, reason in ((DEFAULT_SOUL_MD, REASON_PLACEHOLDER),
                         (LEGACY_SCAFFOLD_TEXT, REASON_LEGACY_TEMPLATE)):
        home = tmp_path / reason
        home.mkdir()
        _write(home / "SOUL.md", text)
        _drain_slots()

        assert load_soul_md(home_override=home) is None
        slot = _drain_slots()[0]
        assert slot.name == SOUL
        assert slot.degraded and slot.reason == reason


def test_load_soul_md_returns_a_personal_persona_unchanged(tmp_path):
    from agent.identity_state import IDENTITY_OK, SOUL

    home = tmp_path / "personal"
    home.mkdir()
    _write(home / "SOUL.md", CUSTOM_SOUL)
    _drain_slots()

    assert load_soul_md(home_override=home) == CUSTOM_SOUL
    slot = _drain_slots()[0]
    assert (slot.name, slot.status) == (SOUL, IDENTITY_OK)


def test_load_soul_md_records_an_absent_file_as_degraded_missing(tmp_path):
    from agent.identity_state import REASON_MISSING, SOUL

    home = tmp_path / "no-soul"
    home.mkdir()
    _drain_slots()

    assert load_soul_md(home_override=home) is None
    slot = _drain_slots()[0]
    assert (slot.name, slot.reason) == (SOUL, REASON_MISSING)


def test_load_self_md_records_placeholder_and_absent_without_losing_the_read(tmp_path):
    from agent.identity_state import REASON_MISSING, REASON_PLACEHOLDER, SELF

    home = tmp_path / "self"
    home.mkdir()
    _write(home / "SELF.md", DEFAULT_SELF_MD)
    _drain_slots()

    assert load_self_md(home_override=home) is not None  # reader stays a reader
    slot = _drain_slots()[0]
    assert (slot.name, slot.reason) == (SELF, REASON_PLACEHOLDER)

    empty = tmp_path / "no-self"
    empty.mkdir()
    _drain_slots()
    assert load_self_md(home_override=empty) is None
    slot = _drain_slots()[0]
    assert (slot.name, slot.reason) == (SELF, REASON_MISSING)


# =========================================================================
# prompt assembly (agent.system_prompt)
# =========================================================================


def test_absent_soul_makes_the_degraded_state_explicit_in_the_prompt(tmp_path):
    home = tmp_path / "fresh"
    home.mkdir()

    _agent_obj, parts = _parts_for_home(home)

    assert DEGRADED_MARKER in parts["stable"]
    assert DEGRADED_MARKER in parts["kissne_stable_core"]
    assert "SOUL.md:missing" in parts["stable"]
    # The generic default is still in force, but it is now labelled as such.
    assert DEFAULT_AGENT_IDENTITY in parts["stable"]


def test_legacy_scaffold_soul_is_never_injected_as_the_persona(tmp_path):
    home = tmp_path / "cloned"
    home.mkdir()
    _write(home / "SOUL.md", LEGACY_SCAFFOLD_TEXT)

    _agent_obj, parts = _parts_for_home(home)

    assert LEGACY_SCAFFOLD_MARKER not in parts["stable"]
    assert "SOUL.md:legacy_template" in parts["stable"]
    assert DEGRADED_MARKER in parts["kissne_stable_core"]


def test_untouched_default_soul_is_reported_as_a_placeholder(tmp_path):
    home = tmp_path / "seeded"
    home.mkdir()
    _write(home / "SOUL.md", DEFAULT_SOUL_MD)

    _agent_obj, parts = _parts_for_home(home)

    assert "SOUL.md:placeholder" in parts["stable"]
    assert DEGRADED_MARKER in parts["stable"]


def test_placeholder_self_md_is_replaced_by_an_explicit_degraded_notice(tmp_path):
    home = tmp_path / "seeded-self"
    home.mkdir()
    _write(home / "SOUL.md", CUSTOM_SOUL)
    _write(home / "SELF.md", DEFAULT_SELF_MD)

    agent, parts = _parts_for_home(home)

    assert "SELF.md:placeholder" in parts["kissne_self"]
    assert DEGRADED_MARKER in parts["kissne_self"]
    # An untouched template must not be injected as recorded self-state.
    assert "No evolving self-description" not in parts["volatile"]
    # SOUL is healthy here, so it is not dragged into the degraded state.
    assert "SOUL.md:" not in parts["kissne_stable_core"]
    assert agent._identity_state.reasons == ("SELF.md:placeholder",)


def test_absent_self_md_is_explicitly_degraded(tmp_path):
    home = tmp_path / "no-self"
    home.mkdir()
    _write(home / "SOUL.md", CUSTOM_SOUL)

    _agent_obj, parts = _parts_for_home(home)

    assert "SELF.md:missing" in parts["kissne_self"]
    assert DEGRADED_MARKER in parts["kissne_self"]


def test_a_personal_identity_is_neither_degraded_nor_marked(tmp_path):
    home = tmp_path / "personal"
    home.mkdir()
    _write(home / "SOUL.md", CUSTOM_SOUL)
    _write(home / "SELF.md", CUSTOM_SELF)

    agent, parts = _parts_for_home(home)

    assert agent._identity_state.degraded is False
    assert agent._identity_state.reasons == ()
    assert DEGRADED_MARKER not in parts["stable"]
    assert DEGRADED_MARKER not in parts["volatile"]
    assert CUSTOM_SOUL in parts["kissne_stable_core"]
    assert "I have started to prefer short answers." in parts["kissne_self"]


def test_degraded_identity_is_announced_to_the_user_once_per_state(tmp_path):
    home = tmp_path / "fresh"
    home.mkdir()
    emitted = []
    agent = _agent(_emit_warning=emitted.append)

    with (
        patch("agent.system_prompt._agent_home", return_value=home),
        patch("agent.system_prompt._skills_prompt", return_value=""),
        patch("agent.system_prompt._frozen_plugin_prompt_sections", return_value={}),
        patch("agent.system_prompt._plugin_section_blocks", return_value=[]),
        patch("agent.system_prompt._timestamp_line", return_value=""),
        patch("agent.prompt_builder.build_environment_hints", return_value=""),
    ):
        build_system_prompt(agent)
        build_system_prompt(agent)  # a rebuild must not repeat itself

    assert len(emitted) == 1
    assert "SOUL.md:missing" in emitted[0]
    assert "no personalized identity" in emitted[0].lower()


def test_untouched_placeholder_soul_is_not_injected_as_project_context(tmp_path):
    """The other SOUL injection path (build_context_files_prompt) must not smuggle
    the untouched default in as project context either."""
    from agent.prompt_builder import build_context_files_prompt

    home = tmp_path / "seeded"
    home.mkdir()
    _write(home / "SOUL.md", DEFAULT_SOUL_MD)

    assert build_context_files_prompt(cwd=str(tmp_path), home_override=home) == ""


def test_a_personal_identity_emits_no_warning(tmp_path):
    home = tmp_path / "personal"
    home.mkdir()
    _write(home / "SOUL.md", CUSTOM_SOUL)
    _write(home / "SELF.md", CUSTOM_SELF)
    emitted = []
    agent = _agent(_emit_warning=emitted.append)

    with (
        patch("agent.system_prompt._agent_home", return_value=home),
        patch("agent.system_prompt._skills_prompt", return_value=""),
        patch("agent.system_prompt._frozen_plugin_prompt_sections", return_value={}),
        patch("agent.system_prompt._plugin_section_blocks", return_value=[]),
        patch("agent.system_prompt._timestamp_line", return_value=""),
        patch("agent.prompt_builder.build_environment_hints", return_value=""),
    ):
        build_system_prompt(agent)

    assert emitted == []