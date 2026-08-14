"""Ventas → CRM bridge (CRM-13, §49): translates the legacy EventBus'
``VENTA_COMPLETADA``/``VENTA_CANCELADA`` payloads (``core/events/
event_bus.py``) into calls against ``RecordCustomerSaleActivityUseCase``/
``RecordCustomerSaleCancelledUseCase``.

``payload["cliente_id"]`` is the LEGACY ``clientes.id`` (see
``core/services/sales_service.py``), never this bounded context's UUIDv7
``customers.id`` — the same unreconciled-identity gap
``CustomerAccountsReceivableSummaryQuery`` (CRM-8) documents for
``cuentas_por_cobrar.cliente_id``. **CRM-21 closes this gap**: these
handlers are now subscribed for real, by
``core/events/wiring.py::_wire_customers_crm_sales_activity``, which
resolves the legacy id through ``ResolveLegacyCustomerUseCase`` (migration
193's ``customers.legacy_customer_id`` bridge) before calling
``handle_sale_completed``/``handle_sale_cancelled`` below — so this module's
own functions still receive a NEW ``customers.id`` in ``cliente_id``, same
contract as always; only the caller changed.

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
