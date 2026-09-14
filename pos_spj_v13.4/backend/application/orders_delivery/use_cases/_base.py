"""Shared plumbing for Pedidos/Delivery use cases — authorization injection,
outbox event emission and the audit trail. Mirrors
backend/application/sales/use_cases/_base.py::_SalesBaseUseCase exactly.

Every emitted event is also audited, in the same unit of work: the audit row
and the change it describes commit or roll back together.
"""

from __future__ import annotations

import json

from backend.application.orders_delivery.audit import record_orders_delivery_audit_entry
from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.domain.orders_delivery.events import delivery_event_payload, order_event_payload
from backend.domain.orders_delivery.value_objects.orders_delivery_audit_entry import (
    OrdersDeliveryAuditEntry,
)


class _OrdersDeliveryBaseUseCase:
    def __init__(self, authorization: OrdersDeliveryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or OrdersDeliveryAuthorizationPolicy()

    @staticmethod
    def _audit(uow, action: str, *, entity: str, entity_id: str, branch_id: str,
               actor_user_id: str, operation_id: str, **after) -> None:
        """Writes the audit row inside `uow`'s transaction. Never swallows a
        failure: an audit that silently disappears is not an audit."""
        record_orders_delivery_audit_entry(
            uow.connection,
            OrdersDeliveryAuditEntry(
                user_id=actor_user_id, operation_id=operation_id, action=action,
                branch_id=branch_id, entity_id=entity_id, after=after),
            entity=entity)

    @staticmethod
    def _emit(uow, event_name: str, *, aggregate_type: str, entity_id: str, operation_id: str,
              branch_id: str, actor_user_id: str, **extra) -> None:
        payload = order_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], aggregate_type=aggregate_type,
            aggregate_id=entity_id, event_type=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
        _OrdersDeliveryBaseUseCase._audit(
            uow, event_name, entity=aggregate_type, entity_id=entity_id, branch_id=branch_id,
            actor_user_id=actor_user_id, operation_id=operation_id, **extra)

    @staticmethod
    def _emit_delivery(uow, event_name: str, *, entity_id: str, operation_id: str,
                        branch_id: str, actor_user_id: str, **extra) -> None:
        payload = delivery_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], aggregate_type="DeliveryJob",
            aggregate_id=entity_id, event_type=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
        # The outbox files settlement events under "DeliveryJob" too, but their
        # entity_id is the settlement's: the audit names what was really touched.
        entity = ("DriverSettlement" if event_name.startswith("DRIVER_SETTLEMENT_")
                  else "DeliveryJob")
        _OrdersDeliveryBaseUseCase._audit(
            uow, event_name, entity=entity, entity_id=entity_id, branch_id=branch_id,
            actor_user_id=actor_user_id, operation_id=operation_id, **extra)
