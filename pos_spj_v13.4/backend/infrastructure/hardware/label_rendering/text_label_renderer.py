"""render_text_label — plain-text rendering of a `LabelDocument`
(SET-14 cutover). Used for `LabelFormat.TEXT` and as a hardware-free
preview/fallback. Each copy is a readable block separated by a form feed
(`\\f`), matching how a text-mode label/receipt printer would treat it.
"""

from __future__ import annotations

from backend.domain.inventory.value_objects.label_document import LabelDocument


def _render_one(document: LabelDocument) -> str:
    lines = [document.title, *document.lines]
    if document.barcode:
        lines.append(f"[Código: {document.barcode}]")
    if document.qr_payload:
        lines.append(f"[QR: {document.qr_payload}]")
    return "\n".join(lines)


def render_text_label(document: LabelDocument, *, copies: int) -> bytes:
    block = _render_one(document)
    return "\f".join([block] * max(1, int(copies))).encode("utf-8")
