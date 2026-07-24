"""DTOs for transfer picking lists."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransferPickingListLineDTO:
    transfer_line_id: str
    product_id: str
    unit_id: str
    reserved_quantity: Decimal
    reserved_weight: Decimal
    picked_quantity: Decimal
    picked_weight: Decimal
    lot_required: bool
    temperature_at_pick: Decimal | None = None


@dataclass(frozen=True, slots=True)
class TransferPickingListDTO:
    transfer_id: str
    transfer_number: str
    status: str
    lines: tuple[TransferPickingListLineDTO, ...]
