"""Relación comercial (§28, §49-51, CRM-43): compras, pedidos, cotizaciones,
devoluciones y productos frecuentes de un cliente.

Sólo lectura: Ventas, Pedidos y Cotizaciones son los dueños (CRM no registra
ventas, §49). Antes las cinco rutas decían «en construcción» y el
``CustomerHistoryQueryService`` sólo tenía la línea de tiempo de auditoría.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from frontend.desktop.components import ColumnSpec
from frontend.desktop.modules.customers_crm.formatting import fmt_date, fmt_datetime, fmt_money
from frontend.desktop.modules.customers_crm.pages.customer_sections import _Section

_SALE_STATUS = {"COMPLETED": "Completada", "REVERSED": "Reversada"}
_METHODS = {"CASH": "Efectivo", "CARD": "Tarjeta", "CREDIT": "Crédito", "TRANSFER": "Transferencia",
            "VOUCHER": "Vale", "MIXED": "Mixto"}


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation:
        return Decimal("0")


class _HistorySection(_Section):
    reader = ""

    def reload(self) -> None:
        self._display = object() if self._customer_id else None
        self._render()
        self._sync()

    def _render(self) -> None:
        rows = []
        if self._customer_id:
            try:
                rows = self._presenter.read(self.reader, customer_id=self._customer_id)
            except Exception as exc:  # noqa: BLE001 — sin permiso o módulo ausente
                self._say(False, f"No fue posible leer el historial: {exc}")
        self._items = {str(r.get("id") or r.get("product_id") or i): r
                       for i, r in enumerate(rows)}
        self._table.load_rows([self.cells(r) for r in rows],
                              row_ids=[str(r.get("id") or r.get("product_id") or i)
                                       for i, r in enumerate(rows)])

    def cells(self, row: dict) -> list[str]:
        raise NotImplementedError


class PurchasesSection(_HistorySection):
    reader = "purchase_history"
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Folio"), ColumnSpec("Total", "numeric"),
               ColumnSpec("Devuelto", "numeric"), ColumnSpec("Partidas", "numeric"),
               ColumnSpec("Estado"))

    def cells(self, r):
        return [fmt_datetime(r["occurred_at"]), r["sale_number"] or "—", fmt_money(r["total"]),
                fmt_money(_dec(r["returned_amount"])) if _dec(r["returned_amount"]) else "—",
                str(r["line_count"]), _SALE_STATUS.get(r["status"], r["status"])]


class PaymentsSection(_HistorySection):
    reader = "payment_history"
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Venta"), ColumnSpec("Forma de pago"),
               ColumnSpec("Importe", "numeric"), ColumnSpec("Referencia"))

    def cells(self, r):
        return [fmt_datetime(r["captured_at"]), r["sale_number"] or "—",
                _METHODS.get(r["method"], r["method"]), fmt_money(r["amount"]),
                r["reference"] or "—"]


class OrdersSection(_HistorySection):
    reader = "order_history"
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Pedido"), ColumnSpec("Canal"),
               ColumnSpec("Entrega"), ColumnSpec("Estado"), ColumnSpec("Pago"),
               ColumnSpec("Total", "numeric"))
    _STATUS = {"DRAFT": "Borrador", "CONFIRMED": "Confirmado", "IN_PREPARATION": "En preparación",
               "READY": "Listo", "DISPATCHED": "En camino", "DELIVERED": "Entregado",
               "CANCELLED": "Cancelado", "COMPLETED": "Completado"}

    def cells(self, r):
        return [fmt_datetime(r["created_at"]), r["order_number"] or "—", r["channel"] or "—",
                r["fulfillment_type"] or "—", self._STATUS.get(r["status"], r["status"] or "—"),
                r["payment_status"] or "—", fmt_money(r["grand_total"])]


class QuotesSection(_HistorySection):
    reader = "quote_history"
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Folio"), ColumnSpec("Total", "numeric"),
               ColumnSpec("Vence", "date"), ColumnSpec("Estado"))

    def cells(self, r):
        return [fmt_date(r["fecha"]), r["folio"] or "—", fmt_money(r["total"]),
                fmt_date(r["fecha_vencimiento"]), (r["estado"] or "—").capitalize()]


class ReturnsSection(_HistorySection):
    reader = "return_history"
    columns = (ColumnSpec("Fecha", "date"), ColumnSpec("Venta"), ColumnSpec("Producto"),
               ColumnSpec("Cantidad", "numeric"), ColumnSpec("Importe", "numeric"),
               ColumnSpec("Motivo", stretch=True))

    def cells(self, r):
        return [fmt_datetime(r["created_at"]), r["sale_number"] or "—", r["product_name"] or "—",
                str(r["quantity"]), fmt_money(r["amount"]), r["reason"] or "—"]


class AffinitySection(_HistorySection):
    """Productos que el cliente compra más (por número de compras)."""

    reader = "product_affinity"
    columns = (ColumnSpec("Producto", stretch=True), ColumnSpec("SKU"),
               ColumnSpec("Veces", "numeric"), ColumnSpec("Cantidad", "numeric"),
               ColumnSpec("Importe", "numeric"), ColumnSpec("Última vez", "date"))

    def cells(self, r):
        quantity = _dec(r["quantity"]).normalize()
        return [r["product_name"] or "—", r["sku"] or "—", str(r["times_bought"]),
                f"{quantity:f} {r['unit'] or ''}".strip(), fmt_money(_dec(r["amount"])),
                fmt_datetime(r["last_bought_at"])]


COMMERCIAL_SECTIONS = {
    "customers.purchase_history": (PurchasesSection, "Compras",
                                   "Ventas completadas del cliente, con devoluciones."),
    "customers.order_history": (OrdersSection, "Pedidos",
                                "Pedidos de mostrador, teléfono, WhatsApp o en línea."),
    "customers.quote_history": (QuotesSection, "Cotizaciones",
                                "Cotizaciones emitidas al cliente."),
    "customers.return_history": (ReturnsSection, "Devoluciones",
                                 "Partidas devueltas y su motivo."),
    "customers.product_affinity": (AffinitySection, "Productos frecuentes",
                                   "Lo que más compra el cliente."),
}
