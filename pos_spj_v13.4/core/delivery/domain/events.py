from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class DeliveryEvents(StrEnum):
    ORDER_CREATED = "DELIVERY_ORDER_CREATED"
    ORDER_RESERVED = "DELIVERY_ORDER_RESERVED"
    ORDER_PREPARING = "DELIVERY_ORDER_PREPARING"
    DRIVER_ASSIGNED = "DELIVERY_DRIVER_ASSIGNED"
    OUT_FOR_DELIVERY = "DELIVERY_OUT_FOR_DELIVERY"
    ORDER_DELIVERED = "DELIVERY_ORDER_DELIVERED"
    ORDER_CANCELLED = "DELIVERY_ORDER_CANCELLED"
    ADJUSTMENT_APPROVAL_REQUIRED = "DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED"
    ITEM_WEIGHT_ADJUSTED = "DELIVERY_ITEM_WEIGHT_ADJUSTED"
    TOTAL_UPDATED = "DELIVERY_TOTAL_UPDATED"
    INVENTORY_COMMIT_REQUIRED = "INVENTORY_COMMIT_REQUIRED"
    INVENTORY_RELEASE_REQUIRED = "INVENTORY_RELEASE_REQUIRED"
    CUSTOMER_NOTIFICATION_REQUESTED = "CUSTOMER_NOTIFICATION_REQUESTED"
    SCHEDULED_ORDER_ACTIVATED = "DELIVERY_SCHEDULED_ORDER_ACTIVATED"


@dataclass(frozen=True, slots=True)
class EventContract:
    payload_fields: tuple[str, ...]
    description: str
    critical: bool = False


EVENT_PAYLOAD_CONTRACTS: Mapping[DeliveryEvents, EventContract] = {
    DeliveryEvents.ORDER_CREATED: EventContract(("order_id", "folio", "direccion", "total", "sucursal_id", "usuario"), "Pedido delivery creado."),
    DeliveryEvents.ORDER_RESERVED: EventContract(("order_id", "operation_id", "items", "branch_id"), "Reserva lógica de inventario solicitada."),
    DeliveryEvents.ORDER_PREPARING: EventContract(("order_id", "folio", "usuario", "sucursal_id"), "Pedido pasó a preparación."),
    DeliveryEvents.DRIVER_ASSIGNED: EventContract(("order_id", "driver_id", "driver_nombre", "tiempo_estimado"), "Repartidor asignado."),
    DeliveryEvents.OUT_FOR_DELIVERY: EventContract(("order_id", "driver_id", "folio", "cliente_tel"), "Pedido salió a ruta."),
    DeliveryEvents.ORDER_DELIVERED: EventContract(("order_id", "folio", "driver_id", "total", "sucursal_id", "responsable"), "Pedido entregado.", critical=True),
    DeliveryEvents.ORDER_CANCELLED: EventContract(("order_id", "folio", "usuario", "motivo"), "Pedido cancelado.", critical=True),
    DeliveryEvents.ADJUSTMENT_APPROVAL_REQUIRED: EventContract(("order_id", "item_id", "folio", "cliente_tel", "requested_qty", "prepared_qty", "new_subtotal"), "Ajuste requiere aprobación del cliente.", critical=True),
    DeliveryEvents.ITEM_WEIGHT_ADJUSTED: EventContract(("order_id", "item_id", "requested_qty", "prepared_qty", "new_total"), "Peso/cantidad aplicado."),
    DeliveryEvents.TOTAL_UPDATED: EventContract(("order_id", "old_total", "new_total", "folio", "cliente_tel"), "Total recalculado."),
    DeliveryEvents.INVENTORY_COMMIT_REQUIRED: EventContract(("order_id", "operation_id", "items", "sucursal_id"), "Commit físico de inventario requerido.", critical=True),
    DeliveryEvents.INVENTORY_RELEASE_REQUIRED: EventContract(("order_id", "operation_id", "reason"), "Liberación de reserva requerida.", critical=True),
    DeliveryEvents.CUSTOMER_NOTIFICATION_REQUESTED: EventContract(("order_id", "canal", "template", "params", "cliente_tel"), "Notificación a cliente requerida.", critical=True),
    DeliveryEvents.SCHEDULED_ORDER_ACTIVATED: EventContract(("order_id", "workflow_type", "usuario", "sucursal_id"), "Pedido programado activado."),
}

CRITICAL_OUTBOX_EVENTS = frozenset(event for event, contract in EVENT_PAYLOAD_CONTRACTS.items() if contract.critical)


def required_payload_fields(event: DeliveryEvents | str) -> tuple[str, ...]:
    return EVENT_PAYLOAD_CONTRACTS[DeliveryEvents(event)].payload_fields
