"""Date formatter (es-MX). Accepts date/datetime/ISO string."""

from __future__ import annotations

from datetime import date, datetime

_MONTHS_ES = ("", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
              "oct", "nov", "dic")


def _coerce(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def format_date(value, *, style: str = "short") -> str:
    """``date(2026,7,17)`` → ``17/07/2026`` (short) or ``17 jul 2026`` (medium)."""
    d = _coerce(value)
    if d is None:
        return "—" if (value is None or value == "") else str(value)
    if style == "medium":
        return f"{d.day:02d} {_MONTHS_ES[d.month]} {d.year}"
    if style == "iso":
        return d.isoformat()
    return f"{d.day:02d}/{d.month:02d}/{d.year}"
