from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping, TypeVar

from .value_objects import DeliveryStatus


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

# Spanish-to-English migration aliases — only needed while any legacy rows exist.
# Remove after migration 110 has run on all databases.
_SPANISH_COMPAT: Mapping[str, DeliveryStatus] = {
    "pendiente": DeliveryStatus.PENDING,
    "preparacion": DeliveryStatus.PREPARING,
    "en_ruta": DeliveryStatus.IN_TRANSIT,
    "entregado": DeliveryStatus.DELIVERED,
    "cancelado": DeliveryStatus.CANCELLED,
    "programado": DeliveryStatus.SCHEDULED,
    "listo_entrega": DeliveryStatus.READY_FOR_PICKUP,
    "listo_envio": DeliveryStatus.READY_FOR_DISPATCH,
    "asignado": DeliveryStatus.ASSIGNED,
    # very old aliases
    "pendiente_wa": DeliveryStatus.PENDING,
    "en_preparacion": DeliveryStatus.PREPARING,
    "entregada": DeliveryStatus.DELIVERED,
    "cancelada": DeliveryStatus.CANCELLED,
    "en_camino": DeliveryStatus.IN_TRANSIT,
}


def _enum_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value or "").strip().lower()
    return str(value or "").strip().lower()


def normalize_status(status: Any) -> DeliveryStatus:
    raw = _enum_value(status)
    if not raw:
        return DeliveryStatus.PENDING
    if raw in _SPANISH_COMPAT:
        return _SPANISH_COMPAT[raw]
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
    if raw == "accepted":
        return AdjustmentStatus.CUSTOMER_ACCEPTED
    if raw == "rejected":
        return AdjustmentStatus.CUSTOMER_REJECTED
    try:
        return AdjustmentStatus(raw)
    except ValueError as exc:
        raise ValueError(f"Estado de ajuste desconocido: {status!r}") from exc
