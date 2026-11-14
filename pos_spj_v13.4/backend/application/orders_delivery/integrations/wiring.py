"""Raíz de composición de las integraciones de Pedidos (SDLC-ORD-001).

Medido: `dispatch_orders_delivery_outbox` no tenía llamador y el efectivo que
cobra un repartidor no llegaba nunca a Finanzas. `wire_orders_delivery` suscribe
a sus consumidores; el despachador entrega lo pendiente.
"""

from __future__ import annotations

from backend.domain.orders_delivery.events import DeliveryEvents

#: Eventos con impacto contable: sin consumidor NO se marcan entregados. Si el
#: cableado de arranque fallara, el bus los entregaría a nadie y el efectivo no
#: llegaría nunca al mayor.
REQUIRES_CONSUMER = frozenset({
    DeliveryEvents.CASH_COLLECTION_RECORDED,
    DeliveryEvents.DRIVER_SETTLEMENT_CLOSED,
})


def to_finance_payload(envelope: dict) -> dict:
    """Sobre de `orders_delivery_outbox` → contrato plano de Finanzas."""
    return {
        **dict(envelope.get("payload") or {}),
        "event_id": envelope.get("event_id"),
        "operation_id": envelope.get("operation_id"),
        "occurred_at": envelope.get("timestamp"),
        "branch_id": envelope.get("branch_id"),
        "entity_id": envelope.get("entity_id"),
    }


def wire_orders_delivery(bus, connection) -> dict:
    from backend.application.event_handlers.finance.driver_cash_handlers import (
        DriverCashCollectedHandler,
        DriverSettlementClosedHandler,
    )

    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    suscritos = []
    for manejador in (DriverCashCollectedHandler(connection),
                      DriverSettlementClosedHandler(connection)):
        def _a_finanzas(envelope: dict, _m=manejador) -> None:
            _m.handle(to_finance_payload(envelope))
        subscribe(manejador.event_name, _a_finanzas, priority=50,
                  label=f"orders_delivery_finance_{manejador.event_name.lower()}")
        suscritos.append(f"out:{manejador.event_name}->finance")
    return {"subscribed": suscritos, "count": len(suscritos)}
