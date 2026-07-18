"""InventoryLot — a traceable production/purchase/slaughter lot (§19).

A lot preserves traceability: its origin (purchase/production/slaughter/return),
its supplier/production/slaughter codes, its dates and its quality status. Meat
lots carry an expiration date that drives FEFO allocation (§20). Not limited to
poultry — any species/product may be lot-controlled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.inventory.enums import LotOrigin, LotQualityStatus
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass(slots=True)
class InventoryLot:
    id: str
    product_id: str
    lot_code: str
    origin_type: LotOrigin
    quality_status: LotQualityStatus = LotQualityStatus.PENDING_INSPECTION
    traceability_status: str = "LINKED"
    supplier_lot_code: str | None = None
    production_lot_code: str | None = None
    slaughter_lot_code: str | None = None
    origin_document_id: str | None = None
    production_date: str | None = None
    slaughter_date: str | None = None
    expiration_date: str | None = None
    received_at: str | None = None
    branch_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, product_id: str, lot_code: str, origin_type: LotOrigin,
               **kwargs) -> "InventoryLot":
        if not product_id:
            raise InventoryDomainError("El lote requiere producto")
        if not lot_code:
            raise InventoryDomainError("El lote requiere código de lote")
        return cls(id=new_uuid(), product_id=product_id, lot_code=lot_code,
                   origin_type=origin_type, **kwargs)

    @property
    def is_released(self) -> bool:
        return self.quality_status is LotQualityStatus.RELEASED

    @property
    def is_allocatable(self) -> bool:
        return self.quality_status in (
            LotQualityStatus.RELEASED, LotQualityStatus.PENDING_INSPECTION)

    def is_expired(self, as_of: str | date | None = None) -> bool:
        exp = _as_date(self.expiration_date)
        if exp is None:
            return False
        ref = _as_date(as_of) or date.today()
        return exp < ref

    def block(self, *, status: LotQualityStatus = LotQualityStatus.BLOCKED) -> None:
        if status not in (LotQualityStatus.BLOCKED, LotQualityStatus.QUARANTINED,
                          LotQualityStatus.REJECTED):
            raise InventoryDomainError("Estado de bloqueo inválido")
        self.quality_status = status

    def release(self) -> None:
        self.quality_status = LotQualityStatus.RELEASED
