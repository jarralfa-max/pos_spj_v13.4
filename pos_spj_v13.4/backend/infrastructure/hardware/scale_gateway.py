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


class SicsScaleGateway:
    """MT-SICS SI: net weight, stable S / dynamic D. No device prices trusted.

    Reference: METTLER TOLEDO MT-SICS, SI (Send weight immediately).
    A serial connection is opened only on the hardware worker thread.
    """

    def __init__(self, serial_profile, *, device_id=None, serial_factory=None):
        self._profile = serial_profile
        self._device_id = device_id
        self._factory = serial_factory
        self._port = None

    request = b"SI\r\n"

    def _decode(self, raw):
        import re
        from decimal import Decimal
        match = re.fullmatch(rb"S\s+([SD])\s+([+-]?\d+(?:\.\d+)?)\s+(kg|g|lb|oz)\s*", raw)
        if not match:
            raise ValueError("Unsupported SICS response")
        return Decimal(match[2].decode("ascii")), match[3].decode("ascii").upper(), match[1] == b"S"

    def read(self):
        from datetime import datetime, timezone
        from decimal import Decimal
        import re
        if self._port is None:
            from serial import Serial
            p = self._profile
            self._port = (self._factory or Serial)(
                port=p.port, baudrate=p.baud_rate, bytesize=p.data_bits,
                parity=p.parity, stopbits=float(p.stop_bits),
                timeout=float(p.read_timeout_seconds), write_timeout=float(p.read_timeout_seconds))
        try:
            self._port.reset_input_buffer()
            self._port.write(self.request)
            raw = self._port.read_until(b"\n", 256)
            if not raw:
                raise TimeoutError("Scale did not respond")
            value, unit, stable = self._decode(raw)
            # SI reports NET. Tare is not reported by SI; never fabricate it.
            return WeightReading(gross=value,
                unit=unit, stable=stable,
                device_id=self._device_id, captured_at=datetime.now(timezone.utc).isoformat())
        except Exception:
            self.close()
            raise

    def close(self):
        if self._port is not None:
            self._port.close()
            self._port = None


class RhinoBar8RsScaleGateway(SicsScaleGateway):
    """BAR-8RS request P (manufacturer manual), using the persisted USB-COM profile.

    Only a complete, unit-tagged weight response is accepted. Never extract the
    first number from a multi-field price/amount frame. For frames without a
    stability marker, the application requires consecutive matching samples.
    Tare is not reported: the returned reading is net, not an invented gross.
    """
    request = b"P"

    def _decode(self, raw):
        import re
        from decimal import Decimal
        match = re.fullmatch(
            rb"\s*(?:(ST|US)[,\s]+)?(?:NT[,\s]+)?([+-]?\d+(?:\.\d+)?)\s*(kg|g|lb|oz)\s*",
            raw, flags=re.IGNORECASE)
        if not match:
            raise ValueError("Respuesta BAR-8RS no reconocida; confirmar formato del dispositivo")
        return (Decimal(match[2].decode("ascii")), match[3].decode("ascii").upper(),
                (match[1] or b"").upper() != b"US")
