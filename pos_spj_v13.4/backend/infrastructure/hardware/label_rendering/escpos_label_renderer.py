"""Genera ESC/POS real para una `LabelDocument` en impresoras térmicas de
etiqueta (corte SET-14).

Los comandos y el rasterizado viven en `backend/infrastructure/printing/escpos.py`,
que reemplazó a `core/ticket_escpos_renderer.py`. La versión anterior de este
archivo llamaba a métodos PRIVADOS de aquella clase (`_sanitize_text`,
`_render_code39_as_image`, `_render_qr`); ahora usa funciones públicas, que es
lo que permite cambiar el rasterizado sin romper esto en silencio.

Las térmicas de etiqueta no suelen tener un comando de "cantidad de copias"
como el `^PQ` de ZPL, así que `copies` repite el bloque entero, cada copia
separada por su corte.
"""

from __future__ import annotations

from backend.domain.inventory.value_objects.label_document import LabelDocument
from backend.infrastructure.printing.escpos import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    BOLD_OFF,
    BOLD_ON,
    CUT_PARTIAL,
    DEFAULT_ENCODING,
    INIT,
    dots_for_paper_width,
    render_barcode,
    render_qr,
    sanitize_text,
)


def _render_one(document: LabelDocument, *, max_width_dots: int) -> bytes:
    buf = bytearray(INIT)
    buf += ALIGN_CENTER + BOLD_ON
    buf += (sanitize_text(document.title) + "\n").encode(DEFAULT_ENCODING, errors="replace")
    buf += BOLD_OFF + ALIGN_LEFT
    for line in document.lines:
        buf += (sanitize_text(line) + "\n").encode(DEFAULT_ENCODING, errors="replace")

    if document.barcode:
        raster = render_barcode(document.barcode, max_width_dots=max_width_dots)
        if raster:
            buf += ALIGN_CENTER + raster + b"\n"

    if document.qr_payload:
        raster = render_qr(document.qr_payload, max_width_dots=max_width_dots)
        if raster:
            buf += ALIGN_CENTER + raster + b"\n"

    buf += CUT_PARTIAL
    return bytes(buf)


def render_escpos_label(document: LabelDocument, *, copies: int, paper_width_mm: int = 58) -> bytes:
    one = _render_one(document, max_width_dots=dots_for_paper_width(paper_width_mm))
    return one * max(1, int(copies))
