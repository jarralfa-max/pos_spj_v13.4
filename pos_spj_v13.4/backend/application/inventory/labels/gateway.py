"""InventoryPrintGateway — the outbound print port (INV-26).

The label print service decides *what* to print (renders a LabelDocument), checks
the permission and audits the print; the gateway turns the document into printer
bytes (ZPL / ESC-POS) and delivers it. Production wires a gateway that fans out to
the configured printers; the in-memory one records prints for tests and offline
setups. A ``PrintDeliveryError`` marks a print as FAILED (audited, never crashes).
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.inventory.enums import LabelFormat
from backend.domain.inventory.value_objects.label_document import LabelDocument


class PrintDeliveryError(Exception):
    """Raised by a gateway when a label could not be delivered to the printer."""


class InventoryPrintGateway(Protocol):
    def print(self, *, document: LabelDocument, printer_ref: str,
              label_format: LabelFormat, copies: int) -> None: ...


class InMemoryPrintGateway:
    """Records printed labels; used in tests and offline/single-node setups."""

    def __init__(self) -> None:
        self.printed: list[dict] = []

    def print(self, *, document: LabelDocument, printer_ref: str,
              label_format: LabelFormat, copies: int) -> None:
        self.printed.append({
            "label_type": document.label_type.value,
            "title": document.title, "lines": list(document.lines),
            "barcode": document.barcode, "qr_payload": document.qr_payload,
            "entity_ref": document.entity_ref, "printer_ref": printer_ref,
            "label_format": label_format.value, "copies": copies})
