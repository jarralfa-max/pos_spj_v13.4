"""Display view models / mappers for the enterprise procurement UI (es-MX)."""

from __future__ import annotations

from dataclasses import dataclass, field

from frontend.desktop.formatters import format_money


@dataclass(frozen=True)
class PurchasingCapabilities:
    """Display-only capabilities resolved from canonical Procurement permissions."""

    module_view: bool = False
    requisition_view: bool = False
    requisition_create: bool = False
    requisition_submit: bool = False
    requisition_approve: bool = False
    requisition_reject: bool = False
    rfq_create: bool = False
    quotation_view: bool = False
    quote_capture: bool = False
    quote_compare: bool = False
    quote_award: bool = False
    order_view: bool = False
    order_create: bool = False
    order_approve: bool = False
    order_send: bool = False
    order_change: bool = False
    receipt_view: bool = False
    receipt_complete: bool = False
    origin_view: bool = False
    origin_create: bool = False
    origin_seal: bool = False
    origin_dispatch: bool = False
    origin_override: bool = False
    invoice_view: bool = False
    invoice_capture: bool = False
    invoice_match: bool = False
    invoice_release_variance: bool = False
    direct_view: bool = False
    direct_create: bool = False
    direct_authorize: bool = False
    direct_confirm: bool = False
    direct_reverse: bool = False
    view_costs: bool = False
    view_analytics: bool = False

REQUISITION_STATUS_ES = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Pendiente", "APPROVED": "Aprobada",
    "PARTIALLY_SOURCED": "Abastecida parcial", "SOURCED": "Abastecida",
    "REJECTED": "Rechazada", "CANCELLED": "Cancelada", "CLOSED": "Cerrada",
}
ORDER_STATUS_ES = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Pendiente", "APPROVED": "Aprobada",
    "SENT": "Enviada", "ACKNOWLEDGED": "Confirmada",
    "PARTIALLY_RECEIVED": "Recibida parcial", "RECEIVED": "Recibida",
    "INVOICED": "Facturada", "CLOSED": "Cerrada", "CANCELLED": "Cancelada",
}
INVOICE_STATUS_ES = {
    "CAPTURED": "Capturada", "PENDING_MATCH": "Por conciliar", "MATCHED": "Conciliada",
    "WITH_DIFFERENCES": "Con diferencias", "APPROVED": "Aprobada", "BLOCKED": "Bloqueada",
    "POSTED": "Contabilizada", "CANCELLED": "Cancelada",
}
MATCH_RESULT_ES = {
    "MATCHED": "Conciliada", "QUANTITY_VARIANCE": "Diferencia de cantidad",
    "PRICE_VARIANCE": "Diferencia de precio", "TAX_VARIANCE": "Diferencia de impuesto",
    "DUPLICATE_INVOICE": "Factura duplicada", "MISSING_RECEIPT": "Sin recepción",
    "MISSING_ORDER": "Sin orden", "MISSING_PURCHASE_DOCUMENT": "Sin documento",
    "VARIANCE_RELEASED": "Diferencia liberada",
}
RFQ_STATUS_ES = {"DRAFT": "Borrador", "SENT": "Enviada", "CLOSED": "Cerrada"}


def requisition_status_es(code):
    return REQUISITION_STATUS_ES.get(str(code or ""), str(code or "—"))


def rfq_status_es(code):
    return RFQ_STATUS_ES.get(str(code or ""), str(code or "—"))


def order_status_es(code):
    return ORDER_STATUS_ES.get(str(code or ""), str(code or "—"))


def invoice_status_es(code):
    return INVOICE_STATUS_ES.get(str(code or ""), str(code or "—"))


def match_result_es(code):
    return MATCH_RESULT_ES.get(str(code or ""), str(code or "—"))


def money(value) -> str:
    return format_money(value)


@dataclass(frozen=True)
class TableViewModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    total: int = 0
