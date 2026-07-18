"""InventoryOperationLimit — a configurable quantity/weight/variance threshold.

Generalises the §48 limits (adjustment, transfer approval, weight variance,
count variance, negative-inventory override): each carries an optional
``approval_threshold`` (above it a hot authorization is required) and an optional
``hard_cap`` (above it the operation is blocked outright). ``warning_threshold``
is informational only. Limits are never hardcoded in UI; they come from
configuration (INV-3 schema) scoped to user/role/branch/warehouse.

Decimal-only: float thresholds are rejected (REGLA CERO / §8).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.inventory.enums import LimitBasis, LimitDecision
from backend.domain.inventory.exceptions import InvalidInventoryLimitError


def _coerce(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidInventoryLimitError(
            "Los umbrales de límite deben ser Decimal/int/str, nunca float")
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:  # pragma: no cover - defensive
        raise InvalidInventoryLimitError(f"Umbral inválido: {value!r}") from exc


@dataclass(frozen=True)
class InventoryOperationLimit:
    basis: LimitBasis = LimitBasis.QUANTITY
    warning_threshold: Decimal | None = None
    approval_threshold: Decimal | None = None
    hard_cap: Decimal | None = None

    def __post_init__(self) -> None:
        for field_name in ("warning_threshold", "approval_threshold", "hard_cap"):
            object.__setattr__(self, field_name, _coerce(getattr(self, field_name)))
        cap, approval = self.hard_cap, self.approval_threshold
        if cap is not None and approval is not None and cap < approval:
            raise InvalidInventoryLimitError(
                "hard_cap no puede ser menor que approval_threshold")

    def classify(self, value: Decimal | int | str) -> LimitDecision:
        magnitude = abs(_coerce(value))  # a variance/adjustment may be negative
        if self.hard_cap is not None and magnitude > self.hard_cap:
            return LimitDecision.EXCEEDS
        if self.approval_threshold is not None and magnitude > self.approval_threshold:
            return LimitDecision.REQUIRES_APPROVAL
        return LimitDecision.WITHIN

    def is_warning(self, value: Decimal | int | str) -> bool:
        if self.warning_threshold is None:
            return False
        return abs(_coerce(value)) > self.warning_threshold
