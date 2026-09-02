"""StabilityPolicy — SET-9 (§22): how many consecutive matching stable
readings a scale gateway must see before a weight is trusted. Not
persisted by this bounded context — the sensible source for its values
is a `ConfigurationValue` (Settings, SET-2) resolved per branch/device,
constructed fresh by the caller and handed to `evaluate_stability()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.device_management.exceptions import DeviceInvalidValueError


@dataclass(frozen=True, slots=True)
class StabilityPolicy:
    required_stable_readings: int = 2
    max_wait_seconds: Decimal = Decimal("5")
    tolerance: Decimal = Decimal("0.005")

    @classmethod
    def create(
        cls, *, required_stable_readings: int = 2, max_wait_seconds: Decimal = Decimal("5"),
        tolerance: Decimal = Decimal("0.005"),
    ) -> "StabilityPolicy":
        if isinstance(required_stable_readings, bool) or not isinstance(required_stable_readings, int) or required_stable_readings < 1:
            raise DeviceInvalidValueError(
                f"required_stable_readings debe ser un entero >= 1, recibido {required_stable_readings!r}"
            )
        for name, value in (("max_wait_seconds", max_wait_seconds), ("tolerance", tolerance)):
            if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
                raise DeviceInvalidValueError(f"{name} debe ser Decimal, nunca float")
            if value < 0:
                raise DeviceInvalidValueError(f"{name} no puede ser negativo, recibido {value!r}")
        return cls(required_stable_readings, max_wait_seconds, tolerance)
