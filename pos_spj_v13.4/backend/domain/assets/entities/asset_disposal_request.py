"""AssetDisposalRequest — the baja workflow (ASSET-12, §46, §48).

Never change status to "baja" via a direct UPDATE (§46 forbids it explicitly)
— every disposal goes through this guarded state machine:

    REQUESTED -> UNDER_REVIEW -> APPROVED -> IN_PROGRESS -> COMPLETED
                               -> REJECTED
    any non-terminal -> CANCELLED

§84: quien solicita una baja no debe aprobarla — enforced literally, same
pattern as AssetTransfer.receive(). Loss/theft (§48) requires extra evidence
fields, validated when reason is LOSS or THEFT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetDisposalReason, AssetDisposalRequestStatus
from backend.domain.assets.exceptions import AssetDisposalNotAllowedError, AssetDomainError
from backend.domain.assets.exceptions import SegregationOfDutiesError
from backend.shared.ids import new_uuid

_TERMINAL = frozenset({
    AssetDisposalRequestStatus.COMPLETED, AssetDisposalRequestStatus.REJECTED,
    AssetDisposalRequestStatus.CANCELLED,
})
_LOSS_OR_THEFT = frozenset({AssetDisposalReason.LOSS, AssetDisposalReason.THEFT})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetDisposalRequest:
    id: str
    asset_id: str
    reason: AssetDisposalReason
    requested_by: str
    justification: str
    operation_id: str
    status: AssetDisposalRequestStatus = AssetDisposalRequestStatus.REQUESTED
    reviewed_by: str | None = None
    decision_notes: str = ""
    last_known_location_id: str | None = None
    last_custodian_user_id: str | None = None
    evidence_reference: str | None = None
    requested_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, reason: AssetDisposalReason, requested_by: str,
               justification: str, operation_id: str, *,
               last_known_location_id: str | None = None,
               last_custodian_user_id: str | None = None,
               evidence_reference: str | None = None) -> "AssetDisposalRequest":
        if not asset_id:
            raise AssetDomainError("AssetDisposalRequest.asset_id is required")
        if not requested_by:
            raise AssetDomainError("AssetDisposalRequest.requested_by is required")
        if not justification or not justification.strip():
            raise AssetDomainError("AssetDisposalRequest.justification is required")
        if reason in _LOSS_OR_THEFT and not (last_known_location_id or last_custodian_user_id):
            raise AssetDomainError(
                "Pérdida/robo (§48) requiere última ubicación o último custodio conocido")
        return cls(
            id=new_uuid(), asset_id=asset_id, reason=reason, requested_by=requested_by,
            justification=justification.strip(), operation_id=operation_id,
            last_known_location_id=last_known_location_id,
            last_custodian_user_id=last_custodian_user_id,
            evidence_reference=evidence_reference,
        )

    def _assert_status(self, *allowed: AssetDisposalRequestStatus) -> None:
        if self.status not in allowed:
            raise AssetDisposalNotAllowedError(
                f"No se puede continuar la solicitud de baja en estado {self.status.value}")

    def begin_review(self) -> None:
        self._assert_status(AssetDisposalRequestStatus.REQUESTED)
        self.status = AssetDisposalRequestStatus.UNDER_REVIEW

    def approve(self, approved_by: str, decision_notes: str = "") -> None:
        self._assert_status(AssetDisposalRequestStatus.UNDER_REVIEW)
        if not approved_by:
            raise AssetDomainError("AssetDisposalRequest.approve requires an approver")
        if approved_by == self.requested_by:
            # §84: quien solicita una baja no debe aprobarla.
            raise SegregationOfDutiesError(
                "Quien solicitó la baja no puede aprobar su propia solicitud")
        self.reviewed_by = approved_by
        self.decision_notes = decision_notes
        self.status = AssetDisposalRequestStatus.APPROVED

    def reject(self, reviewed_by: str, decision_notes: str = "") -> None:
        self._assert_status(AssetDisposalRequestStatus.UNDER_REVIEW)
        if not reviewed_by:
            raise AssetDomainError("AssetDisposalRequest.reject requires a reviewer")
        self.reviewed_by = reviewed_by
        self.decision_notes = decision_notes
        self.status = AssetDisposalRequestStatus.REJECTED

    def start_execution(self) -> None:
        self._assert_status(AssetDisposalRequestStatus.APPROVED)
        self.status = AssetDisposalRequestStatus.IN_PROGRESS

    def complete(self) -> None:
        self._assert_status(AssetDisposalRequestStatus.IN_PROGRESS)
        self.status = AssetDisposalRequestStatus.COMPLETED

    def cancel(self, reason: str = "") -> None:
        if self.status in _TERMINAL:
            raise AssetDisposalNotAllowedError(
                f"No se puede cancelar una solicitud de baja en estado {self.status.value}")
        self.status = AssetDisposalRequestStatus.CANCELLED
        if reason:
            self.decision_notes = f"{self.decision_notes}\n[CANCELLED] {reason}".strip()
