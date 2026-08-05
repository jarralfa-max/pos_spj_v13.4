"""Read model and Decimal projections for CASH-8."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class LedgerReader(Protocol):
    def list_for_shift(self, shift_id: str) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class LedgerRow:
    id: str
    recorded_at: str
    movement_type: str
    concept: str
    direction: str
    amount: Decimal
    balance: Decimal
    reversal_of_id: str | None


@dataclass(frozen=True, slots=True)
class LedgerProjection:
    shift_id: str
    balance: Decimal
    inflows: Decimal
    outflows: Decimal
    movement_count: int
    rows: tuple[LedgerRow, ...]


class CashLedgerQueryService:
    def __init__(self, reader: LedgerReader) -> None:
        self._reader = reader

    def projection(self, shift_id: str) -> LedgerProjection:
        balance = inflows = outflows = Decimal("0")
        rows: list[LedgerRow] = []
        for item in self._reader.list_for_shift(shift_id):
            amount = Decimal(item["amount"])
            if item["direction"] == "INFLOW":
                inflows += amount
                balance += amount
            else:
                outflows += amount
                balance -= amount
            rows.append(LedgerRow(
                id=item["id"], recorded_at=item["recorded_at"],
                movement_type=item["movement_type"], concept=item["concept"],
                direction=item["direction"], amount=amount, balance=balance,
                reversal_of_id=item["reversal_of_id"]))
        return LedgerProjection(shift_id, balance, inflows, outflows, len(rows), tuple(rows))
