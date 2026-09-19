"""KB3-A1 RED contract skeleton.

These tests intentionally fail on the pre-Gate baseline because the public contract
has not been implemented yet. They must remain offline and must not call a provider.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _contract():
    from agent.budget_gate import BudgetDecision, BudgetLedger, BudgetPolicy, RatePolicy

    return BudgetDecision, BudgetLedger, BudgetPolicy, RatePolicy


def _policy(*, max_attempts=2, window_seconds=60, **overrides):
    _, _, BudgetPolicy, RatePolicy = _contract()
    values = {
        "work": 100,
        "learning": 100,
        "life_exploration": 100,
        "social": 100,
        "repair": 100,
    }
    values.update(overrides)
    return BudgetPolicy.from_mapping(
        values,
        rate=RatePolicy(max_attempts=max_attempts, window_seconds=window_seconds),
    )


def _ledger():
    _, BudgetLedger, _, _ = _contract()
    return BudgetLedger.in_memory()


def test_budget_exhaustion_is_structured():
    BudgetDecision, _, _, _ = _contract()
    gate = _ledger().gate(policy=_policy(work=0))
    decision = gate.admit(category="work", units=1, action_id="turn-1")
    assert decision == BudgetDecision.denied("budget_exhausted")


def test_settled_usage_accumulates_toward_positive_budget():
    BudgetDecision, _, _, _ = _contract()
    ledger = _ledger()
    gate = ledger.gate(policy=_policy(work=2, max_attempts=10))
    first = gate.admit(category="work", units=1, action_id="turn-1")
    assert first.allowed
    ledger.settle(first.reservation_id, outcome="success", actual_units=1)

    second = gate.admit(category="work", units=1, action_id="turn-2")
    assert second.allowed
    ledger.settle(second.reservation_id, outcome="success", actual_units=1)

    assert gate.admit(
        category="work", units=1, action_id="turn-3"
    ) == BudgetDecision.denied("budget_exhausted")


def test_rate_gate_denies_then_recovers_after_window():
    BudgetDecision, _, _, _ = _contract()
    ledger = _ledger()
    gate = ledger.gate(policy=_policy())
    assert gate.admit(category="work", units=1, action_id="a").allowed
    assert gate.admit(category="work", units=1, action_id="b").allowed
    assert gate.admit(category="work", units=1, action_id="c") == BudgetDecision.denied("rate_limited")
    ledger.advance_clock(61)
    assert gate.admit(category="work", units=1, action_id="d").allowed


def test_budget_categories_are_isolated_and_repair_is_reserved():
    ledger = _ledger()
    gate = ledger.gate(policy=_policy(work=0, learning=0, repair=50))
    assert gate.admit(category="work", units=1, action_id="w").reason == "budget_exhausted"
    assert gate.admit(category="learning", units=1, action_id="l").reason == "budget_exhausted"
    assert gate.admit(category="repair", units=1, action_id="r").allowed


def test_unknown_reconciliation_is_idempotent_and_keeps_units_accounted():
    ledger = _ledger()
    gate = ledger.gate(policy=_policy(work=2))
    first = gate.admit(category="work", units=1, action_id="turn-1")
    assert first.allowed
    ledger.settle(first.reservation_id, outcome="unknown", actual_units=1)
    settled = ledger.reconcile(first.reservation_id, outcome="success", actual_units=1)
    repeated = ledger.reconcile(first.reservation_id, outcome="success", actual_units=1)
    assert repeated == settled
    assert ledger.outstanding(category="work") == 0


def test_unknown_action_is_retry_blocked_by_same_idempotency_key():
    BudgetDecision, _, _, _ = _contract()
    ledger = _ledger()
    gate = ledger.gate(policy=_policy())
    first = gate.admit(category="work", units=1, action_id="turn-1")
    ledger.settle(first.reservation_id, outcome="unknown", actual_units=1)

    retry = gate.admit(category="work", units=1, action_id="turn-1")

    assert retry == BudgetDecision.denied("retry_blocked")


def test_unknown_usage_survives_reopen_from_dedicated_store(tmp_path):
    _, BudgetLedger, _, _ = _contract()
    ledger_path = tmp_path / "budget-ledger.sqlite3"
    ledger = BudgetLedger.open(ledger_path)
    decision = ledger.gate(policy=_policy()).admit(
        category="work", units=1, action_id="turn-1"
    )
    ledger.settle(decision.reservation_id, outcome="unknown", actual_units=1)

    restored = BudgetLedger.open(ledger_path)

    assert restored is not ledger
    assert restored.outstanding(category="work") == 1


def test_unknown_usage_survives_fresh_process_reopen(tmp_path):
    ledger_path = tmp_path / "budget-ledger.sqlite3"
    repo_root = Path(__file__).resolve().parents[2]
    writer = """
