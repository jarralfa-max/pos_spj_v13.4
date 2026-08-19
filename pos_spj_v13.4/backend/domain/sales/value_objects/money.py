"""Decimal-only money validation for Sales/POS. Mirrors
backend/domain/cash_register/value_objects/money.py exactly — same
validation shape, own exception type."""
from decimal import Decimal

from backend.domain.sales.exceptions import InvalidMoneyValueError


def money(value: Decimal, *, allow_zero: bool = True, allow_negative: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise InvalidMoneyValueError("Sales/POS monetary values require Decimal, never float")
    if not value.is_finite():
        raise InvalidMoneyValueError("Monetary value must be finite")
    if not allow_negative and value < 0:
        raise InvalidMoneyValueError("Monetary value cannot be negative")
    if not allow_zero and value == 0:
        raise InvalidMoneyValueError("Monetary value cannot be zero")
    return value
