"""DeliveryZonePolicy (master prompt §21-22) — what makes a delivery zone valid,
and the rule that keeps zone resolution deterministic.

`DeliveryFeePolicy.resolve_zone` returns the FIRST active zone covering a postal
code, and the zones come from `list_active_for_branch`, which has no ORDER BY.
Two active zones of one branch sharing a postal code would make the delivery
fee depend on physical row order. `ensure_no_overlap` forbids exactly that; an
inactive zone never counts, since resolution ignores it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from backend.domain.orders_delivery.exceptions import (
    DeliveryZoneOverlapError,
    InvalidDeliveryZoneError,
)


class DeliveryZonePolicy:
    @staticmethod
    def normalize_postal_codes(raw: str | Iterable[str] | None) -> tuple[str, ...]:
        """Accepts "06000, 06010" or an iterable; trims, drops blanks and
        duplicates, keeps the order given."""
        if isinstance(raw, str):
            partes = raw.replace(";", ",").replace("\n", ",").split(",")
        else:
            partes = list(raw or ())
        codigos: list[str] = []
        for parte in partes:
            codigo = str(parte).strip()
            if codigo and codigo not in codigos:
                codigos.append(codigo)
        return tuple(codigos)

    @staticmethod
    def validate(
        *, name: str, postal_codes: tuple[str, ...], minimum_order: Decimal,
        delivery_fee: Decimal, free_delivery_threshold: Decimal | None,
        estimated_minutes: int | None, maximum_distance_km: Decimal | None,
    ) -> None:
        if not (name or "").strip():
            raise InvalidDeliveryZoneError("La zona de entrega requiere nombre")
        if not postal_codes:
            raise InvalidDeliveryZoneError(
                "La zona de entrega requiere al menos un código postal: sin códigos "
                "no cubre ningún domicilio")
        if any(" " in codigo for codigo in postal_codes):
            raise InvalidDeliveryZoneError("Un código postal no puede contener espacios")
        for etiqueta, importe in (("El pedido mínimo", minimum_order),
                                  ("El costo de envío", delivery_fee),
                                  ("El envío gratis", free_delivery_threshold)):
            if importe is not None and importe < 0:
                raise InvalidDeliveryZoneError(f"{etiqueta} no puede ser negativo")
        if estimated_minutes is not None and estimated_minutes <= 0:
            raise InvalidDeliveryZoneError("El tiempo estimado debe ser mayor a cero")
        if maximum_distance_km is not None and maximum_distance_km <= 0:
            raise InvalidDeliveryZoneError("La distancia máxima debe ser mayor a cero")

    @staticmethod
    def ensure_no_overlap(zone, active_zones: Iterable) -> None:
        """`zone` may not share a postal code with any OTHER active zone of its
        branch. The message names every clashing code and zone."""
        choques = []
        for otra in sorted(active_zones, key=lambda z: (z.name.lower(), z.id)):
            if otra.id == zone.id or not otra.active or otra.branch_id != zone.branch_id:
                continue
            comunes = sorted(set(zone.postal_codes) & set(otra.postal_codes))
            if comunes:
                choques.append(f"{', '.join(comunes)} (zona «{otra.name}»)")
        if choques:
            raise DeliveryZoneOverlapError(
                "Estos códigos postales ya los cubre otra zona activa de la sucursal: "
                + "; ".join(choques))
