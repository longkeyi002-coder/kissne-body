"""KB2-BIOGRAPHY-CONTRACT — the provider-neutral contract for Biography entries.

Biography is where an instance's long-lived self-description lives.  It is the
layer that grows *after* the conversation: distilled statements about the user,
about the two of them together, and about the agent's own first-person
experience — each one walkable back to the canonical record it came from.

This module is deliberately **only** the contract.  It defines what a
Biography entry *is* — its subject and kind, its provenance, its evidence and
their field shapes — plus a stable ``serialize`` / ``deserialize`` pair so a later
provider can be swapped in without the schema moving.  It stores nothing, reads
nothing, recalls nothing and embeds nothing; there is no writer API here on
purpose, and no second long-term history is created: canonical records
(conversation turns, tool receipts, observations, events) stay the single
source of truth, and a Biography entry only carries *pointers* at them
(``SourceRef``), never a copy of their text.

Four boundaries the tests enforce and this module refuses to soften:

* **Traceability over summarisation.**  ``provenance.sourceRefs`` is mandatory
  and non-empty; an entry that cannot be walked back to evidence is invalid.
* **No fabricated past.**  ``subject=yeqingxu`` requires at least one evidence
  item backed by a real execution, tool receipt or world event.  With no evidence,
  the entry is rejected rather than invented.
* **AI World is KB4.**  ``ai_world_experience`` is named here exactly so it can
  be refused by name instead of silently accepted before KB4 exists.
* **Undecided policy stays undecided.**  Sensitive-memory handling and Shared
  Event granularity are not fixed by this schema: ``policy`` is opaque and
  round-trips untouched, so the future policy layer decides.

Field sets are exported as frozen tuples (``ENTRY_FIELDS`` …) so that widening
the schema has to be an explicit, test-visible change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Tuple

# ── schema identity ─────────────────────────────────────────────────────────

SCHEMA_ID = "kissne.biography/1"

# ── subject (KB2-A: one axis, canonical values only) ────────────────────────
# Biography's three subjects are a subset of the memory subject axis
# (``user`` / ``yeqingxu`` / ``shared`` / ``project``).  The old product names
# (``user_memory`` …) are boundary aliases in agent/memory_claim.py, never a
# stored field: keeping both in one record is how the two start disagreeing.

SUBJECT_USER = "user"
SUBJECT_SHARED = "shared"
SUBJECT_YEQINGXU = "yeqingxu"

SUBJECTS = (SUBJECT_USER, SUBJECT_YEQINGXU, SUBJECT_SHARED)

# ── kind (KB2-A: a second axis, independent of subject) ─────────────────────
# Locked to agent/memory_claim.KINDS by tests; kept literal here so this module
# needs no import from the claim contract (the dependency runs one way).

KIND_FACT = "fact"
KIND_EVENT = "event"
KIND_STATE = "state"
KIND_PREFERENCE = "preference"
KIND_INTENTION = "intention"
KIND_IMPRESSION = "impression"
KIND_EPISODE = "episode"

BIOGRAPHY_KINDS = (
    KIND_FACT,
    KIND_EVENT,
    KIND_STATE,
    KIND_PREFERENCE,
    KIND_INTENTION,
    KIND_IMPRESSION,
    KIND_EPISODE,
)

# ── canonical record kinds a SourceRef may point at ─────────────────────────
# These are the authoritative records; a Biography entry references them and
# never duplicates them.

SOURCE_CONVERSATION_TURN = "conversation_turn"
SOURCE_TOOL_RECEIPT = "tool_receipt"
SOURCE_EARTH_OBSERVATION = "earth_observation"
SOURCE_EVENT = "event"

SOURCE_KINDS = (
    SOURCE_CONVERSATION_TURN,
    SOURCE_TOOL_RECEIPT,
    SOURCE_EARTH_OBSERVATION,
    SOURCE_EVENT,
)

# ── evidence kinds that can back a first-person experience ──────────────────

EVIDENCE_EXECUTION = "execution"
EVIDENCE_TOOL_RECEIPT = "tool_receipt"
EVIDENCE_WORLD_EVENT = "world_event"

SELF_EVIDENCE_KINDS = (EVIDENCE_EXECUTION, EVIDENCE_TOOL_RECEIPT, EVIDENCE_WORLD_EVENT)

# KB4 territory. Listed so the refusal is explicit and greppable: until AI World
# exists, there is nothing that could be its evidence.
EVIDENCE_AI_WORLD_EXPERIENCE = "ai_world_experience"

# ── frozen field sets ───────────────────────────────────────────────────────

ENTRY_FIELDS = ("entry_id", "subject", "kind", "statement", "provenance", "evidence", "policy")
PROVENANCE_FIELDS = ("origin", "recorded_by", "recorded_at", "sourceRefs")
SOURCE_REF_FIELDS = ("kind", "ref", "locator")
EVIDENCE_FIELDS = ("kind", "sourceRef", "detail")


# ── errors ──────────────────────────────────────────────────────────────────

class BiographyError(ValueError):
    """Base class for every contract violation."""


class InvalidSourceRefError(BiographyError):
    """A SourceRef is not a usable pointer at a canonical record."""


class InvalidProvenanceError(BiographyError):
    """Provenance is missing a required, well-formed field."""


class MissingSourceRefError(InvalidProvenanceError):
    """An entry arrived without any traceable source — the case the ticket exists for."""


class InvalidEvidenceKindError(BiographyError):
    """Evidence is not backed by a canonical record, or its kind is unknown."""


class UnsupportedEvidenceKindError(InvalidEvidenceKindError):
    """A real-sounding kind that this milestone cannot support yet (AI World = KB4)."""


class MissingEvidenceError(BiographyError):
    """A first-person claim with nothing behind it."""


class InvalidSubjectError(BiographyError):
    """Subject is not one of the three Biography subjects."""


class InvalidKindError(BiographyError):
    """Kind is not one of the frozen memory kinds."""


class InvalidBiographyEntryError(BiographyError):
    """The entry (or its serialized form) is not a well-formed Biography entry."""


# ── validation helpers ──────────────────────────────────────────────────────

def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_timestamp(value: Any) -> bool:
    if not _text(value):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


# ── the contract ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SourceRef:
    """A stable pointer at one canonical record.  Never a copy of it."""

    kind: str
    ref: str
    locator: str = ""

    def __post_init__(self) -> None:
        if self.kind not in SOURCE_KINDS:
            raise InvalidSourceRefError(
                f"source kind {self.kind!r} is not a canonical record kind; expected one of {SOURCE_KINDS}"
            )
        if not _text(self.ref):
            raise InvalidSourceRefError("source ref must be the canonical record's own non-empty id")
        if self.locator is None:
            object.__setattr__(self, "locator", "")
        elif not isinstance(self.locator, str):
            raise InvalidSourceRefError("locator must be a string when present")


@dataclass(frozen=True)
class Provenance:
    """Where an entry came from, when, and the records that support it."""

    origin: str
    recorded_by: str
    recorded_at: str
    sourceRefs: Tuple[SourceRef, ...]

    def __post_init__(self) -> None:
        if not _text(self.origin):
            raise InvalidProvenanceError("origin must name where the entry came from")
        if not _text(self.recorded_by):
            raise InvalidProvenanceError("recorded_by must name who recorded the entry")
        if not _iso_timestamp(self.recorded_at):
            raise InvalidProvenanceError("recorded_at must be an ISO-8601 timestamp")
        refs = tuple(self.sourceRefs or ())
        if not refs:
            raise MissingSourceRefError(
                "provenance must carry at least one sourceRef; a summary with no way back is not a Biography entry"
            )
        for ref in refs:
            if not isinstance(ref, SourceRef):
                raise InvalidProvenanceError("sourceRefs must contain only SourceRef values")
        object.__setattr__(self, "sourceRefs", refs)


@dataclass(frozen=True)
class Evidence:
    """One piece of real backing for a first-person claim, itself traceable."""

    kind: str
    sourceRef: SourceRef
    detail: str = ""

    def __post_init__(self) -> None:
        if self.kind == EVIDENCE_AI_WORLD_EXPERIENCE:
            raise UnsupportedEvidenceKindError(
                "ai_world_experience is KB4: no AI World experience exists yet, so it cannot back a claim"
            )
        if self.kind not in SELF_EVIDENCE_KINDS:
            raise InvalidEvidenceKindError(
                f"evidence kind {self.kind!r} is not backed by a canonical record; expected one of {SELF_EVIDENCE_KINDS}"
            )
        if not isinstance(self.sourceRef, SourceRef):
            raise InvalidEvidenceKindError("evidence must point at a canonical record via SourceRef")
        if self.detail is None:
            object.__setattr__(self, "detail", "")
        elif not isinstance(self.detail, str):
            raise InvalidEvidenceKindError("evidence detail must be a string when present")


@dataclass(frozen=True)
class BiographyEntry:
    """One distilled, traceable statement: its subject says whose, its kind says which type."""

    entry_id: str
    subject: str
    kind: str
    statement: str
    provenance: Provenance
    evidence: Tuple[Evidence, ...] = ()
    policy: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _text(self.entry_id):
            raise InvalidBiographyEntryError("entry_id must be a stable, non-empty id")
        if self.subject not in SUBJECTS:
            raise InvalidSubjectError(
                f"subject {self.subject!r} is not a Biography subject; expected one of {SUBJECTS}"
            )
        if self.kind not in BIOGRAPHY_KINDS:
            raise InvalidKindError(
                f"kind {self.kind!r} is not a memory kind; expected one of {BIOGRAPHY_KINDS}"
            )
        if not _text(self.statement):
            raise InvalidBiographyEntryError("statement must be the entry's distilled claim")
        if not isinstance(self.provenance, Provenance):
            raise InvalidBiographyEntryError("provenance must be a Provenance value")

        items = tuple(self.evidence or ())
        for item in items:
            if not isinstance(item, Evidence):
                raise InvalidBiographyEntryError("evidence must contain only Evidence values")
        if self.subject == SUBJECT_YEQINGXU and not items:
            raise MissingEvidenceError(
                "subject=yeqingxu requires execution / tool receipt / world event evidence; "
                "without it there is no first-person experience to record"
            )
        object.__setattr__(self, "evidence", items)

        if self.policy is None:
            object.__setattr__(self, "policy", {})
        elif isinstance(self.policy, Mapping):
            # Opaque by design: sensitive-memory handling and Shared Event
            # granularity are decided by a later policy layer, not by this schema.
            object.__setattr__(self, "policy", dict(self.policy))
        else:
            raise InvalidBiographyEntryError("policy must be a mapping (it is left to the policy layer)")


# ── serialization ───────────────────────────────────────────────────────────

def _dump_source_ref(ref: SourceRef) -> dict:
    return {"kind": ref.kind, "ref": ref.ref, "locator": ref.locator}


def _dump_evidence(item: Evidence) -> dict:
    return {"kind": item.kind, "sourceRef": _dump_source_ref(item.sourceRef), "detail": item.detail}


def serialize_entry(entry: BiographyEntry) -> dict:
    """Entry → JSON-ready dict.  Pointers stay pointers; nothing is copied from canon."""
    if not isinstance(entry, BiographyEntry):
        raise InvalidBiographyEntryError("serialize_entry expects a BiographyEntry")
    return {
        "schema": SCHEMA_ID,
        "entry_id": entry.entry_id,
        "subject": entry.subject,
        "kind": entry.kind,
        "statement": entry.statement,
        "provenance": {
            "origin": entry.provenance.origin,
            "recorded_by": entry.provenance.recorded_by,
            "recorded_at": entry.provenance.recorded_at,
            "sourceRefs": [_dump_source_ref(ref) for ref in entry.provenance.sourceRefs],
        },
        "evidence": [_dump_evidence(item) for item in entry.evidence],
        "policy": dict(entry.policy),
    }


def _load_source_ref(data: Any) -> SourceRef:
    if not isinstance(data, Mapping):
        raise InvalidBiographyEntryError("sourceRef must be a mapping")
    unknown = set(data) - set(SOURCE_REF_FIELDS)
    if unknown:
        raise InvalidBiographyEntryError(f"unknown sourceRef fields: {sorted(unknown)}")
    try:
        return SourceRef(kind=data["kind"], ref=data["ref"], locator=data.get("locator", ""))
    except KeyError as exc:
        raise InvalidBiographyEntryError(f"sourceRef is missing {exc}") from exc


def _load_evidence(data: Any) -> Evidence:
    if not isinstance(data, Mapping):
        raise InvalidBiographyEntryError("evidence item must be a mapping")
    unknown = set(data) - set(EVIDENCE_FIELDS)
    if unknown:
        raise InvalidBiographyEntryError(f"unknown evidence fields: {sorted(unknown)}")
    try:
        return Evidence(
            kind=data["kind"],
            sourceRef=_load_source_ref(data["sourceRef"]),
            detail=data.get("detail", ""),
        )
    except KeyError as exc:
        raise InvalidBiographyEntryError(f"evidence is missing {exc}") from exc


def _load_provenance(data: Any) -> Provenance:
    if not isinstance(data, Mapping):
        raise InvalidBiographyEntryError("provenance must be a mapping")
    unknown = set(data) - set(PROVENANCE_FIELDS)
    if unknown:
        raise InvalidBiographyEntryError(f"unknown provenance fields: {sorted(unknown)}")
    refs = data.get("sourceRefs")
    if refs is None:
        raise InvalidBiographyEntryError("provenance is missing sourceRefs")
    if not isinstance(refs, (list, tuple)):
        raise InvalidBiographyEntryError("sourceRefs must be a list")
    try:
        return Provenance(
            origin=data["origin"],
            recorded_by=data["recorded_by"],
            recorded_at=data["recorded_at"],
            sourceRefs=tuple(_load_source_ref(ref) for ref in refs),
        )
    except KeyError as exc:
        raise InvalidBiographyEntryError(f"provenance is missing {exc}") from exc


def deserialize_entry(data: Any) -> BiographyEntry:
    """JSON-ready dict → Entry, with the same validation as direct construction."""
    if not isinstance(data, Mapping):
        raise InvalidBiographyEntryError("a serialized Biography entry must be a mapping")
    allowed = {"schema"} | set(ENTRY_FIELDS)
    unknown = set(data) - allowed
    if unknown:
        raise InvalidBiographyEntryError(f"unknown entry fields: {sorted(unknown)}")
    schema = data.get("schema")
    if schema is not None and schema != SCHEMA_ID:
        raise InvalidBiographyEntryError(f"unsupported schema {schema!r}; this contract is {SCHEMA_ID}")
    missing = [name for name in ("entry_id", "subject", "kind", "statement", "provenance") if name not in data]
    if missing:
        raise InvalidBiographyEntryError(f"serialized entry is missing required fields: {missing}")

    evidence = data.get("evidence", [])
    if not isinstance(evidence, (list, tuple)):
        raise InvalidBiographyEntryError("evidence must be a list")
    return BiographyEntry(
        entry_id=data["entry_id"],
        subject=data["subject"],
        kind=data["kind"],
        statement=data["statement"],
        provenance=_load_provenance(data["provenance"]),
        evidence=tuple(_load_evidence(item) for item in evidence),
        policy=data.get("policy", {}),
    )
