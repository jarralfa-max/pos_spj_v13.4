"""Shared plumbing for Pedidos/Delivery use cases — authorization injection
and outbox event emission. Mirrors
backend/application/sales/use_cases/_base.py::_SalesBaseUseCase exactly.
"""

from __future__ import annotations

import json

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.domain.orders_delivery.events import delivery_event_payload, order_event_payload


class _OrdersDeliveryBaseUseCase:
    def __init__(self, authorization: OrdersDeliveryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or OrdersDeliveryAuthorizationPolicy()

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
