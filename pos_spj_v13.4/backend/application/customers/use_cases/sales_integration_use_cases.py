"""Sale-activity projection use cases (CRM-13, §49 Ventas): "CRM recibe
SALE_COMPLETED/CANCELLED/RETURNED y puede actualizar proyecciones
(last_purchase_at, purchase_count, lifecycle_stage). CRM no registra ventas."

These use cases are triggered by another bounded context's event, not by a
direct user action — there is no human "actor" requesting a CLIENTES
permission here (the same reasoning EventBus-subscribed handlers elsewhere
in this codebase already follow), so unlike every other use case in this
package, ``execute()`` takes no ``actor_user_id``/permission check.

Idempotent via ``CustomerProcessedEventRepository`` (built in CRM-3,
unconsumed until now — the first real consumer of the inbox-style
``customer_processed_events`` table, the same "CRM-N built it, CRM-M
finally calls it" pattern already true of the SoD policy/hot-auth grant/
``search_lookup``): replaying the same source event is a safe no-op.
"""

from __future__ import annotations

import json

from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class RecordCustomerSaleActivityUseCase:
    """Applies a completed sale to a customer's activity projection."""

    def execute(self, connection, *, customer_id: str, occurred_at: str,
                source_event_id: str, operation_id: str) -> bool:
        """Returns True if applied, False if the customer is unknown to
        this bounded context or the source event was already processed
        (both legitimate, silent no-ops — see module docstring)."""
        with CustomerUnitOfWork(connection) as uow:
            if uow.processed_events.was_processed(source_event_id):
                return False
            customer = uow.customers.get(customer_id)
            if customer is None:
                return False
            new_stage = customer.record_sale_activity(occurred_at)
            uow.customers.update(customer)
            if new_stage is not None:
                uow.audit.record(
                    action=CustomerEvents.LIFECYCLE_STAGE_CHANGED, actor_user_id=None,
                    operation_id=operation_id, customer_id=customer_id,
                    after_json=json.dumps({"lifecycle_stage": new_stage.value}))
                payload = build_event_payload(
                    CustomerEvents.LIFECYCLE_STAGE_CHANGED, operation_id=operation_id,
                    customer_id=customer_id, lifecycle_stage=new_stage.value)
                uow.outbox.enqueue(payload["event_id"], CustomerEvents.LIFECYCLE_STAGE_CHANGED,
                                   json.dumps(payload), operation_id)
            uow.processed_events.mark_processed(
                source_event_id, CustomerEvents.LIFECYCLE_STAGE_CHANGED, operation_id)
            return True


class RecordCustomerSaleCancelledUseCase:
    """Un-counts a cancelled sale (§49) — see Customer.record_sale_cancelled
    for why lifecycle_stage and last_purchase_at are left untouched."""

    def execute(self, connection, *, customer_id: str, source_event_id: str,
                operation_id: str) -> bool:
        with CustomerUnitOfWork(connection) as uow:
            if uow.processed_events.was_processed(source_event_id):
                return False
            customer = uow.customers.get(customer_id)
            if customer is None:
                return False
            customer.record_sale_cancelled()
            uow.customers.update(customer)
            uow.processed_events.mark_processed(
                source_event_id, CustomerEvents.UPDATED, operation_id)
            return True
