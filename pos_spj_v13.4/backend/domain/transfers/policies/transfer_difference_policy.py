"""Configuration-driven tolerance and discrepancy classification policy."""
from __future__ import annotations

from decimal import Decimal

from ..enums import DifferenceType


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Transfer tolerances must use Decimal")
    return value if isinstance(value, Decimal) else Decimal(str(value))


class TransferDifferencePolicy:
    def __init__(self, *, quantity_tolerance: Decimal | str | int,
                 weight_tolerance: Decimal | str | int,
                 temperature_tolerance: Decimal | str | int) -> None:
        self.quantity_tolerance = _decimal(quantity_tolerance)
        self.weight_tolerance = _decimal(weight_tolerance)
        self.temperature_tolerance = _decimal(temperature_tolerance)
        if min(self.quantity_tolerance, self.weight_tolerance, self.temperature_tolerance) < 0:
            raise ValueError("Transfer tolerances cannot be negative")

    def classify(self, *, expected_quantity: Decimal | str | int,
                 actual_quantity: Decimal | str | int,
                 expected_weight: Decimal | str | int,
                 actual_weight: Decimal | str | int) -> tuple[DifferenceType, ...]:
        quantity_delta = _decimal(actual_quantity) - _decimal(expected_quantity)
        weight_delta = _decimal(actual_weight) - _decimal(expected_weight)
        detected: list[DifferenceType] = []
        if quantity_delta < -self.quantity_tolerance:
            detected.append(DifferenceType.SHORT_QUANTITY)
        elif quantity_delta > self.quantity_tolerance:
            detected.append(DifferenceType.OVER_QUANTITY)
        if abs(weight_delta) > self.weight_tolerance:
            detected.append(DifferenceType.WEIGHT_VARIANCE)
        return tuple(detected)

    def temperature_outside_tolerance(self, *, expected: Decimal | str | int,
                                      actual: Decimal | str | int) -> bool:
        return abs(_decimal(actual) - _decimal(expected)) > self.temperature_tolerance
