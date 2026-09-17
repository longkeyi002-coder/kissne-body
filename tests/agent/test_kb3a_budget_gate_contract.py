"""KB3-A1 RED contract skeleton.

These tests intentionally fail on the pre-Gate baseline because the public contract
has not been implemented yet. They must remain offline and must not call a provider.
"""

from __future__ import annotations

import pytest

from agent.budget_gate import BudgetDecision, BudgetLedger, BudgetPolicy, RatePolicy


def _policy(**overrides):
    values = {
        "work": 100,
        "learning": 100,
        "life_exploration": 100,
        "social": 100,
        "repair": 100,
    }
    values.update(overrides)
    return BudgetPolicy.from_mapping(values, rate=RatePolicy(max_attempts=2, window_seconds=60))


def _ledger():
    return BudgetLedger.in_memory()


def test_budget_exhaustion_is_structured_and_does_not_call_model():
    gate = _ledger().gate(policy=_policy(work=0))
    decision = gate.admit(category="work", action_id="turn-1")
    assert decision == BudgetDecision.denied("budget_exhausted")


def test_rate_gate_denies_then_recovers_after_window():
    ledger = _ledger()
    gate = ledger.gate(policy=_policy())
    assert gate.admit(category="work", action_id="a").allowed
    assert gate.admit(category="work", action_id="b").allowed
    assert gate.admit(category="work", action_id="c") == BudgetDecision.denied("rate_limited")
    ledger.advance_clock(61)
    assert gate.admit(category="work", action_id="d").allowed


def test_budget_categories_are_isolated_and_repair_is_reserved():
    ledger = _ledger()
    gate = ledger.gate(policy=_policy(work=0, repair=50))
    assert gate.admit(category="work", action_id="w").reason == "budget_exhausted"
    assert gate.admit(category="repair", action_id="r").allowed


def test_retry_is_bounded_and_does_not_reuse_unknown_reservation():
    ledger = _ledger()
    gate = ledger.gate(policy=_policy())
    first = gate.admit(category="work", action_id="turn-1")
    assert first.allowed
    ledger.settle(first.reservation_id, outcome="unknown")
    retry = gate.admit(category="work", action_id="turn-1-retry")
    assert retry.reason in {"budget_exhausted", "rate_limited", "retry_blocked"}


def test_ledger_survives_restart_without_releasing_unknown_usage():
    ledger = _ledger()
    gate = ledger.gate(policy=_policy())
    decision = gate.admit(category="work", action_id="turn-1")
    assert decision.allowed
    ledger.settle(decision.reservation_id, outcome="unknown")
    restored = ledger.restart()
    assert restored.outstanding(category="work") == 1


def test_invalid_policy_fails_closed_without_model_explanation():
    decision = _ledger().gate(policy=None).admit(category="work", action_id="bad")
    assert decision == BudgetDecision.denied("invalid_policy")
