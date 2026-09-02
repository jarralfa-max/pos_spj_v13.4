"""DeliveryZone (master prompt §21) — configuration entity: which postal
codes a branch delivers to, its fee, free-delivery threshold and minimum
order. Fees/zones are never hardcoded (master prompt §22): the zone IS the
data-driven source `DeliveryFeePolicy` reads from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.exceptions import InvalidAddressError
from backend.domain.orders_delivery.value_objects.order_money import money


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DeliveryZone:
    id: str
    branch_id: str
    name: str
    postal_codes: tuple[str, ...] = ()
    minimum_order: Decimal = Decimal("0")
    delivery_fee: Decimal = Decimal("0")
    free_delivery_threshold: Decimal | None = None
    estimated_minutes: int | None = None
    maximum_distance_km: Decimal | None = None
    active: bool = True
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, branch_id: str, name: str, postal_codes: tuple[str, ...] = (),
        minimum_order: Decimal = Decimal("0"), delivery_fee: Decimal = Decimal("0"),
        free_delivery_threshold: Decimal | None = None,
        estimated_minutes: int | None = None,
        maximum_distance_km: Decimal | None = None,
    ) -> "DeliveryZone":
        validate_uuidv7(branch_id)
        if not (name or "").strip():
            raise InvalidAddressError("La zona de entrega requiere nombre")
        return cls(
            id=new_uuid(), branch_id=branch_id, name=name, postal_codes=tuple(postal_codes),
            minimum_order=money(minimum_order), delivery_fee=money(delivery_fee),
            free_delivery_threshold=(money(free_delivery_threshold)
                                      if free_delivery_threshold is not None else None),
            estimated_minutes=estimated_minutes, maximum_distance_km=maximum_distance_km,
        )

    def covers_postal_code(self, postal_code: str) -> bool:
        return bool(postal_code) and postal_code in self.postal_codes

    def fee_for_order_total(self, order_total: Decimal) -> Decimal:
        if self.free_delivery_threshold is not None and order_total >= self.free_delivery_threshold:
            return Decimal("0")
        return self.delivery_fee

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _now()
