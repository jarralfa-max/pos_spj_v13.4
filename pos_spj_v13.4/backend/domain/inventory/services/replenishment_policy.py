"""ReplenishmentPolicy — pure min/max/safety/target evaluation (§34).

Given a rule and the current available quantity (and, optionally, the surplus at
the rule's transfer source), decide whether to replenish, how much, from where,
and how urgently. Pure domain logic: no I/O, Decimal throughout.

Rules:
- Trigger only at/below the reorder point; otherwise no suggestion.
- Replenish back up to the *target* level (deficit = target − available).
- Urgency ladder: STOCKOUT (≤0) → CRITICAL (≤ safety stock) → REORDER (≤ reorder).
- Source: honor TRANSFER only when the source warehouse can fully cover the
  deficit from its surplus; otherwise fall back to PURCHASE. This keeps a
  suggestion to a single actionable source (§34 separates planning from action).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.inventory.entities.replenishment import ReplenishmentRule
from backend.domain.inventory.enums import (
    ReplenishmentSource,
    ReplenishmentUrgency,
)


@dataclass(frozen=True, slots=True)
class ReplenishmentDecision:
    suggested_quantity: Decimal
    source_type: ReplenishmentSource
    urgency: ReplenishmentUrgency
    source_warehouse_id: str | None = None


class ReplenishmentPolicy:
    def evaluate(self, rule: ReplenishmentRule, *, available,
                 source_surplus=None) -> ReplenishmentDecision | None:
        avail = _dec(available)
        if avail > rule.reorder_point:
            return None
        deficit = rule.target_quantity - avail
        if deficit <= 0:
            return None

        urgency = self._urgency(rule, avail)
        source_type = ReplenishmentSource.PURCHASE
        source_wh: str | None = None
        if rule.preferred_source is ReplenishmentSource.TRANSFER:
            surplus = None if source_surplus is None else _dec(source_surplus)
            if surplus is not None and surplus >= deficit:
                source_type = ReplenishmentSource.TRANSFER
                source_wh = rule.source_warehouse_id
        return ReplenishmentDecision(
            suggested_quantity=deficit, source_type=source_type, urgency=urgency,
            source_warehouse_id=source_wh)

    @staticmethod
    def _urgency(rule: ReplenishmentRule, available: Decimal) -> ReplenishmentUrgency:
        if available <= 0:
            return ReplenishmentUrgency.STOCKOUT
        if available <= rule.safety_stock:
            return ReplenishmentUrgency.CRITICAL
        return ReplenishmentUrgency.REORDER


def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("No se permite float en niveles de reposición")
    return Decimal(str(value))
