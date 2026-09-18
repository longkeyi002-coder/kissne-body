"""KB2-C — the Mutation Gate: what should happen to canonical memory.

The gate takes a candidate claim, the current canonical memory state, the
candidate's own ``source_refs`` / ``evidence``, and an **opaque** policy, and
returns a decision.  It decides *only* on evidence and semantic relations:

* it is **not** a scoring function — the decision carries no confidence,
  likelihood or score, and ``policy`` is echoed back untouched, never read as a
  threshold;
* it never writes: no Provider, no SQLite, no Recall, no vector index, and no
  mutation of the canonical state it was handed (see
  ``详细规划/11_Hermes改造与分阶段交付.md`` §0.3.12).

Decisions are one of ``ADD`` / ``UPDATE`` / ``SUPERSEDE`` / ``CONTRADICT`` /
``ARCHIVE`` / ``NO_CHANGE`` / ``REJECT``.  ``REJECT`` is a **gate result**, not a
:class:`~agent.memory_claim.Claim` status — the four frozen statuses live in
:mod:`agent.memory_mutation_semantics` and stay untouched.

``DELETE`` is deliberately *not* here: it is outside this ticket's scope, and a
claim that stops being canonical is ``ARCHIVE``d, never deleted — its own
content and provenance stay where they are.

Six conditions this gate will not soften (each has a counterexample test):

1. replaying the same ``sourceRef`` does not re-strengthen a claim (``NO_CHANGE``);
2. ``INFERRED`` cannot be upgraded by repetition (``REJECT``/``epistemic_promotion``);
3. a hypothetical does not become history without new, real evidence
   (``REJECT``/``hypothetical_history``);
4. realms do not supersede each other (``REJECT``/``cross_realm_supersede``);
5. thin evidence prefers ``NO_CHANGE`` over forcing a change;
6. every decision keeps a way back to evidence and provenance.

``UPDATE`` only ever *supplements* the same canonical claim — it never rewrites
what used to be true.  A fact that used to hold and then changed is
``SUPERSEDE``; a fact that was wrong is ``CONTRADICT``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from agent.memory_claim import Claim
from agent.memory_mutation_semantics import STATUS_ARCHIVED
from agent.memory_vocabulary import (
    EPISTEMIC_AGENT_EXPERIENCED,
    EPISTEMIC_HYPOTHETICAL,
    EPISTEMIC_INFERRED,
    EPISTEMIC_OBSERVED,
    EPISTEMIC_USER_DECLARED,
    KIND_EVENT,
    Evidence,
    Provenance,
    SourceRef,
)

GATE_SCHEMA_ID = "kissne.mutation_gate/1"

ACTION_ADD = "ADD"
ACTION_UPDATE = "UPDATE"
ACTION_SUPERSEDE = "SUPERSEDE"
ACTION_CONTRADICT = "CONTRADICT"
ACTION_ARCHIVE = "ARCHIVE"
ACTION_NO_CHANGE = "NO_CHANGE"
ACTION_REJECT = "REJECT"

MUTATION_ACTIONS = (
    ACTION_ADD,
    ACTION_UPDATE,
    ACTION_SUPERSEDE,
    ACTION_CONTRADICT,
    ACTION_ARCHIVE,
    ACTION_NO_CHANGE,
)
GATE_ACTIONS = MUTATION_ACTIONS + (ACTION_REJECT,)

#: Actions that move canonical memory.  ``NO_CHANGE`` and ``REJECT`` do not.
STATE_CHANGING_ACTIONS = (
    ACTION_ADD,
    ACTION_UPDATE,
    ACTION_SUPERSEDE,
    ACTION_CONTRADICT,
    ACTION_ARCHIVE,
)
#: Actions that re-interpret an existing claim, so they need real evidence.
BACKED_ACTIONS = (ACTION_SUPERSEDE, ACTION_CONTRADICT)

REASON_SAME_SOURCE_REPLAY = "same_source_replay"
REASON_NO_NEW_EVIDENCE = "no_new_evidence"
REASON_UNKNOWN_TARGET = "unknown_target"
REASON_AMBIGUOUS_TARGET = "ambiguous_target"
REASON_CROSS_REALM_SUPERSEDE = "cross_realm_supersede"
REASON_EPISTEMIC_PROMOTION = "epistemic_promotion"
REASON_HYPOTHETICAL_HISTORY = "hypothetical_history"
REASON_NO_EVIDENCE = "no_evidence"
REASON_HISTORY_REWRITE = "history_rewrite"
REASON_BACKDATED_SUPERSEDE = "backdated_supersede"

#: How a memory can be known, ordered **only** to detect an upgrade attempt.
#: This is a semantic ladder, never a confidence value: nothing here measures
#: how likely a claim is, only whether the candidate claims to know it better.
EPISTEMIC_ORDER: Dict[str, int] = {
    EPISTEMIC_HYPOTHETICAL: 1,
    EPISTEMIC_INFERRED: 2,
    EPISTEMIC_USER_DECLARED: 3,
    EPISTEMIC_OBSERVED: 3,
    EPISTEMIC_AGENT_EXPERIENCED: 3,
}


class MutationGateError(ValueError):
    """Base class for every gate failure."""


class InvalidGateInputError(MutationGateError):
    """The gate was handed something that is not a claim / claim state."""


@dataclass(frozen=True)
class GateDecision:
    """What the gate decided, and the evidence that carries the decision.

    There is no score field of any kind here — a decision is either backed by
    evidence and relations or it is refused; it is never graded.
    """

    action: str
    target_claim_id: Optional[str]
    targets: Tuple[str, ...]
    preserved_claim_ids: Tuple[str, ...]
    reason_code: Optional[str]
    reason: str
    evidence: Tuple[Evidence, ...]
    source_refs: Tuple[SourceRef, ...]
    policy: Mapping[str, Any]
    recorded_at: str
    schema: str = GATE_SCHEMA_ID

    @property
    def is_change(self) -> bool:
        """True when canonical memory would actually move."""
        return self.action in STATE_CHANGING_ACTIONS

    @property
    def is_refusal(self) -> bool:
        """True when the gate refused to act at all."""
        return self.action == ACTION_REJECT


def _moment(value: Optional[str], *, field: str) -> datetime:
    if not value:
        raise InvalidGateInputError(f"{field} must be an ISO-8601 timestamp on a validated claim")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - claims are validated upstream
        raise InvalidGateInputError(f"{field} must be an ISO-8601 timestamp") from exc


def _rank(epistemic: Optional[str]) -> int:
    """Ordering only — 0 is the defensive floor for a value Claim already checked."""
    return EPISTEMIC_ORDER.get(epistemic or "", 0)


def _unique(items: Iterable[str]) -> Tuple[str, ...]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


def decide_mutation(
    *,
    candidate: Claim,
    canonical_state: Sequence[Claim] = (),
    policy: Optional[Mapping[str, Any]] = None,
    recorded_at: Optional[str] = None,
) -> GateDecision:
    """Decide what should happen to canonical memory for ``candidate``.

    Reads only: the state passed in is never touched, and the returned decision
    carries the evidence and source refs that justify it.
    """
    if not isinstance(candidate, Claim):
        raise InvalidGateInputError("decide_mutation expects a Claim")

    state = tuple(canonical_state or ())
    index: Dict[str, Claim] = {}
    for item in state:
        if not isinstance(item, Claim):
            raise InvalidGateInputError("canonical_state must contain only Claims")
        if item.claim_id in index:
            raise MutationGateError(
                f"canonical_state carries {item.claim_id!r} twice; a canonical state has one record per claim"
            )
        index[item.claim_id] = item

    evidence = tuple(candidate.evidence)
    refs = tuple(candidate.source_refs)
    supersedes = tuple(candidate.supersedes)
    contradicts = tuple(candidate.contradicts)
    opaque_policy = dict(policy or {})
    stamp = recorded_at or candidate.recorded_at or ""

    def decision(
        action: str,
        *,
        target: Optional[str] = None,
        targets: Tuple[str, ...] = (),
        preserved: Tuple[str, ...] = (),
        reason_code: Optional[str] = None,
        reason: str = "",
    ) -> GateDecision:
        return GateDecision(
            action=action,
            target_claim_id=target,
            targets=targets,
            preserved_claim_ids=preserved,
            reason_code=reason_code,
            reason=reason,
            evidence=evidence,
            source_refs=refs,
            policy=opaque_policy,
            recorded_at=stamp,
            schema=GATE_SCHEMA_ID,
        )

    def single(ids: Tuple[str, ...]) -> Optional[str]:
        return ids[0] if len(ids) == 1 else None

    # A relation can only point at a claim that exists.
    relation_ids = supersedes + contradicts
    unknown = [claim_id for claim_id in relation_ids if claim_id not in index]
    if unknown:
        return decision(
            ACTION_REJECT,
            reason_code=REASON_UNKNOWN_TARGET,
            reason=f"relation target(s) not in canonical memory: {sorted(unknown)}",
        )

    current = index.get(candidate.claim_id)
    same_fact = tuple(
        item
        for item in state
        if item.claim_id != candidate.claim_id
        and item.subject == candidate.subject
        and item.kind == candidate.kind
        and item.realm == candidate.realm
        and item.statement == candidate.statement
    )
    if not relation_ids and current is None and len(same_fact) > 1:
        return decision(
            ACTION_REJECT,
            reason_code=REASON_AMBIGUOUS_TARGET,
            reason=(
                "several canonical claims already carry this exact fact; "
                "refusing to guess which one the candidate is about"
            ),
        )

    touched = tuple(index[claim_id] for claim_id in relation_ids) + tuple(
        [current] if current is not None else []
    ) + same_fact
    seen_refs = {ref for claim in touched for ref in claim.source_refs}
    new_refs = tuple(ref for ref in refs if ref not in seen_refs)

    # 3 — a hypothetical does not become history on the same evidence.
    hypotheticals = [claim for claim in touched if claim.epistemic == EPISTEMIC_HYPOTHETICAL]
    if hypotheticals and candidate.epistemic != EPISTEMIC_HYPOTHETICAL and candidate.kind == KIND_EVENT:
        if not new_refs:
            return decision(
                ACTION_REJECT,
                reason_code=REASON_HYPOTHETICAL_HISTORY,
                reason=(
                    "a HYPOTHETICAL memory cannot become an event that happened on the same "
                    "source refs; repetition is not evidence"
                ),
            )

    # 2 — INFERRED cannot be upgraded by repetition.
    for claim in touched:
        if (
            claim.statement == candidate.statement
            and claim.epistemic != candidate.epistemic
            and _rank(candidate.epistemic) > _rank(claim.epistemic)
            and not new_refs
        ):
            return decision(
                ACTION_REJECT,
                reason_code=REASON_EPISTEMIC_PROMOTION,
                reason=(
                    f"{candidate.epistemic} cannot be claimed over {claim.claim_id}'s "
                    f"{claim.epistemic} on the same source refs: repetition is not evidence"
                ),
            )

    # 4 — worlds do not supersede each other.
    cross_realm = [claim_id for claim_id in supersedes if index[claim_id].realm != candidate.realm]
    if cross_realm:
        return decision(
            ACTION_REJECT,
            reason_code=REASON_CROSS_REALM_SUPERSEDE,
            reason=(
                f"supersede does not cross realms: {sorted(cross_realm)} live in another world "
                f"than this {candidate.realm} claim"
            ),
        )

    # UPDATE supplements; it never rewrites what used to be true.
    if current is not None and not relation_ids:
        rewritten = (
            candidate.statement != current.statement
            or candidate.occurred_at != current.occurred_at
            or candidate.timezone != current.timezone
            or candidate.valid_from != current.valid_from
            or candidate.valid_to != current.valid_to
        )
        if rewritten:
            return decision(
                ACTION_REJECT,
                reason_code=REASON_HISTORY_REWRITE,
                reason=(
                    f"UPDATE cannot rewrite {current.claim_id}: what used to be true stays on the "
                    "record. A fact that changed is SUPERSEDE; a fact that was wrong is CONTRADICT"
                ),
            )

    # A superseding claim cannot be backdated before what it replaces.
    for claim_id in supersedes:
        if _moment(candidate.occurred_at, field="occurred_at") < _moment(
            index[claim_id].occurred_at, field="occurred_at"
        ):
            return decision(
                ACTION_REJECT,
                reason_code=REASON_BACKDATED_SUPERSEDE,
                reason=(
                    f"this claim is dated before {claim_id}, which it claims to replace; "
                    "history does not run backwards"
                ),
            )

    # 5 — thin evidence prefers NO_CHANGE over forcing a change.
    if relation_ids and not new_refs:
        return decision(
            ACTION_NO_CHANGE,
            target=single(relation_ids),
            targets=relation_ids,
            reason_code=REASON_NO_NEW_EVIDENCE,
            reason="no source ref the canonical state has not already seen; nothing to change yet",
        )

    # 6 — a claim that re-interprets memory needs real evidence behind it.
    if supersedes or contradicts:
        action = ACTION_SUPERSEDE if supersedes else ACTION_CONTRADICT
        if action in BACKED_ACTIONS and not evidence:
            return decision(
                ACTION_REJECT,
                target=single(relation_ids),
                targets=relation_ids,
                reason_code=REASON_NO_EVIDENCE,
                reason=f"{action} re-interprets existing memory and needs evidence, not just a pointer",
            )
        return decision(
            action,
            target=single(relation_ids),
            targets=relation_ids,
            preserved=relation_ids,
            reason=(
                f"{action} {sorted(relation_ids)}; the older record keeps its own content and provenance"
            ),
        )

    # 1 — replaying a source ref does not re-strengthen a claim.
    if not new_refs and candidate.status != STATUS_ARCHIVED and (current is not None or same_fact):
        known = current.claim_id if current is not None else same_fact[0].claim_id
        return decision(
            ACTION_NO_CHANGE,
            target=known,
            targets=(known,),
            reason_code=REASON_SAME_SOURCE_REPLAY,
            reason=(
                f"{known} already rests on these source refs; replaying them adds no evidence "
                "and strengthens nothing"
            ),
        )

    if candidate.status == STATUS_ARCHIVED and current is not None:
        return decision(
            ACTION_ARCHIVE,
            target=current.claim_id,
            targets=(current.claim_id,),
            preserved=(current.claim_id,),
            reason=(
                f"archive {current.claim_id}: it stops being canonical but is kept, never deleted"
            ),
        )

    if current is not None:
        return decision(
            ACTION_UPDATE,
            target=current.claim_id,
            targets=(current.claim_id,),
            preserved=(current.claim_id,),
            reason=(
                f"supplement {current.claim_id} with new source refs; its own content and time stay as they are"
            ),
        )

    if same_fact:
        target = same_fact[0].claim_id
        return decision(
            ACTION_UPDATE,
            target=target,
            targets=(target,),
            preserved=(target,),
            reason=(
                f"the same fact is already canonical as {target}; new evidence supplements it "
                "instead of adding a second copy"
            ),
        )

    return decision(
        ACTION_ADD,
        targets=_unique((candidate.claim_id,)),
        reason="no canonical claim covers this; it is new memory",
    )


def decision_provenance(decision: GateDecision) -> Provenance:
    """The provenance a Mutation decision must carry: who decided, when, from what."""
    if not isinstance(decision, GateDecision):
        raise InvalidGateInputError("decision_provenance expects a GateDecision")
    return Provenance(
        origin="mutation_gate",
        recorded_by="kissne.mutation_gate",
        recorded_at=decision.recorded_at,
        sourceRefs=decision.source_refs,
    )