import sys
from agent.budget_gate import BudgetLedger, BudgetPolicy, RatePolicy

path = sys.argv[1]
policy = BudgetPolicy.from_mapping(
    {
        "work": 100,
        "learning": 100,
        "life_exploration": 100,
        "social": 100,
        "repair": 100,
    },
    rate=RatePolicy(max_attempts=10, window_seconds=60),
)
ledger = BudgetLedger.open(path)
decision = ledger.gate(policy=policy).admit(
    category="work", units=1, action_id="turn-process"
)
ledger.settle(decision.reservation_id, outcome="unknown", actual_units=1)
"""
    reader = """
import sys
from agent.budget_gate import BudgetLedger

ledger = BudgetLedger.open(sys.argv[1])
print(ledger.outstanding(category="work"))
"""
    subprocess.run(
        [sys.executable, "-c", writer, str(ledger_path)],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    restored = subprocess.run(
        [sys.executable, "-c", reader, str(ledger_path)],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert restored.stdout.strip() == "1"


def test_conflicting_reconciliation_replay_fails_closed_without_mutation():
    ledger = _ledger()
    gate = ledger.gate(policy=_policy(work=10, max_attempts=10))
    first = gate.admit(category="work", units=1, action_id="turn-conflict")
    assert first.allowed
    ledger.settle(first.reservation_id, outcome="unknown", actual_units=1)
    settled = ledger.reconcile(
        first.reservation_id, outcome="success", actual_units=1
    )

    with pytest.raises(ValueError, match="reconciliation_conflict"):
        ledger.reconcile(
            first.reservation_id, outcome="failure", actual_units=2
        )

    assert ledger.reconcile(
        first.reservation_id, outcome="success", actual_units=1
    ) == settled
    assert ledger.outstanding(category="work") == 0


def test_audit_query_covers_successful_reservation_lifecycle():
    ledger = _ledger()
    gate = ledger.gate(policy=_policy(work=10, max_attempts=10))
    first = gate.admit(category="work", units=1, action_id="turn-lifecycle")
    assert first.allowed
    ledger.settle(first.reservation_id, outcome="unknown", actual_units=1)
    ledger.reconcile(first.reservation_id, outcome="success", actual_units=1)

    records = ledger.audit_records(reservation_id=first.reservation_id)
    events = {record.get("event") for record in records}

    assert {"admit", "reserve", "settle", "reconcile"} <= events
    for record in records:
        if record.get("event") in {"admit", "reserve", "settle", "reconcile"}:
            assert record.get("action_id") == "turn-lifecycle"
            assert record.get("reservation_id") == first.reservation_id
            assert record.get("category") == "work"


def test_audit_query_exposes_required_denial_fields():
    ledger = _ledger()
    ledger.gate(policy=_policy(work=0)).admit(
        category="work", units=1, action_id="turn-audit"
    )

    records = ledger.audit_records(action_id="turn-audit")

    assert records
    latest = records[-1]
    assert {
        "event",
        "action_id",
        "reservation_id",
        "category",
        "units",
        "outcome",
        "timestamp",
        "reason",
    } <= latest.keys()
    assert latest["action_id"] == "turn-audit"
    assert latest["category"] == "work"
    assert latest["units"] == 1
    assert latest["reason"] == "budget_exhausted"


def test_invalid_policy_fails_closed_without_model_explanation():
    _, _, _, _ = _contract()
    decision = _ledger().gate(policy=None).admit(category="work", units=1, action_id="bad")
    assert decision.reason == "invalid_policy"
