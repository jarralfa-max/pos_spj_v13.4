"""Replenishment rule + suggestion (§34).

A ``ReplenishmentRule`` is the per-product/branch/warehouse policy: the reorder
point that triggers a suggestion, the safety stock that marks a critical level,
and the target level to replenish back up to (bounded by min/max). A rule also
declares the *preferred source* — buy it (PURCHASE → procurement) or move surplus
from another warehouse (TRANSFER). Quantities are Decimal.

A ``ReplenishmentSuggestion`` is the immutable output of evaluating a rule against
current availability: how much to bring in, from where, and how urgent. It never
moves stock itself; acting on it creates a purchase or a transfer through their
own use cases (§34 keeps planning and execution separate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import (
    ReplenishmentBasis,
    ReplenishmentSource,
    ReplenishmentSuggestionStatus,
    ReplenishmentUrgency,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en niveles de reposición")
    return Decimal(str(value))


@dataclass(slots=True)
class ReplenishmentRule:
    id: str
    product_id: str
    branch_id: str
    warehouse_id: str
    reorder_point: Decimal
    target_quantity: Decimal
    basis: ReplenishmentBasis = ReplenishmentBasis.QUANTITY
    min_quantity: Decimal = Decimal("0")
    max_quantity: Decimal | None = None
    safety_stock: Decimal = Decimal("0")
    lead_time_days: int = 0
    preferred_source: ReplenishmentSource = ReplenishmentSource.PURCHASE
    source_warehouse_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, product_id: str, branch_id: str, warehouse_id: str,
               reorder_point, target_quantity, basis=ReplenishmentBasis.QUANTITY,
               min_quantity=0, max_quantity=None, safety_stock=0, lead_time_days: int = 0,
               preferred_source=ReplenishmentSource.PURCHASE,
               source_warehouse_id: str | None = None,
               active: bool = True) -> "ReplenishmentRule":
        if not (product_id and branch_id and warehouse_id):
            raise InventoryDomainError(
                "La regla de reposición requiere producto, sucursal y almacén")
        reorder = _dec(reorder_point)
        target = _dec(target_quantity)
        min_q = _dec(min_quantity)
        safety = _dec(safety_stock)
        max_q = None if max_quantity is None else _dec(max_quantity)
        if reorder < 0 or target < 0 or min_q < 0 or safety < 0:
            raise InventoryDomainError("Los niveles de reposición no pueden ser negativos")
        if target < reorder:
            raise InventoryDomainError(
                "El nivel objetivo no puede ser menor que el punto de pedido")
        if max_q is not None and target > max_q:
            raise InventoryDomainError("El nivel objetivo no puede exceder el máximo")
        if lead_time_days < 0:
            raise InventoryDomainError("El lead time no puede ser negativo")
        if (preferred_source is ReplenishmentSource.TRANSFER
                and not source_warehouse_id):
            raise InventoryDomainError(
                "Una regla de transferencia requiere almacén de origen")
        return cls(id=new_uuid(), product_id=product_id, branch_id=branch_id,
                   warehouse_id=warehouse_id, reorder_point=reorder,
                   target_quantity=target, basis=basis, min_quantity=min_q,
                   max_quantity=max_q, safety_stock=safety, lead_time_days=lead_time_days,
                   preferred_source=preferred_source,
                   source_warehouse_id=source_warehouse_id, active=active)


@dataclass(slots=True)
class ReplenishmentSuggestion:
    id: str
    rule_id: str
    product_id: str
    branch_id: str
    warehouse_id: str
    basis: ReplenishmentBasis
    current_available: Decimal
    suggested_quantity: Decimal
    source_type: ReplenishmentSource
    urgency: ReplenishmentUrgency
    source_warehouse_id: str | None = None
    status: ReplenishmentSuggestionStatus = ReplenishmentSuggestionStatus.OPEN
    operation_id: str | None = None
    generated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, rule_id: str, product_id: str, branch_id: str,
               warehouse_id: str, basis: ReplenishmentBasis, current_available,
               suggested_quantity, source_type: ReplenishmentSource,
               urgency: ReplenishmentUrgency, source_warehouse_id: str | None = None,
               operation_id: str | None = None) -> "ReplenishmentSuggestion":
        qty = _dec(suggested_quantity)
        if qty <= 0:
            raise InventoryDomainError(
                "Una sugerencia de reposición debe proponer una cantidad positiva")
        return cls(id=new_uuid(), rule_id=rule_id, product_id=product_id,
                   branch_id=branch_id, warehouse_id=warehouse_id, basis=basis,
                   current_available=_dec(current_available), suggested_quantity=qty,
                   source_type=source_type, urgency=urgency,
                   source_warehouse_id=source_warehouse_id, operation_id=operation_id)
