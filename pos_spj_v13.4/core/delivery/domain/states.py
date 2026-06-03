from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping, TypeVar


class DeliveryStatus(StrEnum):
    PENDIENTE = "pendiente"
    PREPARACION = "preparacion"
    EN_RUTA = "en_ruta"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"
    PROGRAMADO = "programado"


class DeliveryWorkflowType(StrEnum):
    DELIVERY = "delivery"
    COUNTER = "counter"
    SCHEDULED = "scheduled"


class DeliveryType(StrEnum):
    HOME_DELIVERY = "home_delivery"
    PICKUP = "pickup"
    SUCURSAL = "sucursal"


class AdjustmentStatus(StrEnum):
    NONE = "none"
    AUTO_ACCEPTED = "auto_accepted"
    PENDING_CUSTOMER = "pending_customer"
    CUSTOMER_ACCEPTED = "customer_accepted"
    CUSTOMER_REJECTED = "customer_rejected"
    EXPIRED = "expired"


LEGACY_STATUS_MAP: Mapping[str, DeliveryStatus] = {
    "asignado": DeliveryStatus.PREPARACION,
    "listo": DeliveryStatus.PREPARACION,
    "en_camino": DeliveryStatus.EN_RUTA,
    "pendiente_wa": DeliveryStatus.PENDIENTE,
    "en_preparacion": DeliveryStatus.PREPARACION,
    "entregada": DeliveryStatus.ENTREGADO,
    "cancelada": DeliveryStatus.CANCELADO,
}

WORKFLOW_ALIASES: Mapping[str, DeliveryWorkflowType] = {
    "delivery": DeliveryWorkflowType.DELIVERY,
    "domicilio": DeliveryWorkflowType.DELIVERY,
    "home_delivery": DeliveryWorkflowType.DELIVERY,
    "counter": DeliveryWorkflowType.COUNTER,
    "mostrador": DeliveryWorkflowType.COUNTER,
    "pickup": DeliveryWorkflowType.COUNTER,
    "sucursal": DeliveryWorkflowType.COUNTER,
    "scheduled": DeliveryWorkflowType.SCHEDULED,
    "programado": DeliveryWorkflowType.SCHEDULED,
}

DELIVERY_TYPE_ALIASES: Mapping[str, DeliveryType] = {
    "home_delivery": DeliveryType.HOME_DELIVERY,
    "delivery": DeliveryType.HOME_DELIVERY,
    "domicilio": DeliveryType.HOME_DELIVERY,
    "envio": DeliveryType.HOME_DELIVERY,
    "pickup": DeliveryType.PICKUP,
    "recoger": DeliveryType.PICKUP,
    "mostrador": DeliveryType.PICKUP,
    "counter": DeliveryType.PICKUP,
    "sucursal": DeliveryType.SUCURSAL,
}

T = TypeVar("T", bound=StrEnum)


def _enum_value(value: Any) -> str:
    return str(value.value if isinstance(value, StrEnum) else value or "").strip().lower()


def normalize_status(status: Any) -> DeliveryStatus:
    raw = _enum_value(status)
    if not raw:
        return DeliveryStatus.PENDIENTE
    if raw in LEGACY_STATUS_MAP:
        return LEGACY_STATUS_MAP[raw]
    try:
        return DeliveryStatus(raw)
    except ValueError as exc:
        raise ValueError(f"Estado delivery desconocido: {status!r}") from exc


def normalize_workflow_type(workflow_type: Any) -> DeliveryWorkflowType | None:
    raw = _enum_value(workflow_type)
    if not raw:
        return None
    if raw in WORKFLOW_ALIASES:
        return WORKFLOW_ALIASES[raw]
    try:
        return DeliveryWorkflowType(raw)
    except ValueError as exc:
        raise ValueError(f"Workflow delivery desconocido: {workflow_type!r}") from exc


def normalize_delivery_type(delivery_type: Any) -> DeliveryType | None:
    raw = _enum_value(delivery_type)
    if not raw:
        return None
    if raw in DELIVERY_TYPE_ALIASES:
        return DELIVERY_TYPE_ALIASES[raw]
    try:
        return DeliveryType(raw)
    except ValueError as exc:
        raise ValueError(f"Tipo delivery desconocido: {delivery_type!r}") from exc


def normalize_adjustment_status(status: Any) -> AdjustmentStatus:
    raw = _enum_value(status)
    if not raw:
        return AdjustmentStatus.NONE
    # Backwards-compatible values currently persisted by DeliveryService.
    if raw == "accepted":
        return AdjustmentStatus.CUSTOMER_ACCEPTED
    if raw == "rejected":
        return AdjustmentStatus.CUSTOMER_REJECTED
    try:
        return AdjustmentStatus(raw)
    except ValueError as exc:
        raise ValueError(f"Estado de ajuste desconocido: {status!r}") from exc
