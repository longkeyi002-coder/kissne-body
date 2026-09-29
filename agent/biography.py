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
from typing import Any, Mapping, Optional, Tuple

from agent.memory_vocabulary import (
    EPISTEMIC_AGENT_EXPERIENCED,
    EPISTEMICS,
    EVIDENCE_AI_WORLD_EXPERIENCE,
    EVIDENCE_EXECUTION,
    EVIDENCE_FIELDS,
    EVIDENCE_TOOL_RECEIPT,
    EVIDENCE_WORLD_EVENT,
    KIND_EVENT,
    KINDS,
    PROVENANCE_FIELDS,
    REALMS,
    SELF_EVIDENCE_KINDS,
    SOURCE_CONVERSATION_TURN,
    SOURCE_EARTH_OBSERVATION,
    SOURCE_EVENT,
    SOURCE_KINDS,
    SOURCE_REF_FIELDS,
    SOURCE_TOOL_RECEIPT,
    SUBJECT_SHARED,
    SUBJECT_USER,
    SUBJECT_YEQINGXU,
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
    Provenance,
    SourceRef,
    UnsupportedEvidenceKindError,
    check_consistency,
)

# ── schema identity ─────────────────────────────────────────────────────────

SCHEMA_ID = "kissne.biography/1"

# ── vocabulary (one definition, in agent/memory_vocabulary) ────────────────
# The axes, the pointer vocabulary and the shared consistency rules come from
# the single vocabulary module.  Biography narrows the subject axis to its three
# subjects; it does not define a second copy of any value.  Nothing here imports
# the claim contract, and the claim contract imports nothing from here.

BIOGRAPHY_SUBJECTS = (SUBJECT_USER, SUBJECT_YEQINGXU, SUBJECT_SHARED)

# ── frozen field sets ───────────────────────────────────────────────────────

ENTRY_FIELDS = (
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
PROVENANCE_FIELDS = ("origin", "recorded_by", "recorded_at", "sourceRefs")
SOURCE_REF_FIELDS = ("kind", "ref", "locator")
EVIDENCE_FIELDS = ("kind", "sourceRef", "detail")


# ── errors ──────────────────────────────────────────────────────────────────

class BiographyError(ValueError):
    """Base class for every contract violation."""


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
class BiographyEntry:
    """One distilled, traceable statement: its subject says whose, its kind says which type."""

    entry_id: str
    subject: Optional[str] = None
    kind: Optional[str] = None
    realm: Optional[str] = None
    epistemic: Optional[str] = None
    statement: Optional[str] = None
    provenance: Optional[Provenance] = None
    evidence: Tuple[Evidence, ...] = ()
    policy: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _text(self.entry_id):
            raise InvalidBiographyEntryError("entry_id must be a stable, non-empty id")
        if self.subject not in BIOGRAPHY_SUBJECTS:
            raise InvalidSubjectError(
                f"subject {self.subject!r} is not a Biography subject; expected one of {BIOGRAPHY_SUBJECTS}"
            )
        if self.kind not in KINDS:
            raise InvalidKindError(f"kind {self.kind!r} is not a memory kind; expected one of {KINDS}")
        if self.realm not in REALMS:
            raise InvalidRealmError(
                f"realm {self.realm!r} is not a known realm; expected one of {REALMS}"
            )
        if self.epistemic not in EPISTEMICS:
            raise InvalidEpistemicError(
                f"epistemic {self.epistemic!r} is not a known epistemic value; expected one of {EPISTEMICS}"
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
        check_consistency(subject=self.subject, kind=self.kind, epistemic=self.epistemic, evidence=items)
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
    provenance = entry.provenance
    if not isinstance(provenance, Provenance):
        raise InvalidBiographyEntryError(
            "an entry without provenance has no way back and cannot be serialized"
        )
    return {
        "schema": SCHEMA_ID,
        "entry_id": entry.entry_id,
        "subject": entry.subject,
        "kind": entry.kind,
        "realm": entry.realm,
        "epistemic": entry.epistemic,
        "statement": entry.statement,
        "provenance": {
            "origin": provenance.origin,
            "recorded_by": provenance.recorded_by,
            "recorded_at": provenance.recorded_at,
            "sourceRefs": [_dump_source_ref(ref) for ref in provenance.sourceRefs],
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
    missing = [
        name
        for name in ("entry_id", "subject", "kind", "realm", "epistemic", "statement", "provenance")
        if name not in data
    ]
    if missing:
        raise InvalidBiographyEntryError(f"serialized entry is missing required fields: {missing}")

    evidence = data.get("evidence", [])
    if not isinstance(evidence, (list, tuple)):
        raise InvalidBiographyEntryError("evidence must be a list")
    return BiographyEntry(
        entry_id=data["entry_id"],
        subject=data["subject"],
        kind=data["kind"],
        realm=data["realm"],
        epistemic=data["epistemic"],
        statement=data["statement"],
        provenance=_load_provenance(data["provenance"]),
        evidence=tuple(_load_evidence(item) for item in evidence),
        policy=data.get("policy", {}),
    )
