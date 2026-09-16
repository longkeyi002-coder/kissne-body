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

Note on layering: this module imports the pointer vocabulary (``SourceRef`` /
``Evidence``) from :mod:`agent.biography` rather than defining a second one, so
the dependency runs one way only.  ``agent.biography`` keeps its own literal
axis values; ``tests/agent/test_biography.py`` locks them to this module's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from agent.biography import (
    EVIDENCE_AI_WORLD_EXPERIENCE,
    EVIDENCE_TOOL_RECEIPT,
    EVIDENCE_WORLD_EVENT,
    EVIDENCE_EXECUTION,
    SELF_EVIDENCE_KINDS,
    SOURCE_KINDS,
    Evidence,
    InvalidEvidenceKindError,
    SourceRef,
)

# ── schema identity ─────────────────────────────────────────────────────────

SCHEMA_ID = "kissne.memory_claim/1"

# ── 1. subject: whose fact / experience / state this is ─────────────────────

SUBJECT_USER = "user"
SUBJECT_YEQINGXU = "yeqingxu"
SUBJECT_SHARED = "shared"
SUBJECT_PROJECT = "project"

SUBJECTS = (SUBJECT_USER, SUBJECT_YEQINGXU, SUBJECT_SHARED, SUBJECT_PROJECT)

# Product-language names are aliases only.  They are never a canonical value.
LEGACY_SUBJECT_ALIASES = {
    "user_memory": SUBJECT_USER,
    "self_memory": SUBJECT_YEQINGXU,
    "shared_memory": SUBJECT_SHARED,
    "project_memory": SUBJECT_PROJECT,
}

# ── 2. kind: a second axis, fully independent of subject ────────────────────

KIND_FACT = "fact"
KIND_EVENT = "event"
KIND_STATE = "state"
KIND_PREFERENCE = "preference"
KIND_INTENTION = "intention"
KIND_IMPRESSION = "impression"
KIND_EPISODE = "episode"

KINDS = (
    KIND_FACT,
    KIND_EVENT,
    KIND_STATE,
    KIND_PREFERENCE,
    KIND_INTENTION,
    KIND_IMPRESSION,
    KIND_EPISODE,
)

# ── 3. realm: which world the claim belongs to ──────────────────────────────

REALM_EARTH = "EARTH"
REALM_AI_WORLD = "AI_WORLD"
REALM_CONVERSATION = "CONVERSATION"
REALM_SYSTEM = "SYSTEM"

REALMS = (REALM_EARTH, REALM_AI_WORLD, REALM_CONVERSATION, REALM_SYSTEM)

# ── 4. epistemic: how the claim is known ────────────────────────────────────

EPISTEMIC_OBSERVED = "OBSERVED"
EPISTEMIC_USER_DECLARED = "USER_DECLARED"
EPISTEMIC_AGENT_EXPERIENCED = "AGENT_EXPERIENCED"
EPISTEMIC_INFERRED = "INFERRED"
EPISTEMIC_HYPOTHETICAL = "HYPOTHETICAL"

EPISTEMICS = (
    EPISTEMIC_OBSERVED,
    EPISTEMIC_USER_DECLARED,
    EPISTEMIC_AGENT_EXPERIENCED,
    EPISTEMIC_INFERRED,
    EPISTEMIC_HYPOTHETICAL,
)

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


# ── errors ──────────────────────────────────────────────────────────────────

class ClaimError(ValueError):
    """Base class for every claim-contract violation."""


class InvalidSubjectError(ClaimError):
    """Subject is missing, or is not one of the canonical subjects."""


class SubjectConflictError(ClaimError):
    """A legacy ``category`` travelled next to a canonical ``subject``."""


class InvalidKindError(ClaimError):
    """Kind is not one of the frozen memory kinds."""


class InvalidRealmError(ClaimError):
    """Realm is missing or unknown; claims never guess which world they are in."""


class InvalidEpistemicError(ClaimError):
    """Epistemic is missing or unknown, so 'how it is known' would be lost."""


class InvalidTimeError(ClaimError):
    """A required timestamp is missing or malformed, or the timezone is blank."""


class InvalidValidityWindowError(ClaimError):
    """The validity window is malformed, or runs backwards."""


class MissingClaimSourceRefError(ClaimError):
    """A claim arrived with nothing to walk back to — the case this ticket exists for."""


class MissingEvidenceError(ClaimError):
    """A first-person claim with nothing behind it."""


class HypotheticalNotAnEventError(ClaimError):
    """A hypothetical is not an event that happened; it never becomes one here."""


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


def resolve_subject(value: Any) -> str:
    """Boundary translation only: accept a canonical subject, or an old product name.

    Returns the canonical subject so callers can hand it to :class:`Claim`; an
    unknown value is refused rather than guessed.
    """
    if isinstance(value, str):
        if value in SUBJECTS:
            return value
        alias = LEGACY_SUBJECT_ALIASES.get(value)
        if alias is not None:
            return alias
    raise InvalidSubjectError(
        f"subject {value!r} is not a canonical subject {SUBJECTS}; "
        f"legacy product names may be translated ({sorted(LEGACY_SUBJECT_ALIASES)}) but are never stored"
    )


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

        # A hypothetical is a thought about a possible world, not a record that
        # something happened.
        if self.epistemic == EPISTEMIC_HYPOTHETICAL and self.kind == KIND_EVENT:
            raise HypotheticalNotAnEventError(
                "a HYPOTHETICAL claim cannot be an event that happened; "
                "saying it in conversation does not make it history"
            )

        # traceability: pointers at canonical records, never a copy of them.
        refs = tuple(self.source_refs or ())
        if not refs:
            raise MissingClaimSourceRefError(
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
        if self.epistemic == EPISTEMIC_AGENT_EXPERIENCED and self.subject == SUBJECT_YEQINGXU and not items:
            raise MissingEvidenceError(
                "subject=yeqingxu with AGENT_EXPERIENCED requires execution / tool receipt / "
                "world event evidence; without it there is no first-person experience to record"
            )
        object.__setattr__(self, "evidence", items)

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
    unknown = set(data) - {"kind", "ref", "locator"}
    if unknown:
        raise InvalidClaimError(f"unknown source_ref fields: {sorted(unknown)}")
    try:
        return SourceRef(kind=data["kind"], ref=data["ref"], locator=data.get("locator", ""))
    except KeyError as exc:
        raise InvalidClaimError(f"source_ref is missing {exc}") from exc


def _load_evidence(data: Any) -> Evidence:
    if not isinstance(data, Mapping):
        raise InvalidClaimError("evidence item must be a mapping")
    unknown = set(data) - {"kind", "sourceRef", "detail"}
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
