"""Composition root for pricing/costing integrations (PRC-6).

``wire_pricing`` subscribes the canonical cost projection onto the bus so that
procurement receipts and production costings keep ``product_cost`` fresh. The app
calls this once at startup with the EventBus and a connection. Priority 50 =
contabilidad/ledger tier (the cost projection is a costing side-effect that must
run after the inventory stock entry at priority 100 has been accepted).
"""

from __future__ import annotations

import logging

from backend.application.pricing.event_handlers.product_cost_projection_handler import (
    COST_EVENTS,
    ProductCostProjectionHandler,
)

logger = logging.getLogger("spj.pricing.wiring")


def _subscribe(bus, event_name: str, handler, *, priority: int, label: str) -> None:
    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    try:
        subscribe(event_name, handler, priority=priority, label=label)
    except TypeError:
        subscribe(event_name, handler)


def wire_pricing(bus, connection, *, currency: str = "MXN") -> dict:
    """Wire pricing/costing integrations onto the bus. Returns a summary of what
    was subscribed (useful for diagnostics/tests)."""
    cost_handler = ProductCostProjectionHandler(connection, currency=currency)
    subscribed: list[str] = []
    for event_name in COST_EVENTS:
        _subscribe(bus, event_name, cost_handler.handle, priority=50,
                   label=f"pricing_cost_{event_name.lower()}")
        subscribed.append(f"in:{event_name}->product_cost")
    logger.info("pricing integrations wired: %d subscriptions", len(subscribed))
    return {"subscribed": subscribed, "count": len(subscribed)}
