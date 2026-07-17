"""Duration formatter — minutes → human ``Xh YYm`` / ``Xm`` / ``Xd`` (es-MX)."""

from __future__ import annotations


def format_duration(minutes) -> str:
    """``90`` → ``1h 30m``; ``45`` → ``45m``; ``0``/None → ``—``."""
    if minutes is None or minutes == "":
        return "—"
    try:
        total = int(minutes)
    except (ValueError, TypeError):
        return str(minutes)
    if total <= 0:
        return "—"
    days, rem = divmod(total, 60 * 24)
    hours, mins = divmod(rem, 60)
    chunks = []
    if days:
        chunks.append(f"{days}d")
    if hours:
        chunks.append(f"{hours}h")
    if mins or not chunks:
        chunks.append(f"{mins:02d}m" if (hours or days) else f"{mins}m")
    return " ".join(chunks)
