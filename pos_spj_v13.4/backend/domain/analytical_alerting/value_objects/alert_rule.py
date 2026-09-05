"""AnalyticalAlertRule (§46/§48, BI-20).

Severity is configured per rule (§48: "La severidad se configura. No
hardcodear.") — never a fixed severity baked into the alert type itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertType, Comparison
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class AnalyticalAlertRule:
    id: str
    alert_type: AlertType
    metric_key: str
    comparison: Comparison
    threshold: Decimal
    severity: AlertSeverity
    cooldown_minutes: int
    enabled: bool = True

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.metric_key:
            raise ValueError("AnalyticalAlertRule.metric_key is required")
        if self.cooldown_minutes < 0:
            raise ValueError("AnalyticalAlertRule.cooldown_minutes must be >= 0")

    def is_breached(self, metric_value: Decimal) -> bool:
        if self.comparison == Comparison.GREATER_THAN:
            return metric_value > self.threshold
        if self.comparison == Comparison.GREATER_THAN_OR_EQUAL:
            return metric_value >= self.threshold
        if self.comparison == Comparison.LESS_THAN:
            return metric_value < self.threshold
        if self.comparison == Comparison.LESS_THAN_OR_EQUAL:
            return metric_value <= self.threshold
        raise ValueError(f"Unknown comparison: {self.comparison}")  # pragma: no cover
