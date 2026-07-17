"""Composition root for procurement integrations (PUR-11).

``wire_procurement`` subscribes:
- inbound need events (POS / forecast / minimum-stock) → replenishment intake;
- procurement events → downstream translators (inventory, CxP, treasury, supplier).

The app calls this once at startup with the EventBus and a connection. It never
touches the legacy ``core/events/wiring.py``; procurement stays decoupled.
"""

from __future__ import annotations

import logging

from backend.application.procurement.integrations.downstream_translators import (
    ProcurementDownstreamTranslators,
)
from backend.application.procurement.integrations.replenishment_intake import (
    ReplenishmentIntakeHandler,
)
from backend.domain.procurement.events import ProcurementEvents, ReplenishmentNeedEvents

logger = logging.getLogger("spj.procurement.wiring")

#: inbound need events that create requisitions.
NEED_EVENTS = (
    ReplenishmentNeedEvents.STOCK_REPLENISHMENT_REQUIRED,
    ReplenishmentNeedEvents.PURCHASE_NEED_DETECTED,
    ReplenishmentNeedEvents.PURCHASE_REQUISITION_REQUESTED,
    ReplenishmentNeedEvents.CUSTOMER_ORDER_REQUIRES_PURCHASE,
)


def _subscribe(bus, event_name: str, handler, *, priority: int = 80, label: str) -> None:
    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    try:
        subscribe(event_name, handler, priority=priority, label=label)
    except TypeError:
        subscribe(event_name, handler)


def wire_procurement(bus, connection, *, default_user_id: str = "system") -> dict:
    """Wire procurement integrations onto the bus. Returns a summary of what was
    subscribed (useful for diagnostics/tests)."""
    intake = ReplenishmentIntakeHandler(connection, default_user_id=default_user_id)
    translators = ProcurementDownstreamTranslators(bus)

    subscribed: list[str] = []

    # inbound: needs → requisitions
    for event_name in NEED_EVENTS:
        _subscribe(bus, event_name,
                   lambda payload, _e=event_name: intake.handle({**payload, "event_name": _e}),
                   priority=80, label=f"procurement_intake_{event_name.lower()}")
        subscribed.append(f"in:{event_name}")

    # outbound: inventory (accepted qty enters stock)
    for event_name in (ProcurementEvents.GOODS_RECEIPT_COMPLETED,
                       ProcurementEvents.DIRECT_PURCHASE_RECEIVED):
        _subscribe(bus, event_name, translators.on_receipt_completed,
                   priority=100, label=f"procurement_inventory_{event_name.lower()}")
        subscribed.append(f"out:{event_name}->inventory")

    # outbound: supplier performance from receipts
    _subscribe(bus, ProcurementEvents.GOODS_RECEIPT_COMPLETED,
               translators.on_receipt_for_performance, priority=30,
               label="procurement_supplier_performance")
    subscribed.append("out:GOODS_RECEIPT_COMPLETED->supplier")

    # outbound: accounts payable
    _subscribe(bus, ProcurementEvents.PURCHASE_PAYABLE_CREATED,
               translators.on_payable_created, priority=50, label="procurement_cxp")
    subscribed.append("out:PURCHASE_PAYABLE_CREATED->cxp")

    # outbound: treasury / petty cash (immediate payment)
    _subscribe(bus, ProcurementEvents.PURCHASE_PAYMENT_REQUESTED,
               translators.on_payment_requested, priority=50, label="procurement_treasury")
    subscribed.append("out:PURCHASE_PAYMENT_REQUESTED->treasury")

    logger.info("procurement integrations wired: %d subscriptions", len(subscribed))
    return {"subscribed": subscribed, "count": len(subscribed)}
