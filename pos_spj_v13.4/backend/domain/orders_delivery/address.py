"""OrderAddress (master prompt §20) — a delivery address attached to a
CustomerOrder by id (`CustomerOrder.delivery_address_id`), not owned/embedded
in the aggregate: an address can be captured, geocoded and corrected on its
own timeline (a geocoding worker updates it asynchronously), independent of
whatever else is happening to the order. Same `slots=True`/`create()`/
`new_uuid()` shape as `CustomerOrder`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import GeocodingStatus
from backend.domain.orders_delivery.exceptions import InvalidAddressError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class OrderAddress:
    id: str
    order_id: str
    recipient_name: str
    recipient_phone: str
    street: str
    exterior_number: str
    interior_number: str | None = None
    neighborhood: str | None = None
    postal_code: str | None = None
    municipality: str | None = None
    state: str | None = None
    references: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geocoding_status: GeocodingStatus = GeocodingStatus.NOT_REQUESTED
    delivery_zone_id: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, order_id: str, recipient_name: str, recipient_phone: str, street: str,
        exterior_number: str, interior_number: str | None = None,
        neighborhood: str | None = None, postal_code: str | None = None,
        municipality: str | None = None, state: str | None = None,
        references: str | None = None,
    ) -> "OrderAddress":
        validate_uuidv7(order_id)
        if not (recipient_name or "").strip():
            raise InvalidAddressError("La dirección requiere nombre del receptor")
        if not (recipient_phone or "").strip():
            raise InvalidAddressError("La dirección requiere teléfono de contacto")
        if not (street or "").strip():
            raise InvalidAddressError("La dirección requiere calle")
        return cls(
            id=new_uuid(), order_id=order_id, recipient_name=recipient_name,
            recipient_phone=recipient_phone, street=street, exterior_number=exterior_number,
            interior_number=interior_number, neighborhood=neighborhood,
            postal_code=postal_code, municipality=municipality, state=state,
            references=references,
        )

    def mark_geocoded(self, *, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.geocoding_status = GeocodingStatus.GEOCODED
        self.updated_at = _now()

    def mark_manual(self) -> None:
        """§20: geocoding never blocks the order when a manual address is
        already sufficient — this is a legitimate terminal state, not a
        failure."""
        self.geocoding_status = GeocodingStatus.MANUAL
        self.updated_at = _now()

    def mark_geocoding_failed(self) -> None:
        self.geocoding_status = GeocodingStatus.FAILED
        self.updated_at = _now()

    def assign_zone(self, delivery_zone_id: str) -> None:
        validate_uuidv7(delivery_zone_id)
        self.delivery_zone_id = delivery_zone_id
        self.updated_at = _now()
