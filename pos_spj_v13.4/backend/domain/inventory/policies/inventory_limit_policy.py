"""InventoryLimitPolicy — classify an operation value against a limit (§48).

Pure domain logic. ``classify`` returns WITHIN / REQUIRES_APPROVAL / EXCEEDS;
``enforce_direct_execution`` turns those into the canonical escalation:
REQUIRES_APPROVAL → hot authorization, EXCEEDS → hard block.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.inventory.enums import LimitDecision
from backend.domain.inventory.exceptions import (
    InventoryAuthorizationRequiredError,
    InventoryLimitExceededError,
)
from backend.domain.inventory.value_objects.inventory_limit import (
    InventoryOperationLimit,
)


class InventoryLimitPolicy:
    def classify(
        self,
        value: Decimal | int | str,
        limit: InventoryOperationLimit | None,
    ) -> LimitDecision:
        if limit is None:
            return LimitDecision.WITHIN
        return limit.classify(value)

    def enforce_direct_execution(
        self,
        value: Decimal | int | str,
        limit: InventoryOperationLimit | None,
    ) -> None:
        """Raise unless the value can be executed directly (no authorization)."""
        decision = self.classify(value, limit)
        if decision is LimitDecision.REQUIRES_APPROVAL:
            raise InventoryAuthorizationRequiredError(
                "La operación excede el umbral y requiere autorización")
        if decision is LimitDecision.EXCEEDS:
            raise InventoryLimitExceededError(
                "La operación excede el tope máximo permitido")
