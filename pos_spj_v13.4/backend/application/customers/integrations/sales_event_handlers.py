"""Ventas → CRM bridge (CRM-13, §49): translates the legacy EventBus'
``VENTA_COMPLETADA``/``VENTA_CANCELADA`` payloads (``core/events/
event_bus.py``, wired in ``core/events/wiring.py``) into calls against
``RecordCustomerSaleActivityUseCase``/``RecordCustomerSaleCancelledUseCase``.

**Known, documented gap — not wired into ``core/events/wiring.py`` yet**:
``VENTA_COMPLETADA``'s ``cliente_id`` is the LEGACY ``clientes.id`` (see
``core/services/sales_service.py``), never this bounded context's UUIDv7
``customers.id`` — the same unreconciled-identity gap
``CustomerAccountsReceivableSummaryQuery`` (CRM-8) already documents for
``cuentas_por_cobrar.cliente_id``, now confirmed to span Ventas/Pedidos/
Delivery/WhatsApp/Fidelidad too, deferred to CRM-21/22. These handlers are
real, tested, and correct: given a payload whose ``cliente_id`` happens to
match a row in ``customers``, they apply the projection; given today's
actual data (it never does), they no-op, exactly like the CxC query
correctly returns zero exposure for a customer that only exists in the new
table. Subscribing them in ``core/events/wiring.py`` is left to CRM-21/22
(or to whichever future phase performs the identity reconciliation) — doing
it now would either be permanently-dead code (a wiring change to a shared,
cross-bounded-context legacy file that never fires) or would require
inventing a fragile phone/RFC-based matching heuristic this phase was not
asked to build.

No handler exists for ``SALE_RETURNED``: no such event is published
anywhere in this codebase today (only ``VENTA_COMPLETADA``/
``VENTA_CANCELADA`` exist) — nothing to subscribe to.
"""

from __future__ import annotations

from backend.application.customers.use_cases.sales_integration_use_cases import (
    RecordCustomerSaleActivityUseCase,
    RecordCustomerSaleCancelledUseCase,
)


def handle_sale_completed(connection, payload: dict) -> bool:
    """``payload`` is ``VENTA_COMPLETADA``'s raw dict (``core/services/
    sales_service.py``): ``cliente_id``, ``venta_id``, ``operation_id``,
    ``sale_datetime`` are the fields this handler reads."""
    customer_id = payload.get("cliente_id")
    if not customer_id:
        return False
    source_event_id = payload.get("operation_id") or payload.get("venta_id") or ""
    if not source_event_id:
        return False
    occurred_at = payload.get("sale_datetime") or ""
    return RecordCustomerSaleActivityUseCase().execute(
        connection, customer_id=customer_id, occurred_at=occurred_at,
        source_event_id=source_event_id, operation_id=source_event_id)


def handle_sale_cancelled(connection, payload: dict) -> bool:
    customer_id = payload.get("cliente_id")
    if not customer_id:
        return False
    source_event_id = payload.get("operation_id") or payload.get("venta_id") or ""
    if not source_event_id:
        return False
    return RecordCustomerSaleCancelledUseCase().execute(
        connection, customer_id=customer_id, source_event_id=source_event_id,
        operation_id=source_event_id)
