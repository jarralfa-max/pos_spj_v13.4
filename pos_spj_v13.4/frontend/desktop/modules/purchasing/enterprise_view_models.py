"""Display view models / mappers for the enterprise procurement UI (es-MX)."""

from __future__ import annotations

from dataclasses import dataclass, field

from frontend.desktop.formatters import format_money

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


def requisition_status_es(code):
    return REQUISITION_STATUS_ES.get(str(code or ""), str(code or "—"))


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
