"""MapReference — a branch's location for maps/geocoding UIs (§16).
Deliberately minimal at the Settings layer: it holds coordinates and an
external place id, not a live geocoding integration (that belongs to
Integrations, a later SET) — `place_id` is whatever the eventual maps
provider's own reference happens to be.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.settings.exceptions import ConfigurationInvalidValueError

_LAT_RANGE = (Decimal("-90"), Decimal("90"))
_LNG_RANGE = (Decimal("-180"), Decimal("180"))


def _require_decimal(name: str, value: object) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise ConfigurationInvalidValueError(f"{name} debe ser Decimal, nunca float")
    return value


@dataclass(frozen=True, slots=True)
class MapReference:
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    place_id: str | None = None

    @classmethod
    def create(
        cls, *, latitude: Decimal | None = None, longitude: Decimal | None = None,
        place_id: str | None = None,
    ) -> "MapReference":
        if (latitude is None) != (longitude is None):
            raise ConfigurationInvalidValueError("latitude y longitude deben especificarse juntos")
        if latitude is not None:
            latitude = _require_decimal("latitude", latitude)
            longitude = _require_decimal("longitude", longitude)
            if not (_LAT_RANGE[0] <= latitude <= _LAT_RANGE[1]):
                raise ConfigurationInvalidValueError("latitude fuera de rango [-90, 90]")
            if not (_LNG_RANGE[0] <= longitude <= _LNG_RANGE[1]):
                raise ConfigurationInvalidValueError("longitude fuera de rango [-180, 180]")
        return cls(latitude, longitude, place_id.strip() if place_id else None)

    def is_set(self) -> bool:
        return self.latitude is not None or bool(self.place_id)
