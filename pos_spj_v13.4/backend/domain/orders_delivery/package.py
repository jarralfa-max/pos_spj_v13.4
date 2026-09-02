"""OrderPackage (master prompt §29) — a physical container holding a subset
of an order's lines. Not owned/embedded in `CustomerOrder` (same reasoning
as `OrderAddress`/`DeliveryZone`, ORD-7): a package has its own lifecycle
(sealed, cancelled) tracked independently of the order's own status.

`net_weight` is ALWAYS derived (`gross_weight - tare`), never stored as an
independent field a caller could set inconsistently — same "never store what
you can derive" discipline as `CustomerOrderLine.line_total`/`final_subtotal`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import PackageStatus, PackageType
from backend.domain.orders_delivery.exceptions import InvalidPackageError
from backend.domain.orders_delivery.value_objects.order_money import money


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class OrderPackage:
    id: str
    order_id: str
    package_number: str
    package_type: PackageType
    line_ids: tuple[str, ...]
    tare: Decimal = Decimal("0")
    gross_weight: Decimal = Decimal("0")
    temperature: Decimal | None = None
    seal_number: str | None = None
    status: PackageStatus = PackageStatus.OPEN
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, order_id: str, package_number: str, package_type: PackageType,
        line_ids: tuple[str, ...], tare: Decimal = Decimal("0"),
        gross_weight: Decimal = Decimal("0"), temperature: Decimal | None = None,
    ) -> "OrderPackage":
        validate_uuidv7(order_id)
        if not line_ids:
            raise InvalidPackageError("Un paquete requiere al menos una línea")
        for line_id in line_ids:
            validate_uuidv7(line_id)
        if not (package_number or "").strip():
            raise InvalidPackageError("El paquete requiere un número")
        tare = money(tare)
        gross_weight = money(gross_weight)
        if gross_weight < tare:
            raise InvalidPackageError("El peso bruto no puede ser menor que la tara")
        return cls(
            id=new_uuid(), order_id=order_id, package_number=package_number,
            package_type=package_type, line_ids=tuple(line_ids), tare=tare,
            gross_weight=gross_weight, temperature=temperature,
        )

    @property
    def net_weight(self) -> Decimal:
        return self.gross_weight - self.tare

    def seal(self, *, seal_number: str) -> None:
        if self.status != PackageStatus.OPEN:
            raise InvalidPackageError(
                f"No se puede sellar un paquete en estado {self.status.value}")
        if not (seal_number or "").strip():
            raise InvalidPackageError("El sellado requiere un número de sello")
        self.seal_number = seal_number
        self.status = PackageStatus.SEALED
        self.updated_at = _now()

    def cancel(self) -> None:
        if self.status == PackageStatus.SEALED:
            raise InvalidPackageError("No se puede cancelar un paquete ya sellado")
        self.status = PackageStatus.CANCELLED
        self.updated_at = _now()
