"""KB2-A-CLAIM-CONTRACT — the minimum Memory Claim contract, pinned by tests.

Ticket: ``KB2-A-CLAIM-CONTRACT``.  This file is the RED half: it asserts the
contract that ``agent/memory_claim.py`` must provide, so it fails until that
module exists and behaves.

The ticket freezes exactly six semantic groups — nothing more:

1. ``subject``   — whose fact / experience / state this is
2. ``kind``      — what type of memory it is (a second, independent axis)
3. ``realm``     — which world it belongs to (Earth / AI World / conversation / system)
4. ``epistemic`` — how it is known (observed / declared / experienced / inferred / hypothetical)
5. time triple   — ``occurred_at`` / ``recorded_at`` / ``timezone``
6. valid time    — ``valid_from`` / ``valid_to``

…plus the migration of the already-merged Biography ``category`` field to
``subject``.

Deliberately **not** here: ``status`` / ``supersedes`` / ``contradicts`` (KB2-B),
the Mutation Gate and ADD/UPDATE/SUPERSEDE decisions (KB2-C), Recall, Reentry,
``KissneMemoryProvider``, SQLite / FTS / vector, retention, Affect, Impression /
Episode aggregation, Biography features, AI World event generation, KB4.

Field sets are asserted as frozen tuples on purpose: widening the schema has to
show up as a failing test, never as a silent drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import agent.memory_claim as memory_claim
from agent.biography import (
    EVIDENCE_TOOL_RECEIPT,
    EVIDENCE_WORLD_EVENT,
    SOURCE_CONVERSATION_TURN,
    SOURCE_TOOL_RECEIPT,
    Evidence,
    SourceRef,
)
from agent.memory_claim import (
    CLAIM_FIELDS,
    EPISTEMIC_AGENT_EXPERIENCED,
    EPISTEMIC_HYPOTHETICAL,
    EPISTEMIC_INFERRED,
    EPISTEMIC_OBSERVED,
    EPISTEMIC_USER_DECLARED,
    EPISTEMICS,
    KIND_EVENT,
    KIND_FACT,
    KIND_IMPRESSION,
    KIND_INTENTION,
    KIND_PREFERENCE,
    KINDS,
    REALM_AI_WORLD,
    REALM_CONVERSATION,
    REALM_EARTH,
    REALM_SYSTEM,
    REALMS,
    SCHEMA_ID,
    SUBJECT_PROJECT,
    SUBJECT_SHARED,
    SUBJECT_USER,
    SUBJECT_YEQINGXU,
    SUBJECTS,
    Claim,
    ClaimError,
    InvalidEpistemicError,
    InvalidKindError,
    InvalidRealmError,
    InvalidSubjectError,
    InvalidValidityWindowError,
    MissingClaimSourceRefError,
    MissingEvidenceError,
    SubjectConflictError,
    claim_from_legacy_payload,
    deserialize_claim,
    resolve_subject,
    serialize_claim,
)


# ── helpers ─────────────────────────────────────────────────────────────────

def _sourceref(kind: str = SOURCE_CONVERSATION_TURN, ref: str = "turn-1") -> SourceRef:
    return SourceRef(kind=kind, ref=ref)


def _evidence(kind: str = EVIDENCE_TOOL_RECEIPT) -> Evidence:
    return Evidence(kind=kind, sourceRef=_sourceref(SOURCE_TOOL_RECEIPT, "receipt-1"), detail="ran it")


def _claim(**overrides) -> Claim:
    payload = dict(
        claim_id="claim-1",
        subject=SUBJECT_USER,
        kind=KIND_PREFERENCE,
        realm=REALM_EARTH,
        epistemic=EPISTEMIC_USER_DECLARED,
        statement="她喜欢下雨天",
        occurred_at="2026-09-11T21:00:00+08:00",
        recorded_at="2026-09-16T07:40:00+08:00",
        timezone="Asia/Shanghai",
        source_refs=(_sourceref(),),
    )
    payload.update(overrides)
    return Claim(**payload)


# ── 1. subject (the axis拍板 on 2026-09-16) ─────────────────────────────────

def test_subject_axis_is_exactly_the_four_frozen_values():
    assert SUBJECTS == (SUBJECT_USER, SUBJECT_YEQINGXU, SUBJECT_SHARED, SUBJECT_PROJECT)
    assert SUBJECTS == ("user", "yeqingxu", "shared", "project")


@pytest.mark.parametrize("subject", SUBJECTS)
def test_every_subject_builds(subject):
    assert _claim(subject=subject, kind=KIND_FACT).subject == subject


def test_missing_subject_is_rejected():
    assert "subject" in CLAIM_FIELDS
    with pytest.raises(InvalidSubjectError):
        Claim(
            claim_id="claim-1",
            kind=KIND_FACT,
            realm=REALM_EARTH,
            epistemic=EPISTEMIC_OBSERVED,
            statement="缺 subject",
            occurred_at="2026-09-11T21:00:00+08:00",
            recorded_at="2026-09-16T07:40:00+08:00",
            timezone="Asia/Shanghai",
            source_refs=(_sourceref(),),
        )


@pytest.mark.parametrize("bad", ["", "   ", "USER", "user_memory", "self_memory", "selff", None, 7])
def test_invalid_subject_is_rejected_by_value(bad):
    with pytest.raises(InvalidSubjectError):
        _claim(subject=bad)


def test_legacy_product_name_is_not_a_canonical_subject():
    """user_memory / shared_memory / self_memory 只是产品叫法，不是 canonical 取值。"""
    for legacy in ("user_memory", "shared_memory", "self_memory", "project_memory"):
        assert legacy not in SUBJECTS
        with pytest.raises(InvalidSubjectError):
            _claim(subject=legacy)


def test_legacy_names_resolve_to_the_subject_axis_at_the_boundary():
    assert resolve_subject("user_memory") == SUBJECT_USER
    assert resolve_subject("shared_memory") == SUBJECT_SHARED
    assert resolve_subject("self_memory") == SUBJECT_YEQINGXU
    assert resolve_subject("project_memory") == SUBJECT_PROJECT
    # canonical values pass through unchanged
    for subject in SUBJECTS:
        assert resolve_subject(subject) == subject
    with pytest.raises(InvalidSubjectError):
        resolve_subject("memory_memory")


# ── 2. kind (second, independent axis) ──────────────────────────────────────

def test_kind_axis_is_frozen():
    assert KINDS == (
        "fact",
        "event",
        "state",
        "preference",
        "intention",
        "impression",
        "episode",
    )


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_builds(kind):
    assert _claim(kind=kind).kind == kind


def test_subject_and_kind_are_independent_axes_not_one_category():
    """subject=user+kind=preference 与 subject=shared+kind=episode 都是合法组合。"""
    a = _claim(subject=SUBJECT_USER, kind=KIND_PREFERENCE)
    b = _claim(claim_id="claim-2", subject=SUBJECT_SHARED, kind="episode")
    assert (a.subject, a.kind) == (SUBJECT_USER, KIND_PREFERENCE)
    assert (b.subject, b.kind) == (SUBJECT_SHARED, "episode")
    # 单轴 category 式命名不是 kind 的取值
    for bogus in ("user_memory", "episode_memory", "project_memory", "biography"):
        assert bogus not in KINDS
        with pytest.raises(InvalidKindError):
            _claim(kind=bogus)


@pytest.mark.parametrize("bad", ["", "FACT", "Event", None, 3, "memory"])
def test_invalid_kind_is_rejected(bad):
    with pytest.raises(InvalidKindError):
        _claim(kind=bad)


# ── 3. realm ────────────────────────────────────────────────────────────────

def test_realm_axis_is_frozen():
    assert REALMS == (REALM_EARTH, REALM_AI_WORLD, REALM_CONVERSATION, REALM_SYSTEM)
    assert REALMS == ("EARTH", "AI_WORLD", "CONVERSATION", "SYSTEM")


@pytest.mark.parametrize("realm", REALMS)
def test_every_realm_builds_and_is_preserved(realm):
    assert _claim(realm=realm).realm == realm


def test_realm_is_required_and_never_defaulted():
    """没有默认 realm，就不会出现『Earth 事实被 AI World 事件替代』这种静默混用。"""
    with pytest.raises(InvalidRealmError):
        Claim(
            claim_id="claim-1",
            subject=SUBJECT_USER,
            kind=KIND_FACT,
            epistemic=EPISTEMIC_OBSERVED,
            statement="缺 realm",
            occurred_at="2026-09-11T21:00:00+08:00",
            recorded_at="2026-09-16T07:40:00+08:00",
            timezone="Asia/Shanghai",
            source_refs=(_sourceref(),),
        )


@pytest.mark.parametrize("bad", ["", "earth", "Ai_World", "WORLD", None, 1])
def test_invalid_realm_is_rejected(bad):
    with pytest.raises(InvalidRealmError):
        _claim(realm=bad)


def test_earth_claim_does_not_silently_become_ai_world():
    claim = _claim(realm=REALM_EARTH)
    assert claim.realm == REALM_EARTH
    assert deserialize_claim(serialize_claim(claim)).realm == REALM_EARTH


# ── 4. epistemic ────────────────────────────────────────────────────────────

def test_epistemic_axis_is_frozen():
    assert EPISTEMICS == (
        EPISTEMIC_OBSERVED,
        EPISTEMIC_USER_DECLARED,
        EPISTEMIC_AGENT_EXPERIENCED,
        EPISTEMIC_INFERRED,
        EPISTEMIC_HYPOTHETICAL,
    )
    assert EPISTEMICS == ("OBSERVED", "USER_DECLARED", "AGENT_EXPERIENCED", "INFERRED", "HYPOTHETICAL")


@pytest.mark.parametrize("bad", ["", "observed", "GUESSED", "ASSUMED", None, 2])
def test_invalid_epistemic_is_rejected(bad):
    with pytest.raises(InvalidEpistemicError):
        _claim(epistemic=bad)


def test_inferred_never_upgrades_itself_on_round_trip():
    """重复出现的推断不得自动升级成事实 —— 合同里也没有任何升级 API。"""
    claim = _claim(epistemic=EPISTEMIC_INFERRED, kind=KIND_IMPRESSION)
    again = deserialize_claim(serialize_claim(claim))
    assert again.epistemic == EPISTEMIC_INFERRED
    assert again.epistemic != EPISTEMIC_OBSERVED
    assert not hasattr(memory_claim, "promote_epistemic")
    assert not hasattr(memory_claim, "upgrade_epistemic")
    source = Path(memory_claim.__file__).read_text(encoding="utf-8")
    assert "promote_epistemic" not in source
    assert "upgrade_epistemic" not in source


def test_observed_and_declared_stay_distinct():
    observed = _claim(epistemic=EPISTEMIC_OBSERVED)
    declared = _claim(claim_id="claim-2", epistemic=EPISTEMIC_USER_DECLARED)
    assert observed.epistemic != declared.epistemic
    assert deserialize_claim(serialize_claim(observed)).epistemic == EPISTEMIC_OBSERVED


def test_hypothetical_is_not_an_event_that_happened():
    with pytest.raises(ClaimError):
        _claim(epistemic=EPISTEMIC_HYPOTHETICAL, kind=KIND_EVENT)
    # 同一句假设换一种 kind 就只是假设本身，仍是合法的
    assert _claim(epistemic=EPISTEMIC_HYPOTHETICAL, kind=KIND_INTENTION).epistemic == EPISTEMIC_HYPOTHETICAL


def test_agent_experienced_needs_real_evidence():
    """无真实经历来源的 subject=yeqingxu + AGENT_EXPERIENCED 必须被拒绝。"""
    with pytest.raises((MissingEvidenceError, ClaimError)):
        _claim(subject=SUBJECT_YEQINGXU, epistemic=EPISTEMIC_AGENT_EXPERIENCED, evidence=())
    backed = _claim(
        subject=SUBJECT_YEQINGXU,
        epistemic=EPISTEMIC_AGENT_EXPERIENCED,
        evidence=(_evidence(EVIDENCE_TOOL_RECEIPT),),
    )
    assert backed.subject == SUBJECT_YEQINGXU
    assert backed.evidence


def test_ai_world_experience_is_still_refused_by_name():
    """AI World Agent Experience 属 KB4，KB2-A 不得提前实现。"""
    from agent.biography import EVIDENCE_AI_WORLD_EXPERIENCE, UnsupportedEvidenceKindError

    with pytest.raises(UnsupportedEvidenceKindError):
        Evidence(kind=EVIDENCE_AI_WORLD_EXPERIENCE, sourceRef=_sourceref())


# ── 5. time triple ──────────────────────────────────────────────────────────

def test_occurred_at_and_recorded_at_can_differ_and_are_not_conflated():
    """今天告诉我『上周五发生了 X』，不能把今天写成 occurred_at。"""
    claim = _claim(occurred_at="2026-09-11T20:30:00+08:00", recorded_at="2026-09-16T07:40:00+08:00")
    assert claim.occurred_at != claim.recorded_at
    again = deserialize_claim(serialize_claim(claim))
    assert again.occurred_at == "2026-09-11T20:30:00+08:00"
    assert again.recorded_at == "2026-09-16T07:40:00+08:00"


def test_both_timestamps_are_required():
    for field_name in ("occurred_at", "recorded_at"):
        payload = dict(
            claim_id="claim-1",
            subject=SUBJECT_USER,
            kind=KIND_FACT,
            realm=REALM_EARTH,
            epistemic=EPISTEMIC_OBSERVED,
            statement="缺时间",
            occurred_at="2026-09-11T20:30:00+08:00",
            recorded_at="2026-09-16T07:40:00+08:00",
            timezone="Asia/Shanghai",
            source_refs=(_sourceref(),),
        )
        payload.pop(field_name)
        with pytest.raises(memory_claim.InvalidTimeError):
            Claim(**payload)


def test_timezone_is_kept_not_normalised_away():
    claim = _claim(timezone="Asia/Shanghai")
    assert claim.timezone == "Asia/Shanghai"
    assert deserialize_claim(serialize_claim(claim)).timezone == "Asia/Shanghai"
    with pytest.raises(memory_claim.InvalidTimeError):
        _claim(timezone="  ")


def test_contract_only_validates_timestamps_no_natural_language_parser():
    """本票只定义、校验、保存时间合同；不做自然语言时间解析。"""
    source = Path(memory_claim.__file__).read_text(encoding="utf-8")
    for forbidden in ("dateutil", "parsedatetime", "fuzzy", "relative_delta", "last_week", "上周"):
        assert forbidden not in source


# ── 6. valid time ───────────────────────────────────────────────────────────

def test_validity_window_accepts_a_forward_interval():
    claim = _claim(valid_from="2026-01-01T00:00:00+08:00", valid_to="2026-06-01T00:00:00+08:00")
    assert (claim.valid_from, claim.valid_to) == ("2026-01-01T00:00:00+08:00", "2026-06-01T00:00:00+08:00")


def test_open_ended_and_absent_windows_are_allowed():
    assert _claim().valid_from is None and _claim().valid_to is None
    assert _claim(valid_from="2026-01-01T00:00:00+08:00").valid_to is None
    assert _claim(valid_to="2026-06-01T00:00:00+08:00").valid_from is None


def test_reversed_validity_window_is_rejected():
    with pytest.raises(InvalidValidityWindowError):
        _claim(valid_from="2026-06-01T00:00:00+08:00", valid_to="2026-01-01T00:00:00+08:00")


@pytest.mark.parametrize("field_name", ["valid_from", "valid_to"])
def test_malformed_validity_timestamp_is_rejected(field_name):
    with pytest.raises(InvalidValidityWindowError):
        _claim(**{field_name: "昨天"})


def test_validity_window_does_not_implement_status_changes():
    """SUPERSEDE / CONTRADICT 属 KB2-B：本票不提供 status 字段，也不改协议。"""
    assert "status" not in CLAIM_FIELDS
    assert "supersedes" not in CLAIM_FIELDS
    assert "contradicts" not in CLAIM_FIELDS
    assert not hasattr(memory_claim, "STATUSES")
    assert not hasattr(memory_claim, "supersede")


# ── traceability (V1 hard rule: sourceRefs → History) ───────────────────────

def test_source_refs_are_mandatory():
    for empty in ((), []):
        with pytest.raises(MissingClaimSourceRefError):
            _claim(source_refs=empty)
    assert _claim().source_refs


def test_source_refs_survive_round_trip_in_order():
    claim = _claim(
        source_refs=(
            _sourceref(SOURCE_CONVERSATION_TURN, "turn-7"),
            _sourceref(SOURCE_TOOL_RECEIPT, "receipt-9"),
        )
    )
    again = deserialize_claim(serialize_claim(claim))
    assert [r.ref for r in again.source_refs] == ["turn-7", "receipt-9"]


def test_claim_only_carries_pointers_never_copies_canon():
    payload = serialize_claim(_claim())
    assert "raw_text" not in json.dumps(payload)
    assert payload["source_refs"][0] == {
        "kind": SOURCE_CONVERSATION_TURN,
        "ref": "turn-1",
        "locator": "",
    }


# ── schema: frozen fields + canonical-only names ────────────────────────────

def test_claim_fields_are_frozen_and_category_is_not_among_them():
    assert CLAIM_FIELDS == (
        "claim_id",
        "subject",
        "kind",
        "realm",
        "epistemic",
        "statement",
        "occurred_at",
        "recorded_at",
        "timezone",
        "valid_from",
        "valid_to",
        "source_refs",
        "evidence",
        "policy",
    )
    assert "category" not in CLAIM_FIELDS


def test_serialized_claim_has_no_duplicate_category_field():
    payload = serialize_claim(_claim())
    assert payload["schema"] == SCHEMA_ID
    assert payload["subject"] == SUBJECT_USER
    assert "category" not in payload


def test_deserialize_rejects_legacy_category_as_canonical_field():
    payload = serialize_claim(_claim())
    payload["category"] = "user_memory"
    with pytest.raises(SubjectConflictError):
        deserialize_claim(payload)


def test_deserialize_rejects_a_payload_that_lost_its_subject():
    payload = serialize_claim(_claim())
    del payload["subject"]
    with pytest.raises(InvalidSubjectError):
        deserialize_claim(payload)


def test_deserialize_rejects_unknown_fields_and_foreign_schemas():
    payload = serialize_claim(_claim())
    payload["status"] = "CURRENT"
    with pytest.raises(ClaimError):
        deserialize_claim(payload)
    payload = serialize_claim(_claim())
    payload["schema"] = "kissne.memory_claim/2"
    with pytest.raises(ClaimError):
        deserialize_claim(payload)


def test_round_trip_preserves_types_and_values():
    claim = _claim(
        subject=SUBJECT_PROJECT,
        kind=KIND_FACT,
        realm=REALM_CONVERSATION,
        epistemic=EPISTEMIC_OBSERVED,
        evidence=(_evidence(EVIDENCE_WORLD_EVENT),),
        policy={"sensitivity": {"decided": False}},
        valid_from="2026-09-01T00:00:00+08:00",
    )
    again = deserialize_claim(serialize_claim(claim))
    assert again == claim


def test_policy_layer_stays_opaque_and_undecided():
    """敏感策略与 Shared Event 粒度仍未拍板：合同只做不透明保存。"""
    policy = {"granularity": {"decided": False}, "sensitive": {"handling": "policy-layer"}}
    claim = _claim(policy=policy)
    assert deserialize_claim(serialize_claim(claim)).policy == policy
    assert isinstance(claim.policy, dict)


# ── legacy boundary translation (Biography category → subject) ──────────────

def test_legacy_payload_can_be_translated_only_at_the_boundary():
    legacy = {
        "claim_id": "claim-1",
        "category": "self_memory",
        "kind": KIND_FACT,
        "realm": REALM_AI_WORLD,
        "epistemic": EPISTEMIC_AGENT_EXPERIENCED,
        "statement": "跑过一次演练",
        "occurred_at": "2026-09-15T18:00:00+08:00",
        "recorded_at": "2026-09-16T07:40:00+08:00",
        "timezone": "Asia/Shanghai",
        "source_refs": [{"kind": SOURCE_TOOL_RECEIPT, "ref": "receipt-1", "locator": ""}],
        "evidence": [
            {"kind": EVIDENCE_TOOL_RECEIPT, "sourceRef": {"kind": SOURCE_TOOL_RECEIPT, "ref": "receipt-1", "locator": ""}, "detail": ""}
        ],
    }
    claim = claim_from_legacy_payload(legacy)
    assert claim.subject == SUBJECT_YEQINGXU
    assert "category" not in serialize_claim(claim)
    # 但 canonical 反序列化绝不接受 category
    with pytest.raises(SubjectConflictError):
        deserialize_claim({**legacy, "subject": SUBJECT_YEQINGXU})


def test_legacy_translation_refuses_a_conflicting_subject():
    with pytest.raises(SubjectConflictError):
        claim_from_legacy_payload({"category": "user_memory", "subject": SUBJECT_SHARED})


# ── module boundaries: contract only ────────────────────────────────────────

def test_module_is_a_contract_only_no_provider_or_recall_surface():
    exported = dir(memory_claim)
    for forbidden in (
        "MemoryProvider",
        "KissneMemoryProvider",
        "recall",
        "search",
        "embed",
        "SqliteStore",
        "VectorIndex",
        "mutate",
        "MutationGate",
    ):
        assert forbidden not in exported, f"{forbidden} belongs to KB2-C/D, not to this ticket"
