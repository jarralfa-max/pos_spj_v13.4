"""Impresión real del recibo de nómina como ticket (2026-10-14).

Misma vía que los cortes de Caja y el ticket de venta (`routed_printer`): la
impresora la asigna Document Output (ruta «Recibo de nómina» por sucursal), el
recibo se renderiza al ancho del papel del dispositivo y se entrega por
`PrintTransport`. Nada de puertos escritos a mano.
"""

from __future__ import annotations

from backend.domain.document_output.enums import DocumentType
from backend.infrastructure.hr.payroll_receipt_renderers import PayrollReceiptEscPosRenderer
from backend.infrastructure.printing.routed_printer import (
    paper_width_mm,
    resolve_routed_device,
    send,
)

NO_PAYROLL_PRINTER_MESSAGE = (
    "No hay impresora asignada al recibo de nómina en esta sucursal. Asígnala en "
    "Configuración → Dispositivos (ruta de impresión «Recibo de nómina»), o guarda "
    "los recibos en PDF.")


class PayrollReceiptPrinter:
    def __init__(self, connection) -> None:
        self._conn = connection

    def __call__(self, receipts, *, branch_id: str | None,
                 workstation_id: str | None = None) -> str:
        device, profile = resolve_routed_device(
            self._conn, DocumentType.PAYROLL_RECEIPT.value, branch_id=branch_id,
            workstation_id=workstation_id, module=None,
            no_printer_message=NO_PAYROLL_PRINTER_MESSAGE)
        data = PayrollReceiptEscPosRenderer(paper_width_mm=paper_width_mm(profile)).render(receipts)
        send(device, profile, data, what="el recibo de nómina")
        return device.code
