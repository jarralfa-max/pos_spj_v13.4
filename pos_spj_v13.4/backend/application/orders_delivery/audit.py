"""Rastro de auditoría de Pedidos y reparto.

Envoltorio fino sobre `backend/application/shared/audit_trail.py`, que escribe
en `audit_logs` — el rastro transversal, no una tabla por contexto.

Antes cada contexto repetía aquí el mismo bloque de veinticinco líneas y
llamaba a `core.services.auto_audit.audit_write`, que pedía un `container`. Los
casos de uso no lo tienen, y por eso este escritor nunca llegó a usarse. Ahora
recibe la `connection` que sí tienen.

CONECTADO. Toda escritura de los casos de uso deja su renglón, en la MISMA
transacción que el cambio (`_OrdersDeliveryBaseUseCase._audit`):

- los que emiten evento auditan desde `_emit`/`_emit_delivery`, con la acción =
  el nombre del evento;
- los que guardan sin evento usan una acción de `OrdersDeliveryAuditActions`.

`test_orders_delivery_audit_trail.py` falla si un caso de uso guarda sin auditar.
"""

from __future__ import annotations

from backend.application.shared.audit_trail import record_audit_entry
from backend.domain.orders_delivery.events import ALL_DELIVERY_EVENTS, ALL_ORDER_EVENTS
from backend.domain.orders_delivery.value_objects.orders_delivery_audit_entry import (
    OrdersDeliveryAuditEntry,
)

#: Módulo bajo el que aparece este contexto en la auditoría.
AUDIT_MODULE = "DELIVERY"
AUDIT_ENTITY = "pedido_delivery"


class OrdersDeliveryAuditActions:
    """Acciones auditables que NO son un evento del outbox. Las que sí lo son usan
    el nombre del evento; aquí no se repite ninguno."""

    ORDER_DELIVERY_ADDRESS_SET = "ORDER_DELIVERY_ADDRESS_SET"
    ORDER_RESCHEDULED = "ORDER_RESCHEDULED"
    ORDER_INVENTORY_RELEASED = "ORDER_INVENTORY_RELEASED"
    ORDER_PREPARATION_ASSIGNED = "ORDER_PREPARATION_ASSIGNED"
    ORDER_LINE_PREPARED = "ORDER_LINE_PREPARED"
    ORDER_PACKAGE_CREATED = "ORDER_PACKAGE_CREATED"
    ORDER_PACKAGE_SEALED = "ORDER_PACKAGE_SEALED"
    ORDER_READY_FOR_PICKUP = "ORDER_READY_FOR_PICKUP"
    ORDER_PICKUP_COMPLETED = "ORDER_PICKUP_COMPLETED"
    DRIVER_PROFILE_REGISTERED = "DRIVER_PROFILE_REGISTERED"
    DRIVER_ASSIGNMENT_PROPOSED = "DRIVER_ASSIGNMENT_PROPOSED"
    DRIVER_ASSIGNMENT_REJECTED = "DRIVER_ASSIGNMENT_REJECTED"
    DELIVERY_ROUTE_CREATED = "DELIVERY_ROUTE_CREATED"
    DELIVERY_ROUTE_STOP_ADDED = "DELIVERY_ROUTE_STOP_ADDED"
    DELIVERY_ROUTE_PLANNED = "DELIVERY_ROUTE_PLANNED"
    REDELIVERY_REQUEST_CREATED = "REDELIVERY_REQUEST_CREATED"
    REDELIVERY_REQUEST_REJECTED = "REDELIVERY_REQUEST_REJECTED"
    CASH_COLLECTION_REQUESTED = "CASH_COLLECTION_REQUESTED"
    DRIVER_SETTLEMENT_SUBMITTED_FOR_REVIEW = "DRIVER_SETTLEMENT_SUBMITTED_FOR_REVIEW"
    DRIVER_SETTLEMENT_APPROVED = "DRIVER_SETTLEMENT_APPROVED"
    DELIVERY_ZONE_CREATED = "DELIVERY_ZONE_CREATED"
    DELIVERY_ZONE_UPDATED = "DELIVERY_ZONE_UPDATED"
    DELIVERY_ZONE_ACTIVATED = "DELIVERY_ZONE_ACTIVATED"
    DELIVERY_ZONE_DEACTIVATED = "DELIVERY_ZONE_DEACTIVATED"


#: Todo lo que puede aparecer en `audit_logs.accion` bajo este módulo.
ALL_AUDIT_ACTIONS = frozenset(
    ALL_ORDER_EVENTS | ALL_DELIVERY_EVENTS
    | {value for name, value in vars(OrdersDeliveryAuditActions).items()
       if name.isupper() and isinstance(value, str)}
)


def record_orders_delivery_audit_entry(connection, entry: OrdersDeliveryAuditEntry, *,
                                       entity: str = AUDIT_ENTITY) -> None:
    """Persiste una `OrdersDeliveryAuditEntry` en el rastro canónico. `entity` es
    el agregado afectado (`CustomerOrder`, `DeliveryZone`…)."""
    record_audit_entry(
        connection, entry, module=AUDIT_MODULE, entity=entity,
        entity_id=getattr(entry, "entity_id", "") or "",
    )
