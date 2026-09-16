"""KB2-B-MUTATION-SEMANTICS — status and inter-claim relation contract.

B extends a Claim with mutation state, but it does not rewrite KB2-A's frozen
``CLAIM_FIELDS`` tuple.  The B vocabulary lives beside it as ``MUTATION_FIELDS``.
This ticket only represents state/relations; KB2-C decides and applies changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import agent.memory_claim as memory_claim
import agent.memory_mutation_semantics as mutation
from agent.memory_claim import Claim, deserialize_claim, serialize_claim
from agent.memory_mutation_semantics import (
    MUTATION_FIELDS,
    STATUS_ARCHIVED,
    STATUS_CONTRADICTED,
    STATUS_CURRENT,
    STATUS_SUPERSEDED,
    STATUSES,
    InvalidClaimRelationError,
    InvalidClaimStatusError,
)
from agent.memory_vocabulary import (
    EPISTEMIC_USER_DECLARED,
    KIND_PREFERENCE,
    REALM_EARTH,
    SOURCE_CONVERSATION_TURN,
    SUBJECT_USER,
    MissingSourceRefError,
    SourceRef,
)


def _claim(**overrides) -> Claim:
    payload = dict(
        claim_id="claim-new",
        subject=SUBJECT_USER,
        kind=KIND_PREFERENCE,
        realm=REALM_EARTH,
        epistemic=EPISTEMIC_USER_DECLARED,
        statement="现在不喜欢 X 了",
        occurred_at="2026-09-16T08:00:00+08:00",
        recorded_at="2026-09-16T08:01:00+08:00",
        timezone="Asia/Taipei",
        source_refs=(SourceRef(kind=SOURCE_CONVERSATION_TURN, ref="turn-22"),),
    )
    payload.update(overrides)
    return Claim(**payload)


def test_status_axis_is_exactly_the_four_frozen_values():
    assert STATUSES == (
        STATUS_CURRENT,
        STATUS_SUPERSEDED,
        STATUS_CONTRADICTED,
        STATUS_ARCHIVED,
    )
    assert STATUSES == ("CURRENT", "SUPERSEDED", "CONTRADICTED", "ARCHIVED")


def test_mutation_fields_are_separate_from_the_kb2_a_field_freeze():
    assert MUTATION_FIELDS == ("status", "supersedes", "contradicts")
    assert all(field not in memory_claim.CLAIM_FIELDS for field in MUTATION_FIELDS)
    assert "category" not in MUTATION_FIELDS


def test_new_claim_defaults_to_current_without_relations():
    claim = _claim()
    assert claim.status == STATUS_CURRENT
    assert claim.supersedes == ()
    assert claim.contradicts == ()


@pytest.mark.parametrize("status", STATUSES)
def test_every_status_round_trips_without_changing_meaning(status):
    claim = _claim(status=status)
    again = deserialize_claim(serialize_claim(claim))
    assert again.status == status


@pytest.mark.parametrize("bad", ["", "current", "DELETED", "RETRACTED", None, 7])
def test_unknown_status_is_rejected(bad):
    with pytest.raises(InvalidClaimStatusError):
        _claim(status=bad)


def test_current_is_canonical_default_and_is_elided_on_wire():
    payload = serialize_claim(_claim())
    assert "status" not in payload
    assert "supersedes" not in payload
    assert "contradicts" not in payload
    assert deserialize_claim(payload).status == STATUS_CURRENT


def test_explicit_current_on_wire_is_rejected_as_duplicate_encoding():
    payload = serialize_claim(_claim())
    payload["status"] = STATUS_CURRENT
    with pytest.raises(InvalidClaimStatusError):
        deserialize_claim(payload)


def test_new_current_claim_can_point_back_to_claim_it_supersedes():
    claim = _claim(status=STATUS_CURRENT, supersedes=("claim-old",))
    assert claim.status == STATUS_CURRENT
    assert claim.supersedes == ("claim-old",)
    assert claim.contradicts == ()


def test_new_current_claim_can_point_back_to_claim_it_contradicts():
    claim = _claim(status=STATUS_CURRENT, contradicts=("claim-old",))
    assert claim.status == STATUS_CURRENT
    assert claim.contradicts == ("claim-old",)
    assert claim.supersedes == ()


def test_relation_does_not_auto_change_this_claim_status():
    """B only represents relations. C decides and applies mutations."""
    assert _claim(supersedes=("claim-old",)).status == STATUS_CURRENT
    assert _claim(contradicts=("claim-old",)).status == STATUS_CURRENT


def test_superseded_or_contradicted_claim_need_not_have_outgoing_links():
    """The newer claim owns the backward relation; an old claim may only carry status."""
    assert _claim(claim_id="old-1", status=STATUS_SUPERSEDED).supersedes == ()
    assert _claim(claim_id="old-2", status=STATUS_CONTRADICTED).contradicts == ()


def test_archived_is_a_status_not_deletion():
    claim = _claim(status=STATUS_ARCHIVED)
    payload = serialize_claim(claim)
    assert payload["status"] == STATUS_ARCHIVED
    assert payload["statement"] == claim.statement
    assert payload["source_refs"]


@pytest.mark.parametrize(
    "field_name,bad",
    [
        ("supersedes", ("",)),
        ("supersedes", ("   ",)),
        ("supersedes", (7,)),
        ("contradicts", (None,)),
        ("contradicts", "claim-old"),
    ],
)
def test_relation_ids_must_be_a_sequence_of_non_empty_claim_ids(field_name, bad):
    with pytest.raises(InvalidClaimRelationError):
        _claim(**{field_name: bad})


def test_relation_ids_must_be_unique():
    with pytest.raises(InvalidClaimRelationError):
        _claim(supersedes=("old", "old"))
    with pytest.raises(InvalidClaimRelationError):
        _claim(contradicts=("old", "old"))


def test_claim_cannot_point_at_itself():
    with pytest.raises(InvalidClaimRelationError):
        _claim(claim_id="claim-new", supersedes=("claim-new",))
    with pytest.raises(InvalidClaimRelationError):
        _claim(claim_id="claim-new", contradicts=("claim-new",))


def test_same_target_cannot_be_both_superseded_and_contradicted():
    with pytest.raises(InvalidClaimRelationError):
        _claim(supersedes=("claim-old",), contradicts=("claim-old",))


def test_relation_order_is_preserved_and_round_trips():
    claim = _claim(supersedes=("old-a", "old-b"), contradicts=("old-c",))
    again = deserialize_claim(serialize_claim(claim))
    assert again.supersedes == ("old-a", "old-b")
    assert again.contradicts == ("old-c",)


def test_relation_fields_are_ids_only_not_embedded_claim_copies():
    payload = serialize_claim(_claim(supersedes=("old-a",), contradicts=("old-b",)))
    assert payload["supersedes"] == ["old-a"]
    assert payload["contradicts"] == ["old-b"]
    assert all(isinstance(value, str) for value in payload["supersedes"] + payload["contradicts"])


def test_source_refs_stay_mandatory_for_status_and_relation_records():
    """B adds no provenance bypass: historical state must remain traceable."""
    with pytest.raises(MissingSourceRefError):
        _claim(status=STATUS_SUPERSEDED, source_refs=())


def test_validity_time_does_not_silently_choose_status():
    """valid_to and status are separate facts; C will decide mutation transitions."""
    ended = _claim(valid_to="2026-09-15T00:00:00+08:00")
    assert ended.status == STATUS_CURRENT
    explicit = _claim(status=STATUS_SUPERSEDED, valid_to=None)
    assert explicit.status == STATUS_SUPERSEDED


def test_kb2_b_exposes_no_mutation_gate_or_write_decision_api():
    for module in (memory_claim, mutation):
        for forbidden in (
            "MutationGate",
            "mutate",
            "apply_mutation",
            "supersede",
            "contradict",
            "archive_claim",
            "decide_mutation",
        ):
            assert not hasattr(module, forbidden), f"{forbidden} belongs to KB2-C, not KB2-B"

    source = Path(memory_claim.__file__).read_text(encoding="utf-8")
    assert "class MutationGate" not in source
