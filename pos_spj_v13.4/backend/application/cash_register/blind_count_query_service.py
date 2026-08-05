"""CASH-12 read model that hides expected cash unless explicitly authorized."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.infrastructure.db.repositories.cash_register.repositories import (
    CashCountRepository, CashLedgerRepository,
)


@dataclass(frozen=True, slots=True)
class BlindCountLineDTO:
    denomination_id: str
    display_name: str
    denomination: Decimal
    quantity: int
    subtotal: Decimal


@dataclass(frozen=True, slots=True)
class BlindCountDTO:
    id: str
    shift_id: str
    status: str
    total_counted: Decimal
    expected_cash: Decimal | None
    difference: Decimal | None
    locked: bool
    lines: tuple[BlindCountLineDTO, ...]


class BlindCountQueryService:
    def __init__(self, connection, authorization: CashAuthorizationPolicy) -> None:
        self._connection, self._auth = connection, authorization
        self._counts = CashCountRepository(connection)
        self._ledger = CashLedgerRepository(connection)

    def get(self, *, count_id: str, branch_id: str, requester_user_id: str,
            reveal_expected: bool = False) -> BlindCountDTO:
        count = self._counts.get(count_id)
        if not count or count["branch_id"] != branch_id:
            raise CashInvalidStateError("Conteo no encontrado en la sucursal")
        captured = {row["denomination_id"]: row for row in self._counts.list_denominations(count_id)}
        lines = tuple(
            BlindCountLineDTO(
                denomination_id=row["id"], display_name=row["display_name"],
                denomination=Decimal(row["denomination_value"]),
                quantity=int(captured.get(row["id"], {}).get("quantity", 0)),
                subtotal=Decimal(captured.get(row["id"], {}).get("subtotal", "0")))
            for row in self._counts.list_active_denominations())
        expected = difference = None
        if reveal_expected:
            if count["status"] != "CONFIRMED":
                raise CashInvalidStateError("El esperado sólo puede revelarse después de confirmar")
            self._auth.require(
                user_id=requester_user_id,
                permission_code=CashPermissions.BLIND_COUNT_REVEAL_EXPECTED,
                branch_id=branch_id)
            expected = sum((
                Decimal(row["amount"]) if row["direction"] == "INFLOW"
                else -Decimal(row["amount"])
                for row in self._ledger.list_for_shift(count["shift_id"])), Decimal("0"))
            difference = Decimal(count["total_counted"]) - expected
        return BlindCountDTO(
            count["id"], count["shift_id"], count["status"],
            Decimal(count["total_counted"]), expected, difference,
            count["status"] != "OPEN", lines)
