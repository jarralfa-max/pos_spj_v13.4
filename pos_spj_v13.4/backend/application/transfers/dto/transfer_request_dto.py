"""Read DTOs for transfer request use cases."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransferRequestLineDTO:
    line_id: str
    product_id: str
    unit_id: str
    requested_quantity: Decimal
    requested_weight: Decimal
    pieces: Decimal
    notes: str | None


@dataclass(frozen=True, slots=True)
class TransferRequestDTO:
    transfer_id: str
    transfer_number: str
    status: str
    priority: str
    requested_by_user_id: str
    origin_branch_id: str | None
    origin_warehouse_id: str | None
    origin_location_id: str | None
    destination_branch_id: str | None
    destination_warehouse_id: str | None
    destination_location_id: str | None
    lines: tuple[TransferRequestLineDTO, ...]

