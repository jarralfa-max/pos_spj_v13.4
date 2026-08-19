"""SalesScaleGateway — Sales-side `ScaleGateway` (§18) backed by the one
real, working scale reader in this repository.

Research for this phase corrected SALES-0's framing: `modulos/ventas.py::
leer_peso()` does NOT ignore the HAL — it tries `HardwareService.
get_weight()` first and only falls back to a raw `serial.Serial` on COM3
when that HAL path is unavailable. `HardwareService.read_scale()` is the
ONE real, serial-backed scale reader in the repository; the newer
`backend.infrastructure.hardware.scale_gateway.ScaleGateway` Protocol
(Inventory's own §18 port, `StubScaleGateway`/`ManualScaleGateway`) has zero
serial-backed implementation of its own. Rather than write a second,
competing serial driver for Sales, this adapter implements that Protocol by
delegating the actual read to `HardwareService` — one real driver, two
Protocol-conformant fronts.

`HardwareService.read_scale()` returns `0.0` for "no valid reading"
(disabled, unconfigured, timeout, parse failure — all folded into the same
sentinel by the legacy driver, confirmed by reading it before wrapping it
here). This gateway raises `InvalidCatchWeightError` on that sentinel,
exactly like `StubScaleGateway.read()` raises when its queue is empty — the
Protocol's contract is "give me a reading or tell me you can't", never a
silent zero passed off as a real weight.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.inventory.enums import WeightCaptureSource
from backend.domain.inventory.exceptions import InvalidCatchWeightError
from backend.domain.inventory.value_objects.catch_weight import WeightReading
from core.services.hardware_service import HardwareService


class SalesScaleGateway:
    def __init__(self, hardware_service: HardwareService, *, device_id: str | None = None) -> None:
        self._hardware = hardware_service
        self._device_id = device_id

    def read(self) -> WeightReading:
        weight = self._hardware.read_scale()
        if not weight or weight <= 0:
            raise InvalidCatchWeightError("La báscula no devolvió una lectura válida")
        return WeightReading(
            gross=Decimal(str(weight)), stable=True,
            source=WeightCaptureSource.SCALE, device_id=self._device_id)
