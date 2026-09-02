"""render_escpos_label — real ESC/POS generation for a `LabelDocument`
on thermal label printers (SET-14 cutover). Reuses
`core.ticket_escpos_renderer`'s already-live command constants and its
Code-128/QR-to-raster rendering (`TicketESCPOSRenderer._render_code39_as_image`/
`_render_qr`, both real, in production for tickets) rather than
duplicating that raster-generation logic.

Thermal label printers typically have no native "print quantity" command
the way ZPL's `^PQ` does, so `copies` is a real caller-side repeat of the
whole rendered block (each copy separated by a cut).
"""

from __future__ import annotations

from core.ticket_escpos_renderer import ALIGN_CENTER, ALIGN_LEFT, BOLD_OFF, BOLD_ON, CUT_PARTIAL, INIT, TicketESCPOSRenderer
from backend.domain.inventory.value_objects.label_document import LabelDocument


def _render_one(document: LabelDocument, renderer: TicketESCPOSRenderer) -> bytes:
    buf = bytearray(INIT)
    buf += ALIGN_CENTER + BOLD_ON
    buf += (renderer._sanitize_text(document.title) + "\n").encode(renderer.encoding, errors="replace")
    buf += BOLD_OFF + ALIGN_LEFT
    for line in document.lines:
        buf += (renderer._sanitize_text(line) + "\n").encode(renderer.encoding, errors="replace")

    if document.barcode:
        raster = renderer._render_code39_as_image(document.barcode)
        if raster:
            buf += ALIGN_CENTER + raster + b"\n"

    if document.qr_payload:
        raster = renderer._render_qr(document.qr_payload)
        if raster:
            buf += ALIGN_CENTER + raster + b"\n"

    buf += CUT_PARTIAL
    return bytes(buf)


def render_escpos_label(document: LabelDocument, *, copies: int, paper_width_mm: int = 58) -> bytes:
    renderer = TicketESCPOSRenderer(paper_width_mm=paper_width_mm)
    one = _render_one(document, renderer)
    return one * max(1, int(copies))
