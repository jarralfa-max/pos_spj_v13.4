"""Return-to-origin workflow results."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransferReturnLineDTO:
    return_line_id: str
    transfer_line_id: str
    quantity: Decimal
    weight: Decimal
    pieces: Decimal
    received_quantity: Decimal
    received_weight: Decimal


@dataclass(frozen=True, slots=True)
class TransferReturnDTO:
    return_id: str
    transfer_id: str
    return_number: str
    reason: str
    status: str
    source_node: tuple[str | None, str | None, str | None]
    destination_node: tuple[str | None, str | None, str | None]
    custody_event_id: str | None
    lines: tuple[TransferReturnLineDTO, ...]
