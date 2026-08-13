"""CASH-15 permission-aware difference projection."""
from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.infrastructure.db.repositories.cash_register.repositories import CashDifferenceRepository


@dataclass(frozen=True, slots=True)
class CashDifferenceDTO:
    id: str
    shift_id: str
    z_cut_id: str
    status: str
    classification: str
    severity: str
    amount: Decimal
    expected_amount: Decimal
    counted_amount: Decimal
    tolerance_amount: Decimal
    recurrence_count: int
    explanation: str | None
    resolution: str | None
    detected_by: str
    explained_by: str
    reviewed_by: str
    resolved_by: str


class CashDifferenceQueryService:
    def __init__(self, connection, authorization: CashAuthorizationPolicy) -> None:
        self._repo, self._auth = CashDifferenceRepository(connection), authorization

    def get(self, *, difference_id: str, branch_id: str,
            requester_user_id: str) -> CashDifferenceDTO:
        self._auth.require(user_id=requester_user_id,
                           permission_code=CashPermissions.DIFFERENCE_VIEW,
                           branch_id=branch_id)
        row = self._repo.get(difference_id)
        if not row or row["branch_id"] != branch_id:
            raise CashInvalidStateError("Diferencia no encontrada en la sucursal")
        return _dto(row)

    def list_for_branch(self, *, branch_id: str,
                        requester_user_id: str) -> tuple[CashDifferenceDTO, ...]:
        self._auth.require(user_id=requester_user_id,
                           permission_code=CashPermissions.DIFFERENCE_VIEW,
                           branch_id=branch_id)
        return tuple(_dto(row) for row in self._repo.list_for_branch(branch_id=branch_id))


def _dto(row: dict) -> CashDifferenceDTO:
    return CashDifferenceDTO(
        id=str(row["id"]),
        shift_id=str(row["shift_id"]),
        z_cut_id=str(row["z_cut_id"]),
        status=str(row["status"]),
        classification=str(row["classification"]),
        severity=str(row["severity"]),
        amount=Decimal(str(row["amount"])),
        expected_amount=Decimal(str(row["expected_amount"])),
        counted_amount=Decimal(str(row["counted_amount"])),
        tolerance_amount=Decimal(str(row["tolerance_amount"])),
        recurrence_count=int(row["recurrence_count"]),
        explanation=row.get("explanation"),
        resolution=row.get("resolution"),
        detected_by=str(row.get("detected_by") or ""),
        explained_by=str(row.get("explained_by") or ""),
        reviewed_by=str(row.get("reviewed_by") or ""),
        resolved_by=str(row.get("resolved_by") or ""),
    )
