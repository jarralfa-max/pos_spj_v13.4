"""Read-only receipt results for desktop and future API adapters."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransferReceiptLineDTO:
    transfer_line_id: str
    observed_quantity: Decimal
    observed_weight: Decimal
    accepted: bool
    observed_pieces: Decimal = Decimal("0")
    temperature: Decimal | None = None
    expires_on: str | None = None
    cold_chain_status: str = "COMPLIANT"
    quality_status: str = "AVAILABLE"


@dataclass(frozen=True, slots=True)
class TransferReceiptDTO:
    receipt_id: str
    transfer_id: str
    shipment_id: str
    transfer_status: str
    sync_status: str
    difference_ids: tuple[str, ...]
    lines: tuple[TransferReceiptLineDTO, ...]
