"""render_zpl — real Zebra ZPL II generation for a `LabelDocument`
(SET-14 cutover). Pure, text-based protocol — no imaging dependency,
unlike ESC/POS raster barcodes/QR (`escpos_label_renderer.py`).

Layout is fixed and simple (single-column, top-to-bottom): title, then
each body line, then an optional Code-128 barcode (`^BC`), then an
optional QR code (`^BQ`, model 2, error correction level A — the most
widely supported baseline). `^PQ` sets the print quantity so `copies`
is a real printer-side repeat, not a caller-side loop.

Never validated against physical hardware (no printer available in this
environment) — correctness here means protocol-correct ZPL, verified by
exact-string assertions in tests, not a live print.
"""

from __future__ import annotations

from backend.domain.inventory.value_objects.label_document import LabelDocument

_LEFT_MARGIN = 20
_LINE_HEIGHT = 30
_FONT_HEIGHT = 24
_FONT_WIDTH = 24


def _escape(text: str) -> str:
    # ZPL field data ends at ^FS / a caret / a tilde — strip characters
    # that would otherwise prematurely terminate or reinterpret the field.
    return str(text).replace("^", "").replace("~", "").replace("\n", " ")


def render_zpl(document: LabelDocument, *, copies: int) -> bytes:
    y = _LEFT_MARGIN
    parts: list[str] = ["^XA"]

    parts.append(f"^FO{_LEFT_MARGIN},{y}^A0N,30,30^FD{_escape(document.title)}^FS")
    y += _LINE_HEIGHT

    for line in document.lines:
        parts.append(f"^FO{_LEFT_MARGIN},{y}^A0N,{_FONT_HEIGHT},{_FONT_WIDTH}^FD{_escape(line)}^FS")
        y += _LINE_HEIGHT

    if document.barcode:
        parts.append("^BY2")
        parts.append(f"^FO{_LEFT_MARGIN},{y}^BCN,60,Y,N,N")
        parts.append(f"^FD{_escape(document.barcode)}^FS")
        y += 90

    if document.qr_payload:
        parts.append(f"^FO{_LEFT_MARGIN},{y}^BQN,2,4")
        parts.append(f"^FDLA,{_escape(document.qr_payload)}^FS")

    parts.append(f"^PQ{max(1, int(copies))}")
    parts.append("^XZ")
    return "".join(parts).encode("utf-8")
