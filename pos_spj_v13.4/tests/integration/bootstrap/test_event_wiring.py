"""Regression test for the cross-bounded-context EventBus wiring step.

`wire_cross_context_events` is the single place `frontend/desktop/app.py`
calls to connect procurement and pricing onto the live bus at startup (see
`tests/architecture/test_erp_chain_wiring_ratchet.py`, which fails if a
`wire_<context>()` function stops having a production caller). This test
protects the glue itself: that calling it actually subscribes both contexts
onto `get_bus()`, not just onto some throwaway bus instance.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.bootstrap.wiring.event_wiring import wire_cross_context_events
from backend.domain.procurement.events import ProcurementEvents
from backend.application.pricing.event_handlers.product_cost_projection_handler import (
    COST_EVENTS,
)
from backend.shared.events.application_bus import get_bus, reset_bus


@pytest.fixture(autouse=True)
def _isolated_bus():
    reset_bus()
    yield
    reset_bus()


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


def test_wires_procurement_and_pricing_onto_the_live_bus(connection):
    summary = wire_cross_context_events(connection)

    assert summary["procurement"]["count"] > 0
    assert summary["pricing"]["count"] > 0
    assert summary["procurement_downstream_bridges"]["count"] == 4

    bus = get_bus()
    assert bus.subscriptions_for(ProcurementEvents.GOODS_RECEIPT_COMPLETED)
    for event_name in COST_EVENTS:
        assert bus.subscriptions_for(event_name), (
            f"pricing cost projection is not subscribed to {event_name}")
    assert bus.subscriptions_for("PAYABLE_CREATED")
    assert bus.subscriptions_for("SUPPLIER_PAYMENT_SCHEDULED")
    assert bus.subscriptions_for("PURCHASE_STOCK_ENTRY_REGISTERED")


def test_purchase_stock_entry_registered_has_exactly_three_subscribers():
    """Three legitimate, non-colliding subscribers as of this session:
    `CanonicalPurchaseStockEntryHandler` (stock entry),
    `CanonicalPurchaseRecipeExplosionHandler` (component consumption on
    formulated purchases — different products, different movement type, no
    overlap with stock entry), and pricing's `ProductCostProjectionHandler`
    (read-only cost projection, wired since Fase 0). If a FOURTH subscriber
    appears here (e.g. a future `CanonicalInventoryCutover.wire()` call that
    didn't drop `PurchaseReceiptHandler`/`DirectPurchaseReceiptHandler` from
    its own handler list first), check it against the double-post collision
    `wire_procurement_downstream_bridges`'s docstring warns about before
    assuming this count should just go up."""
    reset_bus()
    conn = sqlite3.connect(":memory:")
    try:
        wire_cross_context_events(conn)
        bus = get_bus()
        assert len(bus.subscriptions_for("PURCHASE_STOCK_ENTRY_REGISTERED")) == 3
    finally:
        conn.close()
