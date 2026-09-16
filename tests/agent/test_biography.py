"""KB2-BIOGRAPHY-CONTRACT — provider-neutral Biography contract, pinned by tests.

Ticket: ``KB2-BIOGRAPHY-CONTRACT``.  This file is the RED half: it asserts the
contract that ``agent/biography.py`` must provide, so it fails until that module
exists and behaves.

What the contract has to guarantee (numbers = ticket requirements):

* three categories, exactly: ``user_memory`` / ``shared_memory`` /
  ``self_memory`` (2);
* every entry is traceable — stable ``provenance`` with non-empty
  ``sourceRefs``, never a summary that cannot be walked back to its evidence
  (1);
* the schema carries *pointers* to canonical records, never a copy of them:
  Conversation / Earth observation / tool receipt / event stay the single
  long-term source of truth (3, 6);
* ``self_memory`` only expresses first-person experience that is actually
  backed by execution / tool / world-event evidence — no fabricated past (4);
* AI World Agent Experience is KB4, so it is refused here by name (5);
* the schema stays a contract: no provider, no embedding, no recall, no
  automatic writing, no production data, no persistence API (7);
* the still-undecided policy layer (sensitive-memory handling, Shared Event
  granularity) is *not* hardcoded — ``policy`` is opaque and round-trips
  untouched (8);
* serialize → deserialize is stable: fields, types and ``sourceRefs`` survive
  (9);
* invalid subject, missing provenance / ``sourceRefs`` and unsourced
  ``self_memory`` all fail loudly (10).

The field sets below are asserted as frozen on purpose: adding a ``raw_text``
style field later is exactly how a second long-term history gets built, so a
schema change has to show up as a failing test rather than a silent widening.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import agent.biography as biography
from agent.biography import (
    KIND_PREFERENCE,
    SUBJECTS,
    SUBJECT_YEQINGXU,
    SUBJECT_SHARED,
    SUBJECT_USER,
    ENTRY_FIELDS,
    EVIDENCE_AI_WORLD_EXPERIENCE,
    EVIDENCE_EXECUTION,
    EVIDENCE_TOOL_RECEIPT,
    EVIDENCE_WORLD_EVENT,
    PROVENANCE_FIELDS,
    SCHEMA_ID,
    SOURCE_CONVERSATION_TURN,
    SOURCE_EARTH_OBSERVATION,
    SOURCE_REF_FIELDS,
    SOURCE_TOOL_RECEIPT,
    BiographyEntry,
    Evidence,
    InvalidSubjectError,
    InvalidEvidenceKindError,
    InvalidSourceRefError,
    MissingEvidenceError,
    MissingSourceRefError,
    Provenance,
    SourceRef,
    UnsupportedEvidenceKindError,
    deserialize_entry,
    serialize_entry,
)


# ── helpers ─────────────────────────────────────────────────────────────────

def _ref(kind: str = SOURCE_CONVERSATION_TURN, ref: str = "turn-0001") -> SourceRef:
    return SourceRef(kind=kind, ref=ref)


def _provenance(*refs: SourceRef, origin: str = "runtime", recorded_by: str = "agent",
                recorded_at: str = "2026-09-15T23:50:00+08:00") -> Provenance:
    return Provenance(
        origin=origin,
        recorded_by=recorded_by,
        recorded_at=recorded_at,
        sourceRefs=tuple(refs) or (_ref(),),
    )


def _evidence(kind: str = EVIDENCE_TOOL_RECEIPT) -> Evidence:
    return Evidence(kind=kind, sourceRef=_ref(SOURCE_TOOL_RECEIPT, "receipt-7"), detail="")


def _entry(subject: str = SUBJECT_USER, kind: str = KIND_PREFERENCE, **overrides):
    kwargs = dict(
        entry_id="bio-0001",
        subject=subject,
        kind=kind,
        statement="Holds a green sheep as her own image; the fox is mine.",
        provenance=_provenance(),
        evidence=(),
        policy={},
    )
    kwargs.update(overrides)
    return BiographyEntry(**kwargs)


# ── 2. the three categories exist and are distinct ──────────────────────────

def test_schema_id_is_declared():
    assert SCHEMA_ID == "kissne.biography/1"


def test_exactly_three_categories_are_biography_categories():
    assert SUBJECTS == (SUBJECT_USER, SUBJECT_SHARED, SUBJECT_YEQINGXU)
    assert SUBJECTS == ("user", "yeqingxu", "shared")


@pytest.mark.parametrize("subject", [SUBJECT_USER, SUBJECT_SHARED, SUBJECT_YEQINGXU])
def test_each_subject_builds_and_round_trips(subject):
    entry = _entry(subject=subject, evidence=(_evidence(),) if subject == SUBJECT_YEQINGXU else ())
    assert deserialize_entry(serialize_entry(entry)) == entry


def test_subject_is_validated_by_value_not_by_trust():
    for bad in ("biography", "memory", "", None, 123, ["user_memory"]):
        with pytest.raises(InvalidSubjectError):
            _entry(subject=bad)


# ── 3 / 6. pointers, never a copied canonical record ────────────────────────

def test_entry_field_set_is_frozen_against_a_canonical_text_field():
    assert ENTRY_FIELDS == (
        "entry_id",
        "subject",
        "kind",
        "statement",
        "provenance",
        "evidence",
        "policy",
    )
    assert "category" not in ENTRY_FIELDS
    for forbidden in ("raw", "text", "transcript", "canonical", "conversation", "messages"):
        assert forbidden not in ENTRY_FIELDS


def test_entry_rejects_unknown_fields_instead_of_widening_the_schema():
    with pytest.raises(TypeError):
        _entry(raw_text="the whole conversation verbatim")


def test_source_ref_is_a_pointer_with_a_canonical_kind():
    assert SOURCE_REF_FIELDS == ("kind", "ref", "locator")
    ref = SourceRef(kind=SOURCE_CONVERSATION_TURN, ref="turn-0001", locator="session:abc#12")
    assert ref.kind == SOURCE_CONVERSATION_TURN and ref.ref == "turn-0001"


def test_source_ref_kind_must_be_one_of_the_canonical_kinds():
    assert SourceRef(kind=SOURCE_EARTH_OBSERVATION, ref="obs-3").kind == SOURCE_EARTH_OBSERVATION
    with pytest.raises(InvalidSourceRefError):
        SourceRef(kind="vibes", ref="x")


def test_source_ref_ref_must_be_non_empty():
    for bad in ("", "   ", None):
        with pytest.raises(InvalidSourceRefError):
            SourceRef(kind=SOURCE_CONVERSATION_TURN, ref=bad)


# ── 1. provenance is mandatory and stable ───────────────────────────────────

def test_provenance_field_set_is_frozen():
    assert PROVENANCE_FIELDS == ("origin", "recorded_by", "recorded_at", "sourceRefs")


def test_provenance_without_source_refs_is_rejected():
    with pytest.raises(MissingSourceRefError):
        Provenance(origin="runtime", recorded_by="agent",
                   recorded_at="2026-09-15T23:50:00+08:00", sourceRefs=())


def test_provenance_requires_an_iso_timestamp():
    with pytest.raises(biography.InvalidProvenanceError):
        _provenance(recorded_at="yesterday-ish")


def test_provenance_requires_origin_and_recorder():
    with pytest.raises(biography.InvalidProvenanceError):
        Provenance(origin="", recorded_by="agent",
                   recorded_at="2026-09-15T23:50:00+08:00", sourceRefs=(_ref(),))


def test_entry_statement_must_be_present():
    with pytest.raises(biography.InvalidBiographyEntryError):
        _entry(statement="   ")


def test_entry_id_must_be_stable_and_non_empty():
    with pytest.raises(biography.InvalidBiographyEntryError):
        _entry(entry_id="")


# ── 4 / 5. self_memory needs real evidence; KB4 stays out ───────────────────

def test_self_memory_without_evidence_is_rejected():
    with pytest.raises(MissingEvidenceError):
        _entry(subject=SUBJECT_YEQINGXU, evidence=())


@pytest.mark.parametrize("kind", [EVIDENCE_EXECUTION, EVIDENCE_TOOL_RECEIPT, EVIDENCE_WORLD_EVENT])
def test_self_memory_accepts_evidence_backed_experience(kind):
    entry = _entry(subject=SUBJECT_YEQINGXU, evidence=(_evidence(kind),))
    assert entry.subject == SUBJECT_YEQINGXU
    assert deserialize_entry(serialize_entry(entry)) == entry


def test_ai_world_experience_is_refused_by_name_because_it_is_kb4():
    with pytest.raises(UnsupportedEvidenceKindError):
        _evidence(EVIDENCE_AI_WORLD_EXPERIENCE)


def test_unknown_evidence_kind_is_rejected():
    with pytest.raises(InvalidEvidenceKindError):
        _evidence("felt_like_it")


def test_evidence_itself_must_point_at_a_canonical_record():
    with pytest.raises(InvalidEvidenceKindError):
        Evidence(kind=EVIDENCE_TOOL_RECEIPT, sourceRef="a note I wrote", detail="")
    with pytest.raises(InvalidEvidenceKindError):
        Evidence(kind=EVIDENCE_TOOL_RECEIPT, sourceRef=None, detail="")


def test_user_and_shared_entries_do_not_require_self_evidence():
    assert _entry(subject=SUBJECT_USER, evidence=()).subject == SUBJECT_USER
    assert _entry(subject=SUBJECT_SHARED, evidence=()).subject == SUBJECT_SHARED


# ── 8. undecided policy stays undecided ─────────────────────────────────────

def test_policy_layer_is_opaque_and_preserved_exactly():
    policy = {"granularity": "topic", "sensitivity": "private", "future_flag": {"a": [1, 2]}}
    entry = _entry(subject=SUBJECT_SHARED, policy=policy)
    restored = deserialize_entry(serialize_entry(entry))
    assert restored.policy == policy


def test_schema_does_not_hardcode_the_undecided_policy_decisions():
    for undecided in ("granularity", "sensitivity", "retention", "shared_event_granularity"):
        assert undecided not in ENTRY_FIELDS
        assert undecided not in PROVENANCE_FIELDS
        assert undecided not in SOURCE_REF_FIELDS


# ── 9. round-trip stability ─────────────────────────────────────────────────

def test_round_trip_preserves_types_and_source_ref_order():
    entry = _entry(
        subject=SUBJECT_YEQINGXU,
        evidence=(_evidence(EVIDENCE_EXECUTION), _evidence(EVIDENCE_WORLD_EVENT)),
        provenance=_provenance(
            _ref(SOURCE_CONVERSATION_TURN, "turn-0001"),
            _ref(SOURCE_TOOL_RECEIPT, "receipt-7"),
            _ref(SOURCE_EARTH_OBSERVATION, "obs-3"),
        ),
    )
    payload = serialize_entry(entry)
    assert isinstance(payload["provenance"]["sourceRefs"], list)
    assert payload["provenance"]["sourceRefs"][0]["ref"] == "turn-0001"

    restored = deserialize_entry(payload)
    assert isinstance(restored.provenance.sourceRefs, tuple)
    assert [r.ref for r in restored.provenance.sourceRefs] == [
        "turn-0001", "receipt-7", "obs-3",
    ]
    assert isinstance(restored.provenance.sourceRefs[0], SourceRef)
    assert restored == entry


def test_serialized_form_is_json_stable():
    entry = _entry(subject=SUBJECT_YEQINGXU, evidence=(_evidence(),))
    once = json.dumps(serialize_entry(entry), sort_keys=True)
    twice = json.dumps(serialize_entry(deserialize_entry(serialize_entry(entry))), sort_keys=True)
    assert once == twice


def test_deserialize_rejects_a_payload_that_lost_its_provenance():
    payload = serialize_entry(_entry())
    del payload["provenance"]
    with pytest.raises(biography.InvalidBiographyEntryError):
        deserialize_entry(payload)


def test_deserialize_rejects_non_mapping_payloads():
    for bad in (None, [], "entry", 7):
        with pytest.raises(biography.InvalidBiographyEntryError):
            deserialize_entry(bad)


# ── 7. contract only: no provider, no recall, no persistence ────────────────

def test_module_exposes_no_persistence_api():
    writers = ("write", "save", "append", "store", "persist", "recall", "embed", "search")
    leaked = [
        name for name in dir(biography)
        if not name.startswith("__") and name.lower().startswith(writers)
    ]
    assert leaked == []


def test_module_does_not_drag_in_a_provider_or_a_second_history():
    source = Path(biography.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "memory_manager",
        "memory_provider",
        "MemoryProvider",
        "unified_history",
        "UnifiedHistory",
        "sqlite3",
        "json.dump",
        "agent.kimi",
        "Kimi",
    ):
        assert forbidden not in source, f"{forbidden} must not appear in the contract module"


# ── 迁移（KB2-A）：category 不再是 canonical 字段 ──────────────────────────

def test_legacy_category_is_no_longer_a_canonical_field():
    payload = json.loads(json.dumps(biography.serialize_entry(_entry())))
    payload["category"] = "user_memory"
    with pytest.raises(biography.BiographyError):
        biography.deserialize_entry(payload)


def test_serialized_entry_uses_subject_and_carries_kind():
    payload = biography.serialize_entry(_entry(subject=SUBJECT_SHARED, kind=KIND_PREFERENCE))
    assert payload["subject"] == "shared"
    assert payload["kind"] == "preference"
    assert "category" not in payload


def test_biography_subject_axis_matches_the_claim_axis():
    """三条 Biography subject 是记忆 subject 轴的子集，且 kind 轴与 Claim 完全一致。"""
    import agent.memory_claim as memory_claim

    assert SUBJECTS == ("user", "yeqingxu", "shared")
    assert set(SUBJECTS) < set(memory_claim.SUBJECTS)
    assert biography.BIOGRAPHY_KINDS == memory_claim.KINDS


def test_biography_rejects_a_kind_outside_the_frozen_axis():
    with pytest.raises(biography.InvalidKindError):
        _entry(kind="episode_memory")
