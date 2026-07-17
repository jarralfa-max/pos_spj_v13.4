"""Time formatter — always 24h ``HH:mm``. Accepts time/datetime/ISO string."""

from __future__ import annotations

from datetime import datetime, time


def format_time(value) -> str:
    """``time(8,0)`` → ``08:00``; ``"2026-07-17T14:45:00"`` → ``14:45``."""
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        return f"{value.hour:02d}:{value.minute:02d}"
    if isinstance(value, time):
        return f"{value.hour:02d}:{value.minute:02d}"
    text = str(value)
    # ISO datetime or already HH:mm[:ss]
    if "T" in text:
        text = text.split("T", 1)[1]
    parts = text.strip().split(":")
    try:
        hh, mm = int(parts[0]), int(parts[1])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
    except (ValueError, IndexError):
        pass
    return text
