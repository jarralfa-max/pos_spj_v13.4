"""ScaleGateway — the hardware boundary for weighing (§18).

The application never talks to a scale driver directly: it asks a ScaleGateway
for a stable ``WeightReading``. Concrete drivers (serial/USB/network scales) live
behind this Protocol; ``StubScaleGateway`` feeds preset readings for tests and
headless environments, and ``ManualScaleGateway`` turns an authorized manual
entry into a reading.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.domain.inventory.enums import WeightCaptureSource
from backend.domain.inventory.exceptions import InvalidCatchWeightError
from backend.domain.inventory.value_objects.catch_weight import WeightReading


@runtime_checkable
class ScaleGateway(Protocol):
    def read(self) -> WeightReading:
        """Return the current weight reading (may be unstable)."""
        ...


class StubScaleGateway:
    """Deterministic gateway for tests / headless use: replays queued readings."""

    def __init__(self, readings: list[WeightReading] | None = None) -> None:
        self._readings = list(readings or [])

    def queue(self, reading: WeightReading) -> None:
        self._readings.append(reading)

    def read(self) -> WeightReading:
        if not self._readings:
            raise InvalidCatchWeightError("No hay lectura de báscula disponible")
        return self._readings.pop(0)


class ManualScaleGateway:
    """Wraps an authorized manual entry as a scale reading (source MANUAL_AUTHORIZED)."""

    def __init__(self, *, gross, tare=0, unit: str = "KG",
                 device_id: str | None = None) -> None:
        self._reading = WeightReading(
            gross=gross, tare=tare, unit=unit, stable=True,
            source=WeightCaptureSource.MANUAL_AUTHORIZED, device_id=device_id)

    def read(self) -> WeightReading:
        return self._reading
