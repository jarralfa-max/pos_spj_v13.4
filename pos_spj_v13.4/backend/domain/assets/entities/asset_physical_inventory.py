"""AssetPhysicalInventory — a physical count campaign (ASSET-11, §44).

DRAFT -> IN_PROGRESS -> REVIEW -> COMPLETED
any non-terminal -> CANCELLED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetPhysicalInventoryStatus
from backend.domain.assets.exceptions import (
    AssetDomainError,
    AssetPhysicalInventoryConflictError,
)
from backend.shared.ids import new_uuid

_TERMINAL = frozenset({AssetPhysicalInventoryStatus.COMPLETED, AssetPhysicalInventoryStatus.CANCELLED})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetPhysicalInventory:
    id: str
    branch_id: str
    started_by: str
    operation_id: str
    status: AssetPhysicalInventoryStatus = AssetPhysicalInventoryStatus.DRAFT
    started_at: str | None = None
    completed_at: str | None = None
    notes: str = ""
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, branch_id: str, started_by: str, operation_id: str) -> "AssetPhysicalInventory":
        if not branch_id:
            raise AssetDomainError("AssetPhysicalInventory.branch_id is required")
        if not started_by:
            raise AssetDomainError("AssetPhysicalInventory.started_by is required")
        return cls(id=new_uuid(), branch_id=branch_id, started_by=started_by,
                    operation_id=operation_id)

    def _assert_status(self, *allowed: AssetPhysicalInventoryStatus) -> None:
        if self.status not in allowed:
            raise AssetPhysicalInventoryConflictError(
                f"No se puede continuar el conteo en estado {self.status.value}")

    def start(self) -> None:
        self._assert_status(AssetPhysicalInventoryStatus.DRAFT)
        self.status = AssetPhysicalInventoryStatus.IN_PROGRESS
        self.started_at = _utcnow()

    def submit_for_review(self) -> None:
        self._assert_status(AssetPhysicalInventoryStatus.IN_PROGRESS)
        self.status = AssetPhysicalInventoryStatus.REVIEW

    def complete(self) -> None:
        self._assert_status(AssetPhysicalInventoryStatus.REVIEW)
        self.status = AssetPhysicalInventoryStatus.COMPLETED
        self.completed_at = _utcnow()

    def cancel(self, reason: str = "") -> None:
        if self.status in _TERMINAL:
            raise AssetPhysicalInventoryConflictError(
                f"No se puede cancelar un conteo en estado {self.status.value}")
        self.status = AssetPhysicalInventoryStatus.CANCELLED
        if reason:
            self.notes = f"{self.notes}\n[CANCELLED] {reason}".strip()

    def accepts_scans(self) -> bool:
        return self.status is AssetPhysicalInventoryStatus.IN_PROGRESS
