"""Nombres visibles de los tipos de documento y de los módulos que piden una
ruta de impresión. Una sola tabla para plantillas, rutas y listados: el
administrador elige un nombre en español y se guarda el código canónico.
"""

from __future__ import annotations

from backend.domain.device_management.enums import PrintRouteModule
from backend.domain.document_output.enums import DocumentType

DOCUMENT_TYPE_LABELS: tuple[tuple[str, str], ...] = (
    (DocumentType.SALE_TICKET.value, "Ticket de venta"), (DocumentType.QUOTE.value, "Cotización"),
    (DocumentType.DELIVERY_TICKET.value, "Ticket de delivery"),
    (DocumentType.PICKING_TICKET.value, "Ticket de picking"),
    (DocumentType.ORDER_TICKET.value, "Ticket de pedido"),
    (DocumentType.CASH_OPENING.value, "Apertura de caja"),
    (DocumentType.CASH_WITHDRAWAL.value, "Retiro de caja"),
    (DocumentType.X_REPORT.value, "Corte X"), (DocumentType.Z_REPORT.value, "Corte Z"),
    (DocumentType.PURCHASE_ORDER.value, "Orden de compra"),
    (DocumentType.GOODS_RECEIPT.value, "Recepción de mercancía"),
    (DocumentType.TRANSFER_REQUEST.value, "Solicitud de transferencia"),
    (DocumentType.TRANSFER_DISPATCH.value, "Despacho de transferencia"),
    (DocumentType.TRANSFER_RECEIPT.value, "Recepción de transferencia"),
    (DocumentType.PRODUCTION_ORDER.value, "Orden de producción"),
    (DocumentType.YIELD_REPORT.value, "Reporte de rendimiento"),
    (DocumentType.LOSS_REPORT.value, "Reporte de merma"),
    (DocumentType.DISPOSITION_CERTIFICATE.value, "Certificado de disposición"),
    (DocumentType.CUSTOMER_STATEMENT.value, "Estado de cuenta"),
    (DocumentType.LOYALTY_CARD.value, "Tarjeta de fidelidad"),
    (DocumentType.SWEEPSTAKES_TICKET.value, "Boleto de sorteo"),
    (DocumentType.LOT_LABEL.value, "Etiqueta de lote"),
    (DocumentType.WEIGHT_LABEL.value, "Etiqueta de peso"),
    (DocumentType.TRANSFER_LABEL.value, "Etiqueta de transferencia"),
    (DocumentType.COUNT_LABEL.value, "Etiqueta de conteo"),
    (DocumentType.ADJUSTMENT_LABEL.value, "Etiqueta de ajuste"),
    (DocumentType.PRODUCT_LABEL.value, "Etiqueta de producto"),
)

PRINT_ROUTE_MODULE_LABELS: tuple[tuple[str, str], ...] = (
    (PrintRouteModule.SALES.value, "Ventas"),
)

_LABELS = dict(DOCUMENT_TYPE_LABELS) | dict(PRINT_ROUTE_MODULE_LABELS)


def label_for(code: str | None) -> str:
    """Nombre visible de un código; el código tal cual si no está en la tabla."""
    return _LABELS.get(code or "", code or "")
