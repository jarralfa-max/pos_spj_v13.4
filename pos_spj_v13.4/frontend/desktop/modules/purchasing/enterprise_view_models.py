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
    order_acknowledge: bool = False
    order_change: bool = False
    receipt_view: bool = False
    receipt_complete: bool = False
    origin_view: bool = False
    origin_create: bool = False
    origin_seal: bool = False
    origin_dispatch: bool = False
    origin_override: bool = False
    origin_receive: bool = False
    origin_containers: bool = False
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

# §20: la pantalla nunca muestra el código de estado; estos mapas son la
# ÚNICA traducción (las páginas y paneles los consumen, no inventan la suya).
REQUISITION_STATUS_ES = {
    "DRAFT": "Borrador", "SUBMITTED": "Enviada",
    "PENDING_APPROVAL": "Pendiente de aprobación", "APPROVED": "Aprobada",
    "PARTIALLY_SOURCED": "Abastecida parcialmente", "SOURCED": "Abastecida",
    "REJECTED": "Rechazada", "CANCELLED": "Cancelada", "CLOSED": "Cerrada",
}
ORDER_STATUS_ES = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Pendiente de aprobación",
    "APPROVED": "Aprobada", "SENT": "Enviada", "ACKNOWLEDGED": "Confirmada por proveedor",
    "PARTIALLY_RECEIVED": "Recibida parcialmente", "RECEIVED": "Recibida",
    "INVOICED": "Facturada", "CLOSED": "Cerrada", "CANCELLED": "Cancelada",
}
RECEIPT_STATUS_ES = {
    "DRAFT": "Borrador", "IN_PROGRESS": "En proceso", "COMPLETED": "Completada",
    "WITH_DIFFERENCES": "Con diferencias", "CANCELLED": "Cancelada", "REVERSED": "Reversada",
}
DIRECT_PURCHASE_STATUS_ES = {
    "DRAFT": "Borrador", "PENDING_AUTHORIZATION": "Pendiente de autorización",
    "CONFIRMED": "Confirmada", "PARTIALLY_RECEIVED": "Recibida parcialmente",
    "RECEIVED": "Recibida", "REVERSED": "Reversada", "CANCELLED": "Cancelada",
}
DISCREPANCY_ES = {
    "SHORT_QUANTITY": "Faltante", "OVER_QUANTITY": "Excedente",
    "WRONG_PRODUCT": "Producto equivocado", "DAMAGED": "Dañado",
    "QUALITY_FAILURE": "Rechazo de calidad", "TEMPERATURE_FAILURE": "Temperatura fuera de rango",
    "MISSING_DOCUMENT": "Falta documento", "PRICE_DIFFERENCE": "Diferencia de precio",
    "LOT_DIFFERENCE": "Lote distinto", "EXPIRATION_FAILURE": "Caducidad inválida",
}
PRIORITY_ES = {"LOW": "Baja", "NORMAL": "Normal", "HIGH": "Alta", "URGENT": "Urgente"}
PURCHASE_NATURE_ES = {
    "INVENTORY": "Inventario", "EXPENSE": "Gasto", "ASSET": "Activo", "SERVICE": "Servicio",
    "CONSUMABLE": "Consumible", "PACKAGING": "Empaque", "MAINTENANCE": "Mantenimiento",
    "RAW_MATERIAL": "Materia prima", "SUPPLIES": "Insumos", "GROCERY": "Abarrotes",
    "POULTRY": "Pollo",
}
DOCUMENT_TYPE_ES = {
    "RFQ": "Solicitud de cotización", "PO": "Orden de compra",
    "PURCHASE_ORDER": "Orden de compra", "DIRECT_PURCHASE": "Compra directa",
    "INVOICE": "Factura de proveedor", "RECEIPT": "Recepción", "REQUISITION": "Solicitud",
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
INVITATION_STATUS_ES = {"INVITED": "Invitado", "RESPONDED": "Respondió",
                        "DECLINED": "Declinó"}


def invitation_status_es(code):
    return _label(INVITATION_STATUS_ES, code)


def requisition_status_es(code):
    return _label(REQUISITION_STATUS_ES, code)


def rfq_status_es(code):
    return _label(RFQ_STATUS_ES, code)


def order_status_es(code):
    return _label(ORDER_STATUS_ES, code)


def invoice_status_es(code):
    return _label(INVOICE_STATUS_ES, code)


def match_result_es(code):
    return _label(MATCH_RESULT_ES, code)


def _label(mapping: dict, code) -> str:
    """Traducción o, si el código es desconocido, un texto neutro: nunca el
    código técnico en pantalla."""
    value = str(code or "")
    if not value:
        return "—"
    return mapping.get(value) or value.replace("_", " ").capitalize()


def receipt_status_es(code):
    return _label(RECEIPT_STATUS_ES, code)


def direct_purchase_status_es(code):
    return _label(DIRECT_PURCHASE_STATUS_ES, code)


def discrepancy_es(code):
    return _label(DISCREPANCY_ES, code)


def priority_es(code):
    return _label(PRIORITY_ES, code)


def purchase_nature_es(code):
    return _label(PURCHASE_NATURE_ES, code)


def document_type_es(code):
    return _label(DOCUMENT_TYPE_ES, code)


_STATUS_BY_DOCUMENT_TYPE = {
    "RFQ": RFQ_STATUS_ES, "PO": ORDER_STATUS_ES, "PURCHASE_ORDER": ORDER_STATUS_ES,
    "DIRECT_PURCHASE": DIRECT_PURCHASE_STATUS_ES, "INVOICE": INVOICE_STATUS_ES,
    "RECEIPT": RECEIPT_STATUS_ES, "REQUISITION": REQUISITION_STATUS_ES,
}


def status_filter(mapping: dict, codes) -> list[tuple[str, str]]:
    """Opciones del filtro de estado de una lista, con la MISMA traducción
    que las celdas (antes cada página escribía la suya)."""
    return [("", "Todos")] + [(code, mapping[code]) for code in codes]


def document_status_es(document_type, code):
    """Estado de un documento relacionado según SU tipo (el mismo código
    —MATCHED, CLOSED— significa cosas distintas en cada documento)."""
    return _label(_STATUS_BY_DOCUMENT_TYPE.get(str(document_type or ""), {}), code)


def money(value) -> str:
    return format_money(value)


def local_datetime_text(value, *, date_only: bool = False) -> str:
    """ISO en UTC (como se guarda) → hora LOCAL del equipo para mostrar.
    Recortar el texto mostraba la fecha UTC: lo capturado de noche aparecía
    con la fecha de mañana."""
    from datetime import datetime
    text = str(value or "")
    if not text:
        return "—"
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return text[:10] if date_only else text[:16]
    return moment.strftime("%Y-%m-%d" if date_only else "%Y-%m-%d %H:%M")


PAYABLE_STATUS_ES = {
    "OPEN": "Pendiente de pago", "SCHEDULED": "Pago programado",
    "PARTIALLY_PAID": "Pagada parcialmente", "SETTLED": "Pagada", "CANCELLED": "Cancelada",
}


def invoice_finance_text(detail) -> str:
    """Qué hizo Finanzas con la factura, en una línea para la pantalla."""
    payable = getattr(detail, "payable", None)
    if payable:
        due = str(payable.get("due_date") or "")[:10] or "sin fecha"
        return (f"Cuenta por pagar {payable.get('document_number') or ''} · "
                f"{PAYABLE_STATUS_ES.get(str(payable.get('status') or ''), 'Registrada')} · "
                f"saldo {money(payable.get('outstanding_amount'))} de "
                f"{money(payable.get('original_amount'))} · vence {due}")
    if getattr(detail, "paid_in_cash", False):
        return "Compra pagada de contado: la factura es su soporte fiscal y no genera cuenta por pagar."
    if str(getattr(detail, "status", "")) in ("MATCHED", "APPROVED"):
        return "Cuenta por pagar en proceso en Finanzas."
    return "Genera la cuenta por pagar al conciliar sin diferencias (o al liberarlas)."


@dataclass(frozen=True)
class TableViewModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    total: int = 0


#: Encabezado de la orden (§23). Códigos estables; la pantalla sólo muestra la etiqueta.
PAYMENT_TERMS_OPTIONS = [
    ("CASH", "Contado"), ("NET_7", "Crédito 7 días"), ("NET_15", "Crédito 15 días"),
    ("NET_30", "Crédito 30 días"), ("NET_45", "Crédito 45 días"), ("NET_60", "Crédito 60 días"),
]
DELIVERY_METHOD_OPTIONS = [
    ("SUPPLIER_DELIVERY", "Entrega del proveedor"), ("SUPPLIER_PICKUP", "Recolección en proveedor"),
]
CURRENCY_OPTIONS = [("MXN", "Peso mexicano (MXN)"), ("USD", "Dólar (USD)")]


def payment_terms_es(code):
    return dict(PAYMENT_TERMS_OPTIONS).get(str(code or ""), str(code or "—"))


def delivery_method_es(code):
    return dict(DELIVERY_METHOD_OPTIONS).get(str(code or ""), str(code or "—"))
