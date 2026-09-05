"""AssetPhysicalInventoryLine — one scan result within a physical count (ASSET-11, §44).

A line never auto-corrects the asset record — a non-FOUND result is evidence
that feeds an ``AssetPhysicalDiscrepancy`` (see asset_physical_discrepancy.py),
never a silent write to the Asset itself (§45).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetScanResult
from backend.domain.assets.exceptions import AssetDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetPhysicalInventoryLine:
    id: str
    physical_inventory_id: str
    scanned_code: str
    result: AssetScanResult
    scanned_by: str
    asset_id: str | None = None
    scanned_location_id: str | None = None
    notes: str = ""
    scanned_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, physical_inventory_id: str, scanned_code: str, result: AssetScanResult,
               scanned_by: str, *, asset_id: str | None = None,
               scanned_location_id: str | None = None,
               notes: str = "") -> "AssetPhysicalInventoryLine":
        if not physical_inventory_id:
            raise AssetDomainError("AssetPhysicalInventoryLine.physical_inventory_id is required")
        if not scanned_code:
            raise AssetDomainError("AssetPhysicalInventoryLine.scanned_code is required")
        if not scanned_by:
            raise AssetDomainError("AssetPhysicalInventoryLine.scanned_by is required")
        if result is not AssetScanResult.UNREGISTERED and not asset_id:
            raise AssetDomainError(
                "AssetPhysicalInventoryLine requires asset_id unless result is UNREGISTERED")
        return cls(id=new_uuid(), physical_inventory_id=physical_inventory_id,
                    scanned_code=scanned_code, result=result, scanned_by=scanned_by,
                    asset_id=asset_id, scanned_location_id=scanned_location_id, notes=notes)

    def is_clean(self) -> bool:
        return self.result is AssetScanResult.FOUND
