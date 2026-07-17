"""Address formatter — assembles a readable one-line address from parts (es-MX)."""

from __future__ import annotations

from typing import Mapping

_ORDER = ("street", "exterior_number", "interior_number", "neighborhood",
          "city", "state", "postal_code")


def format_address(parts: Mapping[str, str] | None) -> str:
    """Join available address parts into ``Calle 12 int 3, Centro, Puebla, 72000``."""
    if not parts:
        return "—"
    street = str(parts.get("street", "") or "").strip()
    ext = str(parts.get("exterior_number", "") or "").strip()
    interior = str(parts.get("interior_number", "") or "").strip()
    line1 = " ".join(x for x in (street, ext) if x)
    if interior:
        line1 = f"{line1} int {interior}" if line1 else f"int {interior}"
    tail = [str(parts.get(k, "") or "").strip()
            for k in ("neighborhood", "city", "state", "postal_code")]
    segments = [seg for seg in ([line1] + tail) if seg]
    return ", ".join(segments) if segments else "—"
