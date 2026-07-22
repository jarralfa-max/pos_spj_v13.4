"""Slaughter contracts — future flow payload shapes (§33, INV-21).

Born-clean DTOs the future slaughter module will exchange: a slaughter order
consumes livestock (an input lot) and produces a carcass (canal), which is then
disassembled into classified outputs (primary cuts, co-/by-products, offal,
waste), each its own output lot. Ids are UUIDv7 strings; quantities/weights are
Decimal. These are immutable value objects, not entities — no persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.inventory.enums import (
    CarcassState,
    SlaughterOutputType,
    SlaughterSpecies,
)
from backend.domain.inventory.exceptions import InventoryDomainError


def _dec(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en cantidades/pesos de faena")
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class SlaughterOrderContract:
    order_id: str
    species: SlaughterSpecies
    branch_id: str
    warehouse_id: str
    livestock_lot_id: str            # input lot consumed by the slaughter
    livestock_product_id: str
    livestock_quantity: Decimal = Decimal("0")   # head count
    livestock_weight: Decimal = Decimal("0")      # live weight

    def __post_init__(self) -> None:
        if not (self.order_id and self.branch_id and self.warehouse_id):
            raise InventoryDomainError("La orden de faena requiere id, sucursal y almacén")
        if not (self.livestock_lot_id and self.livestock_product_id):
            raise InventoryDomainError("La orden de faena requiere lote/producto de ganado")
        object.__setattr__(self, "livestock_quantity", _dec(self.livestock_quantity))
        object.__setattr__(self, "livestock_weight", _dec(self.livestock_weight))


@dataclass(frozen=True, slots=True)
class CarcassContract:
    carcass_lot_id: str              # the carcass becomes its own lot
    carcass_product_id: str
    state: CarcassState = CarcassState.WHOLE
    weight: Decimal = Decimal("0")   # cold/hot carcass weight

    def __post_init__(self) -> None:
        if not (self.carcass_lot_id and self.carcass_product_id):
            raise InventoryDomainError("La canal requiere lote y producto")
        object.__setattr__(self, "weight", _dec(self.weight))


@dataclass(frozen=True, slots=True)
class SlaughterOutputContract:
    output_lot_id: str
    product_id: str
    output_type: SlaughterOutputType
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    to_location_id: str | None = None

    def __post_init__(self) -> None:
        if not (self.output_lot_id and self.product_id):
            raise InventoryDomainError("El output de faena requiere lote y producto")
        object.__setattr__(self, "quantity", _dec(self.quantity))
        object.__setattr__(self, "weight", _dec(self.weight))
