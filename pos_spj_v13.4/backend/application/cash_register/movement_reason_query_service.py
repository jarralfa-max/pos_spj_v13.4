"""Read model for active cash movement reason catalogs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


class MovementReasonReader(Protocol):
    def list_active(self, *, movement_type: str, occurred_at: str) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class CashMovementReasonOption:
    code: str
    display_name: str
    movement_type: str
    requires_authorization: bool


class CashMovementReasonQueryService:
    def __init__(self, reader: MovementReasonReader) -> None:
        self._reader = reader

    def list_active(self, movement_type: str) -> tuple[CashMovementReasonOption, ...]:
        movement_type = str(movement_type or "").strip().upper()
        if not movement_type:
            return ()
        occurred_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return tuple(
            CashMovementReasonOption(
                code=str(row["code"]),
                display_name=str(row["display_name"]),
                movement_type=str(row["movement_type"]),
                requires_authorization=bool(row["requires_authorization"]),
            )
            for row in self._reader.list_active(movement_type=movement_type, occurred_at=occurred_at)
        )
