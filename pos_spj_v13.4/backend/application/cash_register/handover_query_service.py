"""Read model for CASH-16 value handovers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class HandoverReader(Protocol):
    def list_for_branch(self, *, branch_id: str, limit: int = 100) -> list[dict]: ...
    def list_denominations(self, handover_id: str) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class CashHandoverRow:
    id: str
    shift_id: str
    amount: Decimal
    status: str
    prepared_by: str
    delivered_by: str
    received_by: str
    prepared_at: str
    delivered_at: str
    received_at: str
    dispute_reason: str


class CashHandoverQueryService:
    def __init__(self, reader: HandoverReader) -> None:
        self._reader = reader

    def list_for_branch(self, branch_id: str) -> tuple[CashHandoverRow, ...]:
        if not str(branch_id or "").strip():
            return ()
        return tuple(
            CashHandoverRow(
                id=str(row["id"]),
                shift_id=str(row["shift_id"]),
                amount=Decimal(str(row["amount"])),
                status=str(row["status"]),
                prepared_by=str(row.get("prepared_by") or ""),
                delivered_by=str(row.get("delivered_by") or ""),
                received_by=str(row.get("received_by") or ""),
                prepared_at=str(row.get("prepared_at") or ""),
                delivered_at=str(row.get("delivered_at") or ""),
                received_at=str(row.get("received_at") or ""),
                dispute_reason=str(row.get("dispute_reason") or ""),
            )
            for row in self._reader.list_for_branch(branch_id=branch_id)
        )

    def denomination_quantities(self, handover_id: str) -> dict[str, int]:
        return {
            str(row["denomination_id"]): int(row["quantity"])
            for row in self._reader.list_denominations(handover_id)
        }
