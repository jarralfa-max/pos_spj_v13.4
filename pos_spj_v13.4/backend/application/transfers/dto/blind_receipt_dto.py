"""DTOs that deliberately omit expectations until a blind count is confirmed."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BlindReceiptObservedLineDTO:
    transfer_line_id: str
    observed_quantity: Decimal
    observed_weight: Decimal
    observed_pieces: Decimal = Decimal("0")
    temperature: Decimal | None = None
    expires_on: str | None = None


@dataclass(frozen=True, slots=True)
class BlindReceiptCountDTO:
    count_id: str
    transfer_id: str
    shipment_id: str
    status: str
    lines: tuple[BlindReceiptObservedLineDTO, ...]


@dataclass(frozen=True, slots=True)
class BlindReceiptComparisonLineDTO:
    transfer_line_id: str
    expected_quantity: Decimal
    observed_quantity: Decimal
    quantity_difference: Decimal
    expected_weight: Decimal
    observed_weight: Decimal
    weight_difference: Decimal


@dataclass(frozen=True, slots=True)
class ConfirmedBlindReceiptDTO:
    count_id: str
    receipt_id: str
    transfer_status: str
    status: str
    comparisons: tuple[BlindReceiptComparisonLineDTO, ...]
