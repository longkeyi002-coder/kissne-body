"""Minimal KB3-A1 contract scaffold.

This module only exposes the frozen contract shape. It deliberately does not
wire any model call path or provide production budget semantics yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reason: str
    reservation_id: str | None = None

    @classmethod
    def denied(cls, reason: str) -> "BudgetDecision":
        return cls(allowed=False, reason=reason)

    @classmethod
    def admitted(cls, reservation_id: str = "red-scaffold") -> "BudgetDecision":
        return cls(allowed=True, reason="allowed", reservation_id=reservation_id)


@dataclass(frozen=True)
class RatePolicy:
    max_attempts: int
    window_seconds: int


@dataclass(frozen=True)
class BudgetPolicy:
    limits: dict[str, int]
    rate: RatePolicy

    @classmethod
    def from_mapping(
        cls, values: dict[str, int], *, rate: RatePolicy
    ) -> "BudgetPolicy":
        return cls(limits=dict(values), rate=rate)


class _Gate:
    def __init__(self, ledger: "BudgetLedger", policy: BudgetPolicy | None) -> None:
        self._ledger = ledger
        self._policy = policy

    def admit(
        self, *, category: str, units: int, action_id: str
    ) -> BudgetDecision:
        del category, units, action_id
        if self._policy is None:
            return BudgetDecision.denied("invalid_policy")
        # Contract-only scaffold: A2 implementation must replace this.
        return BudgetDecision.denied("not_implemented")


class BudgetLedger:
    @classmethod
    def in_memory(cls) -> "BudgetLedger":
        return cls()

    @classmethod
    def open(cls, path: str | Path) -> "BudgetLedger":
        # Signature-only scaffold. A2 must provide real independent persistence.
        del path
        return cls()

    def gate(self, *, policy: BudgetPolicy | None) -> _Gate:
        return _Gate(self, policy)

    def advance_clock(self, seconds: int) -> None:
        del seconds

    def settle(
        self, reservation_id: str | None, *, outcome: str, actual_units: int
    ) -> None:
        del reservation_id, outcome, actual_units

    def reconcile(
        self, reservation_id: str | None, *, outcome: str, actual_units: int
    ) -> Any:
        del reservation_id, outcome, actual_units
        return None

    def outstanding(self, *, category: str) -> int:
        del category
        return 0

    def audit_records(
        self,
        *,
        action_id: str | None = None,
        reservation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        del action_id, reservation_id
        return []
