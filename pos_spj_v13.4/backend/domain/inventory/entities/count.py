"""InventoryCount (+Line) — physical counts, blind and recount (§27-28).

A blind count never exposes the expected quantity during capture; the variance
(counted − expected) is computed only on confirm, after which the count is locked
(no edits). A line beyond tolerance can be sent back for recount before approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import CountStatus, CountType
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en conteos")
    return Decimal(str(value))


@dataclass(slots=True)
class InventoryCountLine:
    id: str
    product_id: str
    location_id: str | None = None
    lot_id: str | None = None
    expected_quantity: Decimal = Decimal("0")
    expected_weight: Decimal = Decimal("0")
    counted_quantity: Decimal = Decimal("0")
    counted_weight: Decimal = Decimal("0")
    variance_quantity: Decimal = Decimal("0")
    variance_weight: Decimal = Decimal("0")
    recount_count: int = 0
    counted: bool = False

    @classmethod
    def create(cls, *, product_id: str, expected_quantity=0, expected_weight=0,
               location_id: str | None = None, lot_id: str | None = None) -> "InventoryCountLine":
        if not product_id:
            raise InventoryDomainError("La línea de conteo requiere producto")
        return cls(id=new_uuid(), product_id=product_id,
                   expected_quantity=_dec(expected_quantity),
                   expected_weight=_dec(expected_weight), location_id=location_id,
                   lot_id=lot_id)

    @property
    def has_variance(self) -> bool:
        return self.variance_quantity != 0 or self.variance_weight != 0


_TRANSITIONS = {
    CountStatus.DRAFT: {CountStatus.PLANNED, CountStatus.CANCELLED},
    CountStatus.PLANNED: {CountStatus.IN_PROGRESS, CountStatus.CANCELLED},
    CountStatus.IN_PROGRESS: {CountStatus.COUNTED, CountStatus.CANCELLED},
    CountStatus.COUNTED: {CountStatus.PENDING_RECOUNT, CountStatus.PENDING_APPROVAL,
                          CountStatus.APPROVED},
    CountStatus.PENDING_RECOUNT: {CountStatus.IN_PROGRESS, CountStatus.CANCELLED},
    CountStatus.PENDING_APPROVAL: {CountStatus.APPROVED, CountStatus.PENDING_RECOUNT},
    CountStatus.APPROVED: {CountStatus.POSTED},
}


@dataclass(slots=True)
class InventoryCount:
    id: str
    folio: str
    count_type: CountType
    branch_id: str
    warehouse_id: str
    status: CountStatus = CountStatus.DRAFT
    blind: bool = True
    lines: list[InventoryCountLine] = field(default_factory=list)
    scope_location_id: str | None = None
    scope_product_id: str | None = None
    scope_lot_id: str | None = None
    created_by_user_id: str | None = None
    counted_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, folio: str, count_type: CountType, branch_id: str,
               warehouse_id: str, lines: list[InventoryCountLine] | None = None,
               blind: bool = True, **kwargs) -> "InventoryCount":
        if not branch_id or not warehouse_id:
            raise InventoryDomainError("El conteo requiere sucursal y almacén")
        blind = blind or count_type is CountType.BLIND_COUNT
        return cls(id=new_uuid(), folio=folio, count_type=count_type, branch_id=branch_id,
                   warehouse_id=warehouse_id, lines=list(lines or []), blind=blind, **kwargs)

    def _to(self, new_status: CountStatus) -> None:
        if new_status not in _TRANSITIONS.get(self.status, set()):
            raise InventoryDomainError(
                f"Transición inválida {self.status.value} → {new_status.value}")
        self.status = new_status

    def plan(self) -> None:
        if not self.lines:
            raise InventoryDomainError("El conteo requiere al menos una línea")
        self._to(CountStatus.PLANNED)

    def start(self) -> None:
        self._to(CountStatus.IN_PROGRESS)

    def record(self, line_id: str, *, counted_quantity=0, counted_weight=0) -> None:
        if self.status is not CountStatus.IN_PROGRESS:
            raise InventoryDomainError(
                "Solo se puede capturar un conteo en progreso (no editable tras confirmar)")
        line = self._line(line_id)
        line.counted_quantity = _dec(counted_quantity)
        line.counted_weight = _dec(counted_weight)
        line.counted = True

    def confirm(self) -> None:
        """Lock the count and compute variances (counted − expected)."""
        if self.status is not CountStatus.IN_PROGRESS:
            raise InventoryDomainError("Solo un conteo en progreso puede confirmarse")
        if not all(l.counted for l in self.lines):
            raise InventoryDomainError("Todas las líneas deben contarse antes de confirmar")
        for line in self.lines:
            line.variance_quantity = line.counted_quantity - line.expected_quantity
            line.variance_weight = line.counted_weight - line.expected_weight
        self._to(CountStatus.COUNTED)

    @property
    def has_variance(self) -> bool:
        return any(l.has_variance for l in self.lines)

    def request_recount(self, line_id: str) -> None:
        if self.status not in (CountStatus.COUNTED, CountStatus.PENDING_APPROVAL):
            raise InventoryDomainError("Solo se recuenta un conteo confirmado")
        line = self._line(line_id)
        line.recount_count += 1
        line.counted = False
        self.status = CountStatus.PENDING_RECOUNT

    def mark_pending_approval(self) -> None:
        self._to(CountStatus.PENDING_APPROVAL)

    def approve(self, *, user_id: str) -> None:
        if self.status not in (CountStatus.COUNTED, CountStatus.PENDING_APPROVAL):
            raise InventoryDomainError(
                f"No se puede aprobar un conteo en estado {self.status.value}")
        self.status = CountStatus.APPROVED
        self.approved_by_user_id = user_id

    def mark_posted(self) -> None:
        self._to(CountStatus.POSTED)

    def cancel(self) -> None:
        self._to(CountStatus.CANCELLED)

    def _line(self, line_id: str) -> InventoryCountLine:
        for line in self.lines:
            if line.id == line_id:
                return line
        raise InventoryDomainError(f"Línea de conteo no encontrada: {line_id}")
