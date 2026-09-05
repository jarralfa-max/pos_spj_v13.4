"""AssetPhysicalDiscrepancy — workflow for a physical-count mismatch (ASSET-11, §45).

Detectada -> Revisión -> Investigación -> Resolución -> Aprobación (when applicable).
Never auto-corrected — every step is explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetDiscrepancyStatus, AssetScanResult
from backend.domain.assets.exceptions import (
    AssetDomainError,
    AssetPhysicalInventoryConflictError,
    SegregationOfDutiesError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetPhysicalDiscrepancy:
    id: str
    physical_inventory_id: str
    asset_id: str
    discrepancy_type: AssetScanResult
    operation_id: str
    status: AssetDiscrepancyStatus = AssetDiscrepancyStatus.DETECTED
    resolution_notes: str = ""
    resolved_by: str | None = None
    approved_by: str | None = None
    detected_at: str = field(default_factory=_utcnow)
    resolved_at: str | None = None

    @classmethod
    def create(cls, physical_inventory_id: str, asset_id: str, discrepancy_type: AssetScanResult,
               operation_id: str) -> "AssetPhysicalDiscrepancy":
        if not physical_inventory_id or not asset_id:
            raise AssetDomainError(
                "AssetPhysicalDiscrepancy requires physical_inventory_id and asset_id")
        if discrepancy_type is AssetScanResult.FOUND:
            raise AssetDomainError("AssetPhysicalDiscrepancy cannot be created for a FOUND result")
        return cls(id=new_uuid(), physical_inventory_id=physical_inventory_id,
                    asset_id=asset_id, discrepancy_type=discrepancy_type,
                    operation_id=operation_id)

    def _assert_status(self, *allowed: AssetDiscrepancyStatus) -> None:
        if self.status not in allowed:
            raise AssetPhysicalInventoryConflictError(
                f"No se puede continuar la diferencia en estado {self.status.value}")

    def begin_review(self) -> None:
        self._assert_status(AssetDiscrepancyStatus.DETECTED)
        self.status = AssetDiscrepancyStatus.UNDER_REVIEW

    def investigate(self) -> None:
        self._assert_status(AssetDiscrepancyStatus.UNDER_REVIEW)
        self.status = AssetDiscrepancyStatus.INVESTIGATING

    def resolve(self, resolved_by: str, resolution_notes: str) -> None:
        self._assert_status(AssetDiscrepancyStatus.UNDER_REVIEW, AssetDiscrepancyStatus.INVESTIGATING)
        if not resolved_by:
            raise AssetDomainError("AssetPhysicalDiscrepancy.resolve requires a resolver")
        if not resolution_notes or not resolution_notes.strip():
            raise AssetDomainError("AssetPhysicalDiscrepancy.resolve requires resolution_notes")
        self.resolved_by = resolved_by
        self.resolution_notes = resolution_notes.strip()
        self.status = AssetDiscrepancyStatus.RESOLVED
        self.resolved_at = _utcnow()

    def approve(self, approved_by: str) -> None:
        self._assert_status(AssetDiscrepancyStatus.RESOLVED)
        if not approved_by:
            raise AssetDomainError("AssetPhysicalDiscrepancy.approve requires an approver")
        if approved_by == self.resolved_by:
            raise SegregationOfDutiesError(
                "Quien resolvió la diferencia no puede aprobarla — §84 segregación de funciones")
        self.approved_by = approved_by
        self.status = AssetDiscrepancyStatus.APPROVED
