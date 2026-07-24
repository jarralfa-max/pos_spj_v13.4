"""Transfer discrepancy and authorized resolution results."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransferDifferenceDTO:
    difference_id: str
    transfer_id: str
    transfer_line_id: str
    difference_type: str
    status: str
    severity: str
    expected_quantity: Decimal
    actual_quantity: Decimal
    quantity_difference: Decimal
    expected_weight: Decimal
    actual_weight: Decimal
    weight_difference: Decimal
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransferDifferenceResolutionDTO:
    resolution_id: str
    difference_id: str
    resolution_type: str
    difference_status: str
    reason: str
    evidence: tuple[str, ...]
