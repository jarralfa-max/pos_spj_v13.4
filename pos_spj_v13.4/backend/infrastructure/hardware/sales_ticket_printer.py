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

COMPARATIVA main ↔ ERP (2026-10-16): el diseño ya no es fijo. Los bytes salen
del diseño de la versión ACTIVA de la plantilla (`TicketDesignQueryService`) con
el logo de la sucursal o de la empresa; un ticket ya emitido se reimprime con su
FOTO guardada (`print_document`). El boleto de sorteo tiene su propio diseño
(`SWEEPSTAKES_TICKET`): antes se convertía en un ticket de venta vacío y, por
leer `folio`/`nombre_sorteo` cuando Sorteos manda `ticket_number`/`raffle_name`,
salía SIN número de boleto.
"""

from __future__ import annotations

import logging
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
        #: Avisos del último ticket (logo/QR/código que no se pudieron imprimir).
        self.last_warnings: list[str] = []

    # ── contrato que usan los casos de uso de recibo ─────────────────────
    def compose_document(self, payload: dict[str, Any], *,
                         document_type: str = "SALE_TICKET") -> dict[str, Any]:
        """El documento a imprimir: diseño activo + marca de la sucursal +
        datos. Es lo que se guarda como foto del ticket (reimpresión idéntica)."""
        from backend.application.queries.document_output.ticket_design_query_service import (
            TicketDesignQueryService,
        )

        design = TicketDesignQueryService(self._conn)
        active = design.active_layout(document_type)
        branding = design.branding(self._branch_id)
        return {"document_type": document_type, "layout_json": active.layout.to_json(),
                "template_version_id": active.template_version_id,
                "layout_problem": active.problem, "header": branding.header,
                "logo_path": branding.logo_path, "payload": dict(payload)}

    def print_document(self, document: dict[str, Any],
                       on_success: Callable[[], None] | None = None,
                       on_error: Callable[[Exception], None] | None = None) -> str:
        job_id = new_uuid()
        try:
            self._deliver_document(document)
        except TicketPrintError as exc:
            logger.warning("Ticket %s no impreso: %s",
                           (document.get("payload") or {}).get("folio"), exc)
            if on_error:
                on_error(exc)
            raise
        if on_success:
            on_success()
        return job_id

    def print_ticket(self, ticket_data: dict[str, Any],
                     on_success: Callable[[], None] | None = None,
                     on_error: Callable[[Exception], None] | None = None) -> str:
        return self.print_document(self.compose_document(ticket_data),
                                   on_success=on_success, on_error=on_error)

    def print_raffle_ticket(self, raffle_ticket_data: dict[str, Any], on_success=None,
                            on_error=None) -> str:
        """El boleto de sorteo con SU diseño (`SWEEPSTAKES_TICKET`): nombre del
        sorteo, número de boleto en grande, premio, fecha del sorteo, código."""
        data = raffle_ticket_data
        payload = {
            "raffle_name": data.get("raffle_name") or data.get("nombre_sorteo")
            or data.get("sorteo") or "",
            "ticket_number": data.get("ticket_number") or data.get("folio")
            or data.get("codigo") or "",
            "prize": data.get("prize") or "", "draw_date": data.get("draw_date") or "",
            "cliente": data.get("cliente") or data.get("customer_name") or "",
            "sale_folio": data.get("sale_folio") or "",
        }
        return self.print_document(self.compose_document(
            payload, document_type="SWEEPSTAKES_TICKET"), on_success=on_success,
            on_error=on_error)

    def print_test(self, layout_json: str, *, document_type: str = "SALE_TICKET") -> list[str]:
        """«Imprimir prueba» del diseñador: el diseño que se está editando con
        datos de ejemplo, en la impresora de esta sucursal. Devuelve los avisos."""
        from backend.domain.document_output.ticket_layout import layout_for_document_type
        from backend.infrastructure.printing.ticket_sample import sample_payload

        document = self.compose_document(
            sample_payload(layout_for_document_type(document_type)), document_type=document_type)
        document["layout_json"] = layout_json
        self.print_document(document)
        return list(self.last_warnings)

    # ── interno ──────────────────────────────────────────────────────────
    def _deliver_document(self, document: dict[str, Any]) -> None:
        from backend.domain.document_output.ticket_layout import parse
        from backend.infrastructure.printing.routed_printer import PrintTargetUnavailable, send
        from backend.infrastructure.printing.ticket_layout_renderer import render_ticket

        device, profile = self._resolve_device()
        rendered = render_ticket(parse(document["layout_json"]), document.get("payload") or {},
                                 header=document.get("header") or {},
                                 paper_width_mm=self._paper_width(profile),
                                 logo_path=document.get("logo_path"))
        self.last_warnings = list(rendered.warnings)
        try:
            send(device, profile, rendered.data, what="el ticket")
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
