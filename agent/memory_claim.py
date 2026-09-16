"""KB2-A-CLAIM-CONTRACT — the minimum contract for a Kissne Memory Claim.

A Memory Claim is the smallest unit of long-term memory: one fact, experience,
state, preference, intention, impression or episode, belonging to exactly one
subject, known in exactly one way, living in exactly one world, and pinned to
real time — with a way back to the canonical record it came from.

This module freezes only the six groups the ticket named:

* ``subject``   — whose fact / experience / state this is
* ``kind``      — what type of memory it is (a second, independent axis)
* ``realm``     — which world it belongs to
* ``epistemic`` — how it is known
* time triple   — ``occurred_at`` / ``recorded_at`` / ``timezone``
* valid time    — ``valid_from`` / ``valid_to``

Two axes, never one: ``subject`` answers *whose*, ``kind`` answers *what type*.
The old product names (``user_memory`` …) survive only as boundary translations
(``resolve_subject`` / ``claim_from_legacy_payload``); a canonical claim — in
memory, in storage, in the serialized form — carries ``subject`` and never a
duplicate ``category``.

The axes, the pointer vocabulary and the shared consistency rules all come from
:mod:`agent.memory_vocabulary` — the single definition, shared with the
Biography contract.  Nothing here imports that contract, and it imports nothing
from here.

Four rules this contract refuses to soften:

* **Traceability.**  ``source_refs`` is mandatory and non-empty: every claim is
  walkable back to a canonical record (Unified History stays the evidence
  ledger).  A claim only carries pointers, never a copy of the original text.
* **No silent promotion.**  ``epistemic`` is stored exactly as given.  There is
  no API here that turns ``INFERRED`` into ``OBSERVED``: repetition is not
  evidence.  A ``HYPOTHETICAL`` claim cannot be an event that happened.
* **No fabricated past.**  ``subject=yeqingxu`` + ``AGENT_EXPERIENCED`` needs
  real execution / tool-receipt / world-event evidence, otherwise it is refused
  rather than invented.
* **Undecided stays undecided.**  Sensitivity handling and Shared Event
  granularity are the future policy layer's call: ``policy`` is opaque and
  round-trips untouched.

Deliberately absent (their own tickets): ``status`` / ``supersedes`` /
``contradicts`` (KB2-B), the Mutation Gate and write decisions (KB2-C), Recall,
reentry, any storage or embedding (KB2-D, KB4).

Field sets are exported as frozen tuples so that widening the schema has to be a
test-visible change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Tuple

from agent.memory_vocabulary import (
    EPISTEMIC_AGENT_EXPERIENCED,
    EPISTEMIC_HYPOTHETICAL,
    EPISTEMIC_INFERRED,
    EPISTEMIC_OBSERVED,
    EPISTEMIC_USER_DECLARED,
    EPISTEMICS,
    EVIDENCE_AI_WORLD_EXPERIENCE,
    EVIDENCE_EXECUTION,
    EVIDENCE_FIELDS,
    EVIDENCE_TOOL_RECEIPT,
    EVIDENCE_WORLD_EVENT,
    KIND_EPISODE,
    KIND_EVENT,
    KIND_FACT,
    KIND_IMPRESSION,
    KIND_INTENTION,
    KIND_PREFERENCE,
    KIND_STATE,
    KINDS,
    LEGACY_SUBJECT_ALIASES,
    REALM_AI_WORLD,
    REALM_CONVERSATION,
    REALM_EARTH,
    REALM_SYSTEM,
    REALMS,
    SELF_EVIDENCE_KINDS,
    SOURCE_CONVERSATION_TURN,
    SOURCE_EARTH_OBSERVATION,
    SOURCE_EVENT,
    SOURCE_KINDS,
    SOURCE_REF_FIELDS,
    SOURCE_TOOL_RECEIPT,
    SUBJECT_PROJECT,
    SUBJECT_SHARED,
    SUBJECT_USER,
    SUBJECT_YEQINGXU,
    SUBJECTS,
    Evidence,
    HypotheticalNotAnEventError,
    InvalidEpistemicError,
    InvalidEvidenceKindError,
    InvalidKindError,
    InvalidProvenanceError,
    InvalidRealmError,
    InvalidSourceRefError,
    InvalidSubjectError,
    MissingEvidenceError,
    MissingSourceRefError,
    MemoryVocabularyError,
    Provenance,
    SourceRef,
    SubjectConflictError,
    UnsupportedEvidenceKindError,
    check_consistency,
    is_hypothetical_event,
    requires_real_evidence,
    resolve_subject,
)

# ── schema identity ─────────────────────────────────────────────────────────

SCHEMA_ID = "kissne.memory_claim/1"

# ── frozen field sets ───────────────────────────────────────────────────────

CLAIM_FIELDS = (
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

CLAIM_TIME_FIELDS = ("occurred_at", "recorded_at")
CLAIM_VALIDITY_FIELDS = ("valid_from", "valid_to")


# ── claim-shape errors (the axes' errors live in the vocabulary) ────────────

class ClaimError(ValueError):
    """Base class for every claim-contract violation."""


class InvalidTimeError(ClaimError):
    """A required timestamp is missing or malformed, or the timezone is blank."""


class InvalidValidityWindowError(ClaimError):
    """The validity window is malformed, or runs backwards."""


class InvalidClaimError(ClaimError):
    """The claim, or its serialized form, is not well formed."""


# ── helpers ─────────────────────────────────────────────────────────────────

def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_timestamp(value: Any) -> bool:
    """Validate an ISO-8601 timestamp.  Storing and checking only — never parsing prose."""
    if not _text(value):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


# ── the contract ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Claim:
    """One minimum memory claim: subject + kind + realm + epistemic + time + evidence pointer."""

    claim_id: str
    subject: Optional[str] = None
    kind: Optional[str] = None
    realm: Optional[str] = None
    epistemic: Optional[str] = None
    statement: Optional[str] = None
    occurred_at: Optional[str] = None
    recorded_at: Optional[str] = None
    timezone: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    source_refs: Tuple[SourceRef, ...] = ()
    evidence: Tuple[Evidence, ...] = ()
    policy: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _text(self.claim_id):
            raise InvalidClaimError("claim_id must be a stable, non-empty id")

        # 1. subject — whose memory this is.  No default: it is never guessed.
        if self.subject not in SUBJECTS:
            raise InvalidSubjectError(
                f"subject {self.subject!r} is not a canonical subject; expected one of {SUBJECTS}"
            )

        # 2. kind — what type of memory it is, on its own axis.
        if self.kind not in KINDS:
            raise InvalidKindError(f"kind {self.kind!r} is not a memory kind; expected one of {KINDS}")

        # 3. realm — which world it belongs to.  No default, so Earth facts and
        #    AI World events can never be silently swapped.
        if self.realm not in REALMS:
            raise InvalidRealmError(f"realm {self.realm!r} is not a known realm; expected one of {REALMS}")

        # 4. epistemic — how it is known, stored as given.
        if self.epistemic not in EPISTEMICS:
            raise InvalidEpistemicError(
                f"epistemic {self.epistemic!r} is not a known epistemic value; expected one of {EPISTEMICS}"
            )

        if not _text(self.statement):
            raise InvalidClaimError("statement must be the claim's own content")

        # 5. time triple — when it happened vs when it was recorded, plus zone.
        for name in CLAIM_TIME_FIELDS:
            if not _iso_timestamp(getattr(self, name)):
                raise InvalidTimeError(
                    f"{name} must be an ISO-8601 timestamp: {name} is when the event "
                    f"{'happened' if name == 'occurred_at' else 'was learned'}, and it is required"
                )
        if not _text(self.timezone):
            raise InvalidTimeError("timezone must record the zone the event happened in")

        # 6. valid time — an interval that may be open, but never backwards.
        for name in CLAIM_VALIDITY_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            if not _iso_timestamp(value):
                raise InvalidValidityWindowError(f"{name} must be an ISO-8601 timestamp when present")
        if self.valid_from is not None and self.valid_to is not None:
            if datetime.fromisoformat(self.valid_from) > datetime.fromisoformat(self.valid_to):
                raise InvalidValidityWindowError(
                    "valid_from is after valid_to; a claim that stops being true before it starts is not valid"
                )

        # traceability: pointers at canonical records, never a copy of them.
        refs = tuple(self.source_refs or ())
        if not refs:
            raise MissingSourceRefError(
                "source_refs must carry at least one pointer at a canonical record"
            )
        for ref in refs:
            if not isinstance(ref, SourceRef):
                raise InvalidClaimError("source_refs must contain only SourceRef values")
        object.__setattr__(self, "source_refs", refs)

        items = tuple(self.evidence or ())
        for item in items:
            if not isinstance(item, Evidence):
                raise InvalidClaimError("evidence must contain only Evidence values")
        object.__setattr__(self, "evidence", items)

        # shared rules, one implementation (agent.memory_vocabulary)
        check_consistency(subject=self.subject, kind=self.kind, epistemic=self.epistemic, evidence=items)

        if self.policy is None:
            object.__setattr__(self, "policy", {})
        elif isinstance(self.policy, Mapping):
            # Opaque by design: sensitivity handling and Shared Event granularity
            # are the policy layer's decision, not this schema's.
            object.__setattr__(self, "policy", dict(self.policy))
        else:
            raise InvalidClaimError("policy must be a mapping (it is left to the policy layer)")


# ── serialization ───────────────────────────────────────────────────────────

def _dump_source_ref(ref: SourceRef) -> dict:
    return {"kind": ref.kind, "ref": ref.ref, "locator": ref.locator}


def _dump_evidence(item: Evidence) -> dict:
    return {"kind": item.kind, "sourceRef": _dump_source_ref(item.sourceRef), "detail": item.detail}


def serialize_claim(claim: Claim) -> dict:
    """Claim → JSON-ready dict.  Canonical field names only; pointers stay pointers."""
    if not isinstance(claim, Claim):
        raise InvalidClaimError("serialize_claim expects a Claim")
    return {
        "schema": SCHEMA_ID,
        "claim_id": claim.claim_id,
        "subject": claim.subject,
        "kind": claim.kind,
        "realm": claim.realm,
        "epistemic": claim.epistemic,
        "statement": claim.statement,
        "occurred_at": claim.occurred_at,
        "recorded_at": claim.recorded_at,
        "timezone": claim.timezone,
        "valid_from": claim.valid_from,
        "valid_to": claim.valid_to,
        "source_refs": [_dump_source_ref(ref) for ref in claim.source_refs],
        "evidence": [_dump_evidence(item) for item in claim.evidence],
        "policy": dict(claim.policy),
    }


def _load_source_ref(data: Any) -> SourceRef:
    if not isinstance(data, Mapping):
        raise InvalidClaimError("source_ref must be a mapping")
    unknown = set(data) - set(SOURCE_REF_FIELDS)
    if unknown:
        raise InvalidClaimError(f"unknown source_ref fields: {sorted(unknown)}")
    try:
        return SourceRef(kind=data["kind"], ref=data["ref"], locator=data.get("locator", ""))
    except KeyError as exc:
        raise InvalidClaimError(f"source_ref is missing {exc}") from exc


def _load_evidence(data: Any) -> Evidence:
    if not isinstance(data, Mapping):
        raise InvalidClaimError("evidence item must be a mapping")
    unknown = set(data) - set(EVIDENCE_FIELDS)
    if unknown:
        raise InvalidClaimError(f"unknown evidence fields: {sorted(unknown)}")
    try:
        return Evidence(
            kind=data["kind"],
            sourceRef=_load_source_ref(data["sourceRef"]),
            detail=data.get("detail", ""),
        )
    except KeyError as exc:
        raise InvalidClaimError(f"evidence is missing {exc}") from exc


def _load_sequence(data: Any, loader, name: str) -> Tuple[Any, ...]:
    if data is None:
        return ()
    if not isinstance(data, (list, tuple)):
        raise InvalidClaimError(f"{name} must be a list")
    return tuple(loader(item) for item in data)


def deserialize_claim(data: Any) -> Claim:
    """JSON-ready dict → Claim.  Canonical form only: a legacy ``category`` is refused."""
    if not isinstance(data, Mapping):
        raise InvalidClaimError("a serialized claim must be a mapping")
    if "category" in data:
        raise SubjectConflictError(
            "category is not a canonical field: claims carry subject, and storing both would let the two disagree"
        )
    unknown = set(data) - ({"schema"} | set(CLAIM_FIELDS))
    if unknown:
        raise InvalidClaimError(f"unknown claim fields: {sorted(unknown)}")
    schema = data.get("schema")
    if schema is not None and schema != SCHEMA_ID:
        raise InvalidClaimError(f"unsupported schema {schema!r}; this contract is {SCHEMA_ID}")
    if "subject" not in data:
        raise InvalidSubjectError("serialized claim is missing subject")
    missing = [name for name in ("claim_id", "kind", "realm", "epistemic", "statement") if name not in data]
    if missing:
        raise InvalidClaimError(f"serialized claim is missing required fields: {missing}")

    return Claim(
        claim_id=data["claim_id"],
        subject=data["subject"],
        kind=data["kind"],
        realm=data["realm"],
        epistemic=data["epistemic"],
        statement=data["statement"],
        occurred_at=data.get("occurred_at"),
        recorded_at=data.get("recorded_at"),
        timezone=data.get("timezone"),
        valid_from=data.get("valid_from"),
        valid_to=data.get("valid_to"),
        source_refs=_load_sequence(data.get("source_refs"), _load_source_ref, "source_refs"),
        evidence=_load_sequence(data.get("evidence"), _load_evidence, "evidence"),
        policy=data.get("policy") or {},
    )


def claim_from_legacy_payload(data: Mapping[str, Any]) -> Claim:
    """Translate an old-shaped payload (``category``) at the boundary, once.

    Nothing inside the system reads ``category``; this exists so that a caller
    holding pre-KB2A data can hand it over without the old name leaking into the
    canonical object.
    """
    if not isinstance(data, Mapping):
        raise InvalidClaimError("a legacy payload must be a mapping")
    payload = dict(data)
    if "category" in payload:
        if "subject" in payload:
            raise SubjectConflictError(
                "both category and subject are present; refusing to guess which one is true"
            )
        payload["subject"] = resolve_subject(payload.pop("category"))
    unknown = set(payload) - ({"schema"} | set(CLAIM_FIELDS))
    if unknown:
        raise InvalidClaimError(f"unknown claim fields: {sorted(unknown)}")
    return deserialize_claim(payload)
