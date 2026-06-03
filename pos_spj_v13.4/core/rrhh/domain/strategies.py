"""Payroll concept strategies for RRHH domain tests and future payroll refactors.

The strategies are intentionally framework-free and additive. They do not change
legacy payroll behavior until application services opt into them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PayrollConceptStrategy(Protocol):
    """Calculates one payroll concept amount from an explicit base amount."""

    code: str

    def calculate(self, *, base_amount: float = 0.0, hours: float = 0.0) -> float: ...


@dataclass(frozen=True)
class FixedAmountStrategy:
    """Returns a fixed additive/deductive amount."""

    code: str
    amount: float

    def calculate(self, *, base_amount: float = 0.0, hours: float = 0.0) -> float:
        return round(float(self.amount or 0.0), 2)


@dataclass(frozen=True)
class PercentageStrategy:
    """Calculates a percentage over a supplied base amount."""

    code: str
    percent: float

    def calculate(self, *, base_amount: float = 0.0, hours: float = 0.0) -> float:
        return round(float(base_amount or 0.0) * float(self.percent or 0.0), 2)


@dataclass(frozen=True)
class HourlyPayStrategy:
    """Calculates pay from hours and an hourly rate."""

    code: str
    hourly_rate: float

    def calculate(self, *, base_amount: float = 0.0, hours: float = 0.0) -> float:
        return round(float(hours or 0.0) * float(self.hourly_rate or 0.0), 2)


@dataclass(frozen=True)
class PayrollConceptCalculator:
    """Aggregates payroll concepts without hardcoding concept types in callers."""

    strategies: tuple[PayrollConceptStrategy, ...]

    def calculate_total(self, *, base_amount: float = 0.0, hours: float = 0.0) -> float:
        total = sum(
            strategy.calculate(base_amount=base_amount, hours=hours)
            for strategy in self.strategies
        )
        return round(total, 2)
