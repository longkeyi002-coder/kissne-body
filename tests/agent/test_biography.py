"""KB2-BIOGRAPHY-CONTRACT — provider-neutral Biography contract, pinned by tests.

Ticket: ``KB2-BIOGRAPHY-CONTRACT``.  This file is the RED half: it asserts the
contract that ``agent/biography.py`` must provide, so it fails until that module
exists and behaves.

What the contract has to guarantee (numbers = ticket requirements):

* three subjects, exactly: ``user`` / ``yeqingxu`` / ``shared`` (2), each with
  a ``kind`` on the second axis — the old ``user_memory`` style names are
  product-language aliases only (KB2-A migration);
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
import agent.memory_vocabulary as vocabulary
from agent.biography import (
    BIOGRAPHY_SUBJECTS,
    ENTRY_FIELDS,
    SCHEMA_ID,
    BiographyEntry,
)
from agent.memory_vocabulary import (
    EPISTEMIC_AGENT_EXPERIENCED,
    EPISTEMIC_HYPOTHETICAL,
    EPISTEMIC_OBSERVED,
    EPISTEMIC_USER_DECLARED,
    EPISTEMICS,
    EVIDENCE_AI_WORLD_EXPERIENCE,
    EVIDENCE_EXECUTION,
    EVIDENCE_TOOL_RECEIPT,
    EVIDENCE_WORLD_EVENT,
    KIND_EVENT,
    KIND_PREFERENCE,
    PROVENANCE_FIELDS,
    REALM_AI_WORLD,
    REALM_EARTH,
    REALMS,
    SOURCE_CONVERSATION_TURN,
    SOURCE_EARTH_OBSERVATION,
    SOURCE_REF_FIELDS,
    SOURCE_TOOL_RECEIPT,
    SUBJECT_YEQINGXU,
    SUBJECT_SHARED,
    SUBJECT_USER,
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


def _entry(
    subject: str = SUBJECT_USER,
    kind: str = KIND_PREFERENCE,
    realm: str = REALM_EARTH,
    epistemic: str = EPISTEMIC_USER_DECLARED,
    **overrides,
):
    kwargs = dict(
        entry_id="bio-0001",
        subject=subject,
        kind=kind,
        realm=realm,
        epistemic=epistemic,
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


def test_exactly_three_subjects_are_biography_subjects():
    assert BIOGRAPHY_SUBJECTS == (SUBJECT_USER, SUBJECT_YEQINGXU, SUBJECT_SHARED)
    assert BIOGRAPHY_SUBJECTS == ("user", "yeqingxu", "shared")
    assert set(BIOGRAPHY_SUBJECTS) < set(vocabulary.SUBJECTS), "Biography 用四轴里的三条，不许自己另立一套"
    assert biography.KINDS is vocabulary.KINDS
    assert biography.REALMS is vocabulary.REALMS
    assert biography.EPISTEMICS is vocabulary.EPISTEMICS


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
        "realm",
        "epistemic",
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


def test_biography_takes_its_axes_from_the_one_vocabulary():
    """hardening：Biography 不再自带一份 kind 取值，四条轴都取自 memory_vocabulary。"""
    assert BIOGRAPHY_SUBJECTS == ("user", "yeqingxu", "shared")
    assert set(BIOGRAPHY_SUBJECTS) < set(vocabulary.SUBJECTS)
    assert biography.KINDS is vocabulary.KINDS
    assert not hasattr(biography, "BIOGRAPHY_KINDS")


def test_biography_rejects_a_kind_outside_the_frozen_axis():
    with pytest.raises(vocabulary.InvalidKindError):
        _entry(kind="episode_memory")


# ── hardening：Biography 补 realm + epistemic ──────────────────────────────

def test_biography_entry_carries_realm_and_epistemic():
    entry = _entry(realm=REALM_EARTH, epistemic=EPISTEMIC_OBSERVED)
    assert (entry.realm, entry.epistemic) == (REALM_EARTH, EPISTEMIC_OBSERVED)
    payload = biography.serialize_entry(entry)
    assert payload["realm"] == REALM_EARTH and payload["epistemic"] == EPISTEMIC_OBSERVED
    again = biography.deserialize_entry(payload)
    assert (again.realm, again.epistemic) == (entry.realm, entry.epistemic)


def test_biography_realm_is_required_and_never_guessed():
    kwargs = dict(
        entry_id="bio-0001",
        subject=SUBJECT_USER,
        kind=KIND_PREFERENCE,
        statement="no realm",
        provenance=_provenance(),
        evidence=(),
        policy={},
    )
    with pytest.raises(vocabulary.InvalidRealmError):
        BiographyEntry(**kwargs, epistemic=EPISTEMIC_USER_DECLARED)
    with pytest.raises(vocabulary.InvalidEpistemicError):
        BiographyEntry(**kwargs, realm=REALM_EARTH)


@pytest.mark.parametrize("bad", ["earth", "", "AI_World", None])
def test_biography_invalid_realm_is_rejected(bad):
    with pytest.raises(vocabulary.InvalidRealmError):
        _entry(realm=bad)


@pytest.mark.parametrize("bad", ["observed", "", "GUESSED", None])
def test_biography_invalid_epistemic_is_rejected(bad):
    with pytest.raises(vocabulary.InvalidEpistemicError):
        _entry(epistemic=bad)


def test_biography_hypothetical_is_not_an_event():
    with pytest.raises(HypotheticalNotAnEventError):
        _entry(kind=KIND_EVENT, epistemic=EPISTEMIC_HYPOTHETICAL)


def test_biography_first_person_entries_still_need_evidence():
    with pytest.raises(MissingEvidenceError):
        _entry(
            subject=SUBJECT_YEQINGXU,
            realm=REALM_AI_WORLD,
            epistemic=EPISTEMIC_AGENT_EXPERIENCED,
            evidence=(),
        )
