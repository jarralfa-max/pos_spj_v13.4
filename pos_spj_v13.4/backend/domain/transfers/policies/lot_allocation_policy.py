"""FEFO lot allocation for transfer reservations."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..exceptions import TransferLotAllocationError


ZERO = Decimal("0")


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Transfer lot allocation quantities must be Decimal")
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class LotAllocationCandidate:
    product_id: str
    lot_id: str
    location_id: str
    available_quantity: Decimal | str | int
    available_weight: Decimal | str | int = ZERO
    expires_at: str | None = None
    quality_status: str = "AVAILABLE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_quantity", _decimal(self.available_quantity))
        object.__setattr__(self, "available_weight", _decimal(self.available_weight))
        if not self.product_id or not self.lot_id or not self.location_id:
            raise ValueError("Lot allocation candidate requires product, lot, and location")
        if self.available_quantity < ZERO or self.available_weight < ZERO:
            raise TransferLotAllocationError("Lot allocation candidate cannot be negative")


@dataclass(frozen=True, slots=True)
class TransferLotAllocation:
    transfer_line_id: str
    product_id: str
    lot_id: str
    location_id: str
    quantity: Decimal
    weight: Decimal = ZERO
    expires_at: str | None = None


class LotAllocationPolicy:
    def allocate_fefo(
        self,
        *,
        transfer_line_id: str,
        product_id: str,
        required_quantity: Decimal | str | int,
        required_weight: Decimal | str | int = ZERO,
        candidates: tuple[LotAllocationCandidate, ...],
    ) -> tuple[TransferLotAllocation, ...]:
        required_quantity = _decimal(required_quantity)
        required_weight = _decimal(required_weight)
        if required_quantity <= ZERO:
            raise TransferLotAllocationError("FEFO allocation requires a positive quantity")
        remaining_quantity = required_quantity
        remaining_weight = required_weight
        allocations: list[TransferLotAllocation] = []
        ordered = sorted(
            (candidate for candidate in candidates
             if candidate.product_id == product_id and candidate.quality_status == "AVAILABLE"),
            key=lambda candidate: (candidate.expires_at is None, candidate.expires_at or "", candidate.lot_id),
        )
        for candidate in ordered:
            if remaining_quantity <= ZERO:
                break
            quantity = min(candidate.available_quantity, remaining_quantity)
            weight = ZERO
            if required_weight > ZERO:
                weight = min(candidate.available_weight, remaining_weight)
            allocations.append(TransferLotAllocation(
                transfer_line_id=transfer_line_id,
                product_id=product_id,
                lot_id=candidate.lot_id,
                location_id=candidate.location_id,
                quantity=quantity,
                weight=weight,
                expires_at=candidate.expires_at,
            ))
            remaining_quantity -= quantity
            remaining_weight -= weight
        if remaining_quantity != ZERO or remaining_weight > ZERO:
            raise TransferLotAllocationError("Available FEFO lots do not satisfy the requested reservation")
        return tuple(allocations)
