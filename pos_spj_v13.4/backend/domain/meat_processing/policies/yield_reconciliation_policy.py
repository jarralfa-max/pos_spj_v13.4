"""Yield variance classification (§26). Thresholds are always caller-supplied —
never hardcoded here — matching §26's explicit "no hardcodear" instruction and root
CLAUDE.md rule #23/24 (no arbitrary defaults in business logic)."""

from decimal import Decimal

from backend.domain.meat_processing.enums import YieldStatus
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


class YieldReconciliationPolicy:
    @staticmethod
    def classify(
        variance_pct: Decimal | None,
        *,
        warning_pct: Decimal,
        tolerance_pct: Decimal,
        critical_pct: Decimal,
    ) -> YieldStatus:
        for name, value in (("warning_pct", warning_pct), ("tolerance_pct", tolerance_pct),
                             ("critical_pct", critical_pct)):
            if value < 0:
                raise MeatProcessingInvariantError(f"{name} no puede ser negativo")
        if not (warning_pct <= tolerance_pct <= critical_pct):
            raise MeatProcessingInvariantError(
                "Los umbrales deben cumplir warning_pct <= tolerance_pct <= critical_pct")
        if variance_pct is None:
            return YieldStatus.PENDING_REVIEW
        magnitude = abs(variance_pct)
        if magnitude <= warning_pct:
            return YieldStatus.WITHIN_TOLERANCE
        if magnitude <= tolerance_pct:
            return YieldStatus.WARNING
        if magnitude <= critical_pct:
            return YieldStatus.OUT_OF_TOLERANCE
        return YieldStatus.CRITICAL
