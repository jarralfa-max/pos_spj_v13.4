"""Deterministic renderers for canonical cash register print documents."""

from __future__ import annotations

from html import escape
import re
import unicodedata

from backend.application.cash_register.printing import (
    CashPrintArtifact,
    CashPrintDocument,
    CashPrintFormat,
)

INIT = b"\x1b@"
CUT_PARTIAL = b"\x1dVA\x00"


class CashDocumentHtmlRenderer:
    def render(self, document: CashPrintDocument) -> CashPrintArtifact:
        fields = "".join(
            f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>"
            for label, value in document.fields)
        lines = "".join(
            "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
            for row in document.lines)
        totals = "".join(
            f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>"
            for label, value in document.totals)
        markers = []
        if document.barcode_value:
            markers.append(f"<p>BARCODE:{escape(document.barcode_value)}</p>")
        if document.qr_value:
            markers.append(f"<p>QR:{escape(document.qr_value)}</p>")
        html = (
            "<!doctype html><html lang='es'><meta charset='utf-8'>"
            f"<title>{escape(document.title)}</title><body>"
            f"<h1>{escape(document.title)}</h1>"
            f"<p>{escape(document.reference)}</p>"
            f"<dl>{fields}</dl><table><tbody>{lines}</tbody></table>"
            f"<dl>{totals}</dl>{''.join(markers)}</body></html>"
        )
        return CashPrintArtifact(
            content=html.encode("utf-8"),
            media_type="text/html",
            filename=f"{document.document_type.value.lower()}-{_filename_token(document.reference)}.html",
            format=CashPrintFormat.HTML,
        )


class CashDocumentEscPosRenderer:
    def __init__(self, *, paper_width_mm: int = 58, encoding: str = "cp850") -> None:
        self._width = 48 if int(paper_width_mm) >= 80 else 32
        self._encoding = encoding

    def render(self, document: CashPrintDocument) -> CashPrintArtifact:
        text = self.render_text_preview(document)
        return CashPrintArtifact(
            content=INIT + text.encode(self._encoding, errors="replace") + b"\n" + CUT_PARTIAL,
            media_type="application/vnd.escpos",
            filename=f"{document.document_type.value.lower()}-{_filename_token(document.reference)}.bin",
            format=CashPrintFormat.ESC_POS,
        )

    def render_text_preview(self, document: CashPrintDocument) -> str:
        lines = [
            _center(_clean(document.title).upper(), self._width),
            _center(_clean(document.reference), self._width),
            "-" * self._width,
        ]
        for label, value in document.fields:
            lines.extend(_wrap_pair(label, value, self._width))
        if document.lines:
            lines.append("-" * self._width)
            for row in document.lines:
                lines.extend(_wrap_text("  ".join(_clean(value) for value in row), self._width))
        if document.totals:
            lines.append("-" * self._width)
            for label, value in document.totals:
                lines.extend(_wrap_pair(label, value, self._width))
        if document.barcode_value:
            lines.append(f"BARCODE:{_clean(document.barcode_value)}")
        if document.qr_value:
            lines.append(f"QR:{_clean(document.qr_value)}")
        return "\n".join(lines)


def _filename_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return token or "cash-document"


def _clean(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return text.encode("ascii", errors="ignore").decode("ascii")


def _center(value: str, width: int) -> str:
    return value[:width].center(width)


def _wrap_text(value: str, width: int) -> list[str]:
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _wrap_pair(label: str, value: str, width: int) -> list[str]:
    return _wrap_text(f"{_clean(label)}: {_clean(value)}", width)
