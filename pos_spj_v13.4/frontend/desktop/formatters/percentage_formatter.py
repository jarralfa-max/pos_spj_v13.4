"""Percentage formatter. Distinguishes a display percent (16) from a ratio (0.16)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def format_percentage(value, *, is_ratio: bool = False, decimals: int = 1) -> str:
    """``16`` → ``16.0%``; ``0.16, is_ratio=True`` → ``16.0%``. Empty → ``—``."""
    if value is None or value == "":
        return "—"
    try:
        pct = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if is_ratio:
        pct = pct * 100
    quant = Decimal(1).scaleb(-decimals) if decimals > 0 else Decimal(1)
    return f"{pct.quantize(quant):,.{decimals}f}%"
