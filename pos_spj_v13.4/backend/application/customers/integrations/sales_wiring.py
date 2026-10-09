"""Ventas → Clientes sobre el bus canónico (§49, CRM-43).

MEDIDO en la base real (2026-10-08): una venta COMPLETADA con cliente y el
expediente marcaba 0 compras. La proyección (número de compras, última
compra, etapa del ciclo de vida) se cableaba en ``core/events/wiring.py``,
borrado con la shell legacy; ``RecordCustomerSaleActivityUseCase`` quedó sin
suscriptor.

Aquí se suscribe al sobre canónico de ``sales_outbox``:

* ``SALE_COMPLETED`` → cuenta la compra (``payload.customer_id`` ya es
  ``customers.id``: no hay puente de identidad que resolver);
* ``SALE_REVERSED``  → la descuenta. NO ``SALE_CANCELLED``: cancelar es de una
  venta que nunca se completó (regla del dominio de Ventas), descontarla
  dejaría el contador por debajo de lo real.

Idempotente por ``event_id`` (``customer_processed_events``). Prioridad 10:
notificación secundaria, después de Finanzas (50) y Fidelidad.
"""

from __future__ import annotations

import logging

from backend.application.customers.use_cases.sales_integration_use_cases import (
    RecordCustomerSaleActivityUseCase,
    RecordCustomerSaleCancelledUseCase,
)

logger = logging.getLogger("spj.customers.sales_wiring")

SALE_COMPLETED = "SALE_COMPLETED"
SALE_REVERSED = "SALE_REVERSED"


def _customer_id(envelope: dict) -> str | None:
    payload = envelope.get("payload") or {}
    value = payload.get("customer_id") if isinstance(payload, dict) else None
    return str(value) if value else None


def on_sale_completed(connection, envelope: dict) -> bool:
    customer_id = _customer_id(envelope)
    event_id = str(envelope.get("event_id") or "")
    if not customer_id or not event_id:
        return False
    return RecordCustomerSaleActivityUseCase().execute(
        connection, customer_id=customer_id,
        occurred_at=str(envelope.get("timestamp") or ""), source_event_id=event_id,
        operation_id=event_id)


def on_sale_reversed(connection, envelope: dict) -> bool:
    customer_id = _customer_id(envelope)
    event_id = str(envelope.get("event_id") or "")
    if not customer_id or not event_id:
        return False
    return RecordCustomerSaleCancelledUseCase().execute(
        connection, customer_id=customer_id, source_event_id=event_id, operation_id=event_id)


def wire_customers_sales(bus, connection) -> dict:
    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    suscritos = []
    for evento, manejador in ((SALE_COMPLETED, on_sale_completed),
                              (SALE_REVERSED, on_sale_reversed)):
        def _handler(envelope: dict, _m=manejador) -> None:
            _m(connection, envelope)
        try:
            subscribe(evento, _handler, priority=10, label=f"customers_{evento.lower()}")
        except TypeError:
            subscribe(evento, _handler)
        suscritos.append(f"in:{evento}->customers")
    return {"subscribed": suscritos, "count": len(suscritos)}
