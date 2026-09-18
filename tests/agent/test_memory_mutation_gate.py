"""KB2-C-MUTATION-GATE — the evidence/semantics gate over a candidate claim.

C answers exactly one question — *what should happen to canonical memory* — and
answers it from evidence and semantic relations only.  It is not a scoring
function: there is no confidence value anywhere in the decision, and the opaque
``policy`` input never changes the verdict.

The gate decides; it does not store.  No Provider, no SQLite, no Recall, no
vector index, and no ``DELETE`` — the last one is deliberately outside this
ticket (see ``详细规划/11_Hermes改造与分阶段交付.md`` §0.3.12).

The six hard conditions are each asserted below with a counterexample, and the
``UPDATE`` vs ``SUPERSEDE`` vs ``CONTRADICT`` split is asserted directly:
``UPDATE`` may only *supplement* the same canonical claim, never rewrite what
used to be true.  A fact that used to hold and then changed goes ``SUPERSEDE``;
a fact that was wrong goes ``CONTRADICT``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import agent.memory_mutation_gate as gate
from agent.memory_claim import Claim
from agent.memory_mutation_gate import (
    ACTION_ADD,
    ACTION_ARCHIVE,
    ACTION_CONTRADICT,
    ACTION_NO_CHANGE,
    ACTION_REJECT,
    ACTION_SUPERSEDE,
    ACTION_UPDATE,
    EPISTEMIC_ORDER,
    GATE_ACTIONS,
    GATE_SCHEMA_ID,
    MUTATION_ACTIONS,
    REASON_AMBIGUOUS_TARGET,
    REASON_BACKDATED_SUPERSEDE,
    REASON_CROSS_REALM_SUPERSEDE,
    REASON_EPISTEMIC_PROMOTION,
    REASON_HISTORY_REWRITE,
    REASON_HYPOTHETICAL_HISTORY,
    REASON_NO_EVIDENCE,
    REASON_NO_NEW_EVIDENCE,
    REASON_SAME_SOURCE_REPLAY,
    REASON_UNKNOWN_TARGET,
    MutationGateError,
    decide_mutation,
    decision_provenance,
)
from agent.memory_mutation_semantics import (
    STATUS_ARCHIVED,
    STATUS_CURRENT,
    STATUSES,
)
from agent.memory_vocabulary import (
    EVIDENCE_EXECUTION,
    EPISTEMIC_HYPOTHETICAL,
    EPISTEMIC_INFERRED,
    EPISTEMIC_OBSERVED,
    EPISTEMIC_USER_DECLARED,
    KIND_EVENT,
    KIND_PREFERENCE,
    KIND_STATE,
    REALM_AI_WORLD,
    REALM_EARTH,
    SOURCE_CONVERSATION_TURN,
    SOURCE_TOOL_RECEIPT,
    SUBJECT_USER,
    Evidence,
    Provenance,
    SourceRef,
)

GATE_MODULE_PATH = Path(gate.__file__)


def _ref(name: str, kind: str = SOURCE_CONVERSATION_TURN) -> SourceRef:
    return SourceRef(kind=kind, ref=name)


def _evidence(name: str) -> Evidence:
    return Evidence(kind=EVIDENCE_EXECUTION, sourceRef=_ref(name, SOURCE_TOOL_RECEIPT), detail="ran it")


def _claim(**overrides) -> Claim:
    payload = dict(
        claim_id="claim-new",
        subject=SUBJECT_USER,
        kind=KIND_PREFERENCE,
        realm=REALM_EARTH,
        epistemic=EPISTEMIC_USER_DECLARED,
        statement="喜欢 X",
        occurred_at="2026-09-16T08:00:00+08:00",
        recorded_at="2026-09-16T08:01:00+08:00",
        timezone="Asia/Taipei",
        source_refs=(_ref("turn-1"),),
    )
    payload.update(overrides)
    return Claim(**payload)


def _src() -> str:
    return GATE_MODULE_PATH.read_text(encoding="utf-8")


# ── vocabulary boundaries ───────────────────────────────────────────────────

def test_gate_actions_are_separate_from_claim_status():
    assert MUTATION_ACTIONS == (
        ACTION_ADD,
        ACTION_UPDATE,
        ACTION_SUPERSEDE,
        ACTION_CONTRADICT,
        ACTION_ARCHIVE,
        ACTION_NO_CHANGE,
    )
    assert GATE_ACTIONS == MUTATION_ACTIONS + (ACTION_REJECT,)
    # REJECT is a gate result, never a Claim status.
    assert ACTION_REJECT not in STATUSES
    assert not set(GATE_ACTIONS).intersection(STATUSES)
    assert GATE_SCHEMA_ID == "kissne.mutation_gate/1"


def test_delete_is_out_of_scope():
    assert "DELETE" not in GATE_ACTIONS
    assert "delete" not in MUTATION_ACTIONS
    assert not re.search(r"\bdef\s+delete\w*\s*\(", _src())
    assert not re.search(r"^\s*from\s+.*\b(?:sqlite3|chromadb|openai|requests)\b", _src(), re.M)


# ── ADD ────────────────────────────────────────────────────────────────────

def test_unseen_claim_is_added_and_carries_provenance():
    decision = decide_mutation(candidate=_claim(claim_id="claim-a"), canonical_state=())
    assert decision.action == ACTION_ADD
    assert decision.target_claim_id is None
    assert decision.is_change is True
    assert decision.is_refusal is False
    assert decision.schema == GATE_SCHEMA_ID
    provenance = decision_provenance(decision)
    assert isinstance(provenance, Provenance)
    assert provenance.recorded_at == "2026-09-16T08:01:00+08:00"
    assert provenance.sourceRefs == (_ref("turn-1"),)


# ── hard condition 1: replay of the same sourceRef must not re-strengthen ───

def test_same_source_replay_does_not_strengthen():
    existing = _claim(claim_id="claim-1")
    replay = _claim(claim_id="claim-2", source_refs=(_ref("turn-1"),))
    decision = decide_mutation(candidate=replay, canonical_state=(existing,))
    assert decision.action == ACTION_NO_CHANGE
    assert decision.reason_code == REASON_SAME_SOURCE_REPLAY
    assert decision.is_change is False
    assert decision.target_claim_id == "claim-1"


# ── hard condition 2: INFERRED cannot be upgraded by repetition ─────────────

def test_inferred_cannot_be_upgraded_by_repetition():
    existing = _claim(claim_id="claim-1", epistemic=EPISTEMIC_INFERRED)
    repetition = _claim(claim_id="claim-2", epistemic=EPISTEMIC_OBSERVED)
    decision = decide_mutation(candidate=repetition, canonical_state=(existing,))
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_EPISTEMIC_PROMOTION
    assert decision.is_refusal is True
    assert EPISTEMIC_ORDER[EPISTEMIC_INFERRED] < EPISTEMIC_ORDER[EPISTEMIC_OBSERVED]


def test_inferred_can_be_upgraded_only_with_new_evidence():
    existing = _claim(claim_id="claim-1", epistemic=EPISTEMIC_INFERRED)
    upgraded = _claim(
        claim_id="claim-2",
        epistemic=EPISTEMIC_OBSERVED,
        source_refs=(_ref("turn-1"), _ref("turn-9")),
        evidence=(_evidence("tool-9"),),
    )
    decision = decide_mutation(candidate=upgraded, canonical_state=(existing,))
    assert decision.action == ACTION_UPDATE
    assert decision.target_claim_id == "claim-1"


# ── hard condition 3: a hypothetical must not become history ────────────────

def test_hypothetical_cannot_become_history_without_new_evidence():
    existing = _claim(
        claim_id="claim-h",
        kind=KIND_STATE,
        epistemic=EPISTEMIC_HYPOTHETICAL,
        statement="假设 X 会发生",
    )
    candidate = _claim(
        claim_id="claim-e",
        kind=KIND_EVENT,
        epistemic=EPISTEMIC_OBSERVED,
        statement="X 发生了",
        supersedes=("claim-h",),
        source_refs=(_ref("turn-1"),),
    )
    decision = decide_mutation(candidate=candidate, canonical_state=(existing,))
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_HYPOTHETICAL_HISTORY


def test_hypothetical_can_be_replaced_by_real_evidence():
    existing = _claim(
        claim_id="claim-h",
        kind=KIND_STATE,
        epistemic=EPISTEMIC_HYPOTHETICAL,
        statement="假设 X 会发生",
    )
    candidate = _claim(
        claim_id="claim-e",
        kind=KIND_EVENT,
        epistemic=EPISTEMIC_OBSERVED,
        statement="X 发生了",
        supersedes=("claim-h",),
        occurred_at="2026-09-16T09:00:00+08:00",
        source_refs=(_ref("turn-1"), _ref("turn-9")),
        evidence=(_evidence("tool-9"),),
    )
    decision = decide_mutation(candidate=candidate, canonical_state=(existing,))
    assert decision.action == ACTION_SUPERSEDE
    assert decision.preserved_claim_ids == ("claim-h",)


# ── hard condition 4: no supersede across realms ────────────────────────────

def test_cross_realm_supersede_is_refused():
    existing = _claim(claim_id="claim-1", realm=REALM_EARTH)
    candidate = _claim(
        claim_id="claim-2",
        realm=REALM_AI_WORLD,
        supersedes=("claim-1",),
        occurred_at="2026-09-16T09:00:00+08:00",
        source_refs=(_ref("turn-1"), _ref("turn-9")),
        evidence=(_evidence("tool-9"),),
    )
    decision = decide_mutation(candidate=candidate, canonical_state=(existing,))
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_CROSS_REALM_SUPERSEDE


# ── hard condition 5: thin evidence prefers NO_CHANGE over forcing a change ─

def test_thin_evidence_prefers_no_change():
    existing = _claim(claim_id="claim-1")
    candidate = _claim(
        claim_id="claim-2",
        supersedes=("claim-1",),
        occurred_at="2026-09-16T09:00:00+08:00",
        source_refs=(_ref("turn-1"),),
        evidence=(_evidence("tool-1"),),
    )
    decision = decide_mutation(candidate=candidate, canonical_state=(existing,))
    assert decision.action == ACTION_NO_CHANGE
    assert decision.reason_code == REASON_NO_NEW_EVIDENCE
    assert decision.is_change is False


# ── hard condition 6: state-changing decisions need evidence + provenance ──

def test_replacing_a_claim_without_evidence_is_refused():
    existing = _claim(claim_id="claim-1")
    candidate = _claim(
        claim_id="claim-2",
        supersedes=("claim-1",),
        occurred_at="2026-09-16T09:00:00+08:00",
        source_refs=(_ref("turn-1"), _ref("turn-9")),
    )
    decision = decide_mutation(candidate=candidate, canonical_state=(existing,))
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_NO_EVIDENCE


def test_every_decision_keeps_a_way_back_to_evidence():
    existing = _claim(claim_id="claim-1")
    cases = (
        _claim(claim_id="claim-add"),
        _claim(claim_id="claim-1", source_refs=(_ref("turn-1"), _ref("turn-9"))),
        _claim(
            claim_id="claim-sup",
            supersedes=("claim-1",),
            occurred_at="2026-09-16T09:00:00+08:00",
            source_refs=(_ref("turn-1"), _ref("turn-9")),
            evidence=(_evidence("tool-9"),),
        ),
        _claim(
            claim_id="claim-con",
            contradicts=("claim-1",),
            source_refs=(_ref("turn-1"), _ref("turn-9")),
            evidence=(_evidence("tool-9"),),
        ),
        _claim(
            claim_id="claim-1",
            status=STATUS_ARCHIVED,
            source_refs=(_ref("turn-1"), _ref("turn-9")),
        ),
    )
    for candidate in cases:
        decision = decide_mutation(candidate=candidate, canonical_state=(existing,))
        assert decision.action in MUTATION_ACTIONS, decision
        provenance = decision_provenance(decision)
        assert provenance.sourceRefs, decision
        assert provenance.origin and provenance.recorded_by, decision


# ── UPDATE may only supplement: the history-rewrite guard ───────────────────

def test_world_change_is_supersede_not_update():
    old = _claim(claim_id="claim-1", statement="喜欢 X")
    changed = _claim(
        claim_id="claim-2",
        statement="不再喜欢 X",
        supersedes=("claim-1",),
        occurred_at="2026-09-16T09:00:00+08:00",
        source_refs=(_ref("turn-1"), _ref("turn-9")),
        evidence=(_evidence("tool-9"),),
    )
    decision = decide_mutation(candidate=changed, canonical_state=(old,))
    assert decision.action == ACTION_SUPERSEDE
    assert decision.preserved_claim_ids == ("claim-1",)


def test_wrong_old_fact_is_contradict_not_update():
    wrong = _claim(claim_id="claim-1", statement="X 是真的")
    corrected = _claim(
        claim_id="claim-2",
        statement="X 不是真的",
        contradicts=("claim-1",),
        source_refs=(_ref("turn-1"), _ref("turn-9")),
        evidence=(_evidence("tool-9"),),
    )
    decision = decide_mutation(candidate=corrected, canonical_state=(wrong,))
    assert decision.action == ACTION_CONTRADICT
    assert decision.preserved_claim_ids == ("claim-1",)


def test_update_supplements_the_same_claim_and_keeps_it():
    existing = _claim(claim_id="claim-1")
    supplemented = _claim(claim_id="claim-1", source_refs=(_ref("turn-1"), _ref("turn-9")))
    decision = decide_mutation(candidate=supplemented, canonical_state=(existing,))
    assert decision.action == ACTION_UPDATE
    assert decision.target_claim_id == "claim-1"
    assert decision.preserved_claim_ids == ("claim-1",)


def test_update_cannot_rewrite_the_old_statement():
    existing = _claim(claim_id="claim-1", statement="喜欢 X")
    rewrite = _claim(
        claim_id="claim-1",
        statement="一直都不喜欢 X",
        source_refs=(_ref("turn-1"), _ref("turn-9")),
    )
    decision = decide_mutation(candidate=rewrite, canonical_state=(existing,))
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_HISTORY_REWRITE


def test_update_cannot_move_the_old_moment_in_time():
    existing = _claim(claim_id="claim-1")
    moved = _claim(
        claim_id="claim-1",
        occurred_at="2026-09-15T08:00:00+08:00",
        source_refs=(_ref("turn-1"), _ref("turn-9")),
    )
    decision = decide_mutation(candidate=moved, canonical_state=(existing,))
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_HISTORY_REWRITE


def test_new_evidence_for_the_same_fact_updates_the_existing_claim():
    existing = _claim(claim_id="claim-1", statement="喜欢 X")
    more_support = _claim(
        claim_id="claim-2",
        statement="喜欢 X",
        source_refs=(_ref("turn-1"), _ref("turn-9")),
    )
    decision = decide_mutation(candidate=more_support, canonical_state=(existing,))
    assert decision.action == ACTION_UPDATE
    assert decision.target_claim_id == "claim-1"


def test_two_identical_facts_in_state_are_an_ambiguous_target():
    first = _claim(claim_id="claim-1", statement="喜欢 X")
    second = _claim(claim_id="claim-2", statement="喜欢 X", recorded_at="2026-09-16T08:05:00+08:00")
    candidate = _claim(claim_id="claim-3", statement="喜欢 X", source_refs=(_ref("turn-9"),))
    decision = decide_mutation(candidate=candidate, canonical_state=(first, second))
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_AMBIGUOUS_TARGET


# ── archive / unknown target / backdating ───────────────────────────────────

def test_archiving_is_a_state_transition_not_a_delete():
    existing = _claim(claim_id="claim-1", status=STATUS_CURRENT)
    archived = _claim(
        claim_id="claim-1",
        status=STATUS_ARCHIVED,
        source_refs=(_ref("turn-1"), _ref("turn-9")),
    )
    decision = decide_mutation(candidate=archived, canonical_state=(existing,))
    assert decision.action == ACTION_ARCHIVE
    assert decision.target_claim_id == "claim-1"
    assert decision.preserved_claim_ids == ("claim-1",)
    assert "DELETE" not in GATE_ACTIONS


def test_unknown_relation_target_is_refused():
    candidate = _claim(
        claim_id="claim-2",
        supersedes=("ghost",),
        occurred_at="2026-09-16T09:00:00+08:00",
        source_refs=(_ref("turn-9"),),
        evidence=(_evidence("tool-9"),),
    )
    decision = decide_mutation(candidate=candidate, canonical_state=())
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_UNKNOWN_TARGET


def test_backdated_supersede_is_refused():
    later = _claim(claim_id="claim-1", occurred_at="2026-09-16T09:00:00+08:00")
    candidate = _claim(
        claim_id="claim-2",
        supersedes=("claim-1",),
        occurred_at="2026-09-16T07:00:00+08:00",
        source_refs=(_ref("turn-1"), _ref("turn-9")),
        evidence=(_evidence("tool-9"),),
    )
    decision = decide_mutation(candidate=candidate, canonical_state=(later,))
    assert decision.action == ACTION_REJECT
    assert decision.reason_code == REASON_BACKDATED_SUPERSEDE


# ── purity: no scoring, no policy influence, no side effects ────────────────

def test_policy_is_opaque_and_cannot_change_the_verdict():
    existing = _claim(claim_id="claim-1", statement="喜欢 X")
    candidate = _claim(claim_id="claim-2", statement="喜欢 X", source_refs=(_ref("turn-1"), _ref("turn-9")))
    baseline = decide_mutation(candidate=candidate, canonical_state=(existing,), policy={})
    for policy in ({"min_confidence": 0.99}, {"threshold": 0.0}, {"score": "low", "note": "不参与判定"}):
        decision = decide_mutation(candidate=candidate, canonical_state=(existing,), policy=policy)
        assert (decision.action, decision.target_claim_id, decision.reason_code) == (
            baseline.action,
            baseline.target_claim_id,
            baseline.reason_code,
        )
        assert decision.policy == policy


def test_the_decision_carries_no_confidence_value():
    assert "confidence" not in gate.GateDecision.__dataclass_fields__
    assert "score" not in gate.GateDecision.__dataclass_fields__
    decision = decide_mutation(candidate=_claim(claim_id="claim-a"), canonical_state=())
    assert not any(isinstance(value, float) for value in decision.__dict__.values())


def test_gate_does_not_mutate_the_canonical_state():
    existing = _claim(claim_id="claim-1", statement="喜欢 X")
    state = [existing]
    candidate = _claim(claim_id="claim-2", statement="喜欢 X", source_refs=(_ref("turn-9"),))
    before = list(state)
    decide_mutation(candidate=candidate, canonical_state=tuple(state))
    assert state == before
    assert state[0] is existing


def test_duplicate_claim_ids_in_state_are_invalid_input():
    first = _claim(claim_id="claim-1")
    second = _claim(claim_id="claim-1", statement="另一件事")
    with pytest.raises(MutationGateError):
        decide_mutation(candidate=_claim(claim_id="claim-2"), canonical_state=(first, second))


def test_canonical_state_must_contain_claims():
    with pytest.raises(MutationGateError):
        decide_mutation(candidate=_claim(claim_id="claim-2"), canonical_state=("not a claim",))  # type: ignore[arg-type]
