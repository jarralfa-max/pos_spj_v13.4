"""AssetTransfer — inter-branch/location transfer workflow (ASSET-5, §20).

Never change an asset's branch via a plain UPDATE (§20) — every relocation
across branches goes through this guarded state machine:
REQUESTED -> APPROVED -> PREPARED -> IN_TRANSIT -> RECEIVED
                                                  -> REJECTED (before shipping)
any non-terminal -> CANCELLED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetTransferStatus
from backend.domain.assets.exceptions import AssetDomainError, AssetTransferNotAllowedError
from backend.domain.assets.exceptions import SegregationOfDutiesError
from backend.shared.ids import new_uuid

_TERMINAL = frozenset({AssetTransferStatus.RECEIVED, AssetTransferStatus.REJECTED,
                        AssetTransferStatus.CANCELLED})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetTransfer:
    id: str
    asset_id: str
    source_branch_id: str
    destination_branch_id: str
    requested_by: str
    operation_id: str
    source_location_id: str | None = None
    destination_location_id: str | None = None
    approved_by: str | None = None
    shipped_by: str | None = None
    received_by: str | None = None
    condition_out: str | None = None
    condition_in: str | None = None
    notes: str = ""
    status: AssetTransferStatus = AssetTransferStatus.REQUESTED
    requested_at: str = field(default_factory=_utcnow)
    approved_at: str | None = None
    shipped_at: str | None = None
    received_at: str | None = None

    @classmethod
    def create(cls, asset_id: str, source_branch_id: str, destination_branch_id: str,
               requested_by: str, operation_id: str, *,
               source_location_id: str | None = None,
               destination_location_id: str | None = None,
               notes: str = "") -> "AssetTransfer":
        if not asset_id:
            raise AssetDomainError("AssetTransfer.asset_id is required")
        if not source_branch_id or not destination_branch_id:
            raise AssetDomainError("AssetTransfer requires source and destination branch")
        if source_branch_id == destination_branch_id:
            raise AssetDomainError("AssetTransfer source and destination branch must differ")
        if not requested_by:
            raise AssetDomainError("AssetTransfer.requested_by is required")
        return cls(
            id=new_uuid(), asset_id=asset_id, source_branch_id=source_branch_id,
            destination_branch_id=destination_branch_id, requested_by=requested_by,
            operation_id=operation_id, source_location_id=source_location_id,
            destination_location_id=destination_location_id, notes=notes,
        )

    def _assert_status(self, *allowed: AssetTransferStatus) -> None:
        if self.status not in allowed:
            raise AssetTransferNotAllowedError(
                f"No se puede continuar la transferencia en estado {self.status.value}")

    def approve(self, approved_by: str) -> None:
        self._assert_status(AssetTransferStatus.REQUESTED)
        if not approved_by:
            raise AssetDomainError("AssetTransfer.approve requires an approver")
        self.approved_by = approved_by
        self.status = AssetTransferStatus.APPROVED
        self.approved_at = _utcnow()

    def prepare(self) -> None:
        self._assert_status(AssetTransferStatus.APPROVED)
        self.status = AssetTransferStatus.PREPARED

    def ship(self, shipped_by: str, condition_out: str | None = None) -> None:
        self._assert_status(AssetTransferStatus.PREPARED)
        if not shipped_by:
            raise AssetDomainError("AssetTransfer.ship requires a shipped_by user")
        self.shipped_by = shipped_by
        self.condition_out = condition_out
        self.status = AssetTransferStatus.IN_TRANSIT
        self.shipped_at = _utcnow()

    def receive(self, received_by: str, condition_in: str | None = None) -> None:
        self._assert_status(AssetTransferStatus.IN_TRANSIT)
        if not received_by:
            raise AssetDomainError("AssetTransfer.receive requires a received_by user")
        if received_by == self.requested_by:
            # §84: quien solicita una transferencia no confirma su propia recepción.
            raise SegregationOfDutiesError(
                "Quien solicitó la transferencia no puede confirmar su propia recepción")
        self.received_by = received_by
        self.condition_in = condition_in
        self.status = AssetTransferStatus.RECEIVED
        self.received_at = _utcnow()

    def reject(self, reason: str = "") -> None:
        self._assert_status(AssetTransferStatus.REQUESTED, AssetTransferStatus.APPROVED)
        self.status = AssetTransferStatus.REJECTED
        if reason:
            self.notes = f"{self.notes}\n[REJECTED] {reason}".strip()

    def cancel(self, reason: str = "") -> None:
        if self.status in _TERMINAL:
            raise AssetTransferNotAllowedError(
                f"No se puede cancelar una transferencia en estado {self.status.value}")
        self.status = AssetTransferStatus.CANCELLED
        if reason:
            self.notes = f"{self.notes}\n[CANCELLED] {reason}".strip()
