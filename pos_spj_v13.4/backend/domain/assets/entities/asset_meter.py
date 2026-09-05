"""AssetMeter — a usage meter attached to an asset (ASSET-8, §39).

Tracks the current cumulative reading; individual readings are recorded as
``AssetMeterReading`` (see asset_meter_reading.py). Can trigger a
METER_BASED MaintenancePlan in a later application-layer phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.assets.enums import AssetMeterType
from backend.domain.assets.exceptions import AssetDomainError, MeterReadingInvalidError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetMeter:
    id: str
    asset_id: str
    meter_type: AssetMeterType
    unit_label: str
    current_reading: Decimal = Decimal("0")
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, meter_type: AssetMeterType, unit_label: str) -> "AssetMeter":
        if not asset_id:
            raise AssetDomainError("AssetMeter.asset_id is required")
        if not unit_label or not unit_label.strip():
            raise AssetDomainError("AssetMeter.unit_label is required")
        return cls(id=new_uuid(), asset_id=asset_id, meter_type=meter_type,
                    unit_label=unit_label.strip())

    def advance_to(self, new_reading: Decimal) -> None:
        if isinstance(new_reading, float):
            raise AssetDomainError("AssetMeter.advance_to must not receive float")
        if new_reading < self.current_reading:
            raise MeterReadingInvalidError(
                f"La lectura {new_reading} es menor que la actual {self.current_reading}")
        self.current_reading = new_reading
        self.updated_at = _utcnow()
