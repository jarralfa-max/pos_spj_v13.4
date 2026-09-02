"""WeightReading — SET-9 (§22): one sample from a scale. Ephemeral by
design — scales stream many readings per second; only the *confirmed
stable* reading a caller decides to act on (§22 "estabilidad") is ever
meaningful to persist, and that's a use-case/audit concern outside this
bounded context, not a `WeightReading` table here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.device_management.enums import WeightUnit
from backend.domain.device_management.exceptions import DeviceInvalidValueError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class WeightReading:
    value: Decimal
    unit: WeightUnit
    stable: bool
    read_at: str

    @classmethod
    def create(
        cls, *, value: Decimal, unit: WeightUnit, stable: bool, at: datetime | None = None,
    ) -> "WeightReading":
        if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
            raise DeviceInvalidValueError("value debe ser Decimal, nunca float")
        if value < 0:
            raise DeviceInvalidValueError(f"value no puede ser negativo, recibido {value!r}")
        return cls(value=value, unit=unit, stable=bool(stable), read_at=(at or _utcnow()).isoformat(timespec="seconds"))
