"""KB2-B-MUTATION-SEMANTICS — state and relation vocabulary for Memory Claims.

This module represents *what the canonical memory state says*, not *what to do*.
It therefore contains no Mutation Gate, no evidence comparison and no write
operation.  KB2-C owns those decisions.

The semantics are intentionally directional:

* ``status`` describes the state of this claim: CURRENT / SUPERSEDED /
  CONTRADICTED / ARCHIVED.
* ``supersedes`` contains older claim ids that this claim replaces because the
  world changed (for example an old preference).
* ``contradicts`` contains older claim ids that this claim disputes/corrects.

A newer CURRENT claim can therefore point backward while the older record keeps
its own content and provenance.  Nothing here edits that older record.

KB2-A's ``CLAIM_FIELDS`` remains frozen.  These fields are a separate extension
layer, ``MUTATION_FIELDS``.  On the serialized wire CURRENT + empty relations is
the canonical default and is elided; non-default state / non-empty relations are
written explicitly.  This preserves one encoding for the default state.
"""

from __future__ import annotations

from typing import Any, Mapping, Tuple

STATUS_CURRENT = "CURRENT"
STATUS_SUPERSEDED = "SUPERSEDED"
STATUS_CONTRADICTED = "CONTRADICTED"
STATUS_ARCHIVED = "ARCHIVED"

STATUSES = (
    STATUS_CURRENT,
    STATUS_SUPERSEDED,
    STATUS_CONTRADICTED,
    STATUS_ARCHIVED,
)

MUTATION_FIELDS = ("status", "supersedes", "contradicts")


class MutationSemanticsError(ValueError):
    """Base class for KB2-B contract violations."""


class InvalidClaimStatusError(MutationSemanticsError):
    """Status is not one of the four frozen KB2-B values."""


class InvalidClaimRelationError(MutationSemanticsError):
    """A supersedes / contradicts relation is malformed or internally impossible."""


def validate_status(value: Any) -> str:
    if value not in STATUSES:
        raise InvalidClaimStatusError(f"status {value!r} is not valid; expected one of {STATUSES}")
    return value


def _normalize_relation_ids(value: Any, *, field_name: str, claim_id: str) -> Tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise InvalidClaimRelationError(f"{field_name} must be a list/tuple of claim ids")

    result = []
    seen = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise InvalidClaimRelationError(f"{field_name} must contain only non-empty claim ids")
        if item == claim_id:
            raise InvalidClaimRelationError(f"claim {claim_id!r} cannot {field_name[:-1]} itself")
        if item in seen:
            raise InvalidClaimRelationError(f"{field_name} contains duplicate claim id {item!r}")
        seen.add(item)
        result.append(item)
    return tuple(result)


def normalize_relations(
    *,
    claim_id: str,
    supersedes: Any = (),
    contradicts: Any = (),
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    supersedes_ids = _normalize_relation_ids(supersedes, field_name="supersedes", claim_id=claim_id)
    contradicts_ids = _normalize_relation_ids(contradicts, field_name="contradicts", claim_id=claim_id)

    overlap = set(supersedes_ids).intersection(contradicts_ids)
    if overlap:
        target = sorted(overlap)[0]
        raise InvalidClaimRelationError(
            f"claim {target!r} cannot be both superseded and contradicted by the same claim"
        )
    return supersedes_ids, contradicts_ids


def encode_mutation_fields(
    *,
    status: str,
    supersedes: Tuple[str, ...],
    contradicts: Tuple[str, ...],
) -> dict:
    """Return the canonical wire extension for a validated Claim.

    CURRENT with no relations is the default and contributes no keys.  This is
    an encoding rule only; the in-memory Claim always exposes ``status``.
    """
    validate_status(status)
    payload = {}
    if status != STATUS_CURRENT:
        payload["status"] = status
    if supersedes:
        payload["supersedes"] = list(supersedes)
    if contradicts:
        payload["contradicts"] = list(contradicts)
    return payload


def decode_mutation_fields(data: Mapping[str, Any], *, claim_id: str) -> Tuple[str, Tuple[str, ...], Tuple[str, ...]]:
    """Decode the optional KB2-B wire extension without making a mutation decision."""
    if "status" in data and data["status"] == STATUS_CURRENT:
        raise InvalidClaimStatusError(
            "explicit CURRENT is non-canonical on the wire; omit status to represent the default"
        )

    status = validate_status(data.get("status", STATUS_CURRENT))
    supersedes, contradicts = normalize_relations(
        claim_id=claim_id,
        supersedes=data.get("supersedes", ()),
        contradicts=data.get("contradicts", ()),
    )
    return status, supersedes, contradicts
