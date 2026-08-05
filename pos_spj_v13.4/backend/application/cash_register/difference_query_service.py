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
    status: str
    classification: str
    severity: str
    amount: Decimal
    tolerance_amount: Decimal
    recurrence_count: int
    explanation: str | None
    resolution: str | None


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
        return CashDifferenceDTO(
            row["id"], row["status"], row["classification"], row["severity"],
            Decimal(row["amount"]), Decimal(row["tolerance_amount"]),
            int(row["recurrence_count"]), row["explanation"], row["resolution"])
