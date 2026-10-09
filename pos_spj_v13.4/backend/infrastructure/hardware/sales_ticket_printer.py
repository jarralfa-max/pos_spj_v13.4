"""SalesTicketPrinter — imprime el ticket de venta en la impresora que Document
Output asigna a la sucursal (§46: "Document Output administra plantilla,
render, impresión").

Es la pieza que faltaba tras borrar `core/services/printer_service.py`: cumple
el mismo contrato de dos métodos que `SalesReceiptClient` y los casos de uso de
recibo ya esperan (`print_ticket(payload, on_success, on_error) -> job_id` y
`print_raffle_ticket(payload)`), sin reconstruir la clase borrada:

1. resuelve el dispositivo con la MISMA ruta de Document Output que usan las
   etiquetas (`DocumentOutputPrintRoutingClient`, tipo ``SALE_TICKET``, por
   sucursal) — no un puerto escrito a mano (§18: nada de ``COM3``/``9600``);
2. compone los bytes con `render_sale_ticket` (ESC/POS);
3. los entrega con `PrintTransport`.

Una impresora sin configurar, apagada o sin papel es operación normal en un
mostrador: NO lanza. Avisa por `on_error` con un motivo que el cajero puede
leer, y la venta —que ya se cobró— no se toca.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Callable

from backend.domain.sales.exceptions import ReceiptPrintFailedError
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.sales.ticket_printer")

NO_PRINTER_MESSAGE = (
    "No hay impresora de tickets configurada para esta sucursal. "
    "Configúrala en Configuración → Dispositivos (ruta de impresión «Ticket de venta»).")


#: El ticket no se pudo entregar; el mensaje es para el cajero. Es el error de
#: dominio de Ventas para que el caso de uso lo devuelva como resultado tipado
#: (`RECEIPT_NOT_PRINTED`) en vez de dejarlo escapar a la pantalla.
TicketPrintError = ReceiptPrintFailedError


class SalesTicketPrinter:
    def __init__(self, connection, *, branch_id: str | None = None,
                 workstation_id: str | None = None) -> None:
        self._conn = connection
        self._branch_id = branch_id or None
        self._workstation_id = workstation_id or None

    # ── contrato que usan los casos de uso de recibo ─────────────────────
    def print_ticket(self, ticket_data: dict[str, Any],
                     on_success: Callable[[], None] | None = None,
                     on_error: Callable[[Exception], None] | None = None) -> str:
        job_id = new_uuid()
        try:
            self._deliver(ticket_data)
        except TicketPrintError as exc:
            logger.warning("Ticket %s no impreso: %s", ticket_data.get("folio"), exc)
            if on_error:
                on_error(exc)
            raise
        if on_success:
            on_success()
        return job_id

    def print_raffle_ticket(self, raffle_ticket_data: dict[str, Any], on_success=None,
                            on_error=None) -> str:
        """Un boleto de sorteo es otro ticket corto en la misma impresora."""
        payload = {
            "folio": raffle_ticket_data.get("folio") or raffle_ticket_data.get("codigo") or "",
            "fecha": raffle_ticket_data.get("fecha") or "",
            "cajero": "", "cliente": raffle_ticket_data.get("cliente") or "",
            "items": [], "totales": {},
            "fomo_messages": [str(raffle_ticket_data.get("nombre_sorteo")
                                  or raffle_ticket_data.get("sorteo") or "Boleto de sorteo")],
        }
        return self.print_ticket(payload, on_success=on_success, on_error=on_error)

    # ── interno ──────────────────────────────────────────────────────────
    def _deliver(self, ticket_data: dict[str, Any]) -> None:
        from backend.infrastructure.printing.routed_printer import PrintTargetUnavailable, send
        from backend.infrastructure.printing.sale_ticket_escpos_renderer import render_sale_ticket

        device, profile = self._resolve_device()
        data = render_sale_ticket(ticket_data, header=self._header(),
                                  paper_width_mm=self._paper_width(profile))
        try:
            send(device, profile, data, what="el ticket")
        except PrintTargetUnavailable as exc:
            raise TicketPrintError(str(exc)) from exc

    def _resolve_device(self):
        """Resolución compartida con Caja (`routed_printer`, 2026-10-07)."""
        from backend.domain.device_management.enums import PrintRouteModule
        from backend.domain.document_output.enums import DocumentType
        from backend.infrastructure.printing.routed_printer import (
            PrintTargetUnavailable,
            resolve_routed_device,
        )

        try:
            return resolve_routed_device(
                self._conn, DocumentType.SALE_TICKET.value, branch_id=self._branch_id,
                workstation_id=self._workstation_id, module=PrintRouteModule.SALES.value,
                no_printer_message=NO_PRINTER_MESSAGE)
        except PrintTargetUnavailable as exc:
            raise TicketPrintError(str(exc)) from exc

    @staticmethod
    def _paper_width(profile) -> int:
        from backend.infrastructure.printing.routed_printer import paper_width_mm

        return paper_width_mm(profile)

    def _header(self) -> dict[str, Any]:
        """Empresa y sucursal de Configuración → Empresa y sucursales. Lo que no
        esté capturado simplemente no se imprime."""
        header: dict[str, Any] = {}
        try:
            empresa = self._conn.execute(
                "SELECT commercial_name, legal_name FROM company_profiles WHERE active=1"
                " LIMIT 1").fetchone()
            if empresa:
                header["company_name"] = (empresa[0] or empresa[1] or "").strip()
            if self._branch_id:
                sucursal = self._conn.execute(
                    "SELECT name, address, phone, ticket_header, ticket_footer"
                    " FROM branch_profiles WHERE branch_id=?", (self._branch_id,)).fetchone()
                if sucursal:
                    header.update({
                        "branch_name": sucursal[0] or "", "address": sucursal[1] or "",
                        "phone": sucursal[2] or "", "header_text": sucursal[3] or "",
                        "footer_text": sucursal[4] or ""})
        except sqlite3.OperationalError:
            logger.info("Sin perfiles de empresa/sucursal: ticket sin encabezado")
        return header
