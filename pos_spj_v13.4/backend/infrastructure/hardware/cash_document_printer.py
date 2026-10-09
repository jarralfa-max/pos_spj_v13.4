"""Impresión real de los documentos de Caja (CASH-26 bloque 2, 2026-10-07).

Medido: los Cortes X/Z se encolaban en `cash_print_jobs` con la impresora
literal ``"default-cash-printer"``, en HTML, y nada despachaba la cola; la
pantalla decía «enviado a impresión» y no salía papel. Ahora la impresora la
asigna Document Output (rutas «Corte X» / «Corte Z» por sucursal), el corte se
renderiza en ESC/POS al ancho del papel del dispositivo y
`DispatchCashPrintQueueUseCase` lo entrega con este adaptador, la misma vía
que el ticket de venta (`routed_printer`).
"""

from __future__ import annotations

from backend.application.cash_register.printing import CashQueuedPrintJob
from backend.infrastructure.printing.routed_printer import (
    PrintTargetUnavailable,
    load_device,
    paper_width_mm,
    resolve_routed_device,
    send,
)

NO_CASH_PRINTER_MESSAGE = (
    "No hay impresora asignada a los cortes de caja de esta sucursal. "
    "Asignala en Configuración → Dispositivos (rutas de impresión «Corte X» y «Corte Z»).")

ESC_POS_MEDIA_TYPE = "application/vnd.escpos"


def resolve_cash_printer(connection, document_type: str, *, branch_id: str,
                         workstation_id: str | None) -> tuple[str, int]:
    """(id del dispositivo, ancho de papel en mm) para ese documento de Caja."""
    device, profile = resolve_routed_device(
        connection, document_type, branch_id=branch_id, workstation_id=workstation_id,
        module=None, no_printer_message=NO_CASH_PRINTER_MESSAGE)
    return device.id, paper_width_mm(profile)


class CashDocumentPrinter:
    """`CashPrintGateway` sobre Dispositivos + `PrintTransport`."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def print_job(self, job: CashQueuedPrintJob) -> str | None:
        if job.media_type != ESC_POS_MEDIA_TYPE:
            raise PrintTargetUnavailable(
                "Este documento se generó para pantalla, no para la impresora de tickets.")
        device, profile = load_device(self._conn, job.printer_id,
                                      no_printer_message=NO_CASH_PRINTER_MESSAGE)
        for _ in range(job.copies):
            send(device, profile, job.content, what="el corte")
        return device.code
