"""Decimal-only money validation for Pedidos/Delivery. Mirrors
backend/domain/sales/value_objects/money.py exactly — same validation shape,
own exception type."""
from decimal import Decimal

from backend.domain.orders_delivery.exceptions import InvalidOrderMoneyError


def money(value: Decimal, *, allow_zero: bool = True, allow_negative: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise InvalidOrderMoneyError("Pedidos/Delivery monetary values require Decimal, never float")
    if not value.is_finite():
        raise InvalidOrderMoneyError("Monetary value must be finite")
    if not allow_negative and value < 0:
        raise InvalidOrderMoneyError("Monetary value cannot be negative")
    if not allow_zero and value == 0:
        raise InvalidOrderMoneyError("Monetary value cannot be zero")
    return value
