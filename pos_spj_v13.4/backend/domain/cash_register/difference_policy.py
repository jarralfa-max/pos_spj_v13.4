"""Pure CASH-15 classification, tolerance, recurrence and alert policy."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.cash_register.enums import (
    CashDifferenceClassification, CashDifferenceSeverity,
)


@dataclass(frozen=True, slots=True)
class CashDifferenceDecision:
    classification: CashDifferenceClassification
    severity: CashDifferenceSeverity
    alert_required: bool
    channels: tuple[str, ...]


class CashDifferencePolicy:
    def __init__(self, *, tolerance: Decimal, critical_threshold: Decimal,
                 recurrence_threshold: int, channels: tuple[str, ...]) -> None:
        if any(not isinstance(value, Decimal) or value < 0
               for value in (tolerance, critical_threshold)):
            raise TypeError("Difference thresholds require non-negative Decimal values")
        if critical_threshold < tolerance or recurrence_threshold < 1:
            raise ValueError("Difference policy thresholds are inconsistent")
        allowed = {"IN_APP", "WHATSAPP", "EMAIL"}
        normalized = tuple(dict.fromkeys(item.upper() for item in channels))
        if not normalized or not set(normalized) <= allowed:
            raise ValueError("Difference policy requires supported alert channels")
        self.tolerance, self.critical_threshold = tolerance, critical_threshold
        self.recurrence_threshold, self.channels = recurrence_threshold, normalized

    def evaluate(self, amount: Decimal, *, recurrence_count: int) -> CashDifferenceDecision:
        if not isinstance(amount, Decimal) or amount == 0:
            raise ValueError("Difference policy requires a non-zero Decimal")
        classification = (CashDifferenceClassification.SHORTAGE
                          if amount < 0 else CashDifferenceClassification.OVERAGE)
        absolute = abs(amount)
        if absolute <= self.tolerance:
            severity = CashDifferenceSeverity.WITHIN_TOLERANCE
        elif absolute >= self.critical_threshold or recurrence_count >= self.recurrence_threshold:
            severity = CashDifferenceSeverity.CRITICAL
        else:
            severity = CashDifferenceSeverity.REVIEW
        alert = severity is not CashDifferenceSeverity.WITHIN_TOLERANCE
        return CashDifferenceDecision(classification, severity, alert,
                                      self.channels if alert else ())
