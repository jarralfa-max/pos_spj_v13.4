from __future__ import annotations

from core.domain.order_models import OrderStatus

DOMAIN_TO_LEGACY_STATUS = {
    OrderStatus.PENDING: "pendiente",
    OrderStatus.PREPARATION: "preparacion",
    OrderStatus.OUT_FOR_DELIVERY: "en_ruta",
    OrderStatus.DELIVERED: "entregado",
    OrderStatus.CANCELLED: "cancelado",
    OrderStatus.SCHEDULED: "programado",
}

LEGACY_TO_DOMAIN_STATUS = {
    "pendiente": OrderStatus.PENDING,
    "pendiente_wa": OrderStatus.PENDING,
    "preparacion": OrderStatus.PREPARATION,
    "en_preparacion": OrderStatus.PREPARATION,
    "en_ruta": OrderStatus.OUT_FOR_DELIVERY,
    "entregado": OrderStatus.DELIVERED,
    "entregada": OrderStatus.DELIVERED,
    "cancelado": OrderStatus.CANCELLED,
    "cancelada": OrderStatus.CANCELLED,
    "programado": OrderStatus.SCHEDULED,
}

STATUS_UI_ES = {
    OrderStatus.PENDING: "Pendiente",
    OrderStatus.PREPARATION: "Preparación",
    OrderStatus.OUT_FOR_DELIVERY: "En ruta",
    OrderStatus.DELIVERED: "Entregado",
    OrderStatus.CANCELLED: "Cancelado",
    OrderStatus.SCHEDULED: "Programado",
}


def to_legacy_status(status: OrderStatus) -> str:
    return DOMAIN_TO_LEGACY_STATUS[status]


def to_domain_status(legacy_status: str) -> OrderStatus:
    key = (legacy_status or "").strip().lower()
    return LEGACY_TO_DOMAIN_STATUS.get(key, OrderStatus.PENDING)


def to_ui_status(status: OrderStatus) -> str:
    return STATUS_UI_ES[status]
