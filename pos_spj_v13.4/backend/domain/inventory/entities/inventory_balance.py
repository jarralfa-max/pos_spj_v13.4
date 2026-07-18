"""InventoryBalance — the ledger projection (§14).

A balance is keyed by the full stock dimension
(product, branch, warehouse, location, lot, serial, status). It is NEVER mutated
by UI or other contexts — only the balance service rebuilds it from the ledger.
``available`` is on-hand minus reserved, and only AVAILABLE-status stock is
sellable/consumable. ``version`` supports optimistic concurrency (§59).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.inventory.enums import InventoryStatus, is_sellable
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _dec(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en balances")
    return Decimal(str(value))


@dataclass(slots=True)
class InventoryBalance:
    id: str
    product_id: str
    branch_id: str
    warehouse_id: str
    inventory_status: InventoryStatus
    location_id: str | None = None
    lot_id: str | None = None
    serial_id: str | None = None
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    reserved_quantity: Decimal = Decimal("0")
    reserved_weight: Decimal = Decimal("0")
    version: int = 0

    def __post_init__(self) -> None:
        for f in ("quantity", "weight", "reserved_quantity", "reserved_weight"):
            setattr(self, f, _dec(getattr(self, f)))

    @classmethod
    def empty(cls, *, product_id: str, branch_id: str, warehouse_id: str,
              inventory_status: InventoryStatus = InventoryStatus.AVAILABLE,
              location_id: str | None = None, lot_id: str | None = None,
              serial_id: str | None = None) -> "InventoryBalance":
        return cls(id=new_uuid(), product_id=product_id, branch_id=branch_id,
                   warehouse_id=warehouse_id, inventory_status=inventory_status,
                   location_id=location_id, lot_id=lot_id, serial_id=serial_id)

    @property
    def available_quantity(self) -> Decimal:
        if not is_sellable(self.inventory_status):
            return Decimal("0")
        return self.quantity - self.reserved_quantity

    @property
    def available_weight(self) -> Decimal:
        if not is_sellable(self.inventory_status):
            return Decimal("0")
        return self.weight - self.reserved_weight

    def apply_delta(self, *, quantity=0, weight=0) -> None:
        self.quantity += _dec(quantity)
        self.weight += _dec(weight)
        self.version += 1

    def reserve(self, *, quantity=0, weight=0) -> None:
        q, w = _dec(quantity), _dec(weight)
        if q > self.available_quantity or w > self.available_weight:
            raise InventoryDomainError(
                "No hay disponibilidad suficiente para reservar")
        self.reserved_quantity += q
        self.reserved_weight += w
        self.version += 1

    def release_reservation(self, *, quantity=0, weight=0) -> None:
        q, w = _dec(quantity), _dec(weight)
        self.reserved_quantity = max(Decimal("0"), self.reserved_quantity - q)
        self.reserved_weight = max(Decimal("0"), self.reserved_weight - w)
        self.version += 1
