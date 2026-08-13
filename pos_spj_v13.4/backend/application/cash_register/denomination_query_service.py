"""Read model for active cash denominations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class DenominationReader(Protocol):
    def list_active_denominations(self) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class CashDenominationOption:
    id: str
    display_name: str
    value: Decimal


class CashDenominationQueryService:
    def __init__(self, reader: DenominationReader) -> None:
        self._reader = reader

    def list_active(self) -> tuple[CashDenominationOption, ...]:
        return tuple(
            CashDenominationOption(
                id=str(row["id"]),
                display_name=str(row["display_name"]),
                value=Decimal(str(row["denomination_value"])),
            )
            for row in self._reader.list_active_denominations()
        )
