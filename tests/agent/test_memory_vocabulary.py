"""KB2-A hardening — the shared memory vocabulary, and the single-source rule.

Hardening ticket (follow-up to ``KB2-A-CLAIM-CONTRACT``): the vocabulary that
both contracts need — the four axes and the pointer/evidence types — lives in
exactly one module, ``agent/memory_vocabulary.py``.  Nothing else may define it
twice, and neither contract may import the other.

What this file pins:

* the four axes and their frozen values, in one place;
* the pointer vocabulary (``SourceRef`` / ``Evidence`` / ``Provenance``) and the
  consistency rules both contracts share, so a rule is written once;
* the legacy product-name translation (``user_memory`` → ``subject=user``);
* **no reverse dependency**: ``memory_claim`` must not import ``biography``,
  ``biography`` must not import ``memory_claim``, and importing one must not
  drag the other in;
* **no second definition**: each axis tuple is the *same object* everywhere it
  is exposed, and the axis literals appear only in the vocabulary module.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import agent.memory_vocabulary as vocabulary
from agent.memory_vocabulary import (
    EPISTEMIC_AGENT_EXPERIENCED,
    EPISTEMIC_HYPOTHETICAL,
    EPISTEMIC_OBSERVED,
    EPISTEMICS,
    EVIDENCE_AI_WORLD_EXPERIENCE,
    EVIDENCE_FIELDS,
    EVIDENCE_TOOL_RECEIPT,
    KIND_EVENT,
    KIND_FACT,
    KINDS,
    PROVENANCE_FIELDS,
    REALMS,
    SELF_EVIDENCE_KINDS,
    SOURCE_KINDS,
    SOURCE_REF_FIELDS,
    SOURCE_TOOL_RECEIPT,
    SUBJECTS,
    Evidence,
    HypotheticalNotAnEventError,
    InvalidEvidenceKindError,
    InvalidSourceRefError,
    InvalidSubjectError,
    MissingEvidenceError,
    MissingSourceRefError,
    Provenance,
    SourceRef,
    UnsupportedEvidenceKindError,
    check_consistency,
    is_hypothetical_event,
    requires_real_evidence,
    resolve_subject,
)

AGENT_DIR = Path(vocabulary.__file__).parent


# ── the four axes, defined once ─────────────────────────────────────────────

def test_subject_axis():
    assert SUBJECTS == ("user", "yeqingxu", "shared", "project")


def test_kind_axis():
    assert KINDS == ("fact", "event", "state", "preference", "intention", "impression", "episode")


def test_realm_axis():
    assert REALMS == ("EARTH", "AI_WORLD", "CONVERSATION", "SYSTEM")


def test_epistemic_axis():
    assert EPISTEMICS == ("OBSERVED", "USER_DECLARED", "AGENT_EXPERIENCED", "INFERRED", "HYPOTHETICAL")


def test_pointer_vocabulary():
    assert SOURCE_KINDS == ("conversation_turn", "tool_receipt", "earth_observation", "event")
    assert SELF_EVIDENCE_KINDS == ("execution", "tool_receipt", "world_event")
    assert SOURCE_REF_FIELDS == ("kind", "ref", "locator")
    assert EVIDENCE_FIELDS == ("kind", "sourceRef", "detail")
    assert PROVENANCE_FIELDS == ("origin", "recorded_by", "recorded_at", "sourceRefs")


def test_legacy_product_names_translate_only_at_the_boundary():
    assert resolve_subject("user_memory") == "user"
    assert resolve_subject("self_memory") == "yeqingxu"
    assert resolve_subject("shared_memory") == "shared"
    assert resolve_subject("project_memory") == "project"
    for canonical in SUBJECTS:
        assert resolve_subject(canonical) == canonical
    with pytest.raises(InvalidSubjectError):
        resolve_subject("memory_memory")


# ── shared consistency rules, written once ──────────────────────────────────

def test_hypothetical_is_not_an_event():
    assert is_hypothetical_event(KIND_EVENT, EPISTEMIC_HYPOTHETICAL) is True
    assert is_hypothetical_event(KIND_FACT, EPISTEMIC_HYPOTHETICAL) is False
    assert is_hypothetical_event(KIND_EVENT, EPISTEMIC_OBSERVED) is False


def test_first_person_experience_requires_real_evidence():
    assert requires_real_evidence("yeqingxu", EPISTEMIC_AGENT_EXPERIENCED) is True
    assert requires_real_evidence("user", EPISTEMIC_AGENT_EXPERIENCED) is False
    assert requires_real_evidence("yeqingxu", EPISTEMIC_OBSERVED) is False


def test_consistency_check_is_the_single_implementation():
    """两个合同都调用同一个校验函数，而不是各写一份规则。"""
    with pytest.raises(HypotheticalNotAnEventError):
        check_consistency(
            subject="user",
            kind=KIND_EVENT,
            epistemic=EPISTEMIC_HYPOTHETICAL,
            evidence=(),
        )
    with pytest.raises(MissingEvidenceError):
        check_consistency(
            subject="yeqingxu",
            kind=KIND_FACT,
            epistemic=EPISTEMIC_AGENT_EXPERIENCED,
            evidence=(),
        )
    # 合法组合不抛
    check_consistency(
        subject="yeqingxu",
        kind=KIND_FACT,
        epistemic=EPISTEMIC_AGENT_EXPERIENCED,
        evidence=(Evidence(kind=EVIDENCE_TOOL_RECEIPT, sourceRef=SourceRef(kind="tool_receipt", ref="r-1")),),
    )


# ── pointer / evidence validation moved here ────────────────────────────────

def test_sourceref_validation():
    ref = SourceRef(kind=SOURCE_TOOL_RECEIPT, ref="r-1")
    assert (ref.kind, ref.ref, ref.locator) == ("tool_receipt", "r-1", "")
    with pytest.raises(InvalidSourceRefError):
        SourceRef(kind="vibes", ref="r-1")
    with pytest.raises(InvalidSourceRefError):
        SourceRef(kind=SOURCE_TOOL_RECEIPT, ref="  ")


def test_provenance_requires_source_refs():
    with pytest.raises(MissingSourceRefError):
        Provenance(origin="conversation", recorded_by="agent", recorded_at="2026-09-16T07:00:00+08:00", sourceRefs=())


def test_ai_world_experience_is_refused_by_name():
    with pytest.raises(UnsupportedEvidenceKindError):
        Evidence(kind=EVIDENCE_AI_WORLD_EXPERIENCE, sourceRef=SourceRef(kind=SOURCE_TOOL_RECEIPT, ref="r-1"))


def test_evidence_requires_a_canonical_pointer():
    with pytest.raises(InvalidEvidenceKindError):
        Evidence(kind=EVIDENCE_TOOL_RECEIPT, sourceRef="receipt-1")  # type: ignore[arg-type]


# ── hardening: no reverse dependency, no duplicate definition ───────────────

def test_no_contract_imports_the_other():
    claim_src = (AGENT_DIR / "memory_claim.py").read_text(encoding="utf-8")
    bio_src = (AGENT_DIR / "biography.py").read_text(encoding="utf-8")
    assert "biography" not in claim_src, "memory_claim must not import biography"
    assert "memory_claim" not in bio_src, "biography must not import memory_claim"
    for src in (claim_src, bio_src):
        assert "agent.memory_vocabulary" in src, "both contracts must take the vocabulary from one module"


def test_importing_one_contract_does_not_drag_in_the_other():
    for module, other in (
        ("agent.biography", "agent.memory_claim"),
        ("agent.memory_claim", "agent.biography"),
    ):
        code = (
            "import sys, importlib\n"
            f"importlib.import_module({module!r})\n"
            f"print({other!r} in sys.modules)\n"
        )
        import subprocess

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(AGENT_DIR.parent),
        )
        assert result.stdout.strip() == "False", result.stderr[-500:]


def test_axis_tuples_are_the_same_object_everywhere_they_appear():
    import agent.biography as biography
    import agent.memory_claim as memory_claim

    assert memory_claim.SUBJECTS is vocabulary.SUBJECTS
    assert memory_claim.KINDS is vocabulary.KINDS
    assert memory_claim.REALMS is vocabulary.REALMS
    assert memory_claim.EPISTEMICS is vocabulary.EPISTEMICS
    assert biography.KINDS is vocabulary.KINDS
    assert biography.REALMS is vocabulary.REALMS
    assert biography.EPISTEMICS is vocabulary.EPISTEMICS
    assert biography.SOURCE_KINDS is vocabulary.SOURCE_KINDS
    assert memory_claim.SOURCE_KINDS is vocabulary.SOURCE_KINDS
    assert biography.SourceRef is vocabulary.SourceRef
    assert memory_claim.SourceRef is vocabulary.SourceRef
    assert biography.Evidence is vocabulary.Evidence
    assert memory_claim.Evidence is vocabulary.Evidence


def test_axis_value_spellings_live_only_in_the_vocabulary():
    """四个轴的取值拼写只允许出现在词表里：别的模块想用就 import，不许再抄一遍。"""
    contracts = ("memory_vocabulary.py", "memory_claim.py", "biography.py")
    literals = set(SUBJECTS) | set(KINDS) | set(REALMS) | set(EPISTEMICS)
    offenders = set()
    for name in contracts:
        if name == "memory_vocabulary.py":
            continue
        text = (AGENT_DIR / name).read_text(encoding="utf-8")
        copied = sorted(value for value in literals if f'"{value}"' in text)
        if copied:
            offenders.add((name, tuple(copied)))
    assert not offenders, f"这些合同模块自己抄了轴取值: {sorted(offenders)}"
