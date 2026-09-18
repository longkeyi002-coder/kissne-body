"""The single memory vocabulary shared by every Kissne memory contract.

Hardening follow-up to ``KB2-A-CLAIM-CONTRACT``.  The claim contract and the
Biography contract need the same four axes and the same pointer/evidence types;
defining them once here means a rule is written once, a value is spelled once,
and neither contract has to import the other.

Contents:

* **Axes** — ``subject`` (whose), ``kind`` (what type), ``realm`` (which world),
  ``epistemic`` (how known).  Values are canonically spelled here and nowhere
  else; the tuples are exported as objects, so ``X.KINDS is KINDS`` holds
  wherever they are re-exported.
* **Product-language aliases** — ``user_memory`` / ``self_memory`` /
  ``shared_memory`` / ``project_memory`` map onto ``subject`` values.  They are
  a boundary translation only (``resolve_subject``); no canonical record stores
  them.
* **Pointer vocabulary** — ``SourceRef`` / ``Evidence`` / ``Provenance``: what
  a memory points at in the canonical record (Unified History), never a copy of
  it.
* **Consistency rules both contracts call** — ``check_consistency`` refuses a
  hypothetical dressed as an event, and a first-person experience with nothing
  behind it.  One implementation, two callers.

This module imports nothing from the contracts; the dependency runs one way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Tuple

# ── 1. subject: whose fact / experience / state this is ─────────────────────

SUBJECT_USER = "user"
SUBJECT_YEQINGXU = "yeqingxu"
SUBJECT_SHARED = "shared"
SUBJECT_PROJECT = "project"

SUBJECTS = (SUBJECT_USER, SUBJECT_YEQINGXU, SUBJECT_SHARED, SUBJECT_PROJECT)

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

KINDS = (KIND_FACT, KIND_EVENT, KIND_STATE, KIND_PREFERENCE, KIND_INTENTION, KIND_IMPRESSION, KIND_EPISODE)

# ── 3. realm: which world the memory belongs to ─────────────────────────────

REALM_EARTH = "EARTH"
REALM_AI_WORLD = "AI_WORLD"
REALM_CONVERSATION = "CONVERSATION"
REALM_SYSTEM = "SYSTEM"

REALMS = (REALM_EARTH, REALM_AI_WORLD, REALM_CONVERSATION, REALM_SYSTEM)

# ── 4. epistemic: how the memory is known ───────────────────────────────────

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

# ── canonical record kinds a pointer may name ───────────────────────────────

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

# KB4 territory: listed so the refusal is explicit and greppable.
EVIDENCE_AI_WORLD_EXPERIENCE = "ai_world_experience"

# ── frozen field sets ───────────────────────────────────────────────────────

SOURCE_REF_FIELDS = ("kind", "ref", "locator")
EVIDENCE_FIELDS = ("kind", "sourceRef", "detail")
PROVENANCE_FIELDS = ("origin", "recorded_by", "recorded_at", "sourceRefs")


# ── errors ──────────────────────────────────────────────────────────────────

class MemoryVocabularyError(ValueError):
    """Base class for every vocabulary violation."""


class InvalidSubjectError(MemoryVocabularyError):
    """Subject is missing, or is not a canonical subject."""


class SubjectConflictError(MemoryVocabularyError):
    """A legacy ``category`` travelled next to a canonical ``subject``."""


class InvalidKindError(MemoryVocabularyError):
    """Kind is not one of the frozen memory kinds."""


class InvalidRealmError(MemoryVocabularyError):
    """Realm is missing or unknown; a memory never guesses which world it is in."""


class InvalidEpistemicError(MemoryVocabularyError):
    """Epistemic is missing or unknown, so 'how it is known' would be lost."""


class InvalidSourceRefError(MemoryVocabularyError):
    """A SourceRef is not a usable pointer at a canonical record."""


class InvalidProvenanceError(MemoryVocabularyError):
    """Provenance is missing a required, well-formed field."""


class MissingSourceRefError(InvalidProvenanceError):
    """Nothing to walk back to — the case the memory contracts exist for."""


class InvalidEvidenceKindError(MemoryVocabularyError):
    """Evidence is not backed by a canonical record, or its kind is unknown."""


class UnsupportedEvidenceKindError(InvalidEvidenceKindError):
    """A real-sounding kind this milestone cannot support yet (AI World = KB4)."""


class MissingEvidenceError(MemoryVocabularyError):
    """A first-person claim with nothing behind it."""


class HypotheticalNotAnEventError(MemoryVocabularyError):
    """A hypothetical is not an event that happened; it never becomes one here."""


# ── helpers ─────────────────────────────────────────────────────────────────

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


def resolve_subject(value: Any) -> str:
    """Boundary translation only: canonical subject, or an old product name.

    Returns the canonical subject; an unknown value is refused rather than
    guessed.  Nothing canonical ever stores the alias.
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


# ── pointer vocabulary ──────────────────────────────────────────────────────

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
class Provenance:
    """Where a memory came from, when, and the records that support it."""

    origin: str
    recorded_by: str
    recorded_at: str
    sourceRefs: Tuple[SourceRef, ...]

    def __post_init__(self) -> None:
        if not _text(self.origin):
            raise InvalidProvenanceError("origin must name where the memory came from")
        if not _text(self.recorded_by):
            raise InvalidProvenanceError("recorded_by must name who recorded the memory")
        if not _iso_timestamp(self.recorded_at):
            raise InvalidProvenanceError("recorded_at must be an ISO-8601 timestamp")
        refs = tuple(self.sourceRefs or ())
        if not refs:
            raise MissingSourceRefError(
                "provenance must carry at least one sourceRef; a summary with no way back is not a memory"
            )
        for ref in refs:
            if not isinstance(ref, SourceRef):
                raise InvalidProvenanceError("sourceRefs must contain only SourceRef values")
        object.__setattr__(self, "sourceRefs", refs)


# ── the rules both contracts call ───────────────────────────────────────────

def requires_real_evidence(subject: Any, epistemic: Any) -> bool:
    """A first-person experience (`subject=yeqingxu`) needs something real behind it."""
    return subject == SUBJECT_YEQINGXU and epistemic == EPISTEMIC_AGENT_EXPERIENCED


def is_hypothetical_event(kind: Any, epistemic: Any) -> bool:
    """A hypothetical is a thought about a possible world, not a record that something happened."""
    return epistemic == EPISTEMIC_HYPOTHETICAL and kind == KIND_EVENT


def check_consistency(
    *,
    subject: Any,
    kind: Any,
    epistemic: Any,
    evidence: Any = (),
) -> None:
    """Refuse the two combinations the memory contracts must never accept.

    Called by both contracts, so the rule lives in one place: saying something
    in conversation does not make it history, and inference does not become
    observation.
    """
    if is_hypothetical_event(kind, epistemic):
        raise HypotheticalNotAnEventError(
            "a HYPOTHETICAL memory cannot be an event that happened; "
            "saying it in conversation does not make it history"
        )
    items = tuple(evidence or ())
    if requires_real_evidence(subject, epistemic) and not items:
        raise MissingEvidenceError(
            "subject=yeqingxu with AGENT_EXPERIENCED requires execution / tool receipt / "
            "world event evidence; without it there is no first-person experience to record"
        )
