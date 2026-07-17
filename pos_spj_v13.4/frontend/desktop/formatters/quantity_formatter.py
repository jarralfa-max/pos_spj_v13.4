"""Quantity formatter: amount + unit, with unit-aware precision."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

_DEFAULT_PRECISION = {"kg": 3, "g": 0, "l": 3, "ml": 0, "pza": 0, "pieza": 0,
                      "piezas": 0, "caja": 0, "cajas": 0}


def format_quantity(amount, unit: str | None = None, *, precision: int | None = None) -> str:
    """``12.5, "kg"`` → ``12.500 kg``; ``8, "piezas"`` → ``8 piezas``."""
    if amount is None or amount == "":
        return "—"
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        return str(amount)
    if precision is None:
        precision = _DEFAULT_PRECISION.get((unit or "").lower(), 2)
    quant = Decimal(1).scaleb(-precision) if precision > 0 else Decimal(1)
    text = f"{value.quantize(quant):,.{precision}f}"
    return f"{text} {unit}" if unit else text
