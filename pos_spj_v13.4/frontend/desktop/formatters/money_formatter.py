"""Money formatter (es-MX). Works on Decimal/str/int; never on float identity."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

_SYMBOLS = {"MXN": "$", "USD": "US$", "EUR": "€"}


def format_money(value, currency_code: str = "MXN", *, show_code: bool = False) -> str:
    """``1234.5`` → ``$1,234.50``. Empty/invalid → ``—`` (never ``$0.00`` by accident)."""
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    symbol = _SYMBOLS.get(currency_code, "$")
    quantized = amount.quantize(Decimal("0.01"))
    text = f"{symbol}{quantized:,.2f}"
    return f"{text} {currency_code}" if show_code else text
