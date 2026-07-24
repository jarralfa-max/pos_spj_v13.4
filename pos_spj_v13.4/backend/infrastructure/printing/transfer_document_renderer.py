"""Deterministic HTML renderer for transfer, shipment, receipt, and picking docs."""
from html import escape
import re

from backend.application.transfers.printing import (
    TransferPrintArtifact, TransferPrintDocument,
)


class TransferDocumentHtmlRenderer:
    def render(self, document: TransferPrintDocument) -> TransferPrintArtifact:
        fields = "".join(
            f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>"
            for label, value in document.fields)
        rows = "".join(
            "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
            for row in document.lines)
        html = (
            "<!doctype html><html lang='es'><meta charset='utf-8'>"
            f"<title>{escape(document.title)}</title><body>"
            f"<h1>{escape(document.title)}</h1><p>{escape(document.reference)}</p>"
            f"<dl>{fields}</dl><table><tbody>{rows}</tbody></table></body></html>"
        )
        return TransferPrintArtifact(
            html.encode("utf-8"), "text/html",
            f"{document.document_type.value.lower()}-{_filename_token(document.reference)}.html")


def _filename_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return token or "document"
