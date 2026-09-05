"""AssetMeterReading — a single point-in-time reading of an AssetMeter (ASSET-8, §39)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.assets.exceptions import AssetDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetMeterReading:
    id: str
    meter_id: str
    asset_id: str
    reading_value: Decimal
    recorded_by: str
    operation_id: str
    reading_at: str = field(default_factory=_utcnow)
    notes: str = ""

    @classmethod
    def create(cls, meter_id: str, asset_id: str, reading_value: Decimal, recorded_by: str,
               operation_id: str, *, notes: str = "") -> "AssetMeterReading":
        if not meter_id or not asset_id:
            raise AssetDomainError("AssetMeterReading requires meter_id and asset_id")
        if isinstance(reading_value, float):
            raise AssetDomainError("AssetMeterReading.reading_value must not be float")
        if reading_value < 0:
            raise AssetDomainError("AssetMeterReading.reading_value must not be negative")
        if not recorded_by:
            raise AssetDomainError("AssetMeterReading.recorded_by is required")
        return cls(id=new_uuid(), meter_id=meter_id, asset_id=asset_id,
                    reading_value=reading_value, recorded_by=recorded_by,
                    operation_id=operation_id, notes=notes)
