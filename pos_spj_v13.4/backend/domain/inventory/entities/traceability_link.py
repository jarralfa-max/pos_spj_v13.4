"""TraceabilityLink — an explicit genealogy edge between lots (§32-33).

Most traceability is *derived* from the ledger: every movement carries its lot,
so the upstream (where a lot came from) and downstream (where it went) chains can
be reconstructed by reading ``inventory_ledger_lines`` by lot. But some
operations break a lot's identity — production consumes input lots and yields a
new output lot, slaughter turns a carcass lot into cut lots — and the ledger
records the two sides as independent movements. The link makes that parent→child
relationship explicit so a recall can walk the genealogy in both directions.

Quantities/weights are Decimal; the link is immutable once created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import TraceabilityLinkType
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en cantidades/pesos")
    return Decimal(str(value))


@dataclass(slots=True)
class TraceabilityLink:
    id: str
    parent_lot_id: str
    child_lot_id: str
    link_type: TraceabilityLinkType
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    product_id: str | None = None
    source_module: str = "inventory"
    source_document_type: str | None = None
    source_document_id: str | None = None
    operation_id: str | None = None
    created_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, parent_lot_id: str, child_lot_id: str,
               link_type: TraceabilityLinkType, quantity=0, weight=0,
               product_id: str | None = None, source_module: str = "inventory",
               source_document_type: str | None = None,
               source_document_id: str | None = None, operation_id: str | None = None,
               created_by_user_id: str | None = None) -> "TraceabilityLink":
        if not parent_lot_id or not child_lot_id:
            raise InventoryDomainError(
                "El enlace de trazabilidad requiere lote padre y lote hijo")
        if parent_lot_id == child_lot_id:
            raise InventoryDomainError(
                "Un lote no puede ser su propio origen en la genealogía")
        q, w = _dec(quantity), _dec(weight)
        if q < 0 or w < 0:
            raise InventoryDomainError(
                "Cantidad y peso del enlace deben ser no negativos")
        return cls(id=new_uuid(), parent_lot_id=parent_lot_id,
                   child_lot_id=child_lot_id, link_type=link_type, quantity=q,
                   weight=w, product_id=product_id, source_module=source_module,
                   source_document_type=source_document_type,
                   source_document_id=source_document_id, operation_id=operation_id,
                   created_by_user_id=created_by_user_id)
