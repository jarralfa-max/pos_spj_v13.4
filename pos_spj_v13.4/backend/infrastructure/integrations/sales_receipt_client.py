"""SalesReceiptClient — Sales' integration point onto the real ticket
printer and print-job audit trail (POS-12/§46, §49-51; POS-17/§46: Receipt
DTO, PrintJob, Reprint, PDF).

Research for SALES-12 confirmed `core.services.printer_service.
PrinterService`/`PrintQueue` is complete, production-used (already the path
`modulos/ventas.py::_imprimir_ticket_consolidado` calls today) and already
owns its own retry/audit/EventBus notification — it does not need
`sales_outbox` integration. This client does not reimplement any of that;
it owns the one thing that is genuinely Sales' responsibility: composing a
`SaleReceiptDataDTO` from a `SaleDTO` (§46: "Ventas proporciona
SaleReceiptDataDTO... Document Output administra plantilla/render/
impresión") and translating it, at this one boundary only, into whatever
shape the legacy printer/PDF machinery actually expects.

Decimal -> float happens here and only here (same boundary discipline as
`SalesInventoryClient`/`SalesLoyaltyClient`): `PrinterService`'s renderer is
legacy-typed and never touches Sales' own Decimal totals directly.

**PDF — must render IDENTICAL output to what already prints today**, per
explicit user correction. `modulos/ventas.py::generar_html_ticket` (the
method the UI's own "save PDF" button calls) turned out NOT to be the only
real renderer in this repository: `core/services/sales_service.py`'s own
`_execute_sale_core` — the canonical, currently-live sale-completion path —
already builds a completed sale's ticket HTML via `core.engines.
template_engine.TicketTemplateEngine.generar_ticket()`, a genuinely
UI-independent engine (constructor takes a bare `db_conn`, no QWidget) that
reads the SAME `configuraciones.ticket_template_html` template the UI's
designer saves, with the SAME default-template fallback
(`SalesService._default_ticket_template()`) production already uses when
none is configured. `save_receipt_document()` below reuses that exact
engine and that exact fallback — not a simplified stand-in, not a second
competing implementation — so the saved document matches what
`SalesService` itself would have produced for the same sale. `core.
services.printer_service.save_ticket_pdf(html, filepath)` still does the
actual file write (worth knowing, found while reading it: despite its
name, it writes raw HTML bytes, not real PDF — a pre-existing characteristic
of that function, not this client's bug to fix).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from backend.application.sales.dto import (
    PrintJobStatusDTO,
    SaleDTO,
    SaleReceiptDataDTO,
    SaleReceiptLineDTO,
)
from backend.domain.document_output.value_objects.loyalty_summary import LoyaltySummary


class SalesReceiptClient:
    def __init__(self, printer_service=None, connection=None) -> None:
        self._printer = printer_service
        self._connection = connection

    @staticmethod
    def build_receipt_data(
        sale: SaleDTO, *, forma_pago: str, cajero_nombre: str,
        cliente_nombre: str = "Público General",
        efectivo_recibido: Decimal | None = None, cambio: Decimal | None = None,
    ) -> SaleReceiptDataDTO:
        lines = tuple(
            SaleReceiptLineDTO(
                name=str(line.product_snapshot.get("name") or line.product_snapshot.get("nombre")
                         or line.product_id),
                unit=line.quantity_unit, quantity=line.quantity,
                unit_price=line.unit_price, line_total=line.line_total,
            )
            for line in sale.lines
        )
        efectivo = efectivo_recibido if efectivo_recibido is not None else sale.total
        return SaleReceiptDataDTO(
            sale_id=sale.id, folio=sale.sale_number or sale.id, created_at=sale.created_at,
            cajero_nombre=cajero_nombre, cliente_nombre=cliente_nombre, lines=lines,
            subtotal=sale.gross_subtotal, discount_total=sale.discount_total,
            tax_total=sale.tax_total, total=sale.total, forma_pago=forma_pago,
            efectivo_recibido=efectivo,
            cambio=cambio if cambio is not None else max(Decimal("0"), efectivo - sale.total),
        )

    @staticmethod
    def build_receipt_data_from_sale(
        sale: SaleDTO, *, cajero_nombre: str, cliente_nombre: str = "Público General",
    ) -> SaleReceiptDataDTO:
        """POS-17 "Reprint": unlike `build_receipt_data` (used at the moment
        of checkout, when the caller already has `forma_pago`/`efectivo_
        recibido` on hand from the payment dialog), a reprint has no such
        context — it only has the historical `Sale` itself. Derives
        `forma_pago`/`efectivo_recibido`/`cambio` from `sale.payments`
        (SALES-13) instead of asking the caller to re-supply them."""
        lines = tuple(
            SaleReceiptLineDTO(
                name=str(line.product_snapshot.get("name") or line.product_snapshot.get("nombre")
                         or line.product_id),
                unit=line.quantity_unit, quantity=line.quantity,
                unit_price=line.unit_price, line_total=line.line_total,
            )
            for line in sale.lines
        )
        if sale.is_mixed_payment:
            forma_pago = "Mixto"
        elif len(sale.payments) == 1:
            forma_pago = sale.payments[0].method
        else:
            forma_pago = ""
        efectivo = sum((p.amount for p in sale.payments if p.method == "CASH"), Decimal("0"))
        cambio = max(Decimal("0"), sale.total_paid - sale.total) if efectivo else Decimal("0")
        return SaleReceiptDataDTO(
            sale_id=sale.id, folio=sale.sale_number or sale.id, created_at=sale.created_at,
            cajero_nombre=cajero_nombre, cliente_nombre=cliente_nombre, lines=lines,
            subtotal=sale.gross_subtotal, discount_total=sale.discount_total,
            tax_total=sale.tax_total, total=sale.total, forma_pago=forma_pago,
            efectivo_recibido=efectivo, cambio=cambio,
        )

    @staticmethod
    def _to_ticket_payload(
        receipt: SaleReceiptDataDTO, *,
        loyalty: LoyaltySummary | None = None, messages: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        payload = {
            "folio": receipt.folio,
            "venta_id": receipt.sale_id,
            "fecha": receipt.created_at,
            "cajero": receipt.cajero_nombre,
            "cliente": receipt.cliente_nombre,
            "items": [
                {
                    "nombre": line.name, "unidad": line.unit, "cantidad": float(line.quantity),
                    "precio_unitario": float(line.unit_price), "total": float(line.line_total),
                }
                for line in receipt.lines
            ],
            "totales": {
                "subtotal": float(receipt.subtotal),
                "descuento": float(receipt.discount_total),
                "impuestos": float(receipt.tax_total),
                "total_final": float(receipt.total),
            },
            "pago": {
                "forma_pago": receipt.forma_pago,
                "efectivo_recibido": float(receipt.efectivo_recibido),
                "cambio": float(receipt.cambio),
            },
        }
        if loyalty is not None:
            payload["loyalty"] = {
                "puntos_totales": loyalty.points_balance,
                "puntos_ganados": loyalty.points_earned,
                "nivel": loyalty.tier,
                "available": loyalty.available,
            }
        if messages:
            payload["fomo_messages"] = list(messages)
        return payload

    def print_receipt(
        self, sale: SaleDTO, *, forma_pago: str, cajero_nombre: str,
        cliente_nombre: str = "Público General",
        efectivo_recibido: Decimal | None = None, cambio: Decimal | None = None,
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> str:
        receipt = self.build_receipt_data(
            sale, forma_pago=forma_pago, cajero_nombre=cajero_nombre,
            cliente_nombre=cliente_nombre, efectivo_recibido=efectivo_recibido, cambio=cambio)
        return self.print_receipt_data(receipt, on_success=on_success, on_error=on_error)

    def print_receipt_data(
        self, receipt: SaleReceiptDataDTO, *,
        loyalty: LoyaltySummary | None = None, messages: tuple[str, ...] = (),
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> str:
        """POS-17 "Reprint": takes an already-built `SaleReceiptDataDTO`
        (e.g. reconstructed from a completed sale for a reprint) rather
        than requiring a fresh `SaleDTO` composition — reprinting doesn't
        need `forma_pago`/`efectivo_recibido` re-derived, they're already
        part of the original receipt data."""
        return self._printer.print_ticket(
            self._to_ticket_payload(receipt, loyalty=loyalty, messages=messages),
            on_success=on_success, on_error=on_error)

    def get_job_status(self, job_id: str) -> PrintJobStatusDTO | None:
        """POS-17 "PrintJob": a real query against `print_job_log`
        (populated by `PrintQueue._log_job_to_db` once the async worker
        finishes a job) — this client's constructor must be given a
        `connection` to use this method (print_ticket itself doesn't need
        one, hence it staying optional)."""
        if self._connection is None:
            raise RuntimeError("get_job_status requiere una connection")
        row = self._connection.execute(
            "SELECT job_id, estado, folio, reintentos, error_msg, finished_at"
            " FROM print_job_log WHERE job_id=? ORDER BY created_at DESC LIMIT 1",
            (job_id,)).fetchone()
        if row is None:
            return None
        return PrintJobStatusDTO(
            job_id=row["job_id"], status=row["estado"], folio=row["folio"] or "",
            retries=int(row["reintentos"] or 0), error_msg=row["error_msg"] or "",
            finished_at=row["finished_at"],
        )

    def save_receipt_document(self, receipt: SaleReceiptDataDTO, filepath: str) -> str:
        """POS-17 "PDF" — renders through the REAL `TicketTemplateEngine`
        (the same engine `SalesService._execute_sale_core` already uses for
        a completed sale's own ticket HTML), so the saved document matches
        what production already generates for this sale — not a simplified
        stand-in. Requires a `connection` (to read `configuraciones.
        ticket_template_html`, same as `TicketTemplateEngine`'s own config
        lookups)."""
        if self._connection is None:
            raise RuntimeError("save_receipt_document requiere una connection")
        from core.engines.template_engine import TicketTemplateEngine
        from core.services.printer_service import save_ticket_pdf
        from core.services.sales_service import SalesService

        try:
            row = self._connection.execute(
                "SELECT valor FROM configuraciones WHERE clave='ticket_template_html'").fetchone()
        except Exception:  # noqa: BLE001 - no configuraciones table (fresh/minimal DB) degrades to default
            row = None
        template_html = (row[0] if row and row[0] else None) or SalesService._default_ticket_template()
        html = TicketTemplateEngine(self._connection).generar_ticket(
            template_html, self._to_ticket_payload(receipt))
        return save_ticket_pdf(html, filepath)
