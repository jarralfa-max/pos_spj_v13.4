"""Decimal-only money validation for Cash Register."""
from decimal import Decimal


def money(value: Decimal, *, allow_zero: bool = True) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise TypeError("Cash Register monetary values require Decimal")
    if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
        raise ValueError("Invalid Cash Register monetary value")
    return value

