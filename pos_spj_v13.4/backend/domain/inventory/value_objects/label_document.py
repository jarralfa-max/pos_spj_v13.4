"""LabelDocument — the immutable, format-agnostic label the print gateway renders.

INV-26. A renderer turns inventory data (a lot, a catch-weight capture, a transfer,
a count) into a ``LabelDocument``: a title, ordered body lines (es-MX), an optional
barcode/QR payload and a copy count. The gateway is responsible for turning it into
ZPL / ESC-POS / text — the document itself carries no printer bytes, so it stays a
pure value object (Decimal-safe, no float, no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.inventory.enums import LabelType


@dataclass(frozen=True)
class LabelDocument:
    label_type: LabelType
    title: str
    lines: tuple[str, ...] = field(default_factory=tuple)
    barcode: str | None = None       # Code-128 / EAN payload (product/lot code)
    qr_payload: str | None = None    # traceability / deep-link payload
    entity_ref: str | None = None    # lot_id / transfer_id / count_id (audit link)
    copies: int = 1

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("LabelDocument requiere un título")
        if int(self.copies) < 1:
            raise ValueError("LabelDocument requiere copies >= 1")
        object.__setattr__(self, "lines", tuple(self.lines))
